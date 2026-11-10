from pathlib import Path

import pytest
from helpers import API, API_TEMPLATE, FULL, TEMPLATE, commit, git, write

from fstack import cli


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("", encoding="utf-8", newline="\n")
    for key, value in {
        "GIT_CONFIG_GLOBAL": str(gitconfig),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
        "DB_ROOT_PASSWORD": "pw",
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(cli, "_tool_version", lambda tool: "1.2.3")


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "fstack"
    write(root / FULL, TEMPLATE)
    write(root / API, API_TEMPLATE)
    git(root.parent, "init", "-q", "-b", "main", str(root))
    commit(root, "template v1")
    monkeypatch.setattr(cli, "templates_root", lambda: root / "templates")
    return root
