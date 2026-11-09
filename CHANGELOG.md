# Changelog

fstack follows [SemVer](https://semver.org). While it is 0.x, a minor release adds features
or template changes a project has to act on (a migration, a new dependency, a
`.fstack.json` change), and a patch release fixes things. **Template** lists what
`fstack update` brings into projects made from that template.

## 0.2.0 — unreleased

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
