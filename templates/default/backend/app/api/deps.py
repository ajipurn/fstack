import secrets
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends, Request

from app.core.exceptions import Forbidden, Unauthorized
from app.core.security import COOKIE
from app.db.session import Connection, transaction
from app.services import auth

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def get_database_url(request: Request) -> str:
    return request.app.state.database_url


def get_db(request: Request) -> Iterator[Connection]:
    """One transaction per request; services never commit."""
    with transaction(get_database_url(request), write=request.method not in SAFE_METHODS) as db:
        yield db


# scope="function": commit before the response goes out. The default ("request")
# commits after it is sent, so a client that refetches right after a write reads
# the old rows, and a failed commit would still have answered 2xx.
DB = Annotated[Connection, Depends(get_db, scope="function")]
DatabaseUrl = Annotated[str, Depends(get_database_url)]


def authenticate(request: Request) -> dict[str, Any]:
    """`Authorization: Bearer <access key>` (scripts, other services) or the dashboard's
    session cookie + CSRF header. Browsers never attach the bearer header on their own,
    so it needs no CSRF token."""
    header = request.headers.get("authorization")
    if header is not None:
        scheme, _, key = header.partition(" ")
        if scheme.lower() != "bearer" or not auth.key_matches(key.strip()):
            raise Unauthorized("Invalid access key.")
        return dict(auth.API)
    # Short read-only transaction: endpoints that call a model must not hold
    # a DB transaction open for the whole provider round-trip.
    with transaction(get_database_url(request), write=False) as db:
        session = auth.session_for(db, request.cookies.get(COOKIE, ""))
    if not session:
        raise Unauthorized("Please sign in.")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(sent, session["csrf_token"]):
            raise Forbidden("Your session expired. Reload the page.")
    return {**auth.DASHBOARD, "csrf_token": session["csrf_token"]}


Actor = Annotated[dict[str, Any], Depends(authenticate)]
