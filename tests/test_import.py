"""`fstack template add`: a repo becomes a template, and projects made from that template
come out as the repo did, renamed."""

import json
import tomllib

from helpers import FULL, commit, git, meta, new_project, write

from fstack import cli

OTHER = cli.Answers(cli.Names("talent-review", "talent_review", "Talent Review"), 8300, 5300, "#123456", "pnpm", "9.0.0")


def manifest(repo, name):
    return tomllib.loads((repo / "templates" / name / cli.MANIFEST).read_text())


def test_a_project_made_by_fstack_round_trips(repo, tmp_path):
    project = new_project(tmp_path)  # Demo App · 8100 / 5200 · #ffbe25 · bun 1.2.3
    domain = 'NAME = "Demo App"\nDB = "demo_app"\nURL = "http://127.0.0.1:8100"\n'
    commit(project, "domain", {"backend/app/domain.py": domain})

    assert cli.main(["template", "add", "demo", "--from", str(project)]) == 0

    spec = manifest(repo, "demo")
    assert spec["answers"] == ["api_port", "web_port", "accent", "pm"]
    assert spec["install"] == manifest(repo, "default")["install"]  # what the default template installs
    assert not (repo / "templates/demo" / cli.META).exists()
    # The same project as the default template plus the domain code, for any answers.
    made = cli.render_tree(repo / "templates/demo", OTHER)
    expected = cli.render_tree(repo / FULL, OTHER)
    assert made.pop("backend/app/domain.py").data.decode() == (
        'NAME = "Talent Review"\nDB = "talent_review"\nURL = "http://127.0.0.1:8300"\n'
    )
    assert made == expected


def test_a_repo_fstack_did_not_make(repo, tmp_path, capsys):
    source = tmp_path / "acme"
    write(
        source,
        {
            "package.json": '{"name": "@acme/acme-board", "packageManager": "bun@1.1.0"}\n',
            "bun.lock": "{}\n",
            "Makefile": "WEB_PORT ?= 5300\n\nhelp:\n\t@echo targets\n",
            "README.md": "# Acme Board\n\nmake dev  # :5300\n",
            "src/app.ts": 'export const TITLE = "Acme Board";\nconst KEY = "acme-board:theme";\nclass AcmeBoard {}\n',
            "src/keys.ts": 'export const key = "sk-abcdefghijklmnopqrstuvwxyz";\n',
            ".env": "SECRET_KEY=abcdefghijklmnop\n",
        },
    )
    git(source.parent, "init", "-q", "-b", "main", str(source))
    commit(source, "acme")

    assert cli.main(["template", "add", "board", "--from", source.as_uri()]) == 0  # a git URL: cloned
    out = capsys.readouterr().out
    assert "looks like a secret" in out and "src/keys.ts:1" in out
    assert "other spellings" in out and "src/app.ts:3" in out  # AcmeBoard
    assert "left out: .env" in out

    spec = manifest(repo, "board")
    assert spec["answers"] == ["web_port", "pm"]
    assert spec["install"] == [{"dir": ".", "run": "{pm} install"}]
    assert spec["next"] == [["make help", "what you can run"]]
    assert not (repo / "templates/board/.env").exists()
    assert (repo / "templates/board/src/app.ts").read_text().startswith('export const TITLE = "Fstack Starter";')

    dest = tmp_path / "thing"
    assert cli.main(["new", "My Thing", "-t", "board", "--dir", str(dest), "--no-install", "--web-port", "5400"]) == 0
    assert (dest / "src/app.ts").read_text() == (
        'export const TITLE = "My Thing";\nconst KEY = "my-thing:theme";\nclass AcmeBoard {}\n'
    )
    assert json.loads((dest / "package.json").read_text())["name"] == "@acme/my-thing"
    assert (dest / "README.md").read_text() == "# My Thing\n\nmake dev  # :5400\n"
    assert meta(dest)["template"] == "board" and meta(dest)["web_port"] == 5400


def test_one_word_names_keep_their_identifiers(repo, tmp_path):
    source = tmp_path / "crm"
    write(source, {"README.md": "# Crm\n", "app.py": 'DB = "mysql://x/crm"\nKEY = "crm:theme"\nPKG = "crm-web"\n'})
    git(source.parent, "init", "-q", "-b", "main", str(source))
    commit(source, "crm")

    assert cli.main(["template", "add", "crm", "--from", str(source)]) == 0
    assert (repo / "templates/crm/app.py").read_text() == (
        'DB = "mysql://x/fstack_starter"\nKEY = "fstack-starter:theme"\nPKG = "fstack-starter-web"\n'
    )


def test_refusals(repo, tmp_path, capsys):
    project = new_project(tmp_path)
    assert cli.main(["template", "add", "default", "--from", str(project)]) == 1
    assert "already exists" in capsys.readouterr().err

    plain = tmp_path / "plain"
    plain.mkdir()
    assert cli.main(["template", "add", "plain", "--from", str(plain)]) == 1
    assert "isn't a git repository" in capsys.readouterr().err

    generic = tmp_path / "x"
    write(generic, {"package.json": '{"name": "app"}\n'})
    git(generic.parent, "init", "-q", "-b", "main", str(generic))
    commit(generic, "x")
    assert cli.main(["template", "add", "gen", "--from", str(generic)]) == 1
    assert "too common" in capsys.readouterr().err
    assert cli.main(["template", "add", "gen", "--from", str(generic), "--source-name", "acme-app"]) == 0

    assert cli.main(["template", "add", "dry", "--from", str(project), "--dry-run"]) == 0
    assert not (repo / "templates/dry").exists()


def test_takes_a_branch_tag_or_commit(repo, tmp_path, capsys):
    source = tmp_path / "acme-board"
    write(source, {"README.md": "# Acme Board\n\none\n"})
    git(source.parent, "init", "-q", "-b", "main", str(source))
    first = commit(source, "one")
    git(source, "tag", "v1")
    git(source, "branch", "old")
    commit(source, "two", {"README.md": "# Acme Board\n\ntwo\n"})

    cases = {"tag": ("v1", str(source)), "branch": ("old", source.as_uri()), "sha": (first, source.as_uri())}
    for name, (ref, where) in cases.items():
        assert cli.main(["template", "add", name, "--from", where, "--ref", ref]) == 0, name
        assert (repo / "templates" / name / "README.md").read_text() == "# Fstack Starter\n\none\n", name
    assert f"@ {first[:7]}" in (repo / "templates/sha" / cli.MANIFEST).read_text()

    assert cli.main(["template", "add", "latest", "--from", source.as_uri()]) == 0
    assert (repo / "templates/latest/README.md").read_text() == "# Fstack Starter\n\ntwo\n"

    capsys.readouterr()
    assert cli.main(["template", "add", "nope", "--from", str(source), "--ref", "missing"]) == 1
    assert "no branch, tag or commit 'missing'" in capsys.readouterr().err
    assert cli.main(["template", "add", "nope", "--from", str(source), "--ref=--upload-pack=x"]) == 1
    assert "isn't a branch, tag or commit" in capsys.readouterr().err
