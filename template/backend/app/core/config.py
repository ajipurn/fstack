"""Settings. Every env var is a field here — never read os.environ elsewhere."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_", env_file=BACKEND_ROOT / ".env", extra="ignore"
    )

    app_name: str = "Fstack Starter"
    environment: Literal["development", "production", "test"] = "development"
    database_url: str = "mysql+pymysql://root@127.0.0.1:3306/fstack_starter"
    allowed_origins: Annotated[list[str], NoDecode] = [
        "http://127.0.0.1:5710",
        "http://localhost:5710",
    ]
    cookie_secure: bool = False
    encryption_key: str = ""
    session_hours: int = Field(default=12, ge=1, le=24 * 30)

    # One key opens the dashboard and the API (Authorization: Bearer). 32+ random chars.
    access_key: str = ""

    bootstrap_provider_kind: str = ""
    bootstrap_provider_base_url: str = ""
    bootstrap_provider_api_key: str = ""
    bootstrap_model: str = ""

    log_llm_payloads: bool = False
    models_dev_url: str = "https://models.dev/api.json"
    llm_timeout_seconds: float = Field(default=120, gt=0)
    worker_concurrency: int = Field(default=2, ge=1, le=16)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def require_safe_runtime(self) -> None:
        """Fail at startup instead of silently running production on dev fallbacks."""
        if self.environment != "production":
            return
        problems = []
        if len(self.access_key.strip()) < 32:
            problems.append("APP_ACCESS_KEY must be set (32+ random characters).")
        if not self.encryption_key.strip():
            problems.append("APP_ENCRYPTION_KEY must be set (32-byte key).")
        if not self.cookie_secure:
            problems.append("APP_COOKIE_SECURE must be true behind HTTPS.")
        if problems:
            raise RuntimeError(" ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
