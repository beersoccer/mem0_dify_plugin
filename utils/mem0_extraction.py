"""Mem0 helpers for long-term memory extraction.

Builds per-subtype Mem0 configs (prompt isolation) and provides add() helpers that
attach required metadata.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from .config_builder import build_local_mem0_config
from .logger import get_logger
from .mem0_client import Memory
from .prompts import (
    EPISODIC_FACT_EXTRACTION_PROMPT,
    MEMORY_CLASSIFICATION_PROMPT,
    PROCEDURAL_FACT_EXTRACTION_PROMPT,
    SEMANTIC_FACT_EXTRACTION_PROMPT,
    build_update_memory_prompt,
)

logger = get_logger(__name__)

MemorySubtype = Literal["semantic", "episodic", "procedural"]


@dataclass(frozen=True)
class SubtypeMem0:
    subtype: MemorySubtype
    memory: Memory


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _subtype_extraction_prompt(subtype: MemorySubtype) -> str:
    if subtype == "semantic":
        return SEMANTIC_FACT_EXTRACTION_PROMPT
    if subtype == "episodic":
        return EPISODIC_FACT_EXTRACTION_PROMPT
    return PROCEDURAL_FACT_EXTRACTION_PROMPT


def build_subtype_memories(
    credentials: dict[str, Any],
) -> dict[MemorySubtype, SubtypeMem0]:
    """Create 3 Mem0 Memory instances with subtype-specific prompts."""
    base = build_local_mem0_config(credentials)
    
    # Extract non-serializable objects (like connection pools) before deepcopy
    # Connection pools contain locks that cannot be pickled/deepcopied
    connection_pool = None
    vector_store_config = base.get("vector_store", {}).get("config", {})
    if isinstance(vector_store_config, dict) and "connection_pool" in vector_store_config:
        connection_pool = vector_store_config.pop("connection_pool")
    
    memories: dict[MemorySubtype, SubtypeMem0] = {}
    for subtype in ("semantic", "episodic", "procedural"):
        cfg = copy.deepcopy(base)
        
        # Restore connection pool to each subtype config (shared pool)
        if connection_pool is not None:
            cfg["vector_store"]["config"]["connection_pool"] = connection_pool  # type: ignore[index]
        
        cfg["custom_fact_extraction_prompt"] = _subtype_extraction_prompt(subtype)  # type: ignore[index]
        cfg["custom_update_memory_prompt"] = build_update_memory_prompt(subtype=subtype)  # type: ignore[index]
        memories[subtype] = SubtypeMem0(subtype=subtype, memory=Memory.from_config(cfg))
    
    # Restore connection pool to original base config (for any future use)
    if connection_pool is not None:
        base["vector_store"]["config"]["connection_pool"] = connection_pool  # type: ignore[index]
    
    return memories


def classify_conversation_memory_type(
    *,
    mem: Memory,
    messages: list[dict[str, str]],
    context: dict[str, Any] | None = None,
) -> tuple[MemorySubtype, bool] | tuple[None, bool]:
    """Classify conversation and evaluate extraction value simultaneously.
    
    Uses LLM to analyze conversation content and determine:
    1. Which single memory type (semantic/episodic/procedural) is most dominant
    2. Whether the content is worth extracting as long-term memory
    
    This combines classification and value assessment in a single LLM call,
    following Mem0 best practices to avoid extracting low-value content.
    
    Args:
        mem: Memory instance (uses its LLM client for classification)
        messages: List of message dicts with 'role' and 'content'
        context: Optional context dict for logging
        
    Returns:
        Tuple of (memory_type, should_extract):
        - memory_type: "semantic", "episodic", "procedural", or None
        - should_extract: True if content is valuable, False otherwise
        
        Returns (None, False) if no significant content or classification fails.
    """
    if not messages:
        return None, False
    
    # Format messages for the prompt and logging
    conversation_text = "\n".join(
        f"{msg['role'].title()}: {msg['content']}" for msg in messages
    )

    # Build safe, compact context string for logging
    log_context = ""
    if isinstance(context, dict):
        safe_ctx: dict[str, Any] = {}
        for key in ("user_id", "conversation_id", "message_id_range"):
            if key in context:
                safe_ctx[key] = context[key]
        if safe_ctx:
            log_context = f" | context={safe_ctx}"
    
    # Call LLM for combined classification and value assessment
    try:
        # Use mem0's internal LLM client
        llm = mem.llm
        
        # Construct the full prompt
        classification_prompt = MEMORY_CLASSIFICATION_PROMPT + "\n" + conversation_text
        
        # Get response from LLM
        response = llm.generate_response(
            messages=[
                {
                    "role": "user",
                    "content": classification_prompt,
                }
            ],
            response_format={"type": "json_object"},
        )
        
        # Parse JSON response
        result = json.loads(response)
        memory_type = result.get("memory_type", "").lower()
        should_extract = result.get("should_extract", False)
        reason = result.get("reason", "")

        # Build short preview of conversation for debugging
        preview = conversation_text.replace("\n", " ")
        if len(preview) > 160:
            preview = preview[:157] + "..."

        logger.info(
            "Memory classification result: type=%s, should_extract=%s, "
            "reason=%s, preview=%s%s",
            memory_type,
            should_extract,
            reason,
            preview,
            log_context,
        )

        # Validate memory type
        if memory_type in ("semantic", "episodic", "procedural"):
            # Return both type and extraction decision
            return memory_type, should_extract  # type: ignore[return-value]

        # "NONE" or invalid type - should not extract
        return None, False
        
    except AttributeError as e:
        # Code error: Memory object doesn't have expected attribute
        logger.error(
            f"Failed to classify conversation memory type: "
            f"Memory object missing attribute. Error: {e}. "
            "This is likely a code error."
        )
        # Re-raise to make the error visible in tests
        raise
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        # Business logic failure: Invalid JSON response or missing fields
        logger.warning(
            f"Failed to parse classification response: {e}. "
            "This may indicate an issue with the LLM response format."
        )
        return None, False
    except Exception as e:
        # Other errors (network, LLM API errors, etc.)
        logger.warning(
            f"Failed to classify conversation memory type: {e}. "
            "This may indicate a configuration or network issue."
        )
        # Fallback: return None, False to skip this segment
        return None, False


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


def _infer_memory_categories(subtype: MemorySubtype) -> list[str]:
    """Infer likely categories based on memory subtype.
    
    Categories reference: openmemory categorization system.
    Multiple categories can apply to a single memory.
    """
    # Base categories by subtype
    category_mapping = {
        "semantic": [
            "Personal",  # Profile facts, demographics
            "Preferences",  # Likes, dislikes, habits
        ],
        "episodic": [
            "Personal",  # Life events
            "Relationships",  # Interactions with others
        ],
        "procedural": [
            "Work",  # Professional workflows
            "Projects",  # Task execution procedures
        ],
    }
    return category_mapping.get(subtype, ["Personal"])


def build_memory_metadata(
    *,
    subtype: MemorySubtype,
    app_id: str | None,
    conversation_id: str,
    segment_id: str,
    run_at: str,
    message_id_range: str,
) -> dict[str, Any]:
    """Build metadata for extracted memory.
    
    Metadata includes:
    1. Extraction tracking: source, subtype, timestamps, IDs
    2. Memory categories: inferred categories for filtering/retrieval
    3. Schema version: for future compatibility
    
    Categories are based on openmemory's categorization system:
    - Personal: family, friends, home, hobbies, lifestyle
    - Relationships: social network, significant others, colleagues
    - Preferences: likes, dislikes, habits, favorite media
    - Health: physical fitness, mental health, diet, sleep
    - Travel: trips, commutes, favorite places, itineraries
    - Work: job roles, companies, projects, promotions
    - Education: courses, degrees, certifications, skills development
    - Projects: tasks, milestones, deadlines, status updates
    - Entertainment: movies, music, games, books, events
    - Organization: meetings, appointments, calendars
    - Goals: ambitions, KPIs, long-term objectives
    """
    md: dict[str, Any] = {
        # Memory classification
        "memory_subtype": subtype,
        "categories": _infer_memory_categories(subtype),
        
        # Extraction tracking
        "source": "dify_extraction",
        "conversation_id": conversation_id,
        "segment_id": segment_id,
        "message_id_range": message_id_range,
        
        # Timestamps
        "run_at": run_at,
        "extracted_at": _utc_now_iso(),
        
        # Schema
        "schema_version": "v1",
    }
    if app_id:
        md["app_id"] = app_id
    return md

