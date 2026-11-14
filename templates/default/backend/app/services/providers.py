"""Provider connections. Secrets are encrypted at rest and never returned."""

import json
from typing import Any

from app.core import crypto
from app.core.config import get_settings
from app.core.exceptions import Conflict, InternalError, NotFound, Unprocessable
from app.core.utils import dumps, loads, stamp, uid
from app.db.session import Connection, IntegrityError
from app.llm.backends import ModelSpec, default_catalog
from app.llm.client import CallFailed, list_models
from app.schemas.models import ProviderProbe, ProviderUpdate, ProviderWrite
from app.services import audit

CONNECTION_FIELDS = ("kind", "protocol", "base_url", "region")


def public(row: dict[str, Any]) -> dict[str, Any]:
    item = {k: v for k, v in row.items() if k != "encrypted_secret"}
    item["models"] = loads(row["models"], [])
    item["enabled"] = bool(row["enabled"])
    item["secret_configured"] = bool(row["encrypted_secret"])
    item["last_test_ok"] = None if row["last_test_ok"] is None else bool(row["last_test_ok"])
    item["catalog_id"] = row["catalog_id"] or default_catalog(row["kind"], row["base_url"])
    return item


def get_row(db: Connection, provider_id: str) -> dict[str, Any]:
    row = db.execute("SELECT * FROM fstack_providers WHERE id=?", (provider_id,)).fetchone()
    if not row:
        raise NotFound("Provider not found.")
    return dict(row)


def find_row(db: Connection, ref: str) -> dict[str, Any]:
    """A provider by id or by its name (what application code usually knows)."""
    row = db.execute(
        "SELECT * FROM fstack_providers WHERE id=? OR name=? LIMIT 1", (ref, ref)
    ).fetchone()
    if not row:
        raise NotFound(f"Provider '{ref}' not found.")
    return dict(row)


def list_providers(db: Connection) -> list[dict[str, Any]]:
    rows = db.execute("SELECT * FROM fstack_providers ORDER BY name").fetchall()
    return [public(dict(r)) for r in rows]


def _pack_secret(body: ProviderWrite) -> tuple[str, str] | None:
    if body.kind == "bedrock":
        if body.aws_access_key_id or body.aws_secret_access_key:
            if not (body.aws_access_key_id and body.aws_secret_access_key):
                raise Unprocessable("Enter both the AWS access key id and secret.")
            payload = {
                "aws_access_key_id": body.aws_access_key_id,
                "aws_secret_access_key": body.aws_secret_access_key,
            }
            return json.dumps(payload), crypto.hint(body.aws_access_key_id)
        return None
    if body.api_key:
        return json.dumps({"api_key": body.api_key}), crypto.hint(body.api_key)
    return None


def _encrypt(provider_id: str, packed: tuple[str, str] | None) -> tuple[str, str] | None:
    if not packed:
        return None
    try:
        return crypto.encrypt(packed[0], provider_id), packed[1]
    except crypto.SecretError as exc:
        raise InternalError(str(exc)) from exc


def secret_for(row: dict[str, Any]) -> dict[str, str]:
    if not row.get("encrypted_secret"):
        return {}
    try:
        return json.loads(crypto.decrypt(row["encrypted_secret"], row["id"]))
    except crypto.SecretError as exc:
        raise InternalError(str(exc)) from exc


def create(db: Connection, actor: dict[str, Any], body: ProviderWrite) -> dict[str, Any]:
    provider_id = uid()
    secret = _encrypt(provider_id, _pack_secret(body)) or ("", "")
    now = stamp()
    try:
        db.execute(
            "INSERT INTO fstack_providers (id, name, kind, protocol, base_url, region, catalog_id,"
            " models, encrypted_secret, secret_hint, enabled, revision, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
            (
                provider_id,
                body.name,
                body.kind,
                body.protocol,
                body.base_url,
                body.region,
                body.catalog_id,
                dumps(body.models),
                secret[0],
                secret[1],
                int(body.enabled),
                now,
                now,
            ),
        )
    except IntegrityError:
        raise Conflict("A provider with this name already exists.") from None
    audit.record(db, actor, provider_id, "provider.created", {"name": body.name})
    return public(get_row(db, provider_id))


def _keep_secret_for(row: dict[str, Any], body: ProviderWrite) -> None:
    """A stored key is only ever sent to the endpoint it was saved for. Otherwise an
    edit (or a connection test) could point it at another server and read it there."""
    if row["encrypted_secret"] and (row["kind"] != body.kind or row["base_url"] != body.base_url):
        raise Unprocessable("Re-enter the API key when changing the provider kind or base URL.")


def update(
    db: Connection, actor: dict[str, Any], provider_id: str, body: ProviderUpdate
) -> dict[str, Any]:
    row = get_row(db, provider_id)
    if row["revision"] != body.revision:
        raise Conflict("Someone else changed this provider. Reload and try again.")
    secret = _encrypt(provider_id, _pack_secret(body))
    if secret is None:
        _keep_secret_for(row, body)
    encrypted, hint = secret or (row["encrypted_secret"], row["secret_hint"])
    changed = secret is not None or any(row[f] != getattr(body, f) for f in CONNECTION_FIELDS)
    try:
        db.execute(
            "UPDATE fstack_providers SET name=?, kind=?, protocol=?, base_url=?, region=?,"
            " catalog_id=?, models=?, encrypted_secret=?, secret_hint=?, enabled=?,"
            " revision=revision+1, updated_at=?"
            + (", last_test_ok=NULL, last_tested_at=NULL" if changed else "")
            + " WHERE id=? AND revision=?",
            (
                body.name,
                body.kind,
                body.protocol,
                body.base_url,
                body.region,
                body.catalog_id,
                dumps(body.models),
                encrypted,
                hint,
                int(body.enabled),
                stamp(),
                provider_id,
                body.revision,
            ),
        )
    except IntegrityError:
        raise Conflict("A provider with this name already exists.") from None
    audit.record(db, actor, provider_id, "provider.updated", {"connection_changed": changed})
    return public(get_row(db, provider_id))


def delete(db: Connection, actor: dict[str, Any], provider_id: str) -> None:
    get_row(db, provider_id)  # call history keeps the provider's name
    db.execute("DELETE FROM fstack_providers WHERE id=?", (provider_id,))
    audit.record(db, actor, provider_id, "provider.deleted")


def spec_for(
    row: dict[str, Any],
    model: str,
    *,
    temperature: float | None,
    max_tokens: int | None,
    secret: dict[str, str] | None = None,
) -> ModelSpec:
    return ModelSpec(
        kind=row["kind"],
        protocol=row["protocol"],
        model=model,
        base_url=row["base_url"],
        region=row["region"],
        secret=secret if secret is not None else secret_for(row),
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=get_settings().llm_timeout_seconds,
    )


def probe_spec(db: Connection, body: ProviderProbe) -> tuple[ModelSpec, str | None]:
    """Spec for a connection test of a saved or unsaved provider (outside transactions)."""
    stored = get_row(db, body.provider_id) if body.provider_id else None
    packed = _pack_secret(body)
    if stored and not packed:
        _keep_secret_for(stored, body)
    secret = json.loads(packed[0]) if packed else (secret_for(stored) if stored else {})
    model = body.model
    row = {
        "kind": body.kind,
        "protocol": body.protocol,
        "base_url": body.base_url,
        "region": body.region,
    }
    spec = spec_for(row, model, temperature=None, max_tokens=16, secret=secret)
    return spec, stored["id"] if stored else None


def run_probe(spec: ModelSpec) -> dict[str, Any]:
    """Connection test = load the model list. Cheap, and it is what the pickers show."""
    try:
        catalog = list_models(spec)
    except CallFailed as failure:
        return {"ok": False, "latency_ms": failure.latency_ms, "message": failure.message}
    count = len(catalog.models)
    listed = f"{count} model{'' if count == 1 else 's'}" if count else "no models listed"
    return {
        "ok": True,
        "latency_ms": catalog.latency_ms,
        "message": f"Connected · {listed} · {catalog.latency_ms} ms",
        "models": catalog.models,
    }


def save_probe(db: Connection, actor: dict[str, Any], provider_id: str, result: dict) -> None:
    """Record the test; a successful one also refreshes the cached model list. Neither is
    an edit of the connection, so the revision stays (an open editor can still save)."""
    models = ", models=?" if result["ok"] else ""
    db.execute(
        "UPDATE fstack_providers SET last_tested_at=?, last_test_ok=?, last_test_ms=?,"
        f" last_test_message=?{models} WHERE id=?",
        (
            stamp(),
            int(result["ok"]),
            result["latency_ms"],
            result["message"][:500],
            *([dumps(result["models"])] if result["ok"] else []),
            provider_id,
        ),
    )
    audit.record(db, actor, provider_id, "provider.tested", {"ok": result["ok"]})
