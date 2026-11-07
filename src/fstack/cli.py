"""fstack — scaffold a new FastAPI + llmfy + MySQL + React/Vite project.

Usage:
    fstack new <name> [options]
    fstack doctor

The template under ``template/`` is a runnable project called
"fstack-starter". Scaffolding copies it, renames the starter tokens, writes a
``.env`` with fresh secrets, installs dependencies and makes the first commit.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import os
import re
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from fstack import __version__

# ── template location ────────────────────────────────────────────────────────


def template_root() -> Path:
    packaged = Path(__file__).parent / "template"
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[2] / "template"


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

_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


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


# ── scaffold ─────────────────────────────────────────────────────────────────


def is_text(path: Path) -> bool:
    if path.suffix.lower() in BINARY_SUFFIXES:
        return False
    try:
        path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    return True


def copy_template(src: Path, dest: Path) -> list[Path]:
    written: list[Path] = []
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        rel = Path(root).relative_to(src)
        (dest / rel).mkdir(parents=True, exist_ok=True)
        for name in sorted(files):
            if name in SKIP_FILES:
                continue
            target = dest / rel / name
            shutil.copy2(Path(root) / name, target)
            written.append(target)
    return written


def render(files: list[Path], replacements: list[tuple[re.Pattern[str], str]]) -> None:
    for path in files:
        if not is_text(path):
            continue
        text = path.read_text(encoding="utf-8")
        new = text
        for pattern, value in replacements:
            new = pattern.sub(value, new)
        if new != text:
            path.write_text(new, encoding="utf-8")


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
    env.write_text(text, encoding="utf-8")
    env.chmod(0o600)
    return True


def set_package_manager(dest: Path, pm: str) -> None:
    pkg = dest / "frontend" / "package.json"
    makefile = dest / "Makefile"
    versions = {"bun": _tool_version("bun"), "pnpm": _tool_version("pnpm")}
    text = pkg.read_text(encoding="utf-8")
    ver = versions.get(pm)
    text = re.sub(r'"packageManager": "[^"]+"', f'"packageManager": "{pm}@{ver or "latest"}"', text)
    pkg.write_text(text, encoding="utf-8")
    mk = makefile.read_text(encoding="utf-8")
    mk = re.sub(r"^PM \?= \w+", f"PM ?= {pm}", mk, flags=re.M)
    makefile.write_text(mk, encoding="utf-8")
    ci = dest / ".github" / "workflows" / "check.yml"
    if pm == "pnpm" and ci.exists():
        text = ci.read_text(encoding="utf-8")
        text = text.replace("- uses: oven-sh/setup-bun@v2", "- uses: pnpm/action-setup@v4\n      - uses: actions/setup-node@v4\n        with: { node-version: 24, cache: pnpm, cache-dependency-path: frontend/pnpm-lock.yaml }")
        text = text.replace("bun install --frozen-lockfile", "pnpm install --frozen-lockfile").replace("PM=bun", "PM=pnpm")
        ci.write_text(text, encoding="utf-8")


def _tool_version(tool: str) -> str | None:
    exe = shutil.which(tool)
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"\d+\.\d+\.\d+", out.stdout + out.stderr)
    return match.group(0) if match else None


def run(cmd: list[str], cwd: Path, label: str) -> bool:
    step(label)
    proc = subprocess.run(cmd, cwd=cwd)
    if proc.returncode != 0:
        fail(f"{label} failed ({' '.join(cmd)})")
        return False
    return True


def cmd_new(args: argparse.Namespace) -> int:
    names = Names.from_raw(args.name, args.title)
    dest = Path(args.dir or names.slug).expanduser().resolve()
    if dest.exists() and any(dest.iterdir()) and not args.force:
        fail(f"{dest} already exists and is not empty (use --force to write into it)")
        return 1

    api_port, web_port = default_ports(names.slug)
    api_port = args.api_port or api_port
    web_port = args.web_port or web_port
    accent = args.accent or STARTER["accent"]
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        fail("--accent must be a 6-digit hex color, e.g. #ffbe25")
        return 1

    print(f"\n  {_c('1', names.title)}  {_c('2', str(dest))}\n")
    # Ask before writing anything, so Ctrl-C leaves no half-made project.
    new_env = not args.database_url and not (dest / "backend" / ".env").exists()
    password, source = root_password() if new_env else ("", "")
    files = copy_template(template_root(), dest)
    replacements = [
        (re.compile(re.escape(STARTER["slug"])), names.slug),
        (re.compile(re.escape(STARTER["snake"])), names.snake),
        (re.compile(re.escape(STARTER["title"])), names.title),
        (re.compile(rf"\b{STARTER['api_port']}\b"), str(api_port)),
        (re.compile(rf"\b{STARTER['web_port']}\b"), str(web_port)),
        (re.compile(re.escape(STARTER["accent"]), re.I), accent),
        (re.compile(r"#ffffff(; /\* fstack:accent-ink \*/)"), rf"{ink_for(accent)}\g<1>"),
    ]
    render(files, replacements)
    set_package_manager(dest, args.pm)
    created_env = write_env(dest, args.database_url, names, password)
    ok(f"files written ({len(files)})  api :{api_port}  web :{web_port}  pm {args.pm}")
    if created_env:
        ok("backend/.env created with fresh secrets (sign in with APP_ACCESS_KEY)")
        if source.startswith("default"):
            warn(f"MySQL root password: {source}")
        elif source:
            ok(f"MySQL root password {source}")

    if not args.no_install:
        if shutil.which("uv"):
            run(["uv", "sync", "--compile-bytecode"], dest / "backend", "backend: uv sync")
        else:
            warn("uv not found — skipped backend install (https://docs.astral.sh/uv/)")
        if shutil.which(args.pm):
            run([args.pm, "install"], dest / "frontend", f"frontend: {args.pm} install")
        else:
            warn(f"{args.pm} not found — skipped frontend install")

    if not args.no_git and shutil.which("git") and not (dest / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=dest)
        subprocess.run(["git", "add", "-A"], cwd=dest)
        subprocess.run(
            ["git", "commit", "-q", "-m", f"chore: scaffold {names.slug} from fstack {__version__}"],
            cwd=dest,
        )
        ok("git repository initialised")

    rel = os.path.relpath(dest)
    print(
        f"""
  Next:
    cd {rel}
    make db-up    {_c('2', '# MySQL via Apple container or Docker (or set APP_DATABASE_URL)')}
    make seed     {_c('2', '# schema, prompts, prices; sign in with APP_ACCESS_KEY (backend/.env)')}
    make dev      {_c('2', f'# api :{api_port} + web :{web_port}')}
"""
    )
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    checks = [
        ("uv", "backend env + deps"),
        ("python3", "python runtime"),
        ("bun", "frontend pm (default)"),
        ("pnpm", "frontend pm (alt)"),
        ("node", "vite tooling"),
        ("container", "local MySQL via `make db-up` (Apple container)"),
        ("docker", "local MySQL via `make db-up` (alt)"),
        ("git", "repository init"),
    ]
    missing = 0
    for tool, purpose in checks:
        version = _tool_version(tool)
        if version:
            ok(f"{tool:<9} {version:<10} {_c('2', purpose)}")
        else:
            warn(f"{tool:<9} {'missing':<10} {_c('2', purpose)}")
            missing += tool in {"uv", "python3"}
    if os.environ.get("DB_ROOT_PASSWORD"):
        ok(f"{'DB_ROOT_PASSWORD':<20} {_c('2', 'set: fstack new writes it into backend/.env')}")
    else:
        warn(f"{'DB_ROOT_PASSWORD':<20} {_c('2', 'not set: fstack new will ask for MySQL’s root password')}")
    print(f"\n  template: {template_root()}")
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(line_buffering=True)  # keep our lines ordered with child output
    parser = argparse.ArgumentParser(prog="fstack", description="Scaffold a new full-stack project.")
    parser.add_argument("--version", action="version", version=f"fstack {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="create a project from the template")
    new.add_argument("name", help="project name, e.g. 'talent-review' or 'Talent Review'")
    new.add_argument("--dir", help="target directory (default: ./<slug>)")
    new.add_argument("--title", help="display name (default: derived from name)")
    new.add_argument("--pm", choices=["bun", "pnpm"], default="bun", help="frontend package manager")
    new.add_argument("--accent", help="primary button color, hex (default graphite #2f3037)")
    new.add_argument(
        "--database-url",
        help="APP_DATABASE_URL for backend/.env (default: local MySQL as root, $DB_ROOT_PASSWORD or root)",
    )
    new.add_argument("--api-port", type=int)
    new.add_argument("--web-port", type=int)
    new.add_argument("--no-install", action="store_true", help="skip uv sync / bun install")
    new.add_argument("--no-git", action="store_true", help="skip git init + first commit")
    new.add_argument("--force", action="store_true", help="write into a non-empty directory")
    new.set_defaults(func=cmd_new)

    doctor = sub.add_parser("doctor", help="check the local toolchain")
    doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
