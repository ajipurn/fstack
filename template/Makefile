PM ?= bun
API_PORT ?= 8710
WEB_PORT ?= 5710
# Dev MySQL (scripts/mysql.sh): DB_RUNTIME=container|docker, empty = auto-detect.
# DB_ROOT_PASSWORD: root password for a container db-up creates (default root).
DB_RUNTIME ?=
DB_CONTAINER ?= mysql
export DB_RUNTIME DB_CONTAINER DB_ROOT_PASSWORD

.PHONY: help setup db-up db-down migrate revision seed key prices api web worker dev test lint check build

help: ## Show targets
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## Install backend + frontend dependencies
	cd backend && uv sync --compile-bytecode  # .pyc up front: no third-party SyntaxWarnings
	cd frontend && $(PM) install

db-up: ## Start MySQL: Apple container (shared) or Docker, whichever runs
	@sh scripts/mysql.sh up

db-down: ## Stop MySQL (Apple container: the shared one, for every project)
	@sh scripts/mysql.sh down

migrate: ## Apply Alembic migrations
	cd backend && uv run alembic upgrade head

revision: ## New migration: make revision m="add widgets"
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

seed: ## Migrate, prompts/*.md, task registry, models.dev prices
	cd backend && uv run python -m app.cli.seed

key: ## Print a fresh access key (paste into APP_ACCESS_KEY, then restart the API)
	@python3 -c "import secrets; print(secrets.token_urlsafe(32))"

prices: ## Refresh model prices from models.dev
	cd backend && uv run python -m app.cli.prices

api: ## FastAPI with reload on :$(API_PORT)
	cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port $(API_PORT) --reload

web: ## Vite on :$(WEB_PORT) (proxies /api)
	cd frontend && API_URL=http://127.0.0.1:$(API_PORT) $(PM) run dev

worker: ## Background job worker (run it as its own process)
	cd backend && uv run python -m app.workers.worker

dev: ## api + web together
	$(MAKE) -j2 api web

test: ## Backend tests (SQLite) + frontend tests
	cd backend && uv run pytest -q
	cd frontend && $(PM) run test

lint: ## ruff + oxlint
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && $(PM) run lint

check: lint test ## Everything CI runs
	cd frontend && $(PM) run build

build: ## Production frontend bundle
	cd frontend && $(PM) run build
