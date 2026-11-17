# Changelog

fstack follows [SemVer](https://semver.org). While it is 0.x, a minor release adds features
or template changes a project has to act on (a migration, a new dependency, a
`.fstack.json` change), and a patch release fixes things. **Template** lists what
`fstack update` brings into projects made from that template.

## 0.4.2 — 2026-11-17

### Template (default)

- **Configure → Layout: navigation on top or in a sidebar**, chosen from the dashboard
  for the whole workspace. The sidebar groups the pages (Workspace, Settings), shows the
  environment under the app's name and the account at its foot, and sets the page on an
  inset sheet; the current page is a raised chip that springs between routes. The switch
  cross-fades, and below 768px the sidebar folds back into the header.
  - Stored in a new `fstack_settings` table (`GET`/`PUT /api/settings`), so **run
    `uv run tasks.py migrate`** after `fstack update` (migration `0003`). Settings with no
    row read as their defaults in `services/settings.py`; adding one needs no migration.
- **The logo and favicon follow the project's name.** Both show its initials ("Acme
  Console" → AC) on the accent, instead of a fixed "F". `APP_NAME` moved to
  `frontend/src/app/brand.ts`; `vite.config.ts` draws the favicon from it and from the
  accent in `tokens.css`, so renaming the app or changing the accent updates both.
  `public/favicon.svg` is gone.

## 0.4.1 — 2026-11-16

### Template (default)

- **Highlighted, copyable payloads in the call drawer** (Usage → a request). System, User
  and Response sit in labelled blocks with syntax highlighting (JSON, also inside prose,
  prompt markdown and `{{placeholders}}`), a **Copy** button, and folding past ~16 lines.
  In the User message, each template variable's value is marked with its name, matched
  against the prompt version's template, so older calls get the marks too. A Response that
  is a JSON document is pretty-printed, and the drawer header copies the whole call as
  JSON. New primitives: `ui/CodeBlock` and `ui/CopyButton`. No migration, no new
  dependency.

## 0.4.0 — 2026-11-16

### Template (default)

- **Tables start with `fstack_`** (`fstack_llm_calls`, `fstack_prompts`…), so a project can
  share a database that already has other tables. Alembic keeps its revision in
  `fstack_alembic_version` and autogenerate only sees `fstack_*` tables, so another app's
  tables and its own `alembic_version` are left alone. CHECK and foreign key names take the
  prefix too (MySQL scopes them to the database); index names don't change.
  - The first `uv run tasks.py migrate` (or `seed`) after `fstack update` renames an
    existing project's tables, CHECK and foreign keys, and moves its revision out of
    `alembic_version`. Data stays as it is.
  - Raw SQL and revisions of your own that name fstack's tables need the new names; tables
    you added yourself keep theirs.
- `fstack_model_prices` keeps only the models.dev catalogs in use: the first-party ones (the
  fallback for gateways and "best match" providers) plus each provider's pricing catalog,
  instead of every catalog (~8,000 rows). Saving a provider loads its catalog when it isn't
  there yet; a failed download still saves the provider. The next `uv run tasks.py prices`
  (or **Sync from models.dev**) drops catalogs no provider uses.
- **Cloudflare Workers AI provider.** A **Workers AI** preset on Configure → Providers takes
  the account id and an API token (Workers AI Read + Edit). It is stored as an
  OpenAI-compatible provider at `https://api.cloudflare.com/client/v4/accounts/<id>/ai/v1`
  (Chat Completions, or Responses for gpt-oss), so there is no migration. **Load models**
  lists the account's Text Generation models through Cloudflare's model search (Workers AI
  has no `/models`), and calls are priced from the `cloudflare-workers-ai` catalog, also
  when the provider's pricing catalog is left blank.
- **No example prompts.** `backend/prompts/rewrite.md` and `summarize.md` and the `Summary`
  output are gone, so a new project starts with an empty Prompts page. `fstack update`
  removes the two files where you left them unchanged; prompts already in the database
  stay. Keep `summarize` structured by listing your own model in `app/llm/outputs.py`.
- **Five pricing catalogs by default**: OpenAI, Anthropic, Google, Bedrock and Cloudflare
  Workers AI (Mistral, xAI and DeepSeek are no longer loaded unless a provider uses them).
  The next `uv run tasks.py prices` drops the ones no provider uses.
- The **OpenRouter** and **Ollama** presets are gone from Configure → Providers; the OpenAI
  preset still takes any OpenAI-compatible URL.
- The Overview page drops the **Setup** checklist; the spend chart takes the full width.
- Tables (latest requests, usage requests, models) no longer sit under a panel header:
  their title and filters are a `SectionHeader` above the panel.
- **Sound is off by default.** The account menu's **Enable sounds** turns it on, and the
  choice is remembered per browser.

## 0.3.0 — 2026-11-10

### fstack

- Runs on Windows. `fstack new` and `fstack update` no longer stop at the first file they
  write (`O_NOFOLLOW` is POSIX-only), keep files byte for byte (no CRLF), read and print
  UTF-8 whatever the console's code page, and run `pnpm.cmd`-style tools. Windows files
  have no executable bit, so there a mode never counts as a change.
- fstack's own files are LF on every OS (`.gitattributes`), so a Windows checkout renders
  templates as they are.
- `fstack doctor` drops `python3` (uv brings Python), lists `make` as an optional shortcut,
  and Apple `container` only on macOS.
- After `fstack update`, the next steps are one command per line and name the project's
  `tasks.py` when it has one.

### Template (default)

- **`tasks.py`** runs every task on macOS, Linux and Windows: `uv run tasks.py dev`,
  `uv run tasks.py help` for the list. It replaces `scripts/mysql.sh` (removed), and the
  Makefile now only forwards to it, so `make dev` still works on macOS and Linux.
- `.gitattributes` keeps the project's files LF on every OS, which `fstack update` merges
  against.
- Docs, error messages, `.claude/launch.json` and CI name `uv run tasks.py <task>`.
- The `revision` task takes the message as words: `uv run tasks.py revision add widgets`
  (`make revision m="add widgets"` still works).

## 0.2.0 — 2026-11-09

### fstack

- `fstack update` merges what changed in a project's template since it was made (or last
  updated) into it, file by file, keeping the project's own edits; overlapping edits get
  conflict markers. `--dry-run`, `--from <rev>`, `--allow-dirty`.
- `fstack new` writes `.fstack.json` (fstack version and commit, template, answers).
  Projects made before it are adopted from their `chore: scaffold …` commit.
- Several templates: each is `templates/<name>/` with an `fstack-template.toml` (answers,
  install and next steps). The original one is `default`; `fstack new -t <name>` picks
  another, and `fstack doctor` lists them.
- `fstack template add <name> --from <path|git url> [--ref <branch|tag|commit>]` turns an
  existing repo into a template (`fstack new` in reverse).
- `fstack update` and `fstack new --force` no longer write or delete through a symlink
  (or a symlinked `.fstack.json`) that leads outside the project or into `.git`; they
  stop with an error and change nothing. Symlinks that stay inside the project work as
  before.
- `fstack new` creates `backend/.env` (MySQL root password, app keys) readable only by
  you from the start, instead of narrowing its permissions after writing it.

### Template (default)

- The theme toggle no longer lags one step behind: the sun/moon icon and the dark-mode
  state showed the previous theme.
- An Anthropic or Google provider saved without an API key is refused instead of quietly
  using the server's `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `GEMINI_API_KEY` (which, for
  Anthropic, went to whatever base URL the provider named). Save the key on the provider.
- Parsing a structured-output reply no longer slows down on a reply that opens a code
  fence and then has a very long run of newlines.

## 0.1.0

First release: `fstack new` and `fstack doctor`, and the FastAPI + llmfy + MySQL + React 19
template.
