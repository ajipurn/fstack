"""Prompt versioning.

A prompt has numbered versions: at most one `draft` (editable, autosaved),
any number of `published` (immutable, digest-stamped) and `retired`. The
prompt's `active_version_id` is what runs use by default; rolling back is pointing it at
an older published version. Every llm_call records the version id + digest.
"""

import hashlib
import re
from pathlib import Path
from typing import Any

from app.core.exceptions import Conflict, NotFound, Unprocessable
from app.core.utils import dumps, loads, stamp, uid
from app.db.session import Connection, IntegrityError
from app.llm.outputs import OUTPUTS
from app.llm.templates import check_template, placeholders
from app.schemas.models import DraftSave, PromptCreate, PromptMeta, Publish
from app.services import audit


def digest(system: str, user_template: str) -> str:
    payload = dumps({"system": system, "user_template": user_template})
    return hashlib.sha256(payload.encode()).hexdigest()


def _version(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item.pop("draft_key", None)
    item["variables"] = loads(row["variables"], [])
    return item


def get_prompt_row(db: Connection, key: str) -> dict[str, Any]:
    row = db.execute("SELECT * FROM prompts WHERE `key`=?", (key,)).fetchone()
    if not row:
        raise NotFound(f"Prompt '{key}' not found.")
    return dict(row)


def list_prompts(db: Connection) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT p.*, av.version AS active_version, av.digest AS active_digest,"
        " (SELECT COUNT(*) FROM prompt_versions v WHERE v.prompt_key=p.`key`"
        "  AND v.status <> 'draft') AS published_count,"
        " (SELECT COUNT(*) FROM prompt_versions v WHERE v.prompt_key=p.`key`"
        "  AND v.status = 'draft') AS has_draft"
        " FROM prompts p LEFT JOIN prompt_versions av ON av.id = p.active_version_id"
        " ORDER BY p.name"
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["has_draft"] = bool(item["has_draft"])
        item["structured"] = item["key"] in OUTPUTS
        out.append(item)
    return out


def get_prompt(db: Connection, key: str) -> dict[str, Any]:
    prompt = get_prompt_row(db, key)
    versions = db.execute(
        "SELECT v.*,"
        " (SELECT COUNT(*) FROM llm_calls c WHERE c.prompt_version_id = v.id) AS call_count"
        " FROM prompt_versions v WHERE v.prompt_key=? ORDER BY v.version DESC",
        (key,),
    ).fetchall()
    output = OUTPUTS.get(key)
    return {
        **prompt,
        "versions": [_version(v) for v in versions],
        "structured": output is not None,
        "output_schema": output.model_json_schema() if output else None,
    }


def _next_version(db: Connection, key: str) -> int:
    current = db.execute(
        "SELECT MAX(version) FROM prompt_versions WHERE prompt_key=?", (key,)
    ).scalar()
    return int(current or 0) + 1


def _insert_version(
    db: Connection,
    key: str,
    *,
    system: str,
    user_template: str,
    note: str,
    status: str,
    source: str,
    actor: dict[str, Any] | None,
) -> str:
    version_id = uid()
    db.execute(
        "INSERT INTO prompt_versions (id, prompt_key, version, status, `system`, user_template,"
        " variables, note, source, digest, revision, created_by, created_at, published_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?,?)",
        (
            version_id,
            key,
            _next_version(db, key),
            status,
            system,
            user_template,
            dumps(placeholders(system, user_template)),
            note,
            source,
            digest(system, user_template),
            (actor or {}).get("id"),
            stamp(),
            stamp() if status == "published" else None,
        ),
    )
    return version_id


def create(db: Connection, actor: dict[str, Any], body: PromptCreate) -> dict[str, Any]:
    now = stamp()
    try:
        db.execute(
            "INSERT INTO prompts (`key`, name, description, active_version_id, revision,"
            " created_at, updated_at) VALUES (?,?,?,NULL,1,?,?)",
            (body.key, body.name, body.description, now, now),
        )
    except IntegrityError:
        raise Conflict(f"Prompt key '{body.key}' is taken.") from None
    _insert_version(
        db,
        body.key,
        system=body.system,
        user_template=body.user_template,
        note=body.note or "Initial draft",
        status="draft",
        source="ui",
        actor=actor,
    )
    audit.record(db, actor, f"prompt:{body.key}", "prompt.created")
    return get_prompt(db, body.key)


def update_meta(db: Connection, actor: dict[str, Any], key: str, body: PromptMeta) -> dict:
    changed = db.execute(
        "UPDATE prompts SET name=?, description=?, revision=revision+1, updated_at=?"
        " WHERE `key`=? AND revision=?",
        (body.name, body.description, stamp(), key, body.revision),
    ).rowcount
    if not changed:
        get_prompt_row(db, key)
        raise Conflict("The prompt changed. Reload and try again.")
    return get_prompt(db, key)


def _draft(db: Connection, key: str) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT * FROM prompt_versions WHERE prompt_key=? AND status='draft'", (key,)
    ).fetchone()
    return dict(row) if row else None


def start_draft(
    db: Connection, actor: dict[str, Any], key: str, from_version_id: str | None
) -> dict[str, Any]:
    prompt = get_prompt_row(db, key)
    if _draft(db, key):
        raise Conflict("This prompt already has a draft.")
    source_id = from_version_id or prompt["active_version_id"]
    base = None
    if source_id:
        base = db.execute(
            "SELECT * FROM prompt_versions WHERE id=? AND prompt_key=?", (source_id, key)
        ).fetchone()
    if not base:
        base = db.execute(
            "SELECT * FROM prompt_versions WHERE prompt_key=? ORDER BY version DESC LIMIT 1",
            (key,),
        ).fetchone()
    if not base:
        raise Unprocessable("Nothing to copy from.")
    try:
        _insert_version(
            db,
            key,
            system=base["system"],
            user_template=base["user_template"],
            note="",
            status="draft",
            source="ui",
            actor=actor,
        )
    except IntegrityError:
        raise Conflict("This prompt already has a draft.") from None
    return get_prompt(db, key)


def save_draft(db: Connection, actor: dict[str, Any], key: str, body: DraftSave) -> dict:
    draft = _draft(db, key)
    if not draft:
        raise NotFound("No draft to save. Start a new draft first.")
    changed = db.execute(
        "UPDATE prompt_versions SET `system`=?, user_template=?, variables=?, note=?, digest=?,"
        " revision=revision+1 WHERE id=? AND status='draft' AND revision=?",
        (
            body.system,
            body.user_template,
            dumps(body.variables),
            body.note,
            digest(body.system, body.user_template),
            draft["id"],
            body.revision,
        ),
    ).rowcount
    if not changed:
        raise Conflict("The draft was changed elsewhere. Reload to continue.")
    return _version(
        dict(
            db.execute("SELECT * FROM prompt_versions WHERE id=?", (draft["id"],)).fetchone() or {}
        )
    )


def discard_draft(db: Connection, actor: dict[str, Any], key: str) -> None:
    draft = _draft(db, key)
    if not draft:
        raise NotFound("No draft to discard.")
    db.execute("DELETE FROM prompt_versions WHERE id=?", (draft["id"],))
    audit.record(db, actor, f"prompt:{key}", "prompt.draft_discarded")


def delete(db: Connection, actor: dict[str, Any], key: str) -> dict[str, Any]:
    """Remove a prompt and all its versions. Call history keeps the prompt key.
    A prompt that still has `prompts/<key>.md` comes back on the next `make seed`."""
    get_prompt_row(db, key)
    versions = db.execute("DELETE FROM prompt_versions WHERE prompt_key=?", (key,)).rowcount
    db.execute("DELETE FROM prompts WHERE `key`=?", (key,))
    audit.record(db, actor, f"prompt:{key}", "prompt.deleted", {"versions": versions})
    return {"key": key, "versions": versions}


def publish(db: Connection, actor: dict[str, Any], key: str, body: Publish) -> dict[str, Any]:
    draft = _draft(db, key)
    if not draft or draft["revision"] != body.revision:
        raise Conflict("The draft changed or was already published. Reload first.")
    check_template(draft["system"])
    check_template(draft["user_template"])
    if not draft["user_template"].strip():
        raise Unprocessable("A published version needs a user template.")
    stamped = digest(draft["system"], draft["user_template"])
    duplicate = db.execute(
        "SELECT version FROM prompt_versions WHERE prompt_key=? AND digest=? AND status <> 'draft'",
        (key, stamped),
    ).fetchone()
    if duplicate:
        raise Conflict(f"Identical to v{duplicate['version']}. Activate that version instead.")
    db.execute(
        "UPDATE prompt_versions SET status='published', digest=?, note=?, published_at=?,"
        " revision=revision+1 WHERE id=?",
        (stamped, body.note or draft["note"], stamp(), draft["id"]),
    )
    if body.activate:
        _activate(db, key, draft["id"])
    audit.record(
        db,
        actor,
        f"prompt:{key}",
        "prompt.published",
        {"version": draft["version"], "digest": stamped, "activated": body.activate},
    )
    return get_prompt(db, key)


def _activate(db: Connection, key: str, version_id: str) -> None:
    db.execute(
        "UPDATE prompts SET active_version_id=?, revision=revision+1, updated_at=? WHERE `key`=?",
        (version_id, stamp(), key),
    )


def activate(db: Connection, actor: dict[str, Any], key: str, version_id: str) -> dict:
    get_prompt_row(db, key)
    row = db.execute(
        "SELECT version, status FROM prompt_versions WHERE id=? AND prompt_key=?",
        (version_id, key),
    ).fetchone()
    if not row:
        raise NotFound("Version not found.")
    if row["status"] != "published":
        raise Unprocessable("Only published versions can be activated.")
    _activate(db, key, version_id)
    audit.record(db, actor, f"prompt:{key}", "prompt.activated", {"version": row["version"]})
    return get_prompt(db, key)


# ── prompts-as-code: backend/prompts/*.md ────────────────────────────────────

_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)
_SECTION = re.compile(r"<!--\s*(system|user)\s*-->", re.I)


def parse_prompt_file(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = _FRONT.match(text)
    if not match:
        raise ValueError(f"{path.name}: missing --- frontmatter ---")
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            name, value = line.split(":", 1)
            meta[name.strip()] = value.strip().strip("\"'")
    sections: dict[str, str] = {"system": "", "user": ""}
    parts = _SECTION.split(match.group(2))
    for marker, content in zip(parts[1::2], parts[2::2], strict=True):
        sections[marker.lower()] = content.strip()
    if not sections["user"]:
        raise ValueError(f"{path.name}: needs a <!-- user --> section")
    for template in sections.values():
        check_template(template)
    return {
        "key": meta.get("key") or path.stem,
        "name": meta.get("name") or path.stem.replace("-", " ").title(),
        "description": meta.get("description", ""),
        "system": sections["system"],
        "user_template": sections["user"],
    }


def sync_files(db: Connection, directory: Path) -> list[str]:
    """New prompt → v1 published + active. Changed file → a new *draft* (review first)."""
    report = []
    for path in sorted(directory.glob("*.md")):
        spec = parse_prompt_file(path)
        key = spec["key"]
        stamped = digest(spec["system"], spec["user_template"])
        existing = db.execute("SELECT `key` FROM prompts WHERE `key`=?", (key,)).fetchone()
        if not existing:
            now = stamp()
            db.execute(
                "INSERT INTO prompts (`key`, name, description, active_version_id, revision,"
                " created_at, updated_at) VALUES (?,?,?,NULL,1,?,?)",
                (key, spec["name"], spec["description"], now, now),
            )
            version_id = _insert_version(
                db,
                key,
                system=spec["system"],
                user_template=spec["user_template"],
                note=f"From {path.name}",
                status="published",
                source="file",
                actor=None,
            )
            _activate(db, key, version_id)
            report.append(f"{key}: created v1")
            continue
        known = db.execute(
            "SELECT version FROM prompt_versions WHERE prompt_key=? AND digest=?", (key, stamped)
        ).fetchone()
        if known:
            continue
        if _draft(db, key):
            report.append(f"{key}: file changed, but a draft exists — left alone")
            continue
        _insert_version(
            db,
            key,
            system=spec["system"],
            user_template=spec["user_template"],
            note=f"From {path.name}",
            status="draft",
            source="file",
            actor=None,
        )
        report.append(f"{key}: file changed → new draft (publish it in the UI)")
    return report
