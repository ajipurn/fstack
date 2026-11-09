from fastapi import APIRouter, Request, Response

from app.api.deps import DB, Actor
from app.core.config import get_settings
from app.core.exceptions import TooManyRequests, Unauthorized
from app.core.security import COOKIE
from app.schemas.models import Login
from app.services import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: Login, request: Request, response: Response, db: DB):
    # Behind a proxy this is the real client only when uvicorn trusts that proxy
    # (FORWARDED_ALLOW_IPS, set in the Dockerfile).
    ip = request.client.host if request.client else ""
    result = auth.login(db, body.key, ip)
    if result == "locked":
        raise TooManyRequests("Too many attempts. Try again in 15 minutes.")
    if result == "invalid":
        # Commit the attempt row before failing: raise from a fresh scope.
        db.commit()
        raise Unauthorized("That access key is not valid.")
    response.set_cookie(
        COOKIE,
        result.token,
        max_age=result.max_age,
        httponly=True,
        samesite="strict",
        secure=get_settings().cookie_secure,
        path="/api",
    )
    return {"csrf_token": result.csrf_token}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DB):
    auth.logout(db, request.cookies.get(COOKIE, ""))
    response.delete_cookie(COOKIE, path="/api")


@router.get("/me")
def me(actor: Actor):
    return {"via": actor["id"], "csrf_token": actor.get("csrf_token", "")}
