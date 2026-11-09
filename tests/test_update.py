"""End to end: a throwaway fstack repo with a tiny template, projects made from it,
then template changes merged back with `fstack update`."""

import json

import pytest
from helpers import (
    API,
    CONFIG,
    FULL,
    PAGE,
    TEMPLATE,
    commit,
    git,
    legacy_project,
    meta,
    new_project,
    rendered,
    template_commit,
)

from fstack import cli


def test_new_records_where_the_project_came_from(repo, tmp_path):
    project = new_project(tmp_path)
    assert meta(project) == {
        "fstack": cli.__version__,
        "commit": git(repo, "rev-parse", "HEAD"),
        "template": "default",
        "name": "demo-app",
        "title": "Demo App",
        "api_port": 8100,
        "web_port": 5200,
        "accent": "#ffbe25",
        "pm": "bun",
        "pm_version": "1.2.3",
    }
    assert ".fstack.json" in git(project, "ls-files")


def test_update_merges_template_changes_into_project_changes(repo, tmp_path):
    project = new_project(tmp_path)
    commit(
        project,
        "project work",
        {
            "backend/app/config.py": CONFIG.replace("setting_1 = 1", "setting_1 = 'project'"),
            "frontend/src/run.tsx": None,
            "backend/app/domain.py": "mine = True\n",
        },
    )
    template_commit(
        repo,
        {
            "backend/app/config.py": CONFIG.replace("setting_10 = 10", "setting_10 = 'template'"),
            "README.md": TEMPLATE["README.md"] + "\nFstack Starter docs on :8710\n",
            "backend/app/new.py": 'TITLE = "Fstack Starter"\n',
            "backend/app/old.py": None,
            "frontend/src/run.tsx": "export const run = 2;\n",
            "scripts/new-tool.sh": "#!/bin/sh\necho fstack-starter\n",
        },
    )
    (repo / FULL / "scripts/new-tool.sh").chmod(0o755)
    head = commit(repo, "make it executable")

    assert cli.main(["update", str(project)]) == 0

    config = (project / "backend/app/config.py").read_text()
    assert "setting_1 = 'project'" in config and "setting_10 = 'template'" in config
    assert (project / "README.md").read_text().endswith("\nDemo App docs on :8100\n")
    assert (project / "backend/app/new.py").read_text() == 'TITLE = "Demo App"\n'
    assert not (project / "backend/app/old.py").exists()
    assert not (project / "frontend/src/run.tsx").exists()  # deleted here: stays deleted
    assert (project / "scripts/new-tool.sh").read_text() == "#!/bin/sh\necho demo-app\n"
    assert (project / "scripts/new-tool.sh").stat().st_mode & 0o111
    assert (project / "backend/app/domain.py").read_text() == "mine = True\n"
    assert not (project / "backend/uv.lock").exists()
    assert meta(project)["commit"] == head
    assert git(project, "log", "-1", "--format=%s") == "project work"  # nothing committed for you


def test_overlapping_edits_leave_conflict_markers(repo, tmp_path):
    project = new_project(tmp_path)
    commit(project, "project", {"backend/app/config.py": CONFIG.replace("setting_5 = 5", "setting_5 = 'mine'")})
    template_commit(repo, {"backend/app/config.py": CONFIG.replace("setting_5 = 5", "setting_5 = 'theirs'")})

    assert cli.main(["update", str(project)]) == 1

    config = (project / "backend/app/config.py").read_text()
    assert "<<<<<<< project\nsetting_5 = 'mine'\n=======\nsetting_5 = 'theirs'\n>>>>>>> fstack" in config


def test_refuses_a_dirty_project_but_dry_run_works(repo, tmp_path):
    project = new_project(tmp_path)
    template_commit(repo, {"README.md": "# Fstack Starter\n\nnew\n"})
    (project / "scratch.txt").write_text("wip")

    assert cli.main(["update", str(project)]) == 1
    assert cli.main(["update", str(project), "--dry-run"]) == 0
    assert (project / "README.md").read_text() == rendered(TEMPLATE["README.md"])


def test_up_to_date_project_stays_clean(repo, tmp_path, capsys):
    project = new_project(tmp_path)
    assert cli.main(["update", str(project)]) == 0
    assert "nothing to update" in capsys.readouterr().out
    assert git(project, "status", "--porcelain") == ""


def test_adopts_a_project_made_before_fstack_json(repo, tmp_path):
    project, answers = legacy_project(tmp_path, repo, "chore: scaffold legacy-app from fstack 0.0.9")
    commit(project, "work", {"backend/app/config.py": CONFIG.replace("setting_0 = 0", "setting_0 = 'here'")})
    head = template_commit(repo, {"backend/app/config.py": CONFIG + "added = 'Fstack Starter'\n"})

    assert cli.main(["update", str(project)]) == 0

    config = (project / "backend/app/config.py").read_text()
    assert config.startswith("setting_0 = 'here'\n") and config.endswith("added = 'Legacy App'\n")
    assert cli.Answers.from_meta(meta(project)) == answers
    assert meta(project)["commit"] == head


def test_from_rev_adopts_a_project_without_a_scaffold_commit(repo, tmp_path, capsys):
    start = git(repo, "rev-parse", "HEAD")
    project, _ = legacy_project(tmp_path, repo, "initial import")
    template_commit(repo, {"README.md": "# Fstack Starter\n\nv2\n"})

    assert cli.main(["update", str(project)]) == 1
    assert "--from" in capsys.readouterr().err
    assert cli.main(["update", str(project), "--from", start]) == 0
    assert (project / "README.md").read_text() == "# Legacy App\n\nv2\n"


def test_fetches_old_templates_from_a_remote_install(repo, tmp_path, monkeypatch):
    url = repo.as_uri()
    cli._cached_clone(url)  # the cache only knows v1…
    template_commit(repo, {"README.md": "# Fstack Starter\n\nv2\n"})
    project = new_project(tmp_path)  # …but the project starts from v2
    v3 = template_commit(repo, {"README.md": "# Fstack Starter\n\nv3\n"})
    monkeypatch.setattr(cli, "installed_source", lambda: cli.Source(repo / "templates", url, v3))
    assert cli.main(["update", str(project)]) == 0
    assert (project / "README.md").read_text() == "# Demo App\n\nv3\n"
    commit(project, "chore: update from fstack")

    # The second update rebuilds its base (v3) from the cached history.
    v4 = template_commit(repo, {"README.md": "# Fstack Starter\n\nv4\n"})
    monkeypatch.setattr(cli, "installed_source", lambda: cli.Source(repo / "templates", url, v4))
    assert cli.main(["update", str(project)]) == 0
    assert (project / "README.md").read_text() == "# Demo App\n\nv4\n"


def test_refetches_branch_names_from_a_remote_install(repo, tmp_path, monkeypatch):
    url = repo.as_uri()
    git(repo, "branch", "release")
    cli._cached_clone(url)  # caches release → v1
    v2 = template_commit(repo, {"README.md": "# Fstack Starter\n\nv2\n"})
    git(repo, "branch", "-f", "release", v2)
    project = new_project(tmp_path)
    v3 = template_commit(repo, {"README.md": "# Fstack Starter\n\nv3\n"})
    monkeypatch.setattr(cli, "installed_source", lambda: cli.Source(repo / "templates", url, v3))

    assert cli.main(["update", str(project), "--from", "release"]) == 0  # base = v2, not the stale v1
    assert (project / "README.md").read_text() == "# Demo App\n\nv3\n"


def test_refuses_to_downgrade_with_an_older_fstack(repo, tmp_path, capsys):
    v1 = git(repo, "rev-parse", "HEAD")
    template_commit(repo, {"README.md": "# Fstack Starter\n\nv2\n"})
    project = new_project(tmp_path)
    git(repo, "checkout", "-q", v1)  # the installed fstack is now older than the project

    assert cli.main(["update", str(project)]) == 1
    assert "uv tool upgrade fstack" in capsys.readouterr().err
    assert (project / "README.md").read_text() == "# Demo App\n\nv2\n"
    assert git(project, "status", "--porcelain") == ""


def test_missing_revision_in_a_local_checkout_says_to_pull(repo, tmp_path, capsys):
    project = new_project(tmp_path)
    data = meta(project) | {"commit": "1" * 40}
    commit(project, "from a newer fstack", {".fstack.json": json.dumps(data)})

    assert cli.main(["update", str(project)]) == 1
    assert "pull it first" in capsys.readouterr().err


def test_leaves_files_git_does_not_track_alone(repo, tmp_path):
    project = new_project(tmp_path)
    commit(project, "ignore local files", {".gitignore": "local.txt\n"})
    (project / "local.txt").write_text("mine\n")
    template_commit(repo, {"local.txt": "from the template\n"})

    assert cli.main(["update", str(project)]) == 0
    assert (project / "local.txt").read_text() == "mine\n"


def test_ignored_template_files_never_reach_projects(repo, tmp_path):
    commit(repo, "ignore local template files", {".gitignore": f"{FULL}/secret.local\n"})
    (repo / FULL / "secret.local").write_text("not for projects\n")
    project = new_project(tmp_path)
    assert not (project / "secret.local").exists()

    template_commit(repo, {"README.md": "# Fstack Starter\n\nv2\n"})
    assert cli.main(["update", str(project)]) == 0  # an ignored file doesn't make the template dirty
    assert not (project / "secret.local").exists()


def test_unreadable_scaffold_commit_is_an_error(repo, tmp_path, monkeypatch, capsys):
    project = new_project(tmp_path)
    monkeypatch.setattr(cli, "extract", lambda *args: False)

    assert cli.main(["update", str(project)]) == 1
    assert "couldn't read the scaffold commit" in capsys.readouterr().err


def test_pm_version_is_frozen_per_project(repo, tmp_path, monkeypatch):
    project = new_project(tmp_path)
    monkeypatch.setattr(cli, "_tool_version", lambda tool: "9.9.9")
    template_commit(repo, {"frontend/package.json": TEMPLATE["frontend/package.json"].replace("}", '  "x": 1\n}')})

    assert cli.main(["update", str(project)]) == 0
    package = (project / "frontend/package.json").read_text()
    assert '"packageManager": "bun@1.2.3"' in package and '"x": 1' in package


def test_keeps_an_executable_bit_the_project_added(repo, tmp_path):
    project = new_project(tmp_path)
    (project / "scripts/tool.sh").chmod(0o755)
    commit(project, "make tool.sh executable")
    template_commit(repo, {"scripts/tool.sh": "#!/bin/sh\necho fstack-starter v2\n"})

    assert cli.main(["update", str(project)]) == 0
    assert (project / "scripts/tool.sh").read_text() == "#!/bin/sh\necho demo-app v2\n"
    assert (project / "scripts/tool.sh").stat().st_mode & 0o111


def test_title_with_backslashes_renders_literally(repo, tmp_path):
    project = new_project(tmp_path, "rnd", "--title", r"R\D \g<0> Hub")
    assert (project / "README.md").read_text().startswith("# R\\D \\g<0> Hub\n")
    template_commit(repo, {"README.md": "# Fstack Starter\n\nv2\n"})
    assert cli.main(["update", str(project)]) == 0
    assert (project / "README.md").read_text() == "# R\\D \\g<0> Hub\n\nv2\n"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [("accent", "red", "isn't a hex color"), ("pm", "npm", "must be one of"), ("api_port", 0, "isn't a port")],
)
def test_rejects_a_malformed_fstack_json(repo, tmp_path, capsys, field, value, message):
    project = new_project(tmp_path)
    commit(project, "hand edit", {".fstack.json": json.dumps(meta(project) | {field: value})})

    assert cli.main(["update", str(project)]) == 1
    assert message in capsys.readouterr().err


def test_template_rename_carries_project_edits(repo, tmp_path):
    project = new_project(tmp_path)
    commit(project, "edit page", {"frontend/src/page.tsx": PAGE.replace("line1 = 1", "line1 = 'project'")})
    moved = PAGE.replace("line6 = 6", "line6 = 'template'")
    template_commit(repo, {"frontend/src/page.tsx": None, "frontend/src/pages/home.tsx": moved})

    assert cli.main(["update", str(project)]) == 0
    assert not (project / "frontend/src/page.tsx").exists()
    home = (project / "frontend/src/pages/home.tsx").read_text()
    assert "line1 = 'project'" in home and "line6 = 'template'" in home


def test_dirty_template_needs_allow_dirty(repo, tmp_path, capsys):
    project = new_project(tmp_path)
    (repo / FULL / "README.md").write_text("# Fstack Starter\n\nwork in progress\n")

    assert cli.main(["update", str(project)]) == 1
    assert "--allow-dirty" in capsys.readouterr().err
    assert cli.main(["update", str(project), "--allow-dirty"]) == 0
    assert meta(project)["dirty"] is True


def test_first_update_starts_from_the_exact_scaffold(repo, tmp_path):
    # Made from uncommitted template changes that were later thrown away: the scaffold
    # commit still knows them, so the update takes them back out.
    (repo / FULL / "README.md").write_text("# Fstack Starter\n\nexperiment\n")
    project = new_project(tmp_path)
    assert meta(project)["dirty"] is True
    git(repo, "checkout", "--", f"{FULL}/README.md")
    template_commit(repo, {"backend/app/config.py": CONFIG + "more = 1\n"})

    assert cli.main(["update", str(project)]) == 0
    assert (project / "README.md").read_text() == rendered(TEMPLATE["README.md"])
    assert "dirty" not in meta(project)


def test_new_from_another_template_keeps_only_its_answers(repo, tmp_path, capsys):
    dest = tmp_path / "svc"
    args = ["new", "Demo Svc", "--template", "lite", "--dir", str(dest), "--no-install", "--api-port", "8100"]
    assert cli.main([*args, "--web-port", "5200"]) == 0
    assert "doesn't use --web-port" in capsys.readouterr().out
    assert meta(dest) == {
        "fstack": cli.__version__,
        "commit": git(repo, "rev-parse", "HEAD"),
        "template": "lite",
        "name": "demo-svc",
        "title": "Demo Svc",
        "api_port": 8100,
    }
    assert sorted(git(dest, "ls-files").split()) == [".fstack.json", "Makefile", "README.md", "backend/app/config.py"]
    # Tokens for answers the template doesn't ask stay as they are.
    assert (dest / "README.md").read_text() == "# Demo Svc API\n\nmake api  # :8100, CORS for :5710\n"


def test_unknown_template_is_refused(repo, tmp_path, capsys):
    with pytest.raises(SystemExit):
        cli.main(["new", "x", "--template", "nope", "--dir", str(tmp_path / "x")])
    assert "invalid choice" in capsys.readouterr().err

    project = new_project(tmp_path)
    commit(project, "hand edit", {".fstack.json": json.dumps(meta(project) | {"template": "gone"})})
    assert cli.main(["update", str(project)]) == 1
    assert "no template 'gone'" in capsys.readouterr().err


def test_update_follows_the_projects_own_template(repo, tmp_path):
    dest = tmp_path / "svc"
    assert cli.main(["new", "svc", "-t", "lite", "--dir", str(dest), "--no-install", "--api-port", "8100"]) == 0
    commit(dest, "work", {"backend/app/config.py": CONFIG.replace("setting_1 = 1", "setting_1 = 'mine'")})
    template_commit(repo, {"backend/app/config.py": CONFIG + "api_only = True\n"}, where=API)
    template_commit(repo, {"README.md": "# Fstack Starter\n\ndefault v2\n"})
    (repo / FULL / "README.md").write_text("# Fstack Starter\n\nwork in progress\n")  # another template is dirty

    assert cli.main(["update", str(dest)]) == 0
    config = (dest / "backend/app/config.py").read_text()
    assert "setting_1 = 'mine'" in config and config.endswith("api_only = True\n")
    assert (dest / "README.md").read_text().startswith("# Svc API")  # the default template's README never applies
    assert meta(dest)["template"] == "lite" and "dirty" not in meta(dest)


def test_update_bridges_the_move_from_template_to_templates(repo, tmp_path):
    # Older fstack kept its one template at template/; a project made then still updates.
    git(repo, "mv", FULL, "template")
    old = commit(repo, "the old layout")
    names = cli.Names("old-app", "old_app", "Old App")
    answers = cli.Answers(names, 8300, 5300, "#2f3037", "bun", "1.2.3")
    project = tmp_path / "old"
    cli.write_tree(cli.render_tree(repo / "template", answers), project)
    data = answers.to_meta(cli.load_template(repo, "template"), old)
    data.pop("template")  # written before templates had names
    (project / ".fstack.json").write_text(json.dumps(data))
    git(project.parent, "init", "-q", "-b", "main", str(project))
    commit(project, "initial import")  # no scaffold commit: the base comes from fstack's history
    git(repo, "mv", "template", FULL)
    template_commit(repo, {"README.md": "# Fstack Starter\n\nafter the move\n"})

    assert cli.main(["update", str(project)]) == 0
    assert (project / "README.md").read_text() == "# Old App\n\nafter the move\n"
    assert meta(project)["template"] == "default"


def test_doctor_lists_the_templates(repo, capsys):
    (repo / API / "README.md").write_text("changed\n")
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "default      API and dashboard" in out
    assert "lite         API only (uncommitted changes)" in out
