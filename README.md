# fstack

fstack starts our new projects from shared templates, and later brings template
improvements into the projects made from them.

```bash
fstack new talent-review           # a new project from the default template
fstack update                      # later, inside it: take what changed in the template
```

The **default** template is a FastAPI + llmfy + MySQL backend with a React 19 + Vite
dashboard. LLM calls work with any provider, and prompt versioning and cost tracking are
built in ([what's in it](#the-default-template)). Any of our repos can become another
template.

- [Install](#install)
- [Start a project](#start-a-project)
- [Update a project](#update-a-project)
- [Templates](#templates)
- [Troubleshooting](#troubleshooting)
- [Contributing](CONTRIBUTING.md): working on fstack and its templates, and releasing

## Install

You need:

| Tool | For |
|---|---|
| [`uv`](https://docs.astral.sh/uv/) | installing fstack, and the backend |
| `bun` or `pnpm` | the frontend (`bun` unless you pass `--pm pnpm`) |
| `git` | fetching fstack, and project history |
| Docker, or Apple `container` on macOS | local MySQL (`db-up`) |

fstack runs on macOS, Linux and Windows. On Windows, install the tools with winget, in
PowerShell:

```powershell
winget install astral-sh.uv Git.Git Oven-sh.Bun Docker.DockerDesktop GitHub.cli
```

1. The repo is private, so ask for read access to `ajipurn/fstack` first. Then let git
   reach it with `gh auth login` (HTTPS) or an SSH key on GitHub.
2. Install fstack and check your toolchain:

   ```bash
   uv tool install git+https://github.com/ajipurn/fstack
   fstack doctor
   ```

   With an SSH key, install from `git+ssh://git@github.com/ajipurn/fstack` instead.
3. Export your local MySQL root password once, e.g. in `~/.zshrc`:

   ```bash
   export DB_ROOT_PASSWORD='…'
   ```

   On Windows, `setx DB_ROOT_PASSWORD "…"` (new terminals see it).

   `fstack new` writes it into each project's `backend/.env`. Without it, `fstack new`
   asks (Enter keeps `root`).

### Upgrade

```bash
uv tool upgrade fstack
fstack --version
```

This takes the latest `main`. Read [CHANGELOG.md](CHANGELOG.md) for what changed, then
[update your projects](#update-a-project).

To stay on a release instead, install its tag:

```bash
uv tool install --force git+https://github.com/ajipurn/fstack@v0.3.0
```

`uv tool upgrade` never moves a pinned tag, so take the next release the same way.

## Start a project

```bash
fstack new talent-review                          # ./talent-review, default template
fstack new "Talent Review" --pm pnpm --accent "#ffbe25"
fstack new crm --database-url "mysql+pymysql://root:secret@127.0.0.1:3306/crm"
fstack new pelni-review -t board                  # another template (fstack doctor lists them)
```

`fstack new`:

1. Copies the template into `./<name>` and renames it.
2. Picks ports from the name, so each project gets stable ports and several can run side
   by side.
3. Writes `backend/.env` with fresh secrets and your MySQL password, plus
   [`.fstack.json`](#fstackjson).
4. Installs the dependencies and makes the first commit.
5. Prints the next steps. For the default template:

```bash
cd talent-review
uv run tasks.py db-up     # MySQL via Apple container or Docker
uv run tasks.py seed      # create the database, migrate, load prompts and model prices
uv run tasks.py dev       # API + web; sign in with APP_ACCESS_KEY from backend/.env
```

`uv run tasks.py <task>` works the same on every OS; on macOS and Linux, `make <task>` is
a shortcut for it (`make dev`). `uv run tasks.py help` lists the tasks.

| Flag | Default | |
|---|---|---|
| `--template`, `-t` | `default` | the template to start from |
| `--dir` | `./<name>` | where to create the project |
| `--title` | from the name | display name |
| `--pm bun\|pnpm` | `bun` | frontend package manager (Makefile, CI, `packageManager`) |
| `--accent #hex` | `#2f3037` (graphite) | brand color; text on it gets a contrasting color |
| `--database-url` | local MySQL as root; database = project name | `APP_DATABASE_URL` in `backend/.env` |
| `--api-port`, `--web-port` | derived from the name | |
| `--no-install` | | skip installing dependencies |
| `--no-git` | | skip `git init` and the first commit |
| `--force` | | write into a non-empty directory |

A template asks only what it uses. Flags it doesn't use are ignored with a warning.

## Update a project

When a template improves, bring the change into a project made from it:

```bash
uv tool upgrade fstack
cd talent-review
fstack update --dry-run     # what would change
fstack update               # apply it; nothing is committed for you
```

The project needs a clean working tree, so the update lands as one diff you can review.
After the update:

1. Review `git diff`.
2. Resolve any conflicts.
3. Run what fstack prints: the `setup` task when dependencies changed, `migrate` for new
   migrations.
4. Commit.

fstack compares the template as the project last got it with the template now. It merges
the difference into the project file by file and keeps the project's own edits:

| Result | Meaning |
|---|---|
| ✓ added / updated / merged / removed | applied cleanly |
| ✓ renamed | the template moved a file; it's moved here too, with the project's edits |
| ✗ conflict | both sides changed the same lines. Resolve the `<<<<<<<` markers (`git diff --check` lists them). The exit code is 1. |
| ! skipped | the template changed a file the project deleted or doesn't track: left as it is |
| ! kept | the template removed a file the project changed: left in place |

fstack never touches:

- files only the project has
- files git ignores
- `.env`
- lockfiles
- `node_modules` and caches

If the project has Alembic migrations of its own, `alembic merge heads` may be needed
after new template migrations; fstack says so.

### `.fstack.json`

`fstack new` writes `.fstack.json`; commit it. It records:

- which template the project follows
- the fstack commit the project last got
- the answers the project was made with

```json
{ "fstack": "0.3.0", "commit": "<fstack git sha>", "template": "default",
  "name": "talent-review", "title": "Talent Review", "api_port": 8410, "web_port": 5510,
  "accent": "#2f3037", "pm": "bun", "pm_version": "1.4.4" }
```

`pm_version` keeps `packageManager` as the project got it, so a teammate's newer bun
doesn't show up as a change.

**Projects made before fstack 0.2.0** (e.g. range-market-assessment) have no
`.fstack.json`. `fstack update` starts from the project's own
`chore: scaffold … from fstack …` commit, reads the answers back from the files, and writes
`.fstack.json`. Without that commit, pass `--from <fstack commit or tag>` (e.g.
`--from v0.1.0`), or write `.fstack.json` by hand like the one above.

## Templates

`fstack doctor` lists the templates your fstack has, and `fstack new -t <name>` uses one.
A project always updates from its own template.

Templates live in this repo under `templates/`, so a new or improved template reaches
everyone with `uv tool upgrade fstack`. To turn an existing repo into a template, see
[Add a template from a repo](CONTRIBUTING.md#add-a-template-from-a-repo).

### The default template

Distilled from `pelni-assessment`, `py-new-assessment-center` (bars-dashboard),
`cimb-assessment` and `daria`.

**Backend** (`backend/`: uv, Python 3.13)

- FastAPI app factory, sync SQLAlchemy Core with `?` SQL, pymysql, and an Alembic baseline.
- **Access**: one access key (`APP_ACCESS_KEY`, generated).
  - The dashboard signs in with it and gets a hashed cookie session with CSRF protection.
  - API clients send `Authorization: Bearer <key>`.
  - Sign-in attempts are throttled per IP.
- **Providers** via llmfy: OpenAI and any OpenAI-compatible URL, Anthropic, Bedrock and
  Gemini. Keys are AES-256-GCM encrypted, and each connection is tested.
- **Runs**: code calls `run_prompt("key", vars, provider=…, model=…)`.
  - Temperature and max tokens default to each model's own values.
  - Providers load their model list from the API.
- **Prompt versioning**:
  - A draft autosaves; a published version is immutable (SHA-256); an active pointer
    picks the version in use.
  - Rollback.
  - Prompts as code, seeded from `prompts/*.md`.
- **Observability**: one `fstack_llm_calls` row per request with:
  - tokens, including cache
  - cost from models.dev rates, including tiers, with a snapshot of the rates
  - latency and prompt version

  A usage summary API reads from these rows.
- Structured output via a pydantic schema, with one correction round-trip.
- Background jobs leased in MySQL and a worker with a heartbeat; billed calls are never
  replayed.
- Tests run on SQLite, including an end-to-end run through llmfy with a mocked OpenAI
  transport.

**Frontend** (`frontend/`: React 19, Vite 8, TypeScript 7, Tailwind v4)

- **Header**: Clerk-style, two rows.
  - A breadcrumb top bar.
  - Tabs with a gliding hover pill and a spring underline.
- **Buttons**: Clerk button anatomy (inner highlight, drop shadows, 1px ring).
- **Libraries**:
  - Base UI primitives (Dialog, AlertDialog, Menu, Select, Tooltip, Switch).
  - Vaul drawer, OverlayScrollbars, torph morphing numbers, notch-toast, cuelume sounds.
  - TanStack Query hooks.
  - react-router data router, with a code chunk per route.
- **Pages**:
  - **Overview**: KPIs, a spend chart and a setup checklist.
  - **Run**: pick a prompt, provider and model, with optional temperature and max tokens.
    Each project builds its own run logic here.
  - **Prompts**: versions, editor, diff, publish and activate.
  - **Usage**: cost, requests and tokens over time, broken down by model and prompt, with
    a drawer for each call.
  - **Configure**: providers, models and pricing.
- **Look**: scaled-down type (13px), a neutral palette, dark mode with a view-transition
  cross-fade, and reduced motion respected.

**Ops**

- `tasks.py` for every task, on macOS, Linux and Windows (`uv run tasks.py help`), and a
  Makefile with the same tasks as shortcuts on macOS and Linux.
- Local MySQL with the `db-up` task:
  - On Apple `container` (macOS), one shared `mysql` with a database per project, created
    by the `seed` task.
  - Or docker compose with MySQL 8.4.
- Dockerfiles for the API and an nginx SPA.
- GitHub Actions.
- `.claude/launch.json`.
- AGENTS.md / CLAUDE.md conventions.

## Troubleshooting

**`uv tool install` says "Repository not found" or asks for a password.**
You don't have access yet, or git can't sign in to GitHub. Run `gh auth login`, or
install over SSH (see [Install](#install)).

**`fstack new` or `fstack update`: "no template 'x' in this fstack".**
The template was added after your install. Run `uv tool upgrade fstack`.

**`fstack update`: "commit or stash your changes first".**
The update needs a clean working tree so it lands as one diff.

**`fstack update`: "the installed fstack … is older than this project's template".**
A teammate updated the project with a newer fstack, and going ahead would undo template
changes. Run `uv tool upgrade fstack`, then update again.

**`fstack update` exits with code 1.**
There are conflicts. Resolve the `<<<<<<<` markers (`git diff --check` lists them), then
commit.

**`seed` gets "Access denied" from MySQL.**
The password in `APP_DATABASE_URL` (`backend/.env`) isn't your MySQL root password. Fix it
there, and export `DB_ROOT_PASSWORD` so the next project gets the right one.
