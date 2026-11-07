# fstack

Personal scaffolder for new projects: **FastAPI + llmfy + MySQL** backend and a
**React 19 + Vite** dashboard (Clerk-style top navigation), with provider-agnostic
LLM calls, prompt versioning and cost observability (models.dev) built in.

Distilled from `pelni-assessment`, `py-new-assessment-center` (bars-dashboard),
`cimb-assessment` and `daria`.

## Install

```bash
uv tool install --editable ~/Developer/Projects/fstack
```

Editable means template changes apply to the next `fstack new` immediately.

## Use

```bash
fstack new talent-review                 # ./talent-review, bun, graphite accent
fstack new "Talent Review" --pm pnpm --accent "#ffbe25"
fstack new crm --database-url "mysql+pymysql://root:secret@127.0.0.1:3306/crm"
fstack doctor                            # check uv / bun / pnpm / container / docker
```

`fstack new` copies `template/`, renames it, picks stable per-project ports (so several
projects can run side by side), writes `backend/.env` with fresh secrets, runs
`uv sync` + `bun install`/`pnpm install`, and makes the first git commit.

| Flag | Default | |
|---|---|---|
| `--pm bun\|pnpm` | `bun` | frontend package manager (Makefile, CI, packageManager) |
| `--accent #hex` | `#2f3037` | primary button / brand color; text color picked for contrast |
| `--database-url` | local MySQL as root (`$DB_ROOT_PASSWORD`, else `root`), DB = project name | written to `backend/.env`; `make seed` creates the DB |
| `--api-port`, `--web-port` | derived from the name | |
| `--title` | from the name | display name |
| `--no-install`, `--no-git`, `--force` | | |

## What a project gets

**Backend** (`backend/`, uv, Python 3.13)
- FastAPI app factory, sync SQLAlchemy Core with `?` SQL, pymysql, Alembic baseline
- One access key (`APP_ACCESS_KEY`, generated): dashboard sign-in → hashed cookie session + CSRF,
  API clients send `Authorization: Bearer <key>`; login throttle per IP
- Providers (OpenAI & any OpenAI-compatible URL, Anthropic, Bedrock, Gemini) via **llmfy**;
  keys AES-256-GCM encrypted; connection probe
- **Runs**: code calls `run_prompt("key", vars, provider=…, model=…)`; temperature and max
  tokens default to each model's own; providers load their model list from the API
- **Prompt versioning**: draft (autosave) → published (immutable, SHA-256) → active pointer,
  rollback, prompts-as-code seeding from `prompts/*.md`
- **Observability**: `llm_calls` row per request (tokens incl. cache, cost from models.dev
  rates with tiers, rate snapshot, latency, prompt version); usage summary API
- Structured output via pydantic schema + one correction round-trip
- MySQL-leased background jobs + worker with heartbeat; never replays billed calls
- Tests on SQLite, including an end-to-end run through llmfy with a mocked OpenAI transport

**Frontend** (`frontend/`, React 19, Vite 8, TypeScript 7, Tailwind v4)
- Clerk-style two-row header: breadcrumb top bar + tabs with a gliding hover pill and
  spring underline; Clerk button anatomy (inner highlight, drops, 1px ring)
- Base UI primitives (Dialog, AlertDialog, Menu, Select, Tooltip, Switch), **vaul** drawer,
  **OverlayScrollbars**, **torph** morphing numbers, **notch-toast**, cuelume sounds
- TanStack Query hooks, react-router data router with per-route chunks
- Pages: Overview (KPIs, spend chart, setup checklist), Run (pick prompt, provider, model;
  optional temperature/max tokens — each project builds its own run logic here), Prompts (versions,
  editor, diff, publish/activate), Usage (cost/requests/tokens chart, by model/prompt, call
  drawer), Configure (Providers, Models & pricing)
- Scaled-down type (13px), neutral palette, dark mode with view-transition cross-fade,
  reduced-motion respected

**Ops**: Makefile, `make db-up` on Apple `container` (one shared `mysql`, a database per
project, created by `make seed`) or docker compose MySQL 8.4, Dockerfiles (API + nginx SPA), GitHub Actions,
`.claude/launch.json`, AGENTS.md/CLAUDE.md conventions.

## Working on the template

`template/` is a runnable project named “Fstack Starter”. Run it like any generated
project (`make -C template dev`). The tokens `fstack-starter`, `fstack_starter`,
`Fstack Starter`, ports `8710`/`5710` and the accent `#2f3037` are what `fstack new`
rewrites — keep them intact when editing.
