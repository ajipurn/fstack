# fstack

Personal scaffolder for new projects. The default template is a **FastAPI + llmfy +
MySQL** backend and a **React 19 + Vite** dashboard (Clerk-style top navigation), with
provider-agnostic LLM calls, prompt versioning and cost observability (models.dev) built
in. Any repo can become another template: `fstack template add` (below).

Distilled from `pelni-assessment`, `py-new-assessment-center` (bars-dashboard),
`cimb-assessment` and `daria`.

## Install

### Team

The repo is private: ask for read access first (a collaborator with `pull` is enough).

1. Have `uv`, `bun` (or `pnpm`), `git`, and Apple `container` or Docker for MySQL.
2. Let git reach the private repo: `gh auth login` (or an SSH key on GitHub).
3. Install, then check the toolchain:

   ```bash
   uv tool install git+https://github.com/ajipurn/fstack
   fstack doctor
   ```

4. Export your local MySQL's root password once (e.g. in `~/.zshrc`) so `fstack new`
   writes it into `backend/.env`: `export DB_ROOT_PASSWORD='…'`. Without it, `fstack new`
   asks (Enter = `root`).

Update with `uv tool upgrade fstack`, then run `fstack update` in a project to bring the
template's changes into it (see [Update a project](#update-a-project)). To stay on a known
release, install a git tag instead: `git+https://github.com/ajipurn/fstack@<tag>`.

### Working on fstack

```bash
uv tool install --editable ~/Developer/Projects/fstack
uv run --group dev pytest          # fstack's own tests (new + update, end to end)
```

Editable means template changes apply to the next `fstack new` immediately (files git
ignores in `templates/` are never copied). `.fstack.json` records fstack's commit, so commit
template changes before updating projects: `fstack update` refuses when the project's
template is dirty unless `--allow-dirty`, and `fstack new` notes it (`fstack doctor` shows
the commit and which templates are dirty).

## Use

```bash
fstack new talent-review                 # ./talent-review, default template, bun, graphite accent
fstack new "Talent Review" --pm pnpm --accent "#ffbe25"
fstack new crm --database-url "mysql+pymysql://root:secret@127.0.0.1:3306/crm"
fstack new pelni-review -t range         # from a template added from a repo
fstack doctor                            # check uv / bun / pnpm / container / docker, list templates
```

`fstack new` copies `templates/<name>/`, renames it, picks stable per-project ports (so
several projects can run side by side), writes `backend/.env` with fresh secrets (templates
with a backend) and `.fstack.json` (below), installs dependencies (`uv sync`,
`bun install`/`pnpm install`) and makes the first git commit.

| Flag | Default | |
|---|---|---|
| `--template`, `-t` | `default` | what to start from; `fstack doctor` lists them |
| `--pm bun\|pnpm` | `bun` | frontend package manager (Makefile, CI, packageManager) |
| `--accent #hex` | `#2f3037` | primary button / brand color; text color picked for contrast |
| `--database-url` | local MySQL as root (`$DB_ROOT_PASSWORD`, else it asks), DB = project name | written to `backend/.env`; `make seed` creates the DB |
| `--api-port`, `--web-port` | derived from the name | |
| `--title` | from the name | display name |
| `--no-install`, `--no-git`, `--force` | | |

A template asks only what it uses (its `fstack-template.toml` says); other flags are ignored
with a warning.

## Update a project

```bash
uv tool upgrade fstack
cd talent-review
fstack update --dry-run     # what would change
fstack update               # apply; nothing is committed for you
```

`fstack update` takes the template the project last got (its own scaffold commit until the
first update, then the fstack commit in `.fstack.json` rebuilt with the project's answers)
and the current one, and merges the difference into the project file by file
(`git merge-file`). The project's own edits stay:

| | |
|---|---|
| ✓ added / updated / merged / removed | applied cleanly |
| ✓ renamed | the template moved a file: moved here too, with the project's edits |
| ✗ conflict | both sides changed the same lines: fix the `<<<<<<<` markers (`git diff --check` lists them) |
| ! skipped | the template changed a file the project deleted (e.g. the Run page), or one git doesn't track here: left as is |
| ! kept | the template removed a file the project changed: left in place |

Files only the project has are never touched, nor files git doesn't track (ignored local
files), `.env`, lockfiles, `node_modules` and caches; a file mode changes only when the
template changed it. It needs a clean working tree, so the update is one diff to review;
exit code 1 means conflicts. Afterwards it prints what's left: `make setup` when
dependencies changed, `make migrate` for new migrations (and `alembic merge heads` when
the project has migrations of its own), then commit.

It refuses when the installed fstack is older than the project's template (a teammate
updated it with a newer fstack): that would undo template changes, so `uv tool upgrade
fstack` first. From an editable install it also refuses while the project's template has
uncommitted changes, since the next update couldn't rebuild them; `--allow-dirty` goes
ahead and notes it in `.fstack.json`. A project always follows its own template:
`.fstack.json` names it.

`.fstack.json` holds what it needs, so commit it. `pm_version` keeps `packageManager` as
the project got it, so another machine's bun version never shows up as a change:

```json
{ "fstack": "0.1.0", "commit": "<fstack git sha>", "template": "default",
  "name": "talent-review", "title": "Talent Review", "api_port": 8410, "web_port": 5510,
  "accent": "#2f3037", "pm": "bun", "pm_version": "1.4.4" }
```

The old template comes from fstack's git history: the local checkout for an editable
install (pull it when it lacks a project's commit), otherwise a cached clone of the repo it
was installed from (`~/.cache/fstack`). Commits from before `templates/` find `default` at
its old place, `template/`.

**Projects made before `.fstack.json`** (e.g. range-market-assessment): `fstack update`
uses the project's own `chore: scaffold … from fstack …` commit as the starting point and
reads the answers back from the files, then writes `.fstack.json`. Without that commit, pass
`--from <fstack commit or tag>`, or write `.fstack.json` by hand.

## Add a template from a repo

```bash
fstack template add range --from ~/Developer/Projects/range-market-assessment --dry-run
fstack template add range --from ~/Developer/Projects/range-market-assessment
fstack template add board --from git@github.com:acme/acme-board.git
fstack new pelni-review -t range         # then commit templates/range in fstack
```

It is `fstack new` in reverse: the repo's committed files (never `.env`, never
`.fstack.json`) go to `templates/<name>/` with the project's own name (`range-market-assessment`,
`range_market_assessment`, “Range Market Assessment”), ports and accent put back to the
starter tokens, so `fstack new -t range` renames them for each new project. The answers
come from the repo's `.fstack.json`, else from its files when fstack made it, else they're
guessed: the name from `package.json` / `pyproject.toml` / `go.mod` / `Cargo.toml` (or the
folder), the title from README's heading, ports from the Makefile (`API_PORT ?=`,
`WEB_PORT ?=`) or `vite.config`; fix a wrong guess with `--source-name`, `--source-title`,
`--api-port`, `--web-port`, `--accent`. The install steps are the original template's, or
read from the repo (`uv sync`, `{pm} install`, `go mod download`, `cargo fetch`).

It reports, and leaves to you: what looks like a secret, other spellings of the name
(`RangeMarketAssessment`), paths with the name in them (fstack never renames paths) and
starter tokens the repo already had. It works in an fstack checkout (editable install);
commit and push the new template so the team gets it. Names too common to replace safely
(`app`, `api`, `web`…) are refused.

## What the default template gives

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

## Working on the templates

Each `templates/<name>/` is a runnable project named “Fstack Starter”. Run it like any
generated project (`make -C templates/default dev`). The
tokens `fstack-starter`, `fstack_starter`, `Fstack Starter`, ports `8710`/`5710` and the
accent `#2f3037` are what `fstack new` rewrites — keep them intact when editing.

Next to the files, `fstack-template.toml` (never copied) says what the template is:

```toml
description = "FastAPI + llmfy + MySQL API and a React dashboard"   # shown by `fstack doctor`
answers = ["api_port", "web_port", "accent", "pm"]   # the rest stay as they are
install = [{ dir = "backend", run = "uv sync --compile-bytecode" }, { dir = "frontend", run = "{pm} install" }]
next = [["make dev", "api :{api_port} + web :{web_port}"]]   # printed after `fstack new`
```

A new template, any stack, is a new folder with that file (its name is the folder's);
`fstack template add` writes both. `uv run --group dev pytest` checks every template renders
without leftover tokens.
