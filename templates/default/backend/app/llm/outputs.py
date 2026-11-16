"""Structured output, keyed by prompt.

A prompt listed in OUTPUTS must answer with JSON matching its schema: the schema
is appended to the system prompt, the reply is validated, and one correction
round-trip is attempted. Every other prompt returns plain text.

Add a prompt in the dashboard (Prompts → Create) or as `prompts/<key>.md` followed by
`uv run tasks.py seed`; list it here only if code needs typed data back:

    class Summary(BaseModel):
        title: str = Field(description="Short headline, at most 8 words")
        key_points: list[str] = Field(description="3-5 bullet points", max_length=8)

    OUTPUTS = {"summarize": Summary}
"""

from pydantic import BaseModel

OUTPUTS: dict[str, type[BaseModel]] = {}
