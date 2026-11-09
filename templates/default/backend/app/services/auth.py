"""Access-key auth: one key (APP_ACCESS_KEY) opens the dashboard and the API.

- Browser: POST /api/auth/login with the key → a random session token in an HttpOnly
  cookie (stored hashed) + a per-session CSRF token. The key never lives in the browser.
- API clients: `Authorization: Bearer <key>` on every request; no cookie, no CSRF.

Each session remembers which key opened it, so changing APP_ACCESS_KEY signs every
browser out. Failed logins are throttled per ip.
"""

import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import get_settings
from app.core.security import digest, new_token
from app.core.utils import stamp, uid
from app.db.session import Connection

MAX_PER_IP = 20  # failed logins per ip per window
WINDOW_SECONDS = 15 * 60

DASHBOARD = {"id": "dashboard"}  # actor for browser sessions
API = {"id": "api"}  # actor for bearer-key requests


@dataclass(frozen=True)
class Session:
    token: str
    csrf_token: str
    max_age: int


def _key() -> str:
    return get_settings().access_key.strip()


def key_id(key: str) -> str:
    """Short fingerprint of the key that opened a session (never the key itself)."""
    return digest(f"session:{key}")[:16]


def key_matches(candidate: str) -> bool:
    key = _key()
    return bool(key) and secrets.compare_digest(digest(candidate), digest(key))


def login(db: Connection, key: str, ip: str = "") -> Session | Literal["locked", "invalid"]:
    """Returns a status instead of raising so attempt rows still commit."""
    now = time.time()
    since = now - WINDOW_SECONDS
    db.execute("DELETE FROM login_attempts WHERE attempted_at < ?", (since,))
    failures = db.execute(
        "SELECT COUNT(*) FROM login_attempts WHERE ip=? AND attempted_at >= ?", (ip, since)
    ).scalar()
    if failures >= MAX_PER_IP:
        return "locked"
    if not key_matches(key):
        db.execute(
            "INSERT INTO login_attempts (id, ip, attempted_at) VALUES (?,?,?)", (uid(), ip, now)
        )
        return "invalid"
    current = key_id(_key())
    db.execute("DELETE FROM login_attempts WHERE ip=?", (ip,))
    db.execute("DELETE FROM sessions WHERE expires_at < ? OR key_id <> ?", (now, current))
    max_age = get_settings().session_hours * 3600
    token, csrf = new_token(), new_token()
    db.execute(
        "INSERT INTO sessions (token_hash, key_id, csrf_token, expires_at, created_at)"
        " VALUES (?,?,?,?,?)",
        (digest(token), current, csrf, now + max_age, stamp()),
    )
    return Session(token, csrf, max_age)


def logout(db: Connection, token: str) -> None:
    if token:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))


def session_for(db: Connection, token: str) -> dict[str, Any] | None:
    """The live session for a cookie token, opened with the current key."""
    key = _key()
    if not token or not key:
        return None
    row = db.execute(
        "SELECT csrf_token FROM sessions WHERE token_hash=? AND key_id=? AND expires_at > ?",
        (digest(token), key_id(key), time.time()),
    ).fetchone()
    return dict(row) if row else None
