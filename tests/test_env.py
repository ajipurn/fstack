"""backend/.env: fresh secrets, readable only by the owner from the moment it exists."""

import os
import stat
from pathlib import Path

import pytest

from fstack import cli

NAMES = cli.Names("demo-app", "demo_app", "Demo App")
EXAMPLE = "APP_DATABASE_URL=mysql+pymysql://root:root@127.0.0.1:3306/x\nAPP_ACCESS_KEY=\nAPP_ENCRYPTION_KEY=\n"


def _project(tmp_path: Path) -> Path:
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / ".env.example").write_text(EXAMPLE, encoding="utf-8")
    return tmp_path


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_env_is_never_readable_by_others(tmp_path, monkeypatch):
    dest = _project(tmp_path)
    env = dest / "backend" / ".env"
    seen = []
    chmod = Path.chmod

    def record(self, mode, **kwargs):
        seen.append(stat.S_IMODE(os.stat(self).st_mode))  # the mode the file was created with
        return chmod(self, mode, **kwargs)

    monkeypatch.setattr(Path, "chmod", record)
    old = os.umask(0)  # the worst case: 0666 & ~umask would be world-readable
    try:
        assert cli.write_env(dest, None, NAMES, "p@ss")
    finally:
        os.umask(old)
    assert seen and all(mode == 0o600 for mode in seen)
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    text = env.read_text(encoding="utf-8")
    assert "APP_DATABASE_URL=mysql+pymysql://root:p%40ss@127.0.0.1:3306/demo_app\n" in text
    assert "APP_ACCESS_KEY=\n" not in text and "APP_ENCRYPTION_KEY=\n" not in text


def test_env_is_left_alone(tmp_path):
    assert not cli.write_env(tmp_path, None, NAMES, "pw")  # no .env.example
    dest = _project(tmp_path)
    env = dest / "backend" / ".env"
    env.write_text("mine\n", encoding="utf-8")
    assert not cli.write_env(dest, None, NAMES, "pw")
    assert env.read_text(encoding="utf-8") == "mine\n"
