# Fstack Starter

FastAPI · llmfy · MySQL · React 19 · Vite · TanStack Query · Base UI · Tailwind v4.

## Run it

```bash
uv run tasks.py db-up     # MySQL: Apple container or Docker — or point APP_DATABASE_URL elsewhere
uv run tasks.py seed      # create the database if missing, migrate, prompts, prices
uv run tasks.py dev       # API :8710 + web :5710
uv run tasks.py worker    # background jobs, in another terminal
```

`tasks.py` runs the same on macOS, Linux and Windows; on macOS/Linux `make <task>` is a
shortcut (`uv run tasks.py dev`). `uv run tasks.py help` lists every task.

`db-up` uses whichever runtime is running, Apple's `container` first (macOS). With Apple
container every project shares one `mysql` container; with Docker each project runs its
own from `compose.yaml`. The app connects as root (`APP_DATABASE_URL`) and `uv run tasks.py seed`
creates the project's database. `fstack new` fills in root's password from
`DB_ROOT_PASSWORD` (export it once in `~/.zshrc`, or `setx` it on Windows), else `root`; a container `db-up`
creates gets the same. Force a runtime with `DB_RUNTIME=docker` in the environment; use a
container with another name via `DB_CONTAINER=…`. `db-down` on Apple container
stops the shared container for every project.

Sign in with `APP_ACCESS_KEY` from `backend/.env`, then:

1. **Configure → Providers**: connect OpenAI, Anthropic, Bedrock (Converse or Mantle),
   Gemini, or any OpenAI-compatible URL (OpenRouter, Groq, vLLM, Ollama). Adding one tests
   it and loads its model list.
2. **Run**: pick a prompt, a provider and a model (temperature and max output tokens
   optional). This page is the project's own: add its inputs and output in
   `frontend/src/features/run/RunPage.tsx` and run with `useRun()`. **Usage** shows
   tokens, cost and latency per call.

## Calling a model from code

```python
from app.services import runs

result = runs.run_prompt(
    "summarize",
    {"text": body, "audience": "the board"},
    provider="OpenAI",          # a provider's name (or id) from Configure → Providers
    model="gpt-5.4-mini",
    user_id=customer_id,
)
result.data        # validated against app.llm.outputs.Summary
result.cost_usd    # from models.dev rates, frozen on the llm_calls row
```

`temperature` and `max_tokens` are optional; left out, each model keeps its own default
(Anthropic requires max_tokens, so it gets the model's output limit from models.dev).
`retries` (default 2) re-sends failures the provider never processed — rate limits,
overload, refused connections — with exponential backoff; timeouts are never retried.
In the dashboard, `useRun()` gives `stop()` (no new request or retry starts; one already
sent finishes and is recorded) and `retry()`; jobs have cancel and retry too.
Add a prompt: write `backend/prompts/<key>.md` and run `uv run tasks.py seed`; list it in
`backend/app/llm/outputs.py` only if code needs typed JSON back. Long work:
`jobs.enqueue(db, "llm.run", {"prompt_key": …, "provider_id": …, "model": …, "variables": {…}})`.

## Access

One key, `APP_ACCESS_KEY`, opens everything. The dashboard trades it for an HttpOnly
session cookie; scripts and other services send it on every request:

```bash
curl -H "Authorization: Bearer $APP_ACCESS_KEY" http://127.0.0.1:8710/api/usage/summary
```

Rotate it with `uv run tasks.py key` → paste into `backend/.env` → restart the API. Every browser
session ends; update the scripts that use it.

## Prompt versioning

Drafts autosave; publishing freezes the text, stamps a SHA-256 and (optionally) activates
it. Runs use the prompt's **active** version unless they pin one; rollback = activate an
older one. Every call records the version and digest it used. Deleting a prompt removes
its versions but not its call history; a prompt that still has `prompts/<key>.md` comes
back on the next `uv run tasks.py seed`.

## Observability

`llm_calls` holds one row per provider request: tokens (input incl. cache read/write,
output), `cost_usd`, the rate snapshot used, latency, status and prompt version.
Prices come from [models.dev](https://models.dev) (`uv run tasks.py prices`), only for the
catalogs in use: the first-party ones plus each provider's pricing catalog, which loads when
the provider is saved. Manual overrides survive syncs. Set `APP_LOG_LLM_PAYLOADS=true` to keep rendered prompts and outputs.
**Usage → Clear usage** deletes every recorded call (prompts, providers and prices stay).

## Layout

See [AGENTS.md](AGENTS.md) for conventions. `uv run tasks.py help` lists every task.
