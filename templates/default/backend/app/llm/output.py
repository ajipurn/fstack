"""Structured output without provider JSON modes: schema in the system prompt,
strict validation, one correction round-trip. Works with every provider kind."""

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n?```\s*$", re.S | re.I)


class OutputInvalid(ValueError):
    def __init__(self, feedback: str) -> None:
        super().__init__(feedback)
        self.feedback = feedback


def schema_instructions(model: type[BaseModel]) -> str:
    schema = json.dumps(model.model_json_schema(), ensure_ascii=False)
    return (
        "\n\nRespond with a single JSON object only — no prose, no code fences. "
        f"It must validate against this JSON Schema:\n{schema}"
    )


def extract_json(text: str) -> str:
    fenced = _FENCE.match(text)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if 0 <= start < end else text


def parse(model: type[BaseModel], text: str) -> dict[str, Any]:
    try:
        return model.model_validate_json(extract_json(text)).model_dump(mode="json")
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'root'}: {err['msg']}"
            for err in exc.errors()[:8]
        )
        raise OutputInvalid(problems) from exc


def correction(feedback: str) -> str:
    return (
        f"\n\nYour previous answer was rejected: {feedback}\nAnswer again with corrected JSON only."
    )
