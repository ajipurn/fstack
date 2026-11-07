# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY . .

FROM python:3.13-slim-bookworm
WORKDIR /app
RUN useradd --create-home app
COPY --from=build --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 APP_ENVIRONMENT=production
# Trust X-Forwarded-For only from the reverse proxy (the nginx container on a private
# network) so the login throttle sees real client IPs. Narrow this to your proxy's
# address if clients can reach the API from a private network directly.
ENV FORWARDED_ALLOW_IPS="127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
USER app
EXPOSE 8000
# Run migrations as a release step (`python -m app.cli.seed --skip-prices` or alembic upgrade head).
# The worker uses the same image: `python -m app.workers.worker`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
