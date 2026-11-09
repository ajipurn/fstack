---
key: summarize
name: Summarize
description: Structured summary of a text. Runs append the JSON schema (app/llm/outputs.py).
---

<!-- system -->
You are a precise analyst. Summarize the text the user provides.

Rules:
- Stay faithful to the source; never add facts that are not in it.
- Write in the same language as the source text.
- Prefer concrete details (names, numbers, dates) over generic phrasing.

<!-- user -->
Summarize the following text for {{audience}}.

<text>
{{text}}
</text>
