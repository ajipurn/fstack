import os
from pathlib import Path

import pytest
from helpers import posix_only

from fstack.merge import HAS_MODES, Change, Entry, apply, plan

LABELS = ("project", "old", "new")
TEXT = "".join(f"line {i}\n" for i in range(10))


def e(text: str, executable: bool = False) -> Entry:
    return Entry(text.encode(), executable)


def kinds(changes: list[Change]) -> dict[str, str]:
    return {c.path: c.kind for c in changes}


def test_untouched_by_template_is_ignored():
    assert plan({"a": e("x")}, {"a": e("x")}, {"a": e("changed here")}, LABELS) == []


def test_template_change_on_unchanged_file_is_taken():
    [change] = plan({"a": e("x")}, {"a": e("y", True)}, {"a": e("x")}, LABELS)
    assert (change.kind, change.data, change.executable) == ("updated", b"y", True)


def test_both_sides_on_different_lines_merge():
    ours = TEXT.replace("line 1\n", "line 1 (project)\n")
    new = TEXT.replace("line 8\n", "line 8 (template)\n")
    [change] = plan({"a": e(TEXT)}, {"a": e(new)}, {"a": e(ours)}, LABELS)
    assert change.kind == "merged"
    assert change.data.decode() == TEXT.replace("line 1\n", "line 1 (project)\n").replace(
        "line 8\n", "line 8 (template)\n"
    )


def test_both_sides_on_the_same_line_conflict():
    ours = TEXT.replace("line 4\n", "mine\n")
    new = TEXT.replace("line 4\n", "theirs\n")
    [change] = plan({"a": e(TEXT)}, {"a": e(new)}, {"a": e(ours)}, LABELS)
    assert (change.kind, change.conflicts) == ("conflict", 1)
    assert b"<<<<<<< project\nmine\n=======\ntheirs\n>>>>>>> new\n" in change.data


def test_additions_and_removals():
    base = {"gone": e("x"), "gone-edited": e("x"), "deleted-here": e("x")}
    new = {"fresh": e("new"), "deleted-here": e("y"), "same": e("s")}
    ours = {"gone": e("x"), "gone-edited": e("mine"), "same": e("s")}
    assert kinds(plan(base, new, ours, LABELS)) == {
        "fresh": "added",
        "gone": "removed",
        "gone-edited": "kept",
        "deleted-here": "skipped",
    }


def test_binary_changed_on_both_sides_keeps_ours():
    [change] = plan({"i": e("\0a")}, {"i": e("\0b")}, {"i": e("\0c")}, LABELS)
    assert (change.kind, change.data) == ("conflict", None)


def test_apply_writes_and_cleans_up(tmp_path):
    (tmp_path / "old" / "deep").mkdir(parents=True)
    (tmp_path / "old" / "deep" / "f").write_text("x", encoding="utf-8", newline="\n")
    apply(
        [
            Change("old/deep/f", "removed"),
            Change("bin/run.sh", "added", b"#!/bin/sh\n", executable=True),
            Change("skip", "skipped"),
        ],
        tmp_path,
    )
    assert not (tmp_path / "old").exists()
    assert not HAS_MODES or (tmp_path / "bin" / "run.sh").stat().st_mode & 0o111
    assert not (tmp_path / "skip").exists()


def test_project_mode_survives_a_content_update():
    [change] = plan({"s": e("x", False)}, {"s": e("y", False)}, {"s": e("x", True)}, LABELS)
    assert (change.kind, change.executable) == ("updated", True)


def test_template_mode_change_wins():
    [change] = plan({"s": e("x", False)}, {"s": e("y", True)}, {"s": e("x", False)}, LABELS)
    assert change.executable is True


def test_untracked_files_are_left_alone():
    changes = plan({"a": e("x")}, {"a": e("y"), "b": e("new")}, {}, LABELS, untracked={"a", "b"})
    assert kinds(changes) == {"a": "skipped", "b": "skipped"}
    assert all(c.data is None for c in changes)


def test_moved_file_carries_project_edits():
    ours = TEXT.replace("line 1\n", "line 1 (project)\n")
    moved = TEXT.replace("line 8\n", "line 8 (template)\n")
    [change] = plan({"old": e(TEXT)}, {"new": e(moved)}, {"old": e(ours)}, LABELS)
    assert (change.path, change.old, change.kind) == ("new", "old", "merged")
    assert b"line 1 (project)" in change.data and b"line 8 (template)" in change.data


def test_pure_move_of_untouched_file_is_a_rename(tmp_path):
    [change] = plan({"old": e(TEXT)}, {"new": e(TEXT)}, {"old": e(TEXT)}, LABELS)
    assert (change.kind, change.old) == ("renamed", "old")
    (tmp_path / "old").write_text(TEXT, encoding="utf-8", newline="\n")
    apply([change], tmp_path)
    assert not (tmp_path / "old").exists() and (tmp_path / "new").read_text(encoding="utf-8") == TEXT


def test_tiny_or_unrelated_files_are_not_moves():
    base = {"a/__init__.py": e(""), "gone.py": e(TEXT)}
    new = {"b/__init__.py": e(""), "other.py": e("".join(f"other {i}\n" for i in range(10)))}
    ours = {"a/__init__.py": e("# mine\n"), "gone.py": e(TEXT)}
    assert kinds(plan(base, new, ours, LABELS)) == {
        "a/__init__.py": "kept",
        "b/__init__.py": "added",
        "gone.py": "removed",
        "other.py": "added",
    }


def test_move_of_a_file_deleted_here_is_skipped():
    [change] = plan({"old": e(TEXT)}, {"new": e(TEXT + "more\n")}, {}, LABELS)
    assert (change.path, change.kind) == ("new", "skipped")


@pytest.fixture
def linked(tmp_path) -> Path:
    """A project whose symlinks lead outside it (and into its .git), next to `outside/`."""
    root, outside = tmp_path / "project", tmp_path / "outside"
    (outside / "deep").mkdir(parents=True)
    (outside / "deep" / "f").write_text("keep", encoding="utf-8", newline="\n")
    (outside / "target").write_text("keep", encoding="utf-8", newline="\n")
    (root / ".git" / "hooks").mkdir(parents=True)
    (root / "Makefile").symlink_to(outside / "target")
    (root / "dangling").symlink_to(outside / "created")
    (root / "old").symlink_to(outside)
    (root / "scripts").symlink_to(outside / "deep")
    (root / "hooks").symlink_to(Path(".git", "hooks"))
    return root


def _files(top: Path) -> dict[str, str]:
    """Every regular file under `top` (symlinks not followed) and what it holds."""
    found = {}
    for where, _, names in os.walk(top):
        for path in (Path(where, name) for name in names):
            if not path.is_symlink():
                found[str(path.relative_to(top))] = path.read_text(encoding="utf-8")
    return found


@posix_only
@pytest.mark.parametrize(
    "change",
    [
        Change("Makefile", "updated", b"evil"),  # a symlinked file
        Change("dangling", "added", b"evil"),  # …that doesn't exist yet
        Change("scripts/new.sh", "added", b"evil"),  # in a symlinked folder
        Change("hooks/post-checkout", "added", b"evil"),  # into .git
        Change("old/deep/f", "removed"),  # removed through a symlinked folder
        Change("moved", "renamed", b"x", old="old/deep/f"),
        Change("../escaped", "added", b"evil"),
        Change("ABS", "added", b"evil"),
        Change("/ABS", "added", b"evil"),  # //…: still absolute
    ],
    ids=lambda c: c.path,
)
def test_apply_refuses_paths_that_leave_the_project(linked, tmp_path, change):
    if change.path.endswith("ABS"):
        change = Change(change.path.replace("ABS", str(tmp_path / "escaped")), change.kind, change.data)
    before = _files(tmp_path)
    with pytest.raises(RuntimeError, match="leads outside the project"):
        apply([Change("first", "added", b"x"), change], linked)
    assert _files(tmp_path) == before  # nothing written anywhere, not even `first`
    assert (linked / "old").is_symlink() and (linked / "scripts").is_symlink()


@posix_only
def test_apply_follows_symlinks_inside_the_project(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("old", encoding="utf-8", newline="\n")
    (tmp_path / "README.md").symlink_to(Path("docs", "README.md"))
    (tmp_path / "AGENTS.md").write_text("old", encoding="utf-8", newline="\n")
    (tmp_path / "CLAUDE.md").symlink_to(tmp_path / "AGENTS.md")  # absolute, still inside
    (tmp_path / "tools").mkdir()
    (tmp_path / "scripts").symlink_to("tools")
    apply(
        [
            Change("README.md", "updated", b"new"),
            Change("CLAUDE.md", "updated", b"agents"),
            Change("scripts/new.sh", "added", b"#!/bin/sh\n", executable=True),
        ],
        tmp_path,
    )
    assert (tmp_path / "docs" / "README.md").read_text(encoding="utf-8") == "new" and (tmp_path / "README.md").is_symlink()
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "agents" and (tmp_path / "CLAUDE.md").is_symlink()
    assert (tmp_path / "tools" / "new.sh").stat().st_mode & 0o111 and (tmp_path / "scripts").is_symlink()


@posix_only
def test_removing_a_symlink_removes_the_link_not_its_target(linked, tmp_path):
    (linked / "tools" / "deep").mkdir(parents=True)
    (linked / "tools" / "deep" / "old.sh").write_text("x", encoding="utf-8", newline="\n")
    (linked / "tools" / "keep.sh").write_text("x", encoding="utf-8", newline="\n")
    (linked / "bin").symlink_to("tools")
    before = _files(tmp_path)
    apply([Change("Makefile", "removed"), Change("bin/deep/old.sh", "removed")], linked)
    assert not (linked / "Makefile").is_symlink()
    assert (tmp_path / "outside" / "target").read_text(encoding="utf-8") == "keep"  # the link went, not what it pointed to
    assert not (linked / "tools" / "deep").exists() and (linked / "tools" / "keep.sh").exists()
    assert _files(tmp_path) == {k: v for k, v in before.items() if k != "project/tools/deep/old.sh"}


def test_cleanup_stops_at_the_project_root(tmp_path):
    root = tmp_path / "project"
    (root / "only").mkdir(parents=True)
    (root / "only" / "f").write_text("x", encoding="utf-8", newline="\n")
    apply([Change("only/f", "removed")], root)
    assert root.is_dir() and not any(root.iterdir())
