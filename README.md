<div align="center">

# fstack

**Scaffold a project from a template, then keep it in step as the template evolves.**

[![CI](https://github.com/ajipurn/fstack/actions/workflows/ci.yml/badge.svg)](https://github.com/ajipurn/fstack/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776ab.svg)
![macOS · Linux · Windows](https://img.shields.io/badge/platform-macOS%20%C2%B7%20Linux%20%C2%B7%20Windows-555.svg)

[Quick start](#quick-start) · [How updates work](#how-updates-work) ·
[The default template](#the-default-template) · [Your own templates](#your-own-templates) ·
[Contributing](CONTRIBUTING.md)

</div>

---

Most scaffolders stop once the project exists. After that, every fix to the template has
to be copied by hand into every project made from it, and the projects slowly drift apart.

fstack doesn't stop there. It remembers which template and which version each project came
from. When the template improves, `fstack update` three-way merges the change into the
project, keeps your own edits, and leaves one diff for you to review.

```bash
fstack new acme-console    # a full-stack app, installed and committed
cd acme-console
fstack update              # later: take what the template has gained since
```

## Highlights

- **Updates that respect your code.** Template changes are merged file by file against the
  version the project last got. Your edits stay, renames are followed, and real conflicts
  show up as ordinary `<<<<<<<` markers.
- **Production-shaped default template.** FastAPI + MySQL + React 19, with any LLM
  provider, versioned prompts, per-call cost tracking and background jobs
  ([details](#the-default-template)).
- **Any repo can become a template.** `fstack template add` turns an existing project back
  into a template, in any stack.
- **Projects run side by side.** Ports come from the project name, so every project gets
  stable ports that don't collide.
- **Secrets from day one.** Each project gets its own access key and encryption key in a
  `backend/.env` only you can read.
- **Cross-platform.** macOS, Linux and Windows, with one task runner (`uv run tasks.py`)
  for all three.

## Quick start

### Requirements

| Tool | Used for |
|---|---|
| [`uv`](https://docs.astral.sh/uv/) | installing fstack, and the Python backend |
| [`bun`](https://bun.sh) or [`pnpm`](https://pnpm.io) | the frontend (`bun` unless you pass `--pm pnpm`) |
| `git` | project history, and what `fstack update` merges against |
| Docker, or Apple [`container`](https://github.com/apple/container) on macOS | local MySQL |

<details>
<summary>Windows: install everything with winget</summary>

```powershell
winget install astral-sh.uv Git.Git Oven-sh.Bun Docker.DockerDesktop
```

</details>

### Install

```bash
uv tool install git+https://github.com/ajipurn/fstack
fstack doctor              # checks your toolchain and lists the templates
```

Export your local MySQL root password once (in `~/.zshrc`, or `setx DB_ROOT_PASSWORD "…"`
on Windows) so new projects get it. Without it, `fstack new` asks.

```bash
export DB_ROOT_PASSWORD='…'
```

### Create and run a project

```bash
fstack new acme-console
cd acme-console
uv run tasks.py db-up      # MySQL via Apple container or Docker
uv run tasks.py seed       # create the database, migrate, load prompts and model prices
uv run tasks.py dev        # API + web; sign in with APP_ACCESS_KEY from backend/.env
```

On macOS and Linux, `make <task>` is a shortcut for `uv run tasks.py <task>`.
`uv run tasks.py help` lists every task.

## Usage

### `fstack new`

```bash
fstack new acme-console                            # ./acme-console, default template
fstack new "Acme Console" --pm pnpm --accent "#ffbe25"
fstack new crm --database-url "mysql+pymysql://root:secret@127.0.0.1:3306/crm"
fstack new reports -t <template>                   # another template (fstack doctor lists them)
```

It copies the template into `./<name>` and renames it in every spelling. It then picks
ports, writes `backend/.env` and [`.fstack.json`](#fstackjson), installs dependencies and
makes the first commit.

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

A template only asks for what it uses. Flags it doesn't use are ignored with a warning.

### `fstack update`

```bash
uv tool upgrade fstack
fstack update --dry-run    # see what would change
fstack update              # apply it; nothing is committed for you
```

The project needs a clean working tree, so the update lands as a single diff. Then review
`git diff`, resolve any conflicts, run what fstack prints (`setup` after dependency
changes, `migrate` after new migrations), and commit.

| Result | Meaning |
|---|---|
| ✓ added / updated / merged / removed | applied cleanly |
| ✓ renamed | the template moved a file; it moves here too, with your edits |
| ✗ conflict | both sides changed the same lines. Resolve the markers (`git diff --check` lists them). Exit code 1. |
| ! skipped | the template changed a file the project deleted or doesn't track: left as it is |
| ! kept | the template removed a file the project changed: left in place |

fstack never touches files only the project has, ignored files, `.env`, lockfiles,
`node_modules` or caches.

### `fstack doctor`

Checks the toolchain (`uv`, `git`, `bun`, `pnpm`, `node`, Docker or Apple `container`),
whether `DB_ROOT_PASSWORD` is set, and lists the templates this fstack ships.

## How updates work

```mermaid
flowchart LR
    base["<b>Base</b><br/>the template as the project<br/>last got it"]
    theirs["<b>Theirs</b><br/>the template now"]
    ours["<b>Ours</b><br/>your project today"]
    merge{{"three-way merge<br/>file by file"}}
    out["one reviewable diff<br/>nothing committed"]
    base --> merge
    theirs --> merge
    ours --> merge
    merge --> out
```

Both template versions are rendered with the project's own answers (name, ports, accent,
package manager), so only real changes reach the merge. A file the template renamed is
matched to the project's copy and moved along with your edits. If the project has Alembic
migrations of its own, fstack says when `alembic merge heads` is needed.

### `.fstack.json`

`fstack new` writes this file. Commit it. It records which template the project follows,
the fstack commit it last got, and the answers it was made with:

```json
{ "fstack": "0.4.2", "commit": "<fstack git sha>", "template": "default",
  "name": "acme-console", "title": "Acme Console", "api_port": 8410, "web_port": 5510,
  "accent": "#2f3037", "pm": "bun", "pm_version": "1.4.4" }
```

`pm_version` pins `packageManager` as the project got it, so a collaborator's newer bun
doesn't show up as a change.

Projects made before fstack 0.2.0 have no `.fstack.json`. `fstack update` starts from their
`chore: scaffold … from fstack …` commit and writes one. Without that commit, pass
`--from <fstack commit or tag>`.

## The default template

A full-stack starting point for LLM-backed internal tools, distilled from several
production FastAPI + React dashboards.

<table>
<tr><td valign="top" width="33%">

**Backend**<br/>
<sub>uv · Python 3.13 · FastAPI · SQLAlchemy Core · MySQL · Alembic</sub>

- One generated access key: dashboard sessions (hashed cookie, CSRF) and
  `Authorization: Bearer` for API clients, with per-IP sign-in throttling
- LLM providers via [llmfy](https://pypi.org/project/llmfy/): OpenAI and any
  OpenAI-compatible URL, Anthropic, Bedrock, Gemini and Cloudflare Workers AI. Keys are
  AES-256-GCM encrypted
- `run_prompt("key", vars, provider=…, model=…)`, with structured output from a pydantic
  schema and one correction round-trip
- Prompt versioning: autosaved drafts, immutable published versions (SHA-256), an active
  pointer and rollback. Prompts as code from `prompts/*.md`
- One row per LLM call: tokens (cache included), cost from models.dev rates, latency and
  prompt version
- Background jobs leased in MySQL; billed calls are never replayed
- Tests on SQLite, including an end-to-end run with a mocked transport

</td><td valign="top" width="33%">

**Frontend**<br/>
<sub>React 19 · Vite 8 · TypeScript 7 · Tailwind v4</sub>

- **Overview**: KPIs, a spend chart and the latest requests
- **Run**: pick a prompt, provider and model and try it
- **Prompts**: versions, editor, diff, publish and activate
- **Usage**: cost, requests and tokens over time by model and prompt, with a drawer per
  call
- **Configure**: providers, models and pricing, and the layout (navigation on top or in
  a sidebar) for the whole workspace
- Base UI primitives, TanStack Query and a code-split data router
- A two-row header with gliding tabs, or a sidebar with an inset page sheet; a logo and
  favicon drawn from the project's name and accent; refined button anatomy, 13px type,
  dark mode with a view-transition cross-fade, and reduced motion respected

</td><td valign="top" width="33%">

**Ops**<br/>
<sub>tasks.py · Docker · GitHub Actions</sub>

- `tasks.py` runs every task on any OS; a Makefile mirrors it on macOS and Linux
- Local MySQL with `db-up`: one shared container on Apple `container`, or docker compose
  with MySQL 8.4
- Dockerfiles for the API and an nginx-served SPA
- GitHub Actions checks
- `AGENTS.md` / `CLAUDE.md` conventions and `.claude/launch.json` for coding agents

</td></tr>
</table>

## Your own templates

Templates live under [`templates/`](templates), one folder each, and the folder name is the
template's name. A template can be any stack. fstack only needs the starter tokens it
renames, described in [CONTRIBUTING.md](CONTRIBUTING.md#working-on-a-template).

To turn an existing project into a template, run `fstack template add` from an fstack
checkout:

```bash
fstack template add survey --from ~/code/survey-portal --dry-run
fstack template add survey --from git@github.com:acme/survey-portal.git --ref v1.2
```

It takes the repo's committed files and puts the starter tokens back in place of the
project's name (every spelling), ports and accent. It flags anything that looks like a
secret. See [Add a template from a repo](CONTRIBUTING.md#add-a-template-from-a-repo).

## Upgrading fstack

```bash
uv tool upgrade fstack     # latest main
uv tool install --force git+https://github.com/ajipurn/fstack@v0.4.2   # or pin a release
```

[CHANGELOG.md](CHANGELOG.md) lists what each release changes. Its **Template** sections
show what `fstack update` will bring into your projects.

## Troubleshooting

<details>
<summary><b>"no template 'x' in this fstack"</b></summary>

The template was added after you installed. Run `uv tool upgrade fstack`.
</details>

<details>
<summary><b><code>fstack update</code>: "commit or stash your changes first"</b></summary>

The update needs a clean working tree so it lands as one diff.
</details>

<details>
<summary><b><code>fstack update</code>: "the installed fstack … is older than this project's template"</b></summary>

The project was already updated with a newer fstack, and going ahead would undo template
changes. Run `uv tool upgrade fstack`, then update again.
</details>

<details>
<summary><b><code>fstack update</code> exits with code 1</b></summary>

There are conflicts. Resolve the `<<<<<<<` markers (`git diff --check` lists them), then
commit.
</details>

<details>
<summary><b><code>seed</code> gets "Access denied" from MySQL</b></summary>

The password in `APP_DATABASE_URL` (`backend/.env`) isn't your MySQL root password. Fix it
there, and export `DB_ROOT_PASSWORD` so the next project gets the right one.
</details>

## Contributing

Issues and pull requests are welcome. [CONTRIBUTING.md](CONTRIBUTING.md) covers the
development setup, how templates work, and how releases are cut.

## License

[MIT](LICENSE) © Aji Purnomo
