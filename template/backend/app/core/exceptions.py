"""Domain errors. Services raise these; the app turns them into {"detail": ...}."""

from typing import Any


class AppError(Exception):
    status_code = 400

    def __init__(self, detail: Any = None) -> None:
        super().__init__(detail)
        self.detail = detail


class Unauthorized(AppError):
    status_code = 401


class Forbidden(AppError):
    status_code = 403


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409


class Unprocessable(AppError):
    status_code = 422


class TooManyRequests(AppError):
    status_code = 429


class ProviderError(AppError):
    """The model provider failed. The message is safe to show (secrets scrubbed)."""

    status_code = 502


class Cancelled(AppError):
    """The run was stopped (client went away, or its job was cancelled)."""

    status_code = 499


class InternalError(AppError):
    status_code = 500
