import hashlib
import secrets

COOKIE = "fstack_starter_session"


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)
