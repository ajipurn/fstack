"""`uv run tasks.py seed` — idempotent: migrate, prompts from files, optional env provider,
models.dev prices. Never runs at API startup.

    python -m app.cli.seed [--skip-prices]
"""

import argparse
import sys

from sqlalchemy.exc import OperationalError

from app.core.config import BACKEND_ROOT, get_settings
from app.core.exceptions import AppError
from app.db.migrations import ensure_database, migrate
from app.db.session import transaction
from app.schemas.models import ProviderWrite
from app.services import pricing, prompts, providers


def say(text: str) -> None:
    print(f"  {text}")


def check_access_key() -> None:
    if len(get_settings().access_key.strip()) < 32:
        say("access: set APP_ACCESS_KEY in backend/.env (`uv run tasks.py key` prints a fresh one)")
    else:
        say("access: sign in with APP_ACCESS_KEY from backend/.env")


def seed_prompts() -> None:
    with transaction() as db:
        for line in prompts.sync_files(db, BACKEND_ROOT / "prompts") or ["prompts: up to date"]:
            say(line)


def seed_provider() -> None:
    settings = get_settings()
    if not settings.bootstrap_provider_kind:
        return
    with transaction() as db:
        if db.execute("SELECT 1 FROM fstack_providers LIMIT 1").fetchone():
            say("provider: providers exist, skipped env bootstrap")
            return
        system = {"id": None}
        body = ProviderWrite(
            name="Default",
            kind=settings.bootstrap_provider_kind,  # type: ignore[arg-type]
            base_url=settings.bootstrap_provider_base_url,
            models=[settings.bootstrap_model] if settings.bootstrap_model else [],
            api_key=settings.bootstrap_provider_api_key,
        )
        created = providers.create(db, system, body)
        say(f"provider: created '{created['name']}' ({created['kind']})")


def seed_prices() -> None:
    try:
        data = pricing.fetch_catalog()
    except AppError as exc:
        say(f"prices: skipped ({exc.detail})")
        return
    with transaction() as db:
        result = pricing.sync_catalog(db, data)
    say(f"prices: {result['models']} models across {result['catalogs']} catalogs (models.dev)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-prices", action="store_true")
    args = parser.parse_args(argv)
    print("seed")
    try:
        created = ensure_database()
    except OperationalError as exc:
        sys.exit(
            f"seed failed: MySQL said {exc.orig}\n"
            "  Is MySQL running (`uv run tasks.py db-up`), and does APP_DATABASE_URL in\n"
            "  backend/.env have root's current password?"
        )
    if created:
        say(f"database: created {created}")
    migrate()
    say("schema: migrated")
    try:
        seed_prompts()
        seed_provider()
        if not args.skip_prices:
            seed_prices()
        check_access_key()
    except (AppError, ValueError) as exc:
        detail = exc.detail if isinstance(exc, AppError) else exc
        sys.exit(f"seed failed: {detail}")


if __name__ == "__main__":
    main()
