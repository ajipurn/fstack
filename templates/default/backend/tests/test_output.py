import time

import pytest

from app.llm.output import extract_json


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('```JSON\r\n{"a": 1}\r\n```\r\n', '{"a": 1}\r'),
        ('  ```\n\n{"a": 1}```  \n', '{"a": 1}'),
        ('```json \t\n \n{"a": 1}\n\n```', '{"a": 1}\n'),
        ("```json\n```inner```\n{}\n```", "```inner```\n{}"),
        ('```json\n{"a": 1}\n```\nmore', '{"a": 1}'),
        ('Here: {"a": 1} done', '{"a": 1}'),
        ("```\n", "```\n"),
    ],
)
def test_extract_json(text: str, expected: str) -> None:
    assert extract_json(text) == expected


@pytest.mark.parametrize("header", ["```", "```json"])
def test_extract_json_is_linear_on_an_unclosed_fence(header: str) -> None:
    # Took many seconds when the fence regex backtracked over every newline.
    text = header + "\n" * 100_000 + "x"
    started = time.perf_counter()
    assert extract_json(text) == text
    assert time.perf_counter() - started < 1.0
