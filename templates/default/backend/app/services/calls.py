"""llm_calls: one row per provider request — the observability source of truth."""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import get_settings
from app.core.utils import dumps, loads, stamp, uid
from app.db.session import Connection
from app.llm.backends import Usage
from app.services.pricing import Rates


def json_list(value: str | None) -> list[Any]:
    data = loads(value, [])
    return data if isinstance(data, list) else []


def record(
    db: Connection,
    *,
    provider: dict[str, Any],
    model: str,
    prompt_key: str,
    version: dict[str, Any] | None,
    usage: Usage,
    cost_usd: float | None,
    rates: Rates | None,
    latency_ms: int,
    status: str,
    error: str | None = None,
    source: str = "api",
    user_id: str | None = None,
    job_id: str | None = None,
    request: dict[str, str] | None = None,
    response: str | None = None,
) -> str:
    keep = get_settings().log_llm_payloads
    call_id = uid()
    db.execute(
        "INSERT INTO llm_calls (id, provider_id, provider_name, provider_kind, model,"
        " prompt_key, prompt_version_id, prompt_version, prompt_digest, status, error,"
        " input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd, pricing,"
        " latency_ms, source, job_id, user_id, request, response, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            call_id,
            provider.get("id"),
            provider.get("name", ""),
            provider.get("kind", ""),
            model,
            prompt_key,
            version["id"] if version else None,
            version["version"] if version else None,
            version["digest"] if version else None,
            status,
            (error or "")[:1000] or None,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_tokens,
            usage.cache_write_tokens,
            cost_usd,
            dumps(rates.snapshot()) if rates else None,
            latency_ms,
            source,
            job_id,
            user_id,
            dumps(request) if keep and request else None,
            response if keep else None,
            stamp(),
        ),
    )
    return call_id


def _since(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="milliseconds")


def _percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def summary(db: Connection, days: int = 30) -> dict[str, Any]:
    since = _since(days)
    totals = db.execute(
        "SELECT COUNT(*) AS calls,"
        " SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors,"
        " COALESCE(SUM(input_tokens),0) AS input_tokens,"
        " COALESCE(SUM(output_tokens),0) AS output_tokens,"
        " COALESCE(SUM(cache_read_tokens),0) AS cache_read_tokens,"
        " COALESCE(SUM(cost_usd),0) AS cost_usd,"
        " SUM(CASE WHEN cost_usd IS NULL THEN 1 ELSE 0 END) AS unpriced"
        " FROM llm_calls WHERE created_at >= ?",
        (since,),
    ).fetchone()
    latencies = [
        r["latency_ms"]
        for r in db.execute(
            "SELECT latency_ms FROM llm_calls WHERE created_at >= ? AND status='ok'"
            " ORDER BY created_at DESC LIMIT 5000",
            (since,),
        ).fetchall()
    ]
    group = (
        "COUNT(*) AS calls, COALESCE(SUM(cost_usd),0) AS cost_usd,"
        " COALESCE(SUM(input_tokens + output_tokens),0) AS tokens,"
        " SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors,"
        " COALESCE(AVG(latency_ms),0) AS avg_latency_ms"
    )
    by_day = db.execute(
        f"SELECT SUBSTR(created_at, 1, 10) AS day, {group} FROM llm_calls"
        " WHERE created_at >= ? GROUP BY SUBSTR(created_at, 1, 10) ORDER BY day",
        (since,),
    ).fetchall()
    by_model = db.execute(
        f"SELECT model, provider_name, {group} FROM llm_calls WHERE created_at >= ?"
        " GROUP BY model, provider_name ORDER BY cost_usd DESC, calls DESC LIMIT 20",
        (since,),
    ).fetchall()
    by_prompt = db.execute(
        f"SELECT prompt_key, {group} FROM llm_calls WHERE created_at >= ?"
        " GROUP BY prompt_key ORDER BY cost_usd DESC, calls DESC LIMIT 20",
        (since,),
    ).fetchall()
    calls = int(totals["calls"] or 0)
    return {
        "days": days,
        "since": since,
        "generated_at": stamp(),
        "totals": {
            "calls": calls,
            "errors": int(totals["errors"] or 0),
            "error_rate": (int(totals["errors"] or 0) / calls) if calls else 0,
            "input_tokens": int(totals["input_tokens"]),
            "output_tokens": int(totals["output_tokens"]),
            "cache_read_tokens": int(totals["cache_read_tokens"]),
            "cost_usd": float(totals["cost_usd"] or 0),
            "unpriced_calls": int(totals["unpriced"] or 0),
            "p50_latency_ms": _percentile(latencies, 0.5),
            "p95_latency_ms": _percentile(latencies, 0.95),
        },
        "by_day": _fill_days([dict(r) for r in by_day], days),
        "by_model": [_num(dict(r)) for r in by_model],
        "by_prompt": [_num(dict(r)) for r in by_prompt],
    }


def _num(row: dict[str, Any]) -> dict[str, Any]:
    for k in ("cost_usd", "avg_latency_ms"):
        row[k] = float(row[k] or 0)
    for k in ("calls", "tokens", "errors"):
        row[k] = int(row[k] or 0)
    return row


def _fill_days(rows: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    """Zero-filled series so charts don't skip quiet days."""
    seen = {r["day"]: _num(r) for r in rows}
    today = datetime.now(UTC).date()
    out = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        out.append(
            seen.get(day)
            or {
                "day": day,
                "calls": 0,
                "cost_usd": 0.0,
                "tokens": 0,
                "errors": 0,
                "avg_latency_ms": 0.0,
            }
        )
    return out


def recent(
    db: Connection, *, limit: int = 50, prompt_key: str = "", status: str = "", before: str = ""
) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, provider_name, provider_kind, model, prompt_key, prompt_version,"
        " status, error, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,"
        " cost_usd, latency_ms, source, job_id, created_at FROM llm_calls WHERE 1=1"
    )
    values: list[Any] = []
    if prompt_key:
        sql += " AND prompt_key=?"
        values.append(prompt_key)
    if status in ("ok", "error"):
        sql += " AND status=?"
        values.append(status)
    if before:
        sql += " AND created_at < ?"
        values.append(before)
    sql += " ORDER BY created_at DESC LIMIT ?"
    values.append(max(1, min(limit, 200)))
    return [dict(r) for r in db.execute(sql, values).fetchall()]


def clear(db: Connection) -> int:
    """Delete every recorded call (tokens, cost, payloads). Returns how many."""
    return db.execute("DELETE FROM llm_calls").rowcount


def detail(db: Connection, call_id: str) -> dict[str, Any] | None:
    row = db.execute("SELECT * FROM llm_calls WHERE id=?", (call_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["pricing"] = loads(item["pricing"])
    item["request"] = loads(item["request"])
    return item
