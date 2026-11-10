"""Structured output, keyed by prompt.

A prompt listed in OUTPUTS must answer with JSON matching its schema: the schema
is appended to the system prompt, the reply is validated, and one correction
round-trip is attempted. Every other prompt returns plain text.

Add a prompt: write `prompts/<key>.md`, run `uv run tasks.py seed`; list it here only if
code needs typed data back.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Summary(BaseModel):
    title: str = Field(description="Short headline, at most 8 words")
    summary: str = Field(description="Two or three sentences")
    key_points: list[str] = Field(description="3-5 bullet points", max_length=8)
    sentiment: Literal["positive", "neutral", "negative", "mixed"]


OUTPUTS: dict[str, type[BaseModel]] = {
    "summarize": Summary,
}
