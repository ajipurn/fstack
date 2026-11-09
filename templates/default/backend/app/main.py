from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.deps import SAFE_METHODS
from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.migrations import check_schema


class OriginGuard:
    """Same-origin SPA behind the Vite proxy / reverse proxy: no CORS needed, so a
    write from any other origin is refused; every response is no-store + nosniff.

    Plain ASGI rather than @app.middleware("http"): that wrapper hides the client
    disconnect from endpoints, and a stopped run relies on seeing it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("Cache-Control", "no-store")
                headers["X-Content-Type-Options"] = "nosniff"
            await send(message)

        if scope["method"] not in SAFE_METHODS:
            origin = Headers(scope=scope).get("origin")
            if origin and origin not in get_settings().allowed_origins:
                refused = JSONResponse({"detail": "Origin is not allowed."}, status_code=403)
                await refused(scope, receive, send_with_headers)
                return
        await self.app(scope, receive, send_with_headers)


def create_app(database_url: str | None = None) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        get_settings().require_safe_runtime()
        check_schema(app.state.database_url)
        yield

    # Interactive docs + schema are a development aid; production doesn't publish its map.
    docs = settings.environment != "production"
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    app.state.database_url = database_url or settings.database_url

    app.add_middleware(OriginGuard)

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        issues = [
            {
                "field": ".".join(str(p) for p in err["loc"] if p not in ("body", "query")),
                "message": str(err["msg"]).removeprefix("Value error, "),
            }
            for err in exc.errors()
        ]
        detail = "; ".join(i["message"] for i in issues) or "Invalid request."
        return JSONResponse({"detail": detail, "issues": issues}, status_code=422)

    app.include_router(api_router)
    return app


app = create_app()
