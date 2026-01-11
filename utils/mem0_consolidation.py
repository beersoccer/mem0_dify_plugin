"""Mem0 helpers for long-term memory consolidation.

Builds per-subtype Mem0 configs (prompt isolation) and provides add() helpers that
attach required metadata.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from mem0 import Memory

from .config_builder import build_local_mem0_config
from .prompts import (
    EPISODIC_FACT_EXTRACTION_PROMPT,
    PROCEDURAL_FACT_EXTRACTION_PROMPT,
    SEMANTIC_FACT_EXTRACTION_PROMPT,
    build_update_memory_prompt,
)

MemorySubtype = Literal["semantic", "episodic", "procedural"]


@dataclass(frozen=True)
class SubtypeMem0:
    subtype: MemorySubtype
    memory: Memory


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _subtype_extraction_prompt(subtype: MemorySubtype) -> str:
    if subtype == "semantic":
        return SEMANTIC_FACT_EXTRACTION_PROMPT
    if subtype == "episodic":
        return EPISODIC_FACT_EXTRACTION_PROMPT
    return PROCEDURAL_FACT_EXTRACTION_PROMPT


def build_subtype_memories(credentials: dict[str, Any]) -> dict[MemorySubtype, SubtypeMem0]:
    """Create 3 Mem0 Memory instances with subtype-specific prompts."""
    base = build_local_mem0_config(credentials)
    memories: dict[MemorySubtype, SubtypeMem0] = {}
    for subtype in ("semantic", "episodic", "procedural"):
        cfg = copy.deepcopy(base)
        cfg["custom_fact_extraction_prompt"] = _subtype_extraction_prompt(subtype)  # type: ignore[index]
        cfg["custom_update_memory_prompt"] = build_update_memory_prompt(subtype=subtype)  # type: ignore[index]
        memories[subtype] = SubtypeMem0(subtype=subtype, memory=Memory.from_config(cfg))
    return memories


def mem0_add_segment(
    *,
    mem: Memory,
    messages: list[dict[str, str]],
    user_id: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Call mem0 add(infer=True) with required ids and metadata."""
    return mem.add(
        messages,
        user_id=user_id,
        metadata=metadata,
        infer=True,
    )


def build_memory_metadata(
    *,
    subtype: MemorySubtype,
    app_id: str | None,
    conversation_id: str,
    segment_id: str,
    run_at: str,
    message_id_range: str,
) -> dict[str, Any]:
    md: dict[str, Any] = {
        "memory_subtype": subtype,
        "source": "dify_consolidation",
        "conversation_id": conversation_id,
        "segment_id": segment_id,
        "run_at": run_at,
        "extracted_at": _utc_now_iso(),
        "message_id_range": message_id_range,
        "schema_version": "v1",
    }
    if app_id:
        md["app_id"] = app_id
    return md


