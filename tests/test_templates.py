"""The templates fstack ships: each one loads and renders without leftover tokens."""

import pytest

from fstack import cli

ROOT = cli.templates_root()
NAMES = cli.template_names(ROOT)
# A template answer → the starter token it replaces.
TOKENS = {"api_port": "8710", "web_port": "5710", "accent": "#2f3037"}


def test_ships_the_default_template():
    assert cli.DEFAULT_TEMPLATE in NAMES


@pytest.mark.parametrize("name", NAMES)
def test_template_renders_without_leftover_tokens(name):
    template = cli.load_template(ROOT, name)
    assert template.description
    names = cli.Names("demo-app", "demo_app", "Demo App")
    answers = cli.Answers(names, 8123, 5123, "#ffbe25", "bun" if "pm" in template.asks else None)
    tree = cli.render_tree(template.path, answers.with_defaults(template.asks), cli.installed_source().files_of(name))
    assert cli.MANIFEST not in tree
    for where, _ in template.install:
        assert any(path.startswith(f"{where}/") for path in tree), f"{name} installs in {where}/, which it lacks"
    for rel, entry in tree.items():
        text = cli._text(rel, entry.data)
        if text is None:
            continue
        for leftover in ("fstack-starter", "fstack_starter", "Fstack Starter"):
            assert leftover not in text, f"{name}: {leftover!r} left in {rel}"
        for key, token in TOKENS.items():
            if key in template.asks:
                assert token not in text, f"{name}: {token} left in {rel}"
