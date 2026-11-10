# /// script
# requires-python = ">=3.12"
# ///
"""Project tasks, the same on macOS, Linux and Windows:

    uv run tasks.py <task>        # e.g. uv run tasks.py dev
    make <task>                   # macOS/Linux shortcut for the same

`uv run tasks.py help` lists them. Settings come from the environment:

    API_PORT, WEB_PORT   dev ports
    PM                   bun or pnpm (default: frontend/package.json's packageManager)
    DB_RUNTIME           container (Apple, macOS) or docker; empty = whichever runs
    DB_CONTAINER, DB_IMAGE, DB_PORT, DB_ROOT_PASSWORD
                         the shared Apple container, when db-up first creates it
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
API_PORT = os.environ.get("API_PORT") or "8710"
WEB_PORT = os.environ.get("WEB_PORT") or "5710"
WINDOWS = os.name == "nt"

TASKS: dict[str, Callable[[list[str]], None]] = {}


def task(name: str):
    def register(fn: Callable[[list[str]], None]) -> Callable[[list[str]], None]:
        TASKS[name] = fn
        return fn

    return register


# ── helpers ──────────────────────────────────────────────────────────────────


def pm() -> str:
    """The frontend package manager: $PM, else the one package.json pins."""
    if os.environ.get("PM"):
        return os.environ["PM"]
    try:
        spec = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))["packageManager"]
    except (OSError, KeyError, ValueError):
        return "bun"
    return str(spec).split("@")[0]


def _env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {**os.environ, **(extra or {})}
    # `uv run tasks.py` puts this script in its own environment; the backend has its own.
    env.pop("VIRTUAL_ENV", None)
    return env


def _argv(cmd: tuple[str, ...]) -> list[str]:
    # By full path: Windows runs `pnpm.cmd` or `bun.exe` only when found this way.
    exe = shutil.which(cmd[0])
    if exe is None:
        sys.exit(f"{cmd[0]} not found: install it, then run this again")
    return [exe, *cmd[1:]]


def sh(*cmd: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    """Run a command; stop with its exit code when it fails."""
    code = subprocess.run(_argv(cmd), check=False, cwd=cwd, env=_env(env)).returncode
    if code:
        sys.exit(code)


def quiet(*cmd: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    exe = shutil.which(cmd[0])
    if exe is None:
        return subprocess.CompletedProcess(cmd, 127, "", "")
    return subprocess.run(
        [exe, *cmd[1:]], check=False, cwd=cwd, env=_env(), capture_output=True, text=True
    )


def together(*commands: tuple[tuple[str, ...], Path, dict[str, str]]) -> None:
    """Run commands side by side until Ctrl+C, or until one of them stops."""
    procs = []
    for cmd, cwd, env in commands:
        # Each in its own process group, so stopping one stops what it started (uvicorn's
        # reloader, vite under bun) instead of leaving it holding the port.
        flags = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if WINDOWS
            else {"start_new_session": True}
        )
        procs.append(subprocess.Popen(_argv(cmd), cwd=cwd, env=_env(env), **flags))
    code = 0
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.2)
        code = next(p.returncode for p in procs if p.returncode is not None)
    except KeyboardInterrupt:
        code = 130
    finally:
        # Ctrl+C can arrive twice (the terminal, and uv passing it on): don't let the second
        # one cut the cleanup short and leave vite or uvicorn running.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        for p in procs:
            _stop(p)
    sys.exit(code)


def _stop(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if WINDOWS:  # the whole tree: uv → python → uvicorn, bun → node
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)], check=False, capture_output=True
        )
        proc.wait()
        return
    for sig, wait in ((signal.SIGINT, 10), (signal.SIGTERM, 5), (signal.SIGKILL, 5)):
        try:
            os.killpg(proc.pid, sig)
            proc.wait(timeout=wait)
            return
        except ProcessLookupError:
            return
        except subprocess.TimeoutExpired:
            continue


# ── MySQL for development ────────────────────────────────────────────────────
# The app connects as root (APP_DATABASE_URL) and `seed` creates the project's database.
#   container  Apple's `container` CLI (macOS): one shared container (default `mysql`)
#              serves every project.
#   docker     docker compose (compose.yaml): one MySQL per project.

DB_NAME = os.environ.get("DB_CONTAINER") or "mysql"
DB_IMAGE = os.environ.get("DB_IMAGE") or "mysql:8.4"
DB_PORT = os.environ.get("DB_PORT") or "3306"


def _apple_running() -> bool:
    return bool(
        re.search(r"^status +running", quiet("container", "system", "status").stdout, re.MULTILINE)
    )


def db_runtime() -> str:
    if os.environ.get("DB_RUNTIME"):
        return os.environ["DB_RUNTIME"]
    apple = sys.platform == "darwin" and shutil.which("container") is not None
    if apple and _apple_running():
        return "container"
    if shutil.which("docker") and quiet("docker", "info").returncode == 0:
        return "docker"
    return "container" if apple else "docker"


def _container_up() -> None:
    if not _apple_running():
        print("starting Apple container services")
        sh("container", "system", "start")
    if quiet("container", "inspect", DB_NAME).returncode != 0:
        volume = f"{DB_NAME}_data"
        if quiet("container", "volume", "inspect", volume).returncode != 0:
            quiet("container", "volume", "create", volume)
        print(f"creating {DB_NAME} ({DB_IMAGE}) on 127.0.0.1:{DB_PORT}")
        password = os.environ.get("DB_ROOT_PASSWORD") or "root"
        created = quiet(
            "container", "run", "-d", "--progress", "none", "--name", DB_NAME,
            "-p", f"127.0.0.1:{DB_PORT}:3306", "-v", f"{volume}:/var/lib/mysql",
            "-e", f"MYSQL_ROOT_PASSWORD={password}", DB_IMAGE,
            "--character-set-server=utf8mb4", "--collation-server=utf8mb4_bin",
        )  # fmt: skip
        if created.returncode:
            sys.exit(created.stderr.strip() or f"couldn't create {DB_NAME}")
    elif DB_NAME not in quiet("container", "ls", "-q").stdout.split():
        quiet("container", "start", DB_NAME)
    # mysqladmin ping succeeds once the server takes TCP, even on "access denied"; the
    # first-boot init server listens on a socket only, so this waits it out.
    print(f"mysql (container {DB_NAME}) ", end="", flush=True)
    for _ in range(120):
        if (
            quiet(
                "container", "exec", DB_NAME, "mysqladmin", "ping", "-h", "127.0.0.1", "--silent"
            ).returncode
            == 0
        ):
            print(" ready")
            return
        print(".", end="", flush=True)
        time.sleep(1)
    sys.exit(f"\nnot ready after 120s (container logs {DB_NAME})")


def _container_down() -> None:
    if DB_NAME in quiet("container", "ls", "-q").stdout.split():
        quiet("container", "stop", DB_NAME)
        print(f"stopped container {DB_NAME} (shared: other projects using it are offline too)")
    else:
        print(f"container {DB_NAME} is not running")


# ── tasks ────────────────────────────────────────────────────────────────────


@task("help")
def help_(_: list[str]) -> None:
    """Show tasks"""
    for name, fn in TASKS.items():
        print(f"  {name:<10} {fn.__doc__}")


@task("setup")
def setup(_: list[str]) -> None:
    """Install backend + frontend dependencies"""
    sh(
        "uv", "sync", "--compile-bytecode", cwd=BACKEND
    )  # .pyc up front: no third-party SyntaxWarnings
    sh(pm(), "install", cwd=FRONTEND)


@task("db-up")
def db_up(_: list[str]) -> None:
    """Start MySQL: Apple container (shared) or Docker, whichever runs"""
    if db_runtime() == "container":
        _container_up()
    else:
        sh("docker", "compose", "up", "-d", "--wait", "mysql")


@task("db-down")
def db_down(_: list[str]) -> None:
    """Stop MySQL (Apple container: the shared one, for every project)"""
    if db_runtime() == "container":
        _container_down()
    else:
        sh("docker", "compose", "down")


@task("migrate")
def migrate(_: list[str]) -> None:
    """Apply Alembic migrations"""
    sh("uv", "run", "alembic", "upgrade", "head", cwd=BACKEND)


@task("revision")
def revision(args: list[str]) -> None:
    """New migration: revision add widgets"""
    if not args:
        sys.exit('usage: uv run tasks.py revision "add widgets"')
    sh("uv", "run", "alembic", "revision", "--autogenerate", "-m", " ".join(args), cwd=BACKEND)


@task("seed")
def seed(_: list[str]) -> None:
    """Migrate, prompts/*.md, task registry, models.dev prices"""
    sh("uv", "run", "python", "-m", "app.cli.seed", cwd=BACKEND)


@task("key")
def key(_: list[str]) -> None:
    """Print a fresh access key (paste into APP_ACCESS_KEY, then restart the API)"""
    print(secrets.token_urlsafe(32))


@task("prices")
def prices(_: list[str]) -> None:
    """Refresh model prices from models.dev"""
    sh("uv", "run", "python", "-m", "app.cli.prices", cwd=BACKEND)


def _api() -> tuple[tuple[str, ...], Path, dict[str, str]]:
    return (
        (
            "uv",
            "run",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            API_PORT,
            "--reload",
        ),
        BACKEND,
        {},
    )


def _web() -> tuple[tuple[str, ...], Path, dict[str, str]]:
    return (pm(), "run", "dev"), FRONTEND, {"API_URL": f"http://127.0.0.1:{API_PORT}"}


@task("api")
def api(_: list[str]) -> None:
    """FastAPI with reload on :API_PORT"""
    cmd, cwd, env = _api()
    sh(*cmd, cwd=cwd, env=env)


@task("web")
def web(_: list[str]) -> None:
    """Vite on :WEB_PORT (proxies /api)"""
    cmd, cwd, env = _web()
    sh(*cmd, cwd=cwd, env=env)


@task("worker")
def worker(_: list[str]) -> None:
    """Background job worker (run it as its own process)"""
    sh("uv", "run", "python", "-m", "app.workers.worker", cwd=BACKEND)


@task("dev")
def dev(_: list[str]) -> None:
    """api + web together"""
    together(_api(), _web())


@task("test")
def test(_: list[str]) -> None:
    """Backend tests (SQLite) + frontend tests"""
    sh("uv", "run", "pytest", "-q", cwd=BACKEND)
    sh(pm(), "run", "test", cwd=FRONTEND)


@task("lint")
def lint(_: list[str]) -> None:
    """ruff + oxlint"""
    sh("uv", "run", "ruff", "check", ".", "../tasks.py", cwd=BACKEND)
    sh("uv", "run", "ruff", "format", "--check", ".", "../tasks.py", cwd=BACKEND)
    sh(pm(), "run", "lint", cwd=FRONTEND)


@task("build")
def build(_: list[str]) -> None:
    """Production frontend bundle"""
    sh(pm(), "run", "build", cwd=FRONTEND)


@task("check")
def check(args: list[str]) -> None:
    """Everything CI runs: lint, test, build"""
    lint(args)
    test(args)
    build(args)


def main(argv: list[str]) -> None:
    name, args = (argv[0], argv[1:]) if argv else ("help", [])
    if name not in TASKS:
        print(f"unknown task {name!r}; these are the tasks:", file=sys.stderr)
        help_([])
        sys.exit(2)
    TASKS[name](args)


if __name__ == "__main__":
    main(sys.argv[1:])
