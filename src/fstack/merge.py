"""Three-way merge of file trees: what changed in the template since a project was
made from it, applied to the project without undoing the project's own edits.

``base`` is the template as the project last got it, ``new`` the template now, and
``ours`` the project's tracked files at those paths. Files only the project has never
show up; files the project has but git doesn't track are never touched.
"""

from __future__ import annotations

import difflib
import os
import subprocess
import tempfile
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

# Like git's rename detection: a file the template removed and one it added count as a
# move when at least this similar (by lines). Tiny files are too alike to tell apart.
RENAME_SIMILARITY = 0.5
RENAME_MIN_LINES = 3


@dataclass(frozen=True)
class Entry:
    data: bytes
    executable: bool = False


Tree = dict[str, Entry]


@dataclass(frozen=True)
class Change:
    path: str
    # added | updated | merged | renamed | removed: applied cleanly
    # conflict: written with conflict markers (or, for binary files, not written)
    # skipped: the template changed it, the project deleted it (or git doesn't track it here)
    # kept: removed from the template, changed in the project
    kind: str
    data: bytes | None = None  # what to write; None leaves the file as it is
    executable: bool = False
    conflicts: int = 0
    note: str = ""
    old: str | None = None  # moved here from this path (removed once `path` is written)


def _same(a: Entry | None, b: Entry | None) -> bool:
    if a is None or b is None:
        return a is b
    return a.data == b.data


def _binary(*entries: Entry | None) -> bool:
    return any(e is not None and b"\0" in e.data for e in entries)


def _executable(b: Entry | None, n: Entry, o: Entry | None) -> bool:
    """The template's mode only when the template changed it; otherwise the project's."""
    if o is None or (b is not None and b.executable != n.executable):
        return n.executable
    return o.executable


def _similarity(a: bytes, b: bytes) -> float:
    if b"\0" in a or b"\0" in b:
        return 1.0 if a == b else 0.0
    lines_a, lines_b = a.splitlines(), b.splitlines()
    if min(len(lines_a), len(lines_b)) < RENAME_MIN_LINES:
        return 0.0
    matcher = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)
    return matcher.ratio() if matcher.real_quick_ratio() >= RENAME_SIMILARITY else 0.0


def renames(base: Tree, new: Tree, existing: Collection[str]) -> dict[str, str]:
    """new path → old path for the files the template moved (onto paths the project doesn't use)."""
    gone = sorted(p for p in base if p not in new)
    moved: dict[str, str] = {}
    for path in sorted(p for p in new if p not in base and p not in existing):
        scored = [(_similarity(base[old].data, new[path].data), old) for old in gone if old not in moved.values()]
        score, old = max(scored, default=(0.0, ""))
        if score >= RENAME_SIMILARITY:
            moved[path] = old
    return moved


def merge_file(ours: bytes, base: bytes, theirs: bytes, labels: tuple[str, str, str]) -> tuple[bytes, int]:
    """`git merge-file`: the merged bytes and how many conflicts it marked."""
    with tempfile.TemporaryDirectory(prefix="fstack-merge-") as tmp:
        paths = []
        for name, data in (("ours", ours), ("base", base), ("theirs", theirs)):
            path = Path(tmp) / name
            path.write_bytes(data)
            paths.append(str(path))
        cmd = ["git", "merge-file", "-p"]
        for label in labels:
            cmd += ["-L", label]
        proc = subprocess.run([*cmd, *paths], capture_output=True)
    if proc.returncode > 127:  # 0..127 = number of conflicts, anything else = error
        raise RuntimeError(proc.stderr.decode(errors="replace").strip() or "git merge-file failed")
    return proc.stdout, proc.returncode


def plan(
    base: Tree,
    new: Tree,
    ours: Tree,
    labels: tuple[str, str, str],
    untracked: Collection[str] = frozenset(),
) -> list[Change]:
    moved = renames(base, new, ours.keys() | set(untracked))
    moved_from = set(moved.values())
    changes: list[Change] = []
    for path in sorted(base.keys() | new.keys()):
        if path in moved_from:
            continue  # handled at its new path
        old = moved.get(path)
        b, n, o = base.get(old or path), new.get(path), ours.get(old or path)
        if not old and _same(b, n):
            continue  # the template didn't touch it
        if path in untracked or old in untracked:
            changes.append(Change(path, "skipped", note="exists here but git doesn't track it: left alone"))
            continue
        if n is None:  # the template removed it
            if o is None:
                continue
            if _same(o, b):
                changes.append(Change(path, "removed"))
            else:
                changes.append(Change(path, "kept", note="removed from the template, changed here"))
            continue
        if o is None:
            if b is None:
                changes.append(Change(path, "added", n.data, n.executable))
            else:
                where = f"moved from {old} in the template" if old else "changed in the template"
                changes.append(Change(path, "skipped", note=f"{where}, deleted here"))
            continue
        if not old and _same(o, n):
            continue  # already there
        executable = _executable(b, n, o)
        if _same(o, b):
            changes.append(Change(path, "renamed" if old else "updated", n.data, executable, old=old))
            continue
        if _binary(b, n, o):
            note = "binary, changed on both sides: kept yours" + (f" at {old}" if old else "")
            changes.append(Change(path, "conflict", conflicts=1, note=note))
            continue
        merged, conflicts = merge_file(o.data, b.data if b else b"", n.data, labels)
        kind = "conflict" if conflicts else "merged"
        changes.append(Change(path, kind, merged, executable, conflicts, old=old))
    return changes


def resolve(root: Path, rel: str, *, follow: bool = True) -> Path:
    """Where `rel` really is under `root`, symlinks resolved (all but the last component
    when not `follow`ing, so it names the link itself). A project's symlinks may come from
    a cloned repo: refuse one that leads outside `root`, or into its .git."""
    path = root / rel
    real = Path(os.path.realpath(path)) if follow else Path(os.path.realpath(path.parent), path.name)
    top = root.resolve()
    if top not in real.parents or real.name in ("", ".", "..") or _in_git_dir(top, real):
        raise RuntimeError(f"{rel} leads outside the project (to {real}): refusing to follow it")
    return real


def _in_git_dir(top: Path, real: Path) -> bool:
    first = top / real.relative_to(top).parts[0]
    try:
        return os.path.samestat(first.lstat(), (top / ".git").lstat())
    except OSError:
        return False


def write(root: Path, rel: str, data: bytes, executable: bool | None = None) -> None:
    """Write `rel` under `root`, through symlinks only when they stay in the project.
    `executable` sets or clears the x bits; None leaves the mode as it is."""
    target = resolve(root, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o666)
    with open(fd, "wb") as f:
        f.write(data)
        if executable is not None:
            mode = os.fstat(fd).st_mode
            os.fchmod(fd, mode | 0o111 if executable else mode & ~0o111)


def _remove(root: Path, rel: str) -> None:
    target = resolve(root, rel, follow=False)
    target.unlink(missing_ok=True)
    top = root.resolve()
    parent = target.parent
    while parent != top and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def apply(changes: list[Change], root: Path) -> None:
    # Check every path first, so a refusal leaves the project as it was.
    for change in changes:
        if change.kind == "removed":
            resolve(root, change.path, follow=False)
        elif change.data is not None:
            resolve(root, change.path)
            if change.old:
                resolve(root, change.old, follow=False)
    for change in changes:
        if change.kind == "removed":
            _remove(root, change.path)
        elif change.data is not None:
            write(root, change.path, change.data, change.executable)
            if change.old:
                _remove(root, change.old)
