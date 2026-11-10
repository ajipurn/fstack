"""A throwaway fstack repo with a tiny template, and projects made from it."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from fstack import cli

# Windows files have no x bits, and its symlinks need a privilege and a file-or-folder flag.
posix_only = pytest.mark.skipif(os.name == "nt", reason="needs POSIX file modes or symlinks")

CONFIG = "".join(f"setting_{i} = {i}\n" for i in range(12))
PAGE = "".join(f"export const line{i} = {i};\n" for i in range(8))
TEMPLATE = {
    "Makefile": "PM ?= bun\nAPI_PORT ?= 8710\nWEB_PORT ?= 5710\n",
    "README.md": "# Fstack Starter\n\nmake dev  # API :8710 + web :5710\n",
    "frontend/package.json": '{\n  "name": "fstack-starter-web",\n  "packageManager": "bun@1.0.0"\n}\n',
    "frontend/src/app/AppShell.tsx": 'const APP_NAME = "Fstack Starter";\n',
    "frontend/src/styles/tokens.css": (
        "--accent-base: #2f3037; /* fstack:accent */\n--accent-ink: #ffffff; /* fstack:accent-ink */\n"
    ),
    "frontend/src/run.tsx": "export const run = 1;\n",
    "frontend/src/page.tsx": PAGE,
    "backend/app/config.py": CONFIG,
    "backend/app/old.py": "old = True\n",
    "backend/uv.lock": "lock\n",  # never copied, never merged
    "scripts/tool.sh": "#!/bin/sh\necho fstack-starter\n",
    cli.MANIFEST: """description = "API and dashboard"
answers = ["api_port", "web_port", "accent", "pm"]
install = [{ dir = "backend", run = "uv sync" }, { dir = "frontend", run = "{pm} install" }]
next = [["make dev", "api :{api_port} + web :{web_port}"]]
""",
}
API_TEMPLATE = {
    "Makefile": "API_PORT ?= 8710\n",
    "README.md": "# Fstack Starter API\n\nmake api  # :8710, CORS for :5710\n",
    "backend/app/config.py": CONFIG,
    cli.MANIFEST: 'description = "API only"\nanswers = ["api_port"]\n',
}
FULL = "templates/default"
API = "templates/lite"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def write(root: Path, files: dict[str, str | None]) -> None:
    for rel, text in files.items():
        path = root / rel
        if text is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def commit(cwd: Path, message: str, files: dict[str, str | None] | None = None) -> str:
    if files:
        write(cwd, files)
    git(cwd, "add", "-A")
    git(cwd, "commit", "-q", "-m", message)
    return git(cwd, "rev-parse", "HEAD")


def template_commit(repo: Path, files: dict[str, str | None], where: str = FULL) -> str:
    return commit(repo, "template change", {f"{where}/{k}": v for k, v in files.items()})


def new_project(tmp_path: Path, name: str = "Demo App", *extra: str) -> Path:
    dest = tmp_path / "demo"
    args = ["new", name, "--dir", str(dest), "--no-install", "--accent", "#ffbe25", "--api-port", "8100"]
    assert cli.main([*args, "--web-port", "5200", *extra]) == 0
    return dest


def legacy_project(tmp_path: Path, repo: Path, subject: str) -> tuple[Path, cli.Answers]:
    """A project rendered by hand and committed the way older fstack did: no .fstack.json."""
    names = cli.Names("legacy-app", "legacy_app", "Legacy App")
    answers = cli.Answers(names, 8300, 5300, "#2f3037", "bun", "1.2.3")
    project = tmp_path / "legacy"
    cli.write_tree(cli.render_tree(repo / FULL, answers), project)
    git(project.parent, "init", "-q", "-b", "main", str(project))
    commit(project, subject)
    return project, answers


def meta(project: Path) -> dict:
    return json.loads((project / ".fstack.json").read_text(encoding="utf-8"))


def rendered(text: str) -> str:
    return text.replace("Fstack Starter", "Demo App").replace("8710", "8100").replace("5710", "5200")
