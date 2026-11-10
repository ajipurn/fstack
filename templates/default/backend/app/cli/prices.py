"""`uv run tasks.py prices` — refresh model prices from models.dev."""

import sys

from app.core.exceptions import AppError
from app.db.migrations import check_schema
from app.db.session import transaction
from app.services import pricing


def main() -> None:
    check_schema()
    try:
        data = pricing.fetch_catalog()
        with transaction() as db:
            result = pricing.sync_catalog(db, data)
    except AppError as exc:
        sys.exit(str(exc.detail))
    print(
        f"{result['models']} models · {result['catalogs']} catalogs"
        f" · {result['manual_kept']} manual overrides kept"
    )


if __name__ == "__main__":
    main()
