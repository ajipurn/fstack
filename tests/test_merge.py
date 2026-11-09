from fstack.merge import Change, Entry, apply, plan

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
    (tmp_path / "old" / "deep" / "f").write_text("x")
    apply(
        [
            Change("old/deep/f", "removed"),
            Change("bin/run.sh", "added", b"#!/bin/sh\n", executable=True),
            Change("skip", "skipped"),
        ],
        tmp_path,
    )
    assert not (tmp_path / "old").exists()
    assert (tmp_path / "bin" / "run.sh").stat().st_mode & 0o111
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
    (tmp_path / "old").write_text(TEXT)
    apply([change], tmp_path)
    assert not (tmp_path / "old").exists() and (tmp_path / "new").read_text() == TEXT


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
