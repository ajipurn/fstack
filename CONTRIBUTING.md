# Contributing to fstack

fstack is a Python CLI (`src/fstack/`, no dependencies) and the templates it ships
(`templates/<name>/`). For using it, see the [README](README.md).

- [Set up](#set-up)
- [Making a change](#making-a-change)
- [Working on a template](#working-on-a-template)
- [Add a template from a repo](#add-a-template-from-a-repo)
- [Releasing](#releasing)

## Set up

```bash
git clone https://github.com/ajipurn/fstack ~/Developer/Projects/fstack
cd ~/Developer/Projects/fstack
uv tool install --force --editable .
uv run pytest
```

With an editable install, the `fstack` command runs this checkout, on whatever branch is
checked out.

- Template edits apply to the next `fstack new` right away. Files git ignores in
  `templates/` are never copied.
- `fstack doctor` shows the checkout's commit and which templates have uncommitted
  changes.

## Making a change

1. Branch from `main`, and open a pull request.
2. Add a line to [CHANGELOG.md](CHANGELOG.md) under the unreleased version:
   - **fstack** for CLI changes.
   - **Template (name)** for template changes. These are what `fstack update` brings into
     projects, so call out migrations, new dependencies and `.env` changes.
3. Make sure `uv run pytest` passes. It renders every template and fails on leftover
   starter tokens. CI runs it on Linux and Windows, and builds and checks a new project
   from the default template on both.
   - Windows has no file modes or easy symlinks: tests that need them use `@posix_only`.
   - Read and write text with `encoding="utf-8"` (and `newline="\n"` when writing): the
     Windows default is the local code page and CRLF.
   - A template's tasks belong in its `tasks.py`, which runs everywhere; its Makefile only
     forwards to it.
4. Merge with a **merge commit**, never squash or rebase. Projects record the fstack commit
   they came from in `.fstack.json`, and `fstack update` needs that commit to stay in
   `main`'s history.

**Commit template changes before you try them on a project.**

- `.fstack.json` records the fstack commit, so a later update can't rebuild uncommitted
  edits.
- `fstack update` refuses while the project's template has uncommitted changes, unless you
  pass `--allow-dirty`. It then notes this in `.fstack.json`.
- `fstack new` warns about uncommitted changes.

## Working on a template

Each `templates/<name>/` is a runnable project named "Fstack Starter". `fstack new`
rewrites these starter tokens, so keep them intact:

| Token | Becomes the project's |
|---|---|
| `fstack-starter`, `fstack_starter`, `Fstack Starter` | name: slug, snake case, title |
| `8710`, `5710` | API and web ports |
| `#2f3037` | accent (the text color marked `/* fstack:accent-ink */` follows it) |

To run the default template, copy `backend/.env.example` to `backend/.env` once and fill it
in (its comments say how). Then:

```bash
uv run templates/default/tasks.py setup
uv run templates/default/tasks.py db-up
uv run templates/default/tasks.py seed
uv run templates/default/tasks.py dev
```

`.claude/launch.json` has `template-api` and `template-web` for Claude Code previews.

Next to the files, `fstack-template.toml` says what the template is. It is never copied
into projects:

```toml
description = "FastAPI + llmfy + MySQL API and a React dashboard"   # shown by `fstack doctor`
answers = ["api_port", "web_port", "accent", "pm"]   # what `fstack new` asks; the rest stay as they are
install = [{ dir = "backend", run = "uv sync --compile-bytecode" }, { dir = "frontend", run = "{pm} install" }]
next = [["uv run tasks.py dev", "api :{api_port} + web :{web_port}"]]   # printed after `fstack new`
```

A new template, in any stack, is a new folder with that file, and the folder's name is the
template's name. `fstack template add` writes both.

## Add a template from a repo

```bash
fstack template add survey --from ~/Developer/Projects/survey-portal --dry-run
fstack template add survey --from ~/Developer/Projects/survey-portal
fstack template add board --from git@github.com:acme/acme-board.git
fstack template add board-v1 --from https://github.com/acme/acme-board.git --ref v1.2
fstack new demo -t survey --dir /tmp/survey-demo  # try it, then commit templates/survey
```

This works in an fstack checkout (editable install). Commit the new template and open a
pull request so the team gets it.

It is `fstack new` in reverse.

1. **What it takes.** The repo's committed files at its latest commit, or at the branch,
   tag or commit `--ref` names. It never takes `.env` or `.fstack.json`.
2. **What it replaces.** The project's own name in every spelling fstack uses
   (`survey-portal`, `survey_portal`, "Survey Portal"), its ports and its accent go back
   to the [starter tokens](#working-on-a-template). That way `fstack new -t survey`
   renames them for each new project.
3. **Where the answers come from**, in this order:
   1. The repo's `.fstack.json`.
   2. Its files, when fstack made the repo.
   3. A guess:
      - the name from `package.json` / `pyproject.toml` / `go.mod` / `Cargo.toml`, or the
        folder
      - the title from the README heading
      - the ports from the Makefile (`API_PORT ?=`, `WEB_PORT ?=`) or `vite.config`

   Fix a wrong guess with `--source-name`, `--source-title`, `--api-port`, `--web-port`
   or `--accent`.
4. **The install steps.** The original template's, or read from the repo (`uv sync`,
   `{pm} install`, `go mod download`, `cargo fetch`).

It reports these and leaves them to you:

- what looks like a secret
- other spellings of the name (`SurveyPortal`)
- paths with the name in them (fstack never renames paths)
- starter tokens the repo already had

A git URL is cloned with your own git credentials, so private repos work. Names too common
to replace safely (`app`, `api`, `web`…) are refused.

## Releasing

Versions are `vX.Y.Z` tags on `main`, following [SemVer](https://semver.org). The top of
[CHANGELOG.md](CHANGELOG.md) says what bumps what. The version is set in one place,
`src/fstack/__init__.py`.

1. On a branch:
   - Set `__version__`.
   - In CHANGELOG, replace "unreleased" with the date.
2. Merge it into `main` with a merge commit.
3. Tag and push:

   ```bash
   git tag -a v0.3.0 -m "fstack 0.3.0" && git push origin main v0.3.0
   ```

4. Tell the team to run `uv tool upgrade fstack`, read the CHANGELOG, and run
   `fstack update` in their projects.

Versions are for people: what changed, what to pin, `fstack update --from v0.1.0`.
`fstack update` itself goes by commits, so a project made between releases updates fine.
