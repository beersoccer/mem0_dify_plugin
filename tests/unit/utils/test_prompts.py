from __future__ import annotations

from utils.prompts import (
    EPISODIC_FACT_EXTRACTION_PROMPT,
    PROCEDURAL_FACT_EXTRACTION_PROMPT,
    SEMANTIC_FACT_EXTRACTION_PROMPT,
    build_update_memory_prompt,
)


def test_fact_prompts_enforce_strict_json() -> None:
    for prompt in (
        SEMANTIC_FACT_EXTRACTION_PROMPT,
        EPISODIC_FACT_EXTRACTION_PROMPT,
        PROCEDURAL_FACT_EXTRACTION_PROMPT,
    ):
        assert "Return ONLY the JSON object" in prompt
        assert "single-line strings" in prompt
        assert "no raw newlines" in prompt


def test_update_prompt_requires_minimal_changes_only() -> None:
    prompt = build_update_memory_prompt(subtype="semantic")
    assert "Include ONLY items that require a change" in prompt
    assert "return { \"memory\": [] }" in prompt
    assert "Memory text must be a single line" in prompt

