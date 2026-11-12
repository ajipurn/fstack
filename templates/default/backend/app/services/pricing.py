"""Model prices from models.dev (USD per 1M tokens) and per-call cost.

`fstack_model_prices` holds only the catalogs in use: the first-party ones (the fallback
for gateways and "best match" providers) plus each provider's own. `uv run tasks.py
prices` (or the Models page) refreshes them; saving a provider brings in its catalog
when it isn't loaded yet. Rows with source='manual' are yours and never overwritten.
Cost is computed once, at call time, and stored on fstack_llm_calls with the rates used —
history never re-prices.
"""

import re
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import ProviderError, Unprocessable
from app.core.utils import dumps, loads, stamp
from app.db.session import Connection
from app.llm.backends import DEFAULT_CATALOG, Usage

FIRST_PARTY = ("openai", "anthropic", "google", "amazon-bedrock", "mistral", "xai", "deepseek")
_BEDROCK_PROFILE = re.compile(r"^(?:us|eu|apac|au|ca|jp|global|us-gov)\.")


@dataclass(frozen=True)
class Rates:
    catalog_id: str
    model_id: str
    input: float | None
    output: float | None
    cache_read: float | None = None
    cache_write: float | None = None
    tiers: tuple[dict[str, Any], ...] = ()
    source: str = "models.dev"
    output_limit: int | None = None  # the model's max output tokens, when known

    @property
    def priced(self) -> bool:
        return self.input is not None and self.output is not None

    def snapshot(self) -> dict[str, Any]:
        data = asdict(self)
        data["tiers"] = list(self.tiers)
        return data


def _rates(row: dict[str, Any]) -> Rates:
    return Rates(
        catalog_id=row["catalog_id"],
        model_id=row["model_id"],
        input=row["input"],
        output=row["output"],
        cache_read=row["cache_read"],
        cache_write=row["cache_write"],
        tiers=tuple(loads(row["tiers"], []) or []),
        source=row["source"],
        output_limit=row["output_limit"],
    )


def find_rates(db: Connection, catalog_id: str, model: str) -> Rates | None:
    """Exact match first, then progressively looser matches. None = unpriced."""
    candidates = [(catalog_id, model)]
    stripped = _BEDROCK_PROFILE.sub("", model)
    if stripped != model:
        candidates.append((catalog_id, stripped))
    for catalog, model_id in candidates:
        if not catalog:
            continue
        row = db.execute(
            "SELECT * FROM fstack_model_prices WHERE catalog_id=? AND model_id=?",
            (catalog, model_id),
        ).fetchone()
        if row and row["input"] is not None:
            return _rates(row)
    # Same model id published by a first-party catalog (e.g. a proxy serving gpt-5.4),
    # or the id after the vendor prefix ("openai/gpt-5.4" on OpenRouter-style gateways).
    names = {stripped, stripped.rsplit("/", 1)[-1]}
    rows = [
        row
        for name in names
        for row in db.execute(
            "SELECT * FROM fstack_model_prices WHERE model_id=? AND input IS NOT NULL", (name,)
        ).fetchall()
    ]
    rows.sort(key=lambda r: (r["catalog_id"] not in FIRST_PARTY, r["catalog_id"]))
    return _rates(rows[0]) if rows else None


def _tier(rates: Rates, input_tokens: int) -> dict[str, Any]:
    chosen: dict[str, Any] = {
        "input": rates.input,
        "output": rates.output,
        "cache_read": rates.cache_read,
        "cache_write": rates.cache_write,
    }
    best = 0
    for tier in rates.tiers:
        size = int((tier.get("tier") or {}).get("size") or 0)
        if input_tokens > size > best:
            best = size
            chosen = {k: tier.get(k, chosen[k]) for k in chosen}
    return chosen


def cost_usd(rates: Rates | None, usage: Usage) -> float | None:
    """USD for one call. Cache tokens bill at their own rate (input rate if unknown)."""
    if rates is None or not rates.priced:
        return None
    price = _tier(rates, usage.input_tokens)
    per = 1_000_000
    read_rate = price["cache_read"] if price["cache_read"] is not None else price["input"]
    write_rate = price["cache_write"] if price["cache_write"] is not None else price["input"]
    uncached = max(0, usage.input_tokens - usage.cache_read_tokens - usage.cache_write_tokens)
    total = (
        uncached * price["input"]
        + usage.cache_read_tokens * read_rate
        + usage.cache_write_tokens * write_rate
        + usage.output_tokens * price["output"]
    ) / per
    return round(total, 10)


# ── models.dev sync ──────────────────────────────────────────────────────────


def fetch_catalog(url: str | None = None) -> dict[str, Any]:
    url = url or get_settings().models_dev_url
    try:
        response = httpx.get(url, timeout=httpx.Timeout(30, connect=10), follow_redirects=True)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError(f"Could not download prices from {url}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProviderError("models.dev returned an unexpected payload.")
    return data


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if value >= 0 else None


def catalogs_in_use(db: Connection) -> set[str]:
    """First-party catalogs (find_rates falls back to them) and every provider's own."""
    used = set(FIRST_PARTY)
    for row in db.execute("SELECT kind, catalog_id FROM fstack_providers").fetchall():
        used.add(row["catalog_id"] or DEFAULT_CATALOG.get(row["kind"], ""))
    used.discard("")
    return used


def missing_catalogs(db: Connection) -> set[str]:
    """Catalogs in use that have no models.dev rows yet."""
    loaded = db.execute(
        "SELECT DISTINCT catalog_id FROM fstack_model_prices WHERE source='models.dev'"
    ).fetchall()
    return catalogs_in_use(db) - {row["catalog_id"] for row in loaded}


def catalog_rows(data: dict[str, Any], catalogs: set[str] | None = None) -> list[tuple[Any, ...]]:
    rows = []
    now = stamp()
    for catalog_id, provider in data.items():
        if catalogs is not None and catalog_id not in catalogs:
            continue
        models = (provider or {}).get("models") or {}
        if not isinstance(models, dict):
            continue
        for model_id, model in models.items():
            if not isinstance(model, dict):
                continue
            cost = model.get("cost") or {}
            limit = model.get("limit") or {}
            tiers = [t for t in cost.get("tiers") or [] if isinstance(t, dict)]
            rows.append(
                (
                    str(catalog_id)[:80],
                    str(model_id)[:200],
                    str(model.get("name") or model_id)[:200],
                    _number(cost.get("input")),
                    _number(cost.get("output")),
                    _number(cost.get("cache_read")),
                    _number(cost.get("cache_write")),
                    dumps(tiers) if tiers else None,
                    int(limit["context"]) if isinstance(limit.get("context"), int) else None,
                    int(limit["output"]) if isinstance(limit.get("output"), int) else None,
                    1 if model.get("reasoning") else 0,
                    now,
                )
            )
    return rows


def sync_catalog(
    db: Connection, data: dict[str, Any], only: set[str] | None = None
) -> dict[str, int]:
    """Load models.dev rows for the catalogs in use, replacing the ones there; catalogs
    no provider uses any more are dropped. `only` loads just those catalogs and leaves
    the rest alone. Manual overrides are never touched."""
    rows = catalog_rows(data, catalogs_in_use(db) if only is None else only)
    if not rows and only is None:
        raise Unprocessable("The models.dev payload had none of the catalogs in use.")
    manual = {
        (r["catalog_id"], r["model_id"])
        for r in db.execute(
            "SELECT catalog_id, model_id FROM fstack_model_prices WHERE source='manual'"
        ).fetchall()
    }
    if only is None:
        db.execute("DELETE FROM fstack_model_prices WHERE source='models.dev'")
    elif only:
        db.execute(
            "DELETE FROM fstack_model_prices WHERE source='models.dev'"
            f" AND catalog_id IN ({','.join('?' * len(only))})",
            sorted(only),
        )
    fresh = [row for row in rows if (row[0], row[1]) not in manual]
    db.executemany(
        "INSERT INTO fstack_model_prices (catalog_id, model_id, name, input, output, cache_read,"
        " cache_write, tiers, context_limit, output_limit, reasoning, source, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,'models.dev',?)",
        fresh,
    )
    return {
        "models": len(fresh),
        "catalogs": len({row[0] for row in fresh}),
        "manual_kept": len(manual),
    }


def set_manual_price(
    db: Connection, catalog_id: str, model_id: str, rates: dict[str, float | None], name: str = ""
) -> None:
    db.execute(
        "DELETE FROM fstack_model_prices WHERE catalog_id=? AND model_id=?", (catalog_id, model_id)
    )
    db.execute(
        "INSERT INTO fstack_model_prices (catalog_id, model_id, name, input, output, cache_read,"
        " cache_write, tiers, context_limit, output_limit, reasoning, source, updated_at)"
        " VALUES (?,?,?,?,?,?,?,NULL,NULL,NULL,0,'manual',?)",
        (
            catalog_id,
            model_id,
            name or model_id,
            rates.get("input"),
            rates.get("output"),
            rates.get("cache_read"),
            rates.get("cache_write"),
            stamp(),
        ),
    )


def catalog_summary(db: Connection) -> dict[str, Any]:
    row = db.execute(
        "SELECT COUNT(*) AS models, COUNT(DISTINCT catalog_id) AS catalogs,"
        " MAX(updated_at) AS updated_at FROM fstack_model_prices"
    ).fetchone()
    return dict(row or {"models": 0, "catalogs": 0, "updated_at": None})


def list_catalogs(db: Connection) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in db.execute(
            "SELECT catalog_id, COUNT(*) AS models FROM fstack_model_prices"
            " GROUP BY catalog_id ORDER BY catalog_id"
        ).fetchall()
    ]


def search_models(
    db: Connection, catalog_id: str = "", query: str = "", limit: int = 100
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM fstack_model_prices WHERE 1=1"
    values: list[Any] = []
    if catalog_id:
        sql += " AND catalog_id=?"
        values.append(catalog_id)
    if query:
        sql += " AND (LOWER(model_id) LIKE ? OR LOWER(name) LIKE ?)"
        needle = f"%{query.lower()}%"
        values += [needle, needle]
    sql += " ORDER BY catalog_id, model_id LIMIT ?"
    values.append(max(1, min(limit, 500)))
    out = []
    for row in db.execute(sql, values).fetchall():
        item = dict(row)
        item["tiers"] = loads(item["tiers"], [])
        item["reasoning"] = bool(item["reasoning"])
        out.append(item)
    return out
