"""`fstack template add`: an existing repo becomes a template — `fstack new` in reverse.

The project's name (slug, snake and title), ports and accent go back to the starter
tokens, so `fstack new -t <name>` renders a fresh project from it exactly the way it
does from the default template. Only committed files are taken; `.env` files and
`.fstack.json` never are.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import tomllib
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from fstack import cli, merge
from fstack.cli import STARTER, Answers, FstackError, Names, _c, ok, step, warn

# Too common to find-and-replace through a codebase (they name folders, modules, routes).
COMMON = {"app", "api", "web", "ui", "server", "client", "core", "main", "src", "test", "demo", "frontend", "backend"}
PACKAGE_SUFFIXES = ("-web", "-api", "-frontend", "-backend", "-server", "-client")
ENV_FILE = re.compile(r"\.env(\..+)?")
KEEP_ENV = {".env.example", ".env.sample", ".env.template"}
SECRET = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|AIza[0-9A-Za-z_-]{35}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)
SECRET_SETTING = re.compile(r"^\s*[A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD)\s*[=:]\s*['\"]?[^\s'\"#]{12,}", re.M)
SETTINGS_FILE = re.compile(r"(^|/)(\.env[^/]*|[^/]*\.(ini|cfg|conf|properties))$")
B, A = r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])"  # word edges that treat - and _ as edges


@dataclass(frozen=True)
class Found:
    answers: Answers
    origin: str | None  # the fstack template the source was made from
    how: str


# ── reading the source ───────────────────────────────────────────────────────


def fetch(source: str, tmp: Path) -> tuple[Path, str, str]:
    """The source's committed files, unpacked: (folder, label, commit)."""
    path = Path(source).expanduser()
    if path.is_dir():
        repo = path.resolve()
        try:
            commit = cli._git(repo, "rev-parse", "HEAD")
        except FstackError as exc:
            raise FstackError(f"{source} isn't a git repository with a commit: templates come from committed files") from exc
        if cli._git(repo, "status", "--porcelain", "--", "."):
            warn(f"{source} has uncommitted changes: only what's committed goes into the template")
        label = repo.name
    elif re.match(r"(https?|ssh|git|file)://|[\w.-]+@[\w.-]+:", source):
        repo = tmp / "clone"
        step(f"cloning {source}")
        cli._git(tmp, "clone", "--quiet", "--depth", "1", source, str(repo))
        commit = cli._git(repo, "rev-parse", "HEAD")
        label = re.sub(r"\.git$", "", re.split(r"[/:]", source.rstrip("/"))[-1])
    else:
        raise FstackError(f"{source} is neither a folder nor a git URL")
    files = tmp / "files"
    if not cli.extract(repo, "HEAD", files):  # run in `repo`: that folder's committed files
        raise FstackError(f"couldn't read {source}'s committed files (git archive failed)")
    return files, label, commit


def collect(root: Path) -> tuple[merge.Tree, list[str]]:
    """Every file that belongs in a template (lockfiles too: the template stays runnable)."""
    tree: merge.Tree = {}
    skipped: list[str] = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in cli.SKIP_DIRS)
        for name in sorted(files):
            rel = (Path(dirpath) / name).relative_to(root).as_posix()
            if name in {cli.META, cli.MANIFEST, ".DS_Store"} or (ENV_FILE.fullmatch(name) and name not in KEEP_ENV):
                skipped.append(rel)
            else:
                tree[rel] = cli._entry(Path(dirpath) / name)
    return tree, skipped


def _read(root: Path, rel: str) -> str:
    path = root / rel
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _package_name(root: Path) -> str | None:
    """The project's name as its package manifests have it."""
    for rel in ("package.json", "frontend/package.json", "web/package.json"):
        try:
            name = json.loads(_read(root, rel) or "{}").get("name")
        except ValueError:
            name = None
        if isinstance(name, str) and name:
            name = name.rsplit("/", 1)[-1]  # @scope/name
            return next((name.removesuffix(s) for s in PACKAGE_SUFFIXES if name.endswith(s)), name)
    for rel in ("pyproject.toml", "backend/pyproject.toml", "Cargo.toml"):
        try:
            data = tomllib.loads(_read(root, rel))
        except tomllib.TOMLDecodeError:
            continue
        name = (data.get("project") or data.get("package") or data.get("tool", {}).get("poetry") or {}).get("name")
        if isinstance(name, str) and name:
            return next((name.removesuffix(s) for s in PACKAGE_SUFFIXES if name.endswith(s)), name)
    if match := re.search(r"^module\s+(\S+)", _read(root, "go.mod"), re.M):
        return re.sub(r"/v\d+$", "", match.group(1)).rsplit("/", 1)[-1]
    return None


def _readme_title(root: Path, slug: str) -> str | None:
    """README's first heading, when it is the project's name written out."""
    match = re.search(r"^#\s+(.+?)\s*$", _read(root, "README.md"), re.M)
    if match:
        try:
            if Names.from_raw(match.group(1), None).slug == slug:
                return match.group(1)
        except SystemExit:
            return None
    return None


def _number(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text, re.M)
    return int(match.group(1)) if match else None


def guess(root: Path, tree: merge.Tree, label: str) -> Answers:
    """Answers for a repo fstack didn't make: name from its manifests, ports from its Makefile."""
    try:
        names = Names.from_raw(_package_name(root) or label, None)
    except SystemExit as exc:
        raise FstackError(f"couldn't tell the project's name: pass --source-name ({exc})") from exc
    names = replace(names, title=_readme_title(root, names.slug) or names.title)
    makefile = _read(root, "Makefile")
    api_port = _number(makefile, r"^API_PORT\s*[?:]?=\s*(\d+)")
    web_port = _number(makefile, r"^WEB_PORT\s*[?:]?=\s*(\d+)")
    for rel in ("vite.config.ts", "vite.config.js", "frontend/vite.config.ts", "frontend/vite.config.js"):
        web_port = web_port or _number(_read(root, rel), r"^\s*port:\s*(\d+)")
    paths = set(tree)
    pm = pm_version = None
    if any(PurePosixPath(p).name == "package.json" for p in paths):
        names_here = {PurePosixPath(p).name for p in paths}
        pm = "bun" if names_here & {"bun.lock", "bun.lockb"} else "pnpm" if "pnpm-lock.yaml" in names_here else None
        for rel in ("package.json", "frontend/package.json"):
            if pm and (match := re.search(rf'"packageManager":\s*"{pm}@([^"]+)"', _read(root, rel))):
                pm_version = match.group(1)
    accent = None
    for rel, entry in tree.items():
        text = cli._text(rel, entry.data) or ""
        if match := re.search(r"(#[0-9a-fA-F]{6}); /\* fstack:accent \*/", text):
            accent = match.group(1)
            break
    return Answers(names, api_port, web_port, accent, pm, pm_version)


def detect(root: Path, tree: merge.Tree, label: str, args: argparse.Namespace) -> Found:
    if (root / cli.META).is_file():
        meta = cli._json_object((root / cli.META).read_text(encoding="utf-8"), cli.META)
        found = Found(cli._answers(meta, cli.META), cli.project_template(meta), f"from its {cli.META}")
    else:
        try:  # made by fstack before .fstack.json: the default template's layout
            found = Found(cli.infer_answers(root), cli.DEFAULT_TEMPLATE, "read from its files, made by fstack")
        except FstackError:
            found = Found(guess(root, tree, label), None, "guessed from its files")
    a = found.answers
    if args.source_name or args.source_title:
        names = Names.from_raw(args.source_name or a.names.slug, args.source_title or (None if args.source_name else a.names.title))
        a = replace(a, names=names)
    if args.accent and not cli.HEX.fullmatch(args.accent):
        raise FstackError("--accent must be a 6-digit hex color, e.g. #ffbe25")
    a = replace(
        a,
        api_port=args.api_port or a.api_port,
        web_port=args.web_port or a.web_port,
        accent=args.accent or a.accent,
    )
    if a.names.slug in COMMON or len(a.names.slug) < 3:
        raise FstackError(
            f"the project's name {a.names.slug!r} is too common to replace through the code safely: "
            "pass --source-name with how the source spells it, or rename the project first"
        )
    return replace(found, answers=a)


# ── reversing the render ─────────────────────────────────────────────────────


def reverse_rules(a: Answers) -> tuple[re.Pattern[str], dict[str, str]]:
    """One pattern for every value to put back (so no replacement feeds another), and
    what each named group becomes."""
    n = a.names
    parts: list[tuple[str, str, str]] = []  # group, regex, starter token
    if n.title not in (n.slug, n.snake):
        parts.append(("title", B + re.escape(n.title) + A, STARTER["title"]))
    if n.slug != n.snake:
        parts.append(("slug", B + re.escape(n.slug) + A, STARTER["slug"]))
        parts.append(("snake", B + re.escape(n.snake) + A, STARTER["snake"]))
    else:  # one word: the slug where it reads like one (crm-web, crm:theme), else the identifier
        parts.append(("slug", B + re.escape(n.slug) + r"(?=[-:])", STARTER["slug"]))
        parts.append(("snake", B + re.escape(n.slug) + A, STARTER["snake"]))
    for key, group in (("api_port", "api"), ("web_port", "web")):
        value = getattr(a, key)
        if value is not None and str(value) != STARTER[key]:
            parts.append((group, rf"\b{value}\b", STARTER[key]))
    if a.accent is not None:
        # The text color on the accent first, so an accent that equals it can't claim it.
        parts.append(("ink", r"#[0-9a-fA-F]{6}(?=; /\* fstack:accent-ink \*/)", "#ffffff"))
        if a.accent.lower() != STARTER["accent"]:
            parts.append(("accent", f"(?i:{re.escape(a.accent)})", STARTER["accent"]))
    pattern = re.compile("|".join(f"(?P<{group}>{regex})" for group, regex, _ in parts))
    return pattern, {group: token for group, _, token in parts}


def reverse(tree: merge.Tree, a: Answers) -> tuple[merge.Tree, dict[str, Counter[str]]]:
    pattern, tokens = reverse_rules(a)
    out: merge.Tree = {}
    counts: dict[str, Counter[str]] = {}
    for rel, entry in tree.items():
        text = cli._text(rel, entry.data)
        if text is None:
            out[rel] = entry
            continue
        seen: Counter[str] = Counter()

        def put_back(match: re.Match[str], seen: Counter[str] = seen) -> str:
            group = match.lastgroup or ""
            if match.group(0) != tokens[group]:
                seen[group] += 1
            return tokens[group]

        new = pattern.sub(put_back, text)
        out[rel] = merge.Entry(new.encode("utf-8"), entry.executable) if new != text else entry
        if seen:
            counts[rel] = seen
    return out, counts


def _lines(tree: merge.Tree, pattern: re.Pattern[str], only: re.Pattern[str] | None = None) -> list[str]:
    hits = []
    for rel, entry in sorted(tree.items()):
        if only is not None and not only.search(rel):
            continue
        text = cli._text(rel, entry.data)
        if text is None or rel.endswith(".lock") or rel.endswith("-lock.yaml"):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if match := pattern.search(line):
                hits.append(f"{rel}:{number} ({match.group(0)[:12]}…)")
    return hits


def asked(tree: merge.Tree, a: Answers) -> list[str]:
    """The answers whose starter token the template now holds."""
    text = "\n".join(t for rel, e in tree.items() if (t := cli._text(rel, e.data)) is not None)
    keys = []
    for key in ("api_port", "web_port"):
        if getattr(a, key) is not None and re.search(rf"\b{STARTER[key]}\b", text):
            keys.append(key)
    if a.accent is not None and STARTER["accent"] in text.lower():
        keys.append("accent")
    if a.pm is not None:
        keys.append("pm")
    return keys


# ── the manifest ─────────────────────────────────────────────────────────────

INSTALLS = (
    ("pyproject.toml", lambda names, pm: "uv sync" if "uv.lock" in names else None),
    (
        "package.json",
        lambda names, pm: "{pm} install" if pm else "yarn install" if "yarn.lock" in names else "npm install",
    ),
    ("go.mod", lambda names, pm: "go mod download"),
    ("Cargo.toml", lambda names, pm: "cargo fetch"),
)


def detect_install(tree: merge.Tree, pm: str | None) -> list[tuple[str, str]]:
    by_dir: dict[str, set[str]] = {}
    for rel in tree:
        path = PurePosixPath(rel)
        if len(path.parts) <= 3:
            by_dir.setdefault(str(path.parent), set()).add(path.name)
    steps: list[tuple[str, str]] = []
    for where in sorted(by_dir, key=lambda d: (d != ".", d)):
        names = by_dir[where]
        for marker, command in INSTALLS:
            # A workspace member installs with the package above it.
            above = [d for d, _ in steps if d == "." or where.startswith(d + "/")]
            if marker in names and not (marker == "package.json" and above):
                if run := command(names, pm):
                    steps.append((where, run))
    return steps


def manifest(label: str, commit: str, description: str, keys: list[str], install, steps) -> str:
    def s(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    lines = [
        f"# Made by `fstack template add` from {label} @ {commit[:7]}. Never copied into projects.",
        f"description = {s(description)}",
        "",
        "# Answers this template uses (besides the name and title): api_port, web_port, accent, pm.",
        f"answers = [{', '.join(s(k) for k in keys)}]",
        "",
        "# Run after the files are written, in order; {pm} is the chosen package manager.",
        "install = [",
        *(f"  {{ dir = {s(where)}, run = {s(run)} }}," for where, run in install),
        "]",
        "",
        '# Printed under "Next:"; {api_port}, {web_port}, … are the project\'s answers.',
        "next = [",
        *(f"  [{s(cmd)}, {s(comment)}]," for cmd, comment in steps),
        "]",
    ]
    return "\n".join(lines) + "\n"


# ── the command ──────────────────────────────────────────────────────────────


def _show(items: list[str], limit: int = 8) -> str:
    more = f" … and {len(items) - limit} more" if len(items) > limit else ""
    return ", ".join(items[:limit]) + more


def add(args: argparse.Namespace) -> int:
    name = args.name
    if not cli.SLUG.fullmatch(name):
        raise FstackError(f"template name {name!r} must be a slug like range or crm-lite")
    source = cli.installed_source()
    if source.repo is None or not Path(source.repo).is_dir():
        raise FstackError(
            "templates are added in a fstack checkout: `uv tool install --editable <your fstack clone>`, "
            "add it there, then commit and push it"
        )
    dest = source.root / name
    if dest.exists():
        raise FstackError(f"{dest} already exists: pick another name, or remove it first")

    with tempfile.TemporaryDirectory(prefix="fstack-import-") as tmp:
        root, label, commit = fetch(args.source, Path(tmp))
        tree, skipped = collect(root)
        if not tree:
            raise FstackError(f"{args.source} has no committed files")
        found = detect(root, tree, label, args)
    a = found.answers
    secrets = _lines(tree, SECRET) + _lines(tree, SECRET_SETTING, SETTINGS_FILE)
    already = _lines(tree, re.compile("|".join(re.escape(STARTER[k]) for k in ("slug", "snake", "title"))))
    reversed_tree, counts = reverse(tree, a)
    keys = asked(reversed_tree, a)
    words = re.findall(r"[a-z0-9]+", a.names.slug)
    leftover = _lines(reversed_tree, re.compile(r"[\s_-]?".join(map(re.escape, words)), re.I))
    named_paths = [p for p in reversed_tree if a.names.slug in p.lower() or a.names.snake in p.lower()]

    origin = None
    if found.origin and found.origin in cli.template_names(source.root):
        origin = source.template(found.origin)
    install = [(d, r) for d, r in origin.install if d == "." or any(p.startswith(d + "/") for p in tree)] if origin else []
    install = install or detect_install(reversed_tree, a.pm)
    makefile = cli._text("Makefile", reversed_tree["Makefile"].data) if "Makefile" in reversed_tree else ""
    steps = list(origin.next) if origin else ([("make help", "what you can run")] if "help:" in (makefile or "") else [])
    made = f", a project of the {found.origin} template" if found.origin else ""
    description = args.description or f"Made from {label}{made}"

    n = a.names
    print(f"\n  {_c('1', name)}  {_c('2', f'← {label} @ {commit[:7]} (answers {found.how})')}\n")
    print(f"    name    {n.slug} · {n.snake} · “{n.title}”")
    details = [f"api :{a.api_port}" if a.api_port else "", f"web :{a.web_port}" if a.web_port else ""]
    details += [f"accent {a.accent}" if a.accent else "", f"pm {a.pm}" if a.pm else ""]
    if any(details):
        print(f"    values  {' · '.join(d for d in details if d)}")
    print(f"    asks    {', '.join(keys) or 'only the name and title'}")
    print(f"    install {'; '.join(f'{d}: {r}' for d, r in install) or 'nothing'}\n")
    ok(f"{len(tree)} files, {len(counts)} with the project's values put back to the starter's")
    for rel, seen in sorted(counts.items()) if args.dry_run else []:
        print(f"    {rel}  {_c('2', ', '.join(f'{g} ×{c}' for g, c in sorted(seen.items())))}")
    if skipped:
        warn(f"left out: {_show(skipped)}")
    if secrets:
        warn(f"looks like a secret, check before committing: {_show(secrets)}")
    if already:
        warn(f"already holds starter tokens, which projects will rewrite: {_show(already)}")
    if leftover:
        warn(f"other spellings of the name stay as they are: {_show(leftover)}")
    if named_paths:
        warn(f"paths keep the name (fstack never renames paths): {_show(named_paths)}")
    if args.dry_run:
        print(f"\n  {_c('2', 'Dry run: nothing written.')}\n")
        return 0

    cli.write_tree(reversed_tree, dest)
    (dest / cli.MANIFEST).write_text(manifest(label, commit, description, keys, install, steps), encoding="utf-8")
    cli.load_template(source.root, name)  # the manifest must read back
    rel = os.path.relpath(dest, Path(source.repo))
    print(
        f"""
  Next:
    fstack new demo -t {name} --dir /tmp/{name}-demo   {_c('2', '# try it')}
    git -C {source.repo} add {rel} && git -C {source.repo} commit -m "feat(templates): add {name}"
"""
    )
    return 0
