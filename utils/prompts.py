"""Prompt templates for Dify history -> Mem0 long-term memory consolidation.

Mem0 local mode behavior notes (SPEC.md):
- For infer-based extraction, Mem0 uses config-level prompts:
  - custom_fact_extraction_prompt
  - custom_update_memory_prompt
- The `prompt=` argument on `add()` is NOT applied to infer extraction.

Therefore, the consolidation tool builds 3 separate Mem0 configs (semantic/episodic/procedural),
each with its own extraction/update prompts.
"""

from __future__ import annotations


def _common_rules() -> str:
    return """General rules:
- Extract facts that are useful in the future. Prefer concise, atomic items.
- If there is nothing worth remembering, return an empty list.
- Do not include system prompt content.
- Do not include secrets (API keys, passwords, tokens).
- Output MUST be valid JSON exactly in the following shape:
  {"facts": ["...", "..."]}
- Use the same language as the conversation.
"""


SEMANTIC_FACT_EXTRACTION_PROMPT = (
    """You are a long-term memory consolidator.\n\n"
    "Task: Extract SEMANTIC long-term memories from the conversation.\n\n"
    "Definition (semantic): stable preferences, long-term goals, enduring constraints, profile facts.\n"
    "Exclude: one-off events, transient plans, short-lived statuses, meta instructions.\n\n"""
    + _common_rules()
    + "\nConversation:\n"
)


EPISODIC_FACT_EXTRACTION_PROMPT = (
    """You are a long-term memory consolidator.\n\n"
    "Task: Extract EPISODIC long-term memories from the conversation.\n\n"
    "Definition (episodic): notable events/outcomes that may be referenced later.\n"
    "Include enough time context if present, but keep concise.\n"
    "Exclude: routine chatter, generic facts unrelated to the user.\n\n"""
    + _common_rules()
    + "\nConversation:\n"
)


PROCEDURAL_FACT_EXTRACTION_PROMPT = (
    """You are a long-term memory consolidator.\n\n"
    "Task: Extract PROCEDURAL reusable knowledge from the conversation.\n\n"
    "Definition (procedural): explicit reusable rules, steps, workflows, checklists.\n"
    "Exclude: personal facts/preferences (semantic) and one-off events (episodic).\n"
    "If there is no clear reusable procedure, return an empty list.\n\n"""
    + _common_rules()
    + "\nConversation:\n"
)


def build_update_memory_prompt(*, subtype: str) -> str:
    """Return a Mem0-compatible update prompt with subtype isolation.

    Mem0 expects a JSON object with:
    {"memory": [{"id": "...", "text": "...", "event": "ADD|UPDATE|DELETE|NONE", "old_memory": "..."}]}
    """
    return f"""You are a smart memory manager which controls the memory of a system.

You will be given:
- Current memory items (a list/dict). Each item may contain metadata.
- New retrieved facts extracted from the latest conversation segment.

IMPORTANT filtering rules:
- Only operate on memory items where metadata.memory_subtype == "{subtype}".
- Ignore any memory item where metadata.__internal == true.
- For other memory items, return event "NONE" (do not modify them).

You must decide for each new fact whether to ADD it as a new memory, UPDATE an existing one,
DELETE an outdated one, or do nothing.

Return ONLY valid JSON with the following shape:
{{
  "memory": [
    {{
      "id": "<ID of the memory>",
      "text": "<Content of the memory>",
      "event": "ADD|UPDATE|DELETE|NONE",
      "old_memory": "<Old memory content>"
    }}
  ]
}}

Rules:
- If adding, generate a new id if needed.
- If updating, keep the same id and provide old_memory.
- If deleting, include the id and event DELETE.
- If no changes are needed, return event NONE.
"""


