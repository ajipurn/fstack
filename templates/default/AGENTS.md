# Fstack Starter — conventions

Scaffolded with **fstack**. FastAPI + llmfy + MySQL backend, React 19 + Vite dashboard.

## Layout

```
backend/   FastAPI app (uv). app/{api,services,llm,db,core,workers,cli}, prompts/*.md, alembic/
frontend/  React + Vite + Tailwind v4. src/{app,features,ui,lib,styles}
```

## Backend rules

- Dependencies flow `api → services → db/core/llm`. Routes hold no SQL and no business rules.
  `workers/` and `cli/` call services. Services never import `api` or FastAPI.
- Services take `(db, actor, ...)`, never commit or roll back, and raise `core/exceptions`
  (`NotFound`, `Conflict`, `Unprocessable`, `ProviderError`…). One transaction per request.
- SQL is plain text with `?` placeholders through `db.session.Connection`; every `INSERT`
  lists its columns. Reserved words (`key`, `system`) are back-quoted.
- Schema changes go through Alembic only (`uv run tasks.py revision "…"`), never `create_all`,
  never edit an applied revision. Tables: InnoDB, utf8mb4_bin, JSON in LONGTEXT,
  ISO timestamps (`stamp()`), uuid ids (`uid()`), integer `revision` for optimistic locks.
- Table names start with `fstack_` (new tables too), so the database can be shared with
  other apps. Alembic only sees `fstack_*` tables and records revisions in
  `fstack_alembic_version`; CHECK and foreign key names carry the prefix, index names don't.
- Auth is one access key (`APP_ACCESS_KEY`): no users, no roles. Protected routes take
  `actor: Actor` — `{"id": "dashboard"}` (cookie session) or `{"id": "api"}` (bearer key).
- New env vars become `Settings` fields (`APP_` prefix) — never read `os.environ` elsewhere.
- Never call a model while holding a DB transaction. Auto-retry only failures the provider
  never processed (rate limit, overload, connection refused; `app/llm/errors.py`), never a
  timeout — it may already be billed. Jobs that lose their lease become `interrupted`.
- Runs can be stopped: `runs.run(..., stop=callable)`; the API stops a run when its client
  disconnects, the worker when its job is cancelled. Keep long loops checking `stop()`.

## LLM rules (provider-agnostic)

- Application code runs a **prompt** on a provider + model:
  `runs.run_prompt("summarize", {"text": ...}, provider="OpenAI", model="gpt-5.4-mini")`.
  Never import an SDK outside `app/llm/`.
- Temperature and max tokens are optional; unset = the model's own default (never invent one).
- A prompt that must return typed JSON is listed in `app/llm/outputs.py` (prompt key →
  pydantic model); the run validates it and allows one correction round-trip.
- Only `app/llm/backends.py` knows SDK specifics (llmfy models, timeouts, retries off).
- Prompts are versioned: draft → published (immutable, SHA-256 digest) → active pointer.
  `prompts/*.md` seeds new prompts; a changed file becomes a *draft* to review in the UI.
- Every provider request is a row in `fstack_llm_calls` (tokens incl. cache, cost_usd, rate
  snapshot, latency, prompt version). Cost uses models.dev prices; unknown = NULL
  ("unpriced"), never 0.

## Frontend rules

- Server state lives in TanStack Query (`lib/hooks.ts` owns keys + endpoints). No global stores.
- UI primitives come from `src/ui` (Base UI, vaul, OverlayScrollbars, torph, notch-toast).
  Pages compose them; don't restyle primitives inside features.
- Styling: tokens in `styles/tokens.css`, kit classes in `styles/kit.css`, Tailwind utilities
  for layout. Neutral surfaces, one accent, hairline rings — no loud gradients.
- Motion: 120–280 ms, `--ease-out`, interruptible transitions; everything respects
  `prefers-reduced-motion`. Numbers that change use `<Morph>`.
- Text sizes: 13px body, 12px secondary, 20px page titles.

## Commands

`uv run tasks.py setup · db-up · seed · dev · worker · test · lint · check` (see
`uv run tasks.py help`); `make <task>` is the same on macOS/Linux.
Commits follow Conventional Commits.
