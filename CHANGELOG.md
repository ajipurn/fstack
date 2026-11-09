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

### Template (default)

- The theme toggle no longer lags one step behind: the sun/moon icon and the dark-mode
  state showed the previous theme.

## 0.1.0

First release: `fstack new` and `fstack doctor`, and the FastAPI + llmfy + MySQL + React 19
template.
