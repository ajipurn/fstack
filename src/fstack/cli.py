"""fstack — scaffold new projects from templates (FastAPI + llmfy + MySQL, React/Vite, …).

Usage:
    fstack new <name> [--template <name>] [options]
    fstack update [path] [--dry-run] [--from <rev>]
    fstack doctor

Each template under ``templates/<name>/`` is a runnable project called
"fstack-starter", plus ``fstack-template.toml`` (what it asks, how to install it).
Scaffolding copies one, renames the starter tokens, writes a ``.env`` with fresh
secrets when it has a backend, installs dependencies and makes the first commit.
It also writes ``.fstack.json`` (fstack version + commit + template + the answers),
which ``fstack update`` uses to rebuild the template the project started from and
merge what changed since into the project.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import importlib.metadata
import io
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import quote

from fstack import __version__, merge

# ── template location ────────────────────────────────────────────────────────

TEMPLATES = "templates"  # templates/<name>/ in fstack's repo, fstack/templates/ in the wheel
DEFAULT_TEMPLATE = "default"  # the original FastAPI + React template
LEGACY_DIR = "template"  # where `default` lived before there were several templates
MANIFEST = "fstack-template.toml"  # in each template; never copied into projects


def templates_root() -> Path:
    packaged = Path(__file__).parent / TEMPLATES
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[2] / TEMPLATES


SKIP_DIRS = {
    "node_modules",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "dist",
    ".data",
    ".git",
}
SKIP_FILES = {".DS_Store", ".env", "bun.lock", "pnpm-lock.yaml", "uv.lock", "tsconfig.tsbuildinfo"}
META = ".fstack.json"
BINARY_SUFFIXES = {".png", ".ico", ".jpg", ".jpeg", ".webp", ".woff", ".woff2", ".gif", ".pdf"}

STARTER = {
    "slug": "fstack-starter",
    "snake": "fstack_starter",
    "title": "Fstack Starter",
    "api_port": "8710",
    "web_port": "5710",
    "accent": "#2f3037",
}

# ── output helpers ───────────────────────────────────────────────────────────

def _ansi_ok() -> bool:
    """Whether stdout shows ANSI colors. A Windows console does once asked to."""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        enable_vt = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(kernel32.GetConsoleMode(handle, ctypes.byref(mode))) and bool(
            kernel32.SetConsoleMode(handle, mode.value | enable_vt)
        )
    except (AttributeError, OSError):
        return False


_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None and _ansi_ok()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def step(text: str) -> None:
    print(f"{_c('2', '›')} {text}")


def ok(text: str) -> None:
    print(f"{_c('32', '✓')} {text}")


def warn(text: str) -> None:
    print(f"{_c('33', '!')} {text}")


def fail(text: str) -> None:
    print(f"{_c('31', '✗')} {text}", file=sys.stderr)


# ── naming ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Names:
    slug: str
    snake: str
    title: str

    @classmethod
    def from_raw(cls, raw: str, title: str | None) -> Names:
        words = re.findall(r"[a-zA-Z0-9]+", raw)
        if not words:
            raise SystemExit(f"invalid project name: {raw!r}")
        slug = "-".join(w.lower() for w in words)
        if not slug[0].isalpha():
            raise SystemExit("project name must start with a letter")
        return cls(
            slug=slug,
            snake=slug.replace("-", "_"),
            title=title or " ".join(w[:1].upper() + w[1:] for w in words),
        )


def ink_for(hex_color: str) -> str:
    """Readable text color on top of the accent (WCAG relative luminance)."""
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    return "#131316" if luminance > 0.4 else "#ffffff"


def default_ports(slug: str) -> tuple[int, int]:
    """Stable, collision-resistant ports per project so several can run at once."""
    n = int(hashlib.sha1(slug.encode()).hexdigest(), 16) % 90
    return 8100 + n * 10, 5200 + n * 10


SLUG = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
HEX = re.compile(r"#[0-9a-fA-F]{6}")
PMS = ("bun", "pnpm")
# The answers a template may use (besides name and title), with their `fstack new` flags.
ANSWER_FLAGS = {"api_port": "--api-port", "web_port": "--web-port", "accent": "--accent", "pm": "--pm"}


class FstackError(Exception):
    pass


@dataclass(frozen=True)
class Template:
    name: str
    path: Path
    description: str
    asks: tuple[str, ...]  # which of ANSWER_FLAGS it uses
    install: tuple[tuple[str, str], ...]  # (dir, command) run after scaffolding
    next: tuple[tuple[str, str], ...]  # (command, comment) printed at the end


def template_names(root: Path) -> list[str]:
    return sorted(p.parent.name for p in root.glob(f"*/{MANIFEST}"))


def load_template(root: Path, name: str) -> Template:
    path = root / name
    if not SLUG.fullmatch(name) or not (path / MANIFEST).is_file():
        known = ", ".join(template_names(root)) or "none"
        raise FstackError(f"no template {name!r} in this fstack (it has: {known}): `uv tool upgrade fstack`?")
    where = f"{TEMPLATES}/{name}/{MANIFEST}"
    try:
        spec = tomllib.loads((path / MANIFEST).read_text(encoding="utf-8"))
        asks = tuple(spec.get("answers", []))
        if unknown := sorted(set(asks) - ANSWER_FLAGS.keys()):
            raise ValueError(f"unknown answers {unknown}")
        install = tuple((str(s["dir"]), str(s["run"])) for s in spec.get("install", []))
        steps = tuple((str(cmd), str(comment)) for cmd, comment in spec.get("next", []))
        return Template(name, path, str(spec.get("description", "")), asks, install, steps)
    except (tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as exc:
        raise FstackError(f"{where} is malformed: {exc}") from exc


def _port(value: object, key: str) -> int:
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if not isinstance(value, int) or isinstance(value, bool) or not 0 < value < 65536:
        raise ValueError(f"{key} {value!r} isn't a port number")
    return value


@dataclass(frozen=True)
class Answers:
    """Everything that turns the starter into one project; kept in .fstack.json.
    None = the template doesn't use it (its starter token, if any, stays as it is)."""

    names: Names
    api_port: int | None = None
    web_port: int | None = None
    accent: str | None = None
    pm: str | None = None
    # The pm version written into package.json, frozen per project so renders are reproducible.
    pm_version: str | None = None

    def replacements(self) -> list[tuple[re.Pattern[str], Callable[[re.Match[str]], str]]]:
        def literal(value: str) -> Callable[[re.Match[str]], str]:
            return lambda _: value  # a function, so a `\` in a title is never read as an escape

        rules = [
            (re.compile(re.escape(STARTER["slug"])), literal(self.names.slug)),
            (re.compile(re.escape(STARTER["snake"])), literal(self.names.snake)),
            (re.compile(re.escape(STARTER["title"])), literal(self.names.title)),
        ]
        if self.api_port is not None:
            rules.append((re.compile(rf"\b{STARTER['api_port']}\b"), literal(str(self.api_port))))
        if self.web_port is not None:
            rules.append((re.compile(rf"\b{STARTER['web_port']}\b"), literal(str(self.web_port))))
        if self.accent is not None:
            ink = ink_for(self.accent)
            rules.append((re.compile(re.escape(STARTER["accent"]), re.I), literal(self.accent)))
            rules.append((re.compile(r"#ffffff(; /\* fstack:accent-ink \*/)"), lambda m: ink + m.group(1)))
        return rules

    def with_defaults(self, asks: tuple[str, ...]) -> Answers:
        """Fill what `asks` needs but these answers lack, the way `fstack new` would."""
        api_port, web_port = default_ports(self.names.slug)
        defaults: dict[str, object] = {
            "api_port": api_port,
            "web_port": web_port,
            "accent": STARTER["accent"],
            "pm": PMS[0],
        }
        filled = replace(self, **{k: v for k, v in defaults.items() if k in asks and getattr(self, k) is None})
        if filled.pm is not None and filled.pm_version is None:
            filled = replace(filled, pm_version=_tool_version(filled.pm) or "latest")
        return filled

    def fields(self) -> dict[str, object]:
        """For `{api_port}`-style placeholders in a template's manifest."""
        values = {k: getattr(self, k) for k in ANSWER_FLAGS if getattr(self, k) is not None}
        return {"name": self.names.slug, "title": self.names.title, **values}

    def to_meta(self, template: Template, commit: str | None, dirty: bool = False) -> dict[str, object]:
        meta: dict[str, object] = {
            "fstack": __version__,
            "commit": commit,
            "template": template.name,
            "name": self.names.slug,
            "title": self.names.title,
        }
        meta.update({key: getattr(self, key) for key in template.asks})
        if "pm" in template.asks:
            meta["pm_version"] = self.pm_version
        if dirty:
            meta["dirty"] = True  # rendered from uncommitted template changes
        return meta

    @classmethod
    def from_meta(cls, meta: dict[str, object]) -> Answers:
        """Raises KeyError / ValueError for anything `fstack new` wouldn't have written."""
        slug, title = meta["name"], meta["title"]
        accent, pm, version = meta.get("accent"), meta.get("pm"), meta.get("pm_version")
        if not isinstance(slug, str) or not SLUG.fullmatch(slug):
            raise ValueError(f"name {slug!r} isn't a slug like talent-review")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("title must be a non-empty string")
        if accent is not None and (not isinstance(accent, str) or not HEX.fullmatch(accent)):
            raise ValueError(f"accent {accent!r} isn't a hex color like #2f3037")
        if pm is not None and pm not in PMS:
            raise ValueError(f"pm {pm!r} must be one of {', '.join(PMS)}")
        if version is not None and (not isinstance(version, str) or not re.fullmatch(r"[\w.+-]+", version)):
            raise ValueError(f"pm_version {version!r} isn't a version")
        names = Names(slug=slug, snake=slug.replace("-", "_"), title=title)
        ports = {k: _port(meta[k], k) if meta.get(k) is not None else None for k in ("api_port", "web_port")}
        return cls(names, ports["api_port"], ports["web_port"], accent, pm and str(pm), version)


# ── scaffold ─────────────────────────────────────────────────────────────────


def template_files(src: Path) -> Iterator[Path]:
    """Files that belong to a project, relative to `src` (no deps, caches, secrets, locks)."""
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name not in SKIP_FILES and name != META:
                yield (Path(root) / name).relative_to(src)


def _entry(path: Path) -> merge.Entry:
    return merge.Entry(path.read_bytes(), merge.HAS_MODES and os.access(path, os.X_OK))


def _text(rel: str, data: bytes) -> str | None:
    if Path(rel).suffix.lower() in BINARY_SUFFIXES:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def render_tree(src: Path, answers: Answers, only: frozenset[str] | None = None) -> merge.Tree:
    """The project `answers` make from the template at `src`, in memory. `only` limits it
    to those paths (a checkout's git-ignored files never belong in a project)."""
    rules = answers.replacements()
    tree: merge.Tree = {}
    for rel in template_files(src):
        key = rel.as_posix()
        if key == MANIFEST or (only is not None and key not in only):
            continue
        entry = _entry(src / rel)
        text = _text(key, entry.data)
        if text is not None:
            for pattern, value in rules:
                text = pattern.sub(value, text)
            entry = merge.Entry(text.encode("utf-8"), entry.executable)
        tree[key] = entry
    set_package_manager(tree, answers)
    return tree


def write_tree(tree: merge.Tree, dest: Path) -> None:
    try:
        merge.apply([merge.Change(rel, "added", e.data, e.executable) for rel, e in tree.items()], dest)
    except RuntimeError as exc:
        raise FstackError(str(exc)) from exc


def snapshot(root: Path) -> merge.Tree:
    """An already rendered project on disk (e.g. its scaffold commit) as a tree."""
    return {rel.as_posix(): _entry(root / rel) for rel in template_files(root)}


def root_password() -> tuple[str, str]:
    """Local MySQL's root password and where it came from. $DB_ROOT_PASSWORD wins;
    otherwise ask (a silent `root` default broke projects whose server uses another)."""
    if value := os.environ.get("DB_ROOT_PASSWORD"):
        return value, "from $DB_ROOT_PASSWORD"
    if sys.stdin.isatty():
        entered = getpass.getpass("  MySQL root password (DB_ROOT_PASSWORD isn't set; Enter = root): ")
        if entered:
            return entered, "as entered"
    return "root", "default `root` (export DB_ROOT_PASSWORD if yours differs)"


def write_env(dest: Path, database_url: str | None, names: Names, password: str) -> bool:
    """backend/.env with fresh secrets. Returns True when it was created.

    Without --database-url the project connects to local MySQL as root with
    `password`; `make seed` creates the database.
    """
    example = dest / "backend" / ".env.example"
    env = dest / "backend" / ".env"
    if not example.exists() or env.exists():
        return False
    text = example.read_text(encoding="utf-8")
    key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    text = text.replace("APP_ENCRYPTION_KEY=\n", f"APP_ENCRYPTION_KEY={key}\n", 1)
    text = text.replace("APP_ACCESS_KEY=\n", f"APP_ACCESS_KEY={secrets.token_urlsafe(32)}\n", 1)
    if not database_url:
        encoded = quote(password, safe="")
        database_url = f"mysql+pymysql://root:{encoded}@127.0.0.1:3306/{names.snake}"
    line = f"APP_DATABASE_URL={database_url}"
    text = re.sub(r"^APP_DATABASE_URL=.*$", lambda _: line, text, flags=re.M)
    # Created 0600, not 0666 & ~umask and narrowed after: no window where others can read the secrets.
    fd = os.open(env, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    env.chmod(0o600)
    return True


def _edit(tree: merge.Tree, rel: str, change: Callable[[str], str]) -> None:
    if (entry := tree.get(rel)) is not None:
        tree[rel] = merge.Entry(change(entry.data.decode("utf-8")).encode("utf-8"), entry.executable)


def _pnpm_ci(text: str) -> str:
    text = text.replace("- uses: oven-sh/setup-bun@v2", "- uses: pnpm/action-setup@v4\n      - uses: actions/setup-node@v4\n        with: { node-version: 24, cache: pnpm, cache-dependency-path: frontend/pnpm-lock.yaml }")
    return text.replace("bun install --frozen-lockfile", "pnpm install --frozen-lockfile").replace("PM=bun", "PM=pnpm")


def set_package_manager(tree: merge.Tree, answers: Answers) -> None:
    if answers.pm is None:
        return
    pm, field = answers.pm, f'"packageManager": "{answers.pm}@{answers.pm_version or "latest"}"'
    _edit(tree, "frontend/package.json", lambda t: re.sub(r'"packageManager": "[^"]+"', lambda _: field, t))
    _edit(tree, "Makefile", lambda t: re.sub(r"^PM \?= \w+", lambda _: f"PM ?= {pm}", t, flags=re.M))
    if pm == "pnpm":
        _edit(tree, ".github/workflows/check.yml", _pnpm_ci)


def _tool_version(tool: str) -> str | None:
    exe = shutil.which(tool)
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"\d+\.\d+(?:\.\d+)?", out.stdout + out.stderr)  # make says 3.81
    return match.group(0) if match else None


def run(cmd: list[str], cwd: Path, label: str) -> bool:
    step(label)
    # By full path: Windows runs `pnpm.cmd` only when named, not as `pnpm`.
    proc = subprocess.run([shutil.which(cmd[0]) or cmd[0], *cmd[1:]], cwd=cwd)
    if proc.returncode != 0:
        fail(f"{label} failed ({' '.join(cmd)})")
        return False
    return True


# ── where the template comes from ────────────────────────────────────────────

FULL_SHA = re.compile(r"[0-9a-f]{40}")
REV = re.compile(r"\w[\w./@{}^~-]*")  # no leading `-`: never an option to git


@dataclass(frozen=True)
class Source:
    root: Path  # the templates this fstack ships: root/<name>/
    repo: str | None  # git checkout or URL holding the templates' history
    commit: str | None  # the commit `root` is from
    dirty: frozenset[str] = frozenset()  # templates with changes `commit` doesn't have
    files: frozenset[str] | None = None  # in a checkout: the files git doesn't ignore, relative to root

    def template(self, name: str) -> Template:
        return load_template(self.root, name)

    def files_of(self, name: str) -> frozenset[str] | None:
        if self.files is None:
            return None
        prefix = f"{name}/"
        return frozenset(p.removeprefix(prefix) for p in self.files if p.startswith(prefix))


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise FstackError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def _git_z(cwd: Path, *args: str) -> list[str]:
    """A NUL-separated git listing (`-z`), paths kept exactly."""
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if proc.returncode != 0:
        raise FstackError(proc.stderr.decode(errors="replace").strip() or f"git {' '.join(args)} failed")
    return [p for p in proc.stdout.decode("utf-8", errors="surrogateescape").split("\0") if p]


def installed_source() -> Source:
    root = templates_root()
    checkout = root.parent
    if (checkout / ".git").exists() and shutil.which("git"):  # editable install / run from the repo
        try:
            commit = _git(checkout, "rev-parse", "HEAD")
            changed = _git_z(checkout, "status", "--porcelain", "-z", "--no-renames", "-uall", "--", TEMPLATES)
            listed = _git_z(checkout, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", TEMPLATES)
        except FstackError:
            return Source(root, None, None)
        # "XY templates/<name>/…": the templates with uncommitted changes
        dirty = frozenset(entry[3:].split("/")[1] for entry in changed if entry[3:].count("/") >= 2)
        files = frozenset(p.removeprefix(f"{TEMPLATES}/") for p in listed)
        return Source(root, str(checkout), commit, dirty, files)
    try:  # `uv tool install git+…` records the URL and commit (PEP 610)
        raw = importlib.metadata.distribution("fstack").read_text("direct_url.json") or "{}"
        info = json.loads(raw)
    except (importlib.metadata.PackageNotFoundError, json.JSONDecodeError):
        info = {}
    vcs = info.get("vcs_info") or {}
    if vcs.get("vcs") == "git" and info.get("url"):
        return Source(root, info["url"], vcs.get("commit_id"))
    return Source(root, None, None)


def _cached_clone(url: str) -> Path:
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "fstack" / "repo.git"
    if not cache.exists():
        step(f"fetching fstack's history from {url}")
        cache.parent.mkdir(parents=True, exist_ok=True)
        _git(cache.parent, "clone", "--bare", "--quiet", url, str(cache))
    return cache


def _has_commit(gitdir: Path, rev: str) -> bool:
    proc = subprocess.run(["git", "cat-file", "-e", f"{rev}^{{commit}}"], cwd=gitdir, capture_output=True)
    return proc.returncode == 0


def fstack_repo(source: Source, *revs: str) -> Path:
    """A git dir with fstack's history that has every one of `revs`."""
    if source.repo is None:
        raise FstackError(
            "this fstack wasn't installed from git, so older templates can't be fetched; "
            "reinstall with `uv tool install git+https://github.com/ajipurn/fstack`"
        )
    if Path(source.repo).is_dir():  # editable install: the checkout itself, never fetched into
        gitdir = Path(source.repo)
        if missing := [rev for rev in revs if not _has_commit(gitdir, rev)]:
            raise FstackError(f"fstack revision {missing[0]!r} isn't in {gitdir}: pull it first (git -C {gitdir} pull)")
        return gitdir
    gitdir = _cached_clone(source.repo)
    # A branch or tag name may have moved since the last fetch; a full SHA only matters when absent.
    if any(not FULL_SHA.fullmatch(rev) or not _has_commit(gitdir, rev) for rev in revs):
        _git(gitdir, "remote", "set-url", "origin", source.repo)
        _git(gitdir, "fetch", "--quiet", "--tags", "--force", "--prune", "origin", "+refs/heads/*:refs/heads/*")
    if missing := [rev for rev in revs if not _has_commit(gitdir, rev)]:
        raise FstackError(f"fstack revision {missing[0]!r} not found in {source.repo}")
    return gitdir


def check_not_older(gitdir: Path, base_rev: str, commit: str) -> None:
    """Refuse when the installed fstack doesn't contain the project's template: the update
    would undo template changes the project already has."""
    proc = subprocess.run(["git", "merge-base", "--is-ancestor", base_rev, commit], cwd=gitdir, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode == 1:
        raise FstackError(
            f"the installed fstack ({commit[:7]}) is older than this project's template ({base_rev[:7]}) "
            "or on another branch, so updating would undo template changes: `uv tool upgrade fstack` first"
        )
    if proc.returncode != 0:
        raise FstackError(proc.stderr.strip() or "git merge-base failed")


def extract(gitdir: Path, rev: str, dest: Path, *paths: str) -> bool:
    """`git archive` of `rev` (optionally only `paths`) unpacked into `dest`."""
    archive = subprocess.run(["git", "archive", "--format=tar", rev, *paths], cwd=gitdir, capture_output=True)
    if archive.returncode != 0:
        return False
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(dest, filter="data")
    return True


def checkout_template(gitdir: Path, rev: str, name: str, dest: Path) -> Path:
    """Template `name` as it was at fstack revision `rev`, extracted under `dest`."""
    paths = [f"{TEMPLATES}/{name}"] + ([LEGACY_DIR] if name == DEFAULT_TEMPLATE else [])
    for path in paths:
        if extract(gitdir, rev, dest, path):
            return dest / path
    raise FstackError(f"fstack revision {rev!r} has no {TEMPLATES}/{name}/")


def write_meta(dest: Path, answers: Answers, template: Template, commit: str | None, dirty: bool = False) -> None:
    text = json.dumps(answers.to_meta(template, commit, dirty), indent=2) + "\n"
    try:
        merge.write(dest, META, text.encode("utf-8"))
    except RuntimeError as exc:
        raise FstackError(str(exc)) from exc


def _summary(template: Template, answers: Answers) -> str:
    parts = [template.name]
    parts += [f"api :{answers.api_port}"] if answers.api_port is not None else []
    parts += [f"web :{answers.web_port}"] if answers.web_port is not None else []
    parts += [f"pm {answers.pm}"] if answers.pm is not None else []
    return " · ".join(parts)


def cmd_new(args: argparse.Namespace) -> int:
    names = Names.from_raw(args.name, args.title)
    dest = Path(args.dir or names.slug).expanduser().resolve()
    if dest.exists() and any(dest.iterdir()) and not args.force:
        fail(f"{dest} already exists and is not empty (use --force to write into it)")
        return 1
    if args.accent and not HEX.fullmatch(args.accent):
        fail("--accent must be a 6-digit hex color, e.g. #ffbe25")
        return 1
    source = installed_source()
    template = source.template(args.template)

    given = {key: getattr(args, key) for key in ANSWER_FLAGS}
    for key, value in given.items():
        if value is not None and key not in template.asks:
            warn(f"the {template.name} template doesn't use {ANSWER_FLAGS[key]}: ignored")
    asked = {key: value for key, value in given.items() if key in template.asks}
    answers = Answers(names, **asked).with_defaults(template.asks)
    tree = render_tree(template.path, answers, source.files_of(template.name))

    print(f"\n  {_c('1', names.title)}  {_c('2', str(dest))}\n")
    # Ask before writing anything, so Ctrl-C leaves no half-made project.
    has_env = "backend/.env.example" in tree
    if args.database_url and not has_env:
        warn(f"the {template.name} template has no backend/.env: --database-url ignored")
    new_env = has_env and not args.database_url and not (dest / "backend" / ".env").exists()
    password, password_source = root_password() if new_env else ("", "")
    write_tree(tree, dest)
    dirty = template.name in source.dirty
    write_meta(dest, answers, template, source.commit, dirty)
    created_env = has_env and write_env(dest, args.database_url, names, password)
    ok(f"files written ({len(tree)})  {_summary(template, answers)}")
    if created_env:
        ok("backend/.env created with fresh secrets (sign in with APP_ACCESS_KEY)")
        if password_source.startswith("default"):
            warn(f"MySQL root password: {password_source}")
        elif password_source:
            ok(f"MySQL root password {password_source}")
    if source.commit is None:
        warn("can't tell which fstack commit this is: `fstack update` will need --from <rev>")
    elif dirty:
        warn(f"the {template.name} template has uncommitted changes (noted in .fstack.json): commit them in fstack")

    fields = answers.fields()
    if not args.no_install:
        for where, command in template.install:
            cmd = shlex.split(command.format_map(fields))
            label = " ".join(cmd) if where == "." else f"{where}: {' '.join(cmd)}"
            if shutil.which(cmd[0]):
                run(cmd, dest / where, label)
            else:
                warn(f"{cmd[0]} not found — skipped {label}")

    if not args.no_git and shutil.which("git") and not (dest / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=dest)
        subprocess.run(["git", "add", "-A"], cwd=dest)
        subprocess.run(
            ["git", "commit", "-q", "-m", f"chore: scaffold {names.slug} from fstack {__version__}"],
            cwd=dest,
        )
        ok("git repository initialised")

    steps = [(cmd.format_map(fields), comment and "# " + comment.format_map(fields)) for cmd, comment in template.next]
    width = max((len(cmd) for cmd, _ in steps), default=0)
    try:
        where = os.path.relpath(dest)
    except ValueError:  # Windows: on another drive than the current folder
        where = str(dest)
    print(f"\n  Next:\n    cd {shlex.quote(where) if ' ' in where else where}")
    for cmd, comment in steps:
        print(f"    {cmd:<{width}}  {_c('2', comment)}".rstrip())
    print()
    return 0


# ── update ───────────────────────────────────────────────────────────────────

SCAFFOLD_SUBJECT = re.compile(r"^chore: scaffold (\S+) from fstack (\S+)$")
DEPENDENCY_FILES = {"backend/pyproject.toml", "frontend/package.json"}
MIGRATIONS = "backend/alembic/versions/"
REPORT = {
    "added": ("32", "✓"),
    "updated": ("32", "✓"),
    "merged": ("32", "✓"),
    "renamed": ("32", "✓"),
    "removed": ("32", "✓"),
    "conflict": ("31", "✗"),
    "skipped": ("33", "!"),
    "kept": ("33", "!"),
}


def scaffold_commit(root: Path) -> tuple[str, str] | None:
    """The first commit `fstack new` made: (sha, fstack version)."""
    for sha in _git(root, "rev-list", "--max-parents=0", "HEAD").split():
        if match := SCAFFOLD_SUBJECT.match(_git(root, "log", "-1", "--format=%s", sha)):
            return sha, match.group(2)
    return None


def _json_object(text: str, where: str) -> dict[str, object]:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise FstackError(f"{where} isn't valid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise FstackError(f"{where} must hold a JSON object")
    return data


def _answers(meta: dict[str, object], where: str) -> Answers:
    try:
        return Answers.from_meta(meta)
    except KeyError as exc:
        raise FstackError(f"{where} is missing {exc}") from exc
    except (TypeError, ValueError) as exc:
        raise FstackError(f"{where}: {exc}") from exc


def infer_answers(project: Path) -> Answers:
    """Read the answers back out of a rendered project (one made before .fstack.json)."""

    def find(rel: str, pattern: str) -> str | None:
        path = project / rel
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        match = re.search(pattern, text, re.M)
        return match.group(1) if match else None

    found: dict[str, object] = {
        "name": find("frontend/package.json", r'"name":\s*"(.+?)-web"'),
        "title": find("frontend/src/app/AppShell.tsx", r'^const APP_NAME = "(.+?)";'),
        "api_port": find("Makefile", r"^API_PORT \?= (\d+)"),
        "web_port": find("Makefile", r"^WEB_PORT \?= (\d+)"),
        "accent": find("frontend/src/styles/tokens.css", r"--accent-base: (#[0-9a-fA-F]{6}); /\* fstack:accent \*/"),
        "pm": find("Makefile", r"^PM \?= (\w+)"),
    }
    if missing := [key for key, value in found.items() if value is None]:
        raise FstackError(f"couldn't read {', '.join(missing)} from the project: write {META} by hand (see README)")
    found["pm_version"] = find("frontend/package.json", r'"packageManager":\s*"\w+@([^"]+)"')
    return _answers(found, "the project's files")


def read_meta(root: Path) -> dict[str, object] | None:
    try:
        path = merge.resolve(root, META)
    except RuntimeError as exc:
        raise FstackError(str(exc)) from exc
    return _json_object(path.read_text(encoding="utf-8"), META) if path.exists() else None


def project_template(meta: dict[str, object] | None) -> str:
    """The template a project was made from (before there were several: the default)."""
    name = DEFAULT_TEMPLATE if meta is None else meta.get("template", DEFAULT_TEMPLATE)
    if not isinstance(name, str) or not SLUG.fullmatch(name):
        raise FstackError(f"{META}: template {name!r} isn't a template name")
    return name


def resolve_base(
    root: Path, source: Source, template: Template, meta: dict[str, object] | None, from_rev: str | None, tmp: Path
) -> tuple[merge.Tree, Answers, str]:
    """The template as the project last got it, the project's answers, and a label for it."""
    scaffold = scaffold_commit(root)
    scaffold_dir = tmp / "scaffold"
    if scaffold and not extract(root, scaffold[0], scaffold_dir):
        raise FstackError(f"couldn't read the scaffold commit {scaffold[0][:7]} (git archive failed)")

    if meta is not None:
        answers = _answers(meta, META)
        rev = from_rev or meta.get("commit")
        if not rev:
            raise FstackError(f"{META} has no commit: pass --from <the fstack rev this project was made from>")
        if not isinstance(rev, str) or not REV.fullmatch(rev):
            raise FstackError(f"{META}: commit {rev!r} isn't a git revision")
        made_from = str(meta.get("fstack", "?"))
    elif scaffold or from_rev:
        answers = infer_answers(scaffold_dir if scaffold else root)
        rev, made_from = from_rev, scaffold[1] if scaffold else "?"
        a = answers
        step(f"no {META} yet: {a.names.slug} · “{a.names.title}” · api :{a.api_port} · web :{a.web_port} · {a.accent} · {a.pm}")
    else:
        raise FstackError(f"no {META} and no `chore: scaffold … from fstack …` commit: pass --from <fstack rev>")
    answers = answers.with_defaults(template.asks)  # what the template asks since it was made

    # The scaffold commit is exactly what the project got, rendered by the fstack that made
    # it: use it until the project's first update.
    scaffold_meta = None
    if scaffold:
        shown = subprocess.run(["git", "show", f"{scaffold[0]}:{META}"], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
        scaffold_meta = _json_object(shown.stdout, f"{META} in the scaffold commit") if shown.returncode == 0 else None
    use_scaffold = bool(scaffold) and not from_rev and (meta is None or (scaffold_meta or {}).get("commit") == rev)

    gitdir = None
    if rev and (source.repo is not None or not use_scaffold):
        gitdir = fstack_repo(source, rev, *filter(None, [source.commit]))
        if source.commit:
            check_not_older(gitdir, rev, source.commit)
        else:
            warn("can't tell which fstack commit is installed, so not checking it's newer than the project's")
    elif rev:
        warn("can't check that the installed fstack is newer than this project's template")
    if meta and meta.get("dirty") and not use_scaffold:
        warn("the last update used uncommitted template changes: they may show up again, or linger if discarded")

    if use_scaffold:
        assert scaffold is not None
        return snapshot(scaffold_dir), answers, f"fstack {made_from} (scaffold {scaffold[0][:7]})"
    assert gitdir is not None and rev
    label = f"fstack {rev}" if from_rev else f"fstack {made_from}{_short(rev)}"
    return render_tree(checkout_template(gitdir, rev, template.name, tmp / "old"), answers), answers, label


def _short(rev: str | None) -> str:
    return f" ({rev[:7]})" if rev else ""


def cmd_update(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser().resolve()
    return update(root, dry_run=args.dry_run, from_rev=args.from_rev, allow_dirty=args.allow_dirty)


def update(root: Path, *, dry_run: bool = False, from_rev: str | None = None, allow_dirty: bool = False) -> int:
    if not shutil.which("git"):
        raise FstackError("git is required")
    if not root.is_dir():
        raise FstackError(f"{root} doesn't exist")
    if Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise FstackError(f"{root} isn't the root of a git repository")
    if from_rev is not None and not REV.fullmatch(from_rev):
        raise FstackError(f"--from {from_rev!r} isn't a git revision")
    if not dry_run and _git(root, "status", "--porcelain"):
        raise FstackError("commit or stash your changes first, so the update lands as one diff you can review")
    meta = read_meta(root)
    source = installed_source()
    template = source.template(project_template(meta))
    dirty = template.name in source.dirty
    if dirty and not (allow_dirty or dry_run):
        raise FstackError(
            f"fstack's {template.name} template has uncommitted changes, which the next update couldn't rebuild: "
            "commit them first (or pass --allow-dirty)"
        )

    with tempfile.TemporaryDirectory(prefix="fstack-update-") as tmp:
        base, answers, base_label = resolve_base(root, source, template, meta, from_rev, Path(tmp))
    new = render_tree(template.path, answers, source.files_of(template.name))
    new_label = f"fstack {__version__}{_short(source.commit)}"
    tracked = set(_git_z(root, "ls-files", "-z"))
    present = {p for p in base.keys() | new.keys() if (root / p).is_file()}
    ours = {p: _entry(root / p) for p in present & tracked}
    try:
        changes = merge.plan(base, new, ours, ("project", base_label, new_label), untracked=present - tracked)
    except RuntimeError as exc:
        raise FstackError(str(exc)) from exc

    print(f"\n  {_c('1', answers.names.title)}  {_c('2', f'{template.name} · {base_label} → {new_label}')}\n")
    for change in changes:
        color, mark = REPORT[change.kind]
        path = f"{change.old} → {change.path}" if change.old else change.path
        note = change.note or (f"{change.conflicts} conflict(s)" if change.conflicts else "")
        print(f"{_c(color, mark)} {change.kind:<9} {path}  {_c('2', note)}".rstrip())
    conflicted = [c for c in changes if c.kind == "conflict"]
    attention = [c for c in changes if c.kind in {"skipped", "kept"}]
    if not changes:
        ok("nothing to update")
    if dry_run:
        print(f"\n  {_c('2', 'Dry run: nothing written.')}\n")
        return 1 if conflicted else 0

    try:
        merge.apply(changes, root)
    except RuntimeError as exc:
        raise FstackError(str(exc)) from exc
    write_meta(root, answers, template, source.commit, dirty)
    if source.commit is None:
        warn("can't tell which fstack commit this is: the next `fstack update` will need --from <rev>")
    if attention:
        warn(f"{len(attention)} file(s) marked ! were left as they are: check the project doesn't need the template's version")

    touched = {c.path for c in changes if c.data is not None}
    added_migrations = [c.path for c in changes if c.kind == "added" and c.path.startswith(MIGRATIONS)]
    own_migrations = [p for p in (root / MIGRATIONS).glob("*.py") if f"{MIGRATIONS}{p.name}" not in new]
    # One command per line, no `cd … &&`: Windows PowerShell 5 has no `&&`.
    task = "uv run tasks.py" if (root / "tasks.py").is_file() else "make"
    hints = []
    if conflicted:
        hints.append(("git diff --check", "# lists leftover conflict markers (✗): fix them by hand"))
    if touched & DEPENDENCY_FILES:
        hints.append((f"{task} setup", "# dependencies changed: refresh the lockfiles"))
    if added_migrations and own_migrations:
        hints.append(("uv run --directory backend alembic heads", "# two heads? `alembic merge heads -m fstack`"))
    if added_migrations:
        hints.append((f"{task} migrate", "# new migrations from the template"))
    hints.append(("git diff", "# review"))
    hints.append(("git add -A", ""))
    hints.append((f'git commit -m "chore: update from fstack {__version__}"', ""))
    width = max(len(cmd) for cmd, comment in hints if comment)
    print("\n  Next:")
    for cmd, comment in hints:
        print(f"    {cmd:<{width}}  {_c('2', comment)}".rstrip())
    print()
    return 1 if conflicted else 0


def cmd_template_add(args: argparse.Namespace) -> int:
    from fstack import importer  # imports this module

    return importer.add(args)


def cmd_doctor(_: argparse.Namespace) -> int:
    checks = [
        ("uv", "python, backend env + deps, project tasks (uv run tasks.py)"),
        ("bun", "frontend pm (default)"),
        ("pnpm", "frontend pm (alt)"),
        ("node", "vite tooling"),
        *([("container", "local MySQL via db-up (Apple container)")] if sys.platform == "darwin" else []),
        ("docker", "local MySQL via db-up" + (" (alt)" if sys.platform == "darwin" else "")),
        ("git", "repository init, fstack update"),
        *([("make", "make <task>: shortcut for uv run tasks.py <task>")] if os.name != "nt" else []),
    ]
    missing = 0
    for tool, purpose in checks:
        version = _tool_version(tool)
        if version:
            ok(f"{tool:<9} {version:<10} {_c('2', purpose)}")
        else:
            warn(f"{tool:<9} {'missing':<10} {_c('2', purpose)}")
            missing += tool in {"uv", "git"}
    if os.environ.get("DB_ROOT_PASSWORD"):
        ok(f"{'DB_ROOT_PASSWORD':<20} {_c('2', 'set: fstack new writes it into backend/.env')}")
    else:
        warn(f"{'DB_ROOT_PASSWORD':<20} {_c('2', 'not set: fstack new will ask for MySQL’s root password')}")
    source = installed_source()
    origin = f"{source.repo} @ {source.commit[:7]}" if source.repo and source.commit else "unknown origin"
    print(f"\n  templates: {source.root}\n             {_c('2', origin)}")
    for name in template_names(source.root):
        try:
            about = source.template(name).description
        except FstackError as exc:
            about = str(exc)
        about += " (uncommitted changes)" if name in source.dirty else ""
        print(f"    {name:<12} {_c('2', about)}")
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(line_buffering=True)  # keep our lines ordered with child output
    if os.name == "nt":  # ✓ · ← and names print anywhere, not only where cp1252 has them
        for stream in (sys.stdout, sys.stderr):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="fstack", description="Scaffold new projects from templates.")
    parser.add_argument("--version", action="version", version=f"fstack {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="create a project from a template")
    new.add_argument("name", help="project name, e.g. 'talent-review' or 'Talent Review'")
    new.add_argument(
        "--template",
        "-t",
        choices=template_names(templates_root()),
        default=DEFAULT_TEMPLATE,
        help=f"what to start from (default: {DEFAULT_TEMPLATE}; `fstack doctor` lists them)",
    )
    new.add_argument("--dir", help="target directory (default: ./<slug>)")
    new.add_argument("--title", help="display name (default: derived from name)")
    new.add_argument("--pm", choices=list(PMS), help="frontend package manager (default: bun)")
    new.add_argument("--accent", help="primary button color, hex (default graphite #2f3037)")
    new.add_argument(
        "--database-url",
        help="APP_DATABASE_URL for backend/.env (default: local MySQL as root, $DB_ROOT_PASSWORD or root)",
    )
    new.add_argument("--api-port", type=int)
    new.add_argument("--web-port", type=int)
    new.add_argument("--no-install", action="store_true", help="skip installing dependencies")
    new.add_argument("--no-git", action="store_true", help="skip git init + first commit")
    new.add_argument("--force", action="store_true", help="write into a non-empty directory")
    new.set_defaults(func=cmd_new)

    upd = sub.add_parser("update", help="merge template changes since the project was made into it")
    upd.add_argument("path", nargs="?", default=".", help="project root (default: current directory)")
    upd.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    upd.add_argument(
        "--from",
        dest="from_rev",
        metavar="REV",
        help="fstack commit or tag the project was made from (default: from .fstack.json)",
    )
    upd.add_argument(
        "--allow-dirty",
        action="store_true",
        help="update from a template with uncommitted changes (editable installs)",
    )
    upd.set_defaults(func=cmd_update)

    tpl = sub.add_parser("template", help="add templates to this fstack checkout")
    tsub = tpl.add_subparsers(dest="template_command", required=True)
    add = tsub.add_parser("add", help="make a template from an existing repo (a folder or a git URL)")
    add.add_argument("name", help="the template's name: `fstack new <project> -t <name>`")
    add.add_argument("--from", dest="source", required=True, metavar="PATH|URL", help="the repo (committed files only)")
    add.add_argument("--ref", help="branch, tag or commit to take (default: the latest commit)")
    add.add_argument("--dry-run", action="store_true", help="show what would be written, write nothing")
    add.add_argument("--description", help="shown by `fstack doctor` (default: where it came from)")
    add.add_argument("--source-name", help="the project's name as the source spells it (default: detected)")
    add.add_argument("--source-title", help="its display name (default: detected)")
    add.add_argument("--api-port", type=int, help="its API port (default: detected)")
    add.add_argument("--web-port", type=int, help="its web port (default: detected)")
    add.add_argument("--accent", help="its accent color (default: detected)")
    add.set_defaults(func=cmd_template_add)

    doctor = sub.add_parser("doctor", help="check the local toolchain")
    doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FstackError as exc:
        fail(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
