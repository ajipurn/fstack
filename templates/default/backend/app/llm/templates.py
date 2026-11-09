"""Prompt templates use {{variable}} placeholders (same syntax llmfy validates)."""

import json
import re
from typing import Any

NAME = r"[a-z][a-z0-9_]{0,59}"
PLACEHOLDER = re.compile(r"\{\{\s*(" + NAME + r")\s*\}\}")


def placeholders(*templates: str) -> list[str]:
    """Variables in first-seen order across all templates."""
    seen: dict[str, None] = {}
    for template in templates:
        for name in PLACEHOLDER.findall(template):
            seen.setdefault(name, None)
    return list(seen)


def check_template(template: str) -> None:
    """Reject stray braces like `{{ Name }}` or `{{x` that would silently not render."""
    remaining = PLACEHOLDER.sub("", template)
    if "{{" in remaining or "}}" in remaining:
        raise ValueError(
            "Placeholders must look like {{variable_name}} (lowercase, digits, underscores)."
        )


def normalize(template: str) -> str:
    """`{{ name }}` → `{{name}}` so llmfy's exact-match replacement finds it."""
    return PLACEHOLDER.sub(lambda m: "{{" + m.group(1) + "}}", template)


def as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def render(template: str, variables: dict[str, Any]) -> str:
    return PLACEHOLDER.sub(lambda m: as_text(variables.get(m.group(1), "")), template)


def missing(required: list[str], variables: dict[str, Any]) -> list[str]:
    return [name for name in required if name not in variables]
