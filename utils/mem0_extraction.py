"""Mem0 helpers for long-term memory extraction.

Builds per-subtype Mem0 configs (prompt isolation) and provides add() helpers that
attach required metadata.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from mem0 import AsyncMemory

from .config_builder import build_local_mem0_config
from .logger import get_logger
from .mem0_client import AsyncMem0Client, Memory, SyncMem0Client
from .prompts import (
    EPISODIC_FACT_EXTRACTION_PROMPT,
    MEMORY_CLASSIFICATION_PROMPT,
    PROCEDURAL_FACT_EXTRACTION_PROMPT,
    SEMANTIC_FACT_EXTRACTION_PROMPT,
    build_update_memory_prompt,
)

logger = get_logger(__name__)

MemorySubtype = Literal["semantic", "episodic", "procedural"]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _subtype_extraction_prompt(subtype: MemorySubtype) -> str:
    if subtype == "semantic":
        return SEMANTIC_FACT_EXTRACTION_PROMPT
    if subtype == "episodic":
        return EPISODIC_FACT_EXTRACTION_PROMPT
    return PROCEDURAL_FACT_EXTRACTION_PROMPT


def build_subtype_sync_clients(
    credentials: dict[str, Any],
) -> dict[MemorySubtype, SyncMem0Client]:
    """Create 3 SyncMem0Client instances with subtype-specific prompts.
    
    Each client is configured with a custom prompt for its memory subtype.
    This function reuses SyncMem0Client mechanism, consistent with other tools.
    
    Note: Since SyncMem0Client creates Memory in __init__, we create the client
    first, then replace its memory with a Memory instance created from custom config.
    This ensures each subtype has the correct prompt configuration.
    
    Args:
        credentials: Configuration dictionary for Mem0 clients.
        
    Returns:
        Dictionary mapping subtype to SyncMem0Client instance.
    """
    base = build_local_mem0_config(credentials)
    
    # Extract non-serializable objects (like connection pools) before deepcopy
    connection_pool = None
    vector_store_config = base.get("vector_store", {}).get("config", {})
    if isinstance(vector_store_config, dict) and "connection_pool" in vector_store_config:
        connection_pool = vector_store_config.pop("connection_pool")
    
    clients: dict[MemorySubtype, SyncMem0Client] = {}
    for subtype in ("semantic", "episodic", "procedural"):
        cfg = copy.deepcopy(base)
        
        # Restore connection pool to each subtype config (shared pool)
        if connection_pool is not None:
            cfg["vector_store"]["config"]["connection_pool"] = connection_pool  # type: ignore[index]
        
        # Set custom prompts for this subtype
        cfg["custom_fact_extraction_prompt"] = _subtype_extraction_prompt(subtype)  # type: ignore[index]
        cfg["custom_update_memory_prompt"] = build_update_memory_prompt(subtype=subtype)  # type: ignore[index]
        
        # Create SyncMem0Client (will create a Memory with default config)
        client = SyncMem0Client(credentials)
        
        # Replace memory with one created from custom config
        # This ensures the subtype-specific prompts are used
        memory_instance = Memory.from_config(cfg)
        client.memory = memory_instance
        
        # Update ConnectionKeepAlive to use the new memory instance
        # This ensures heartbeat uses the correct memory with custom prompts
        if hasattr(client, "_keepalive") and client._keepalive is not None:
            client._keepalive.memory = memory_instance
        
        # Verify custom prompt is loaded
        if not memory_instance.config.custom_fact_extraction_prompt:
            raise ValueError(
                f"Failed to load custom_fact_extraction_prompt for {subtype} memory. "
                "This indicates a configuration error."
            )
        
        clients[subtype] = client
    
    # Restore connection pool to original base config
    if connection_pool is not None:
        base["vector_store"]["config"]["connection_pool"] = connection_pool  # type: ignore[index]
    
    return clients


def classify_sync_conversation_memory_type(
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


def mem0_sync_add_memory(
    *,
    client: SyncMem0Client,
    messages: list[dict[str, str]],
    user_id: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Sync version: Call mem0 add(infer=True) using SyncMem0Client.
    
    Uses SyncMem0Client.add() which provides the same interface as other tools.
    
    Args:
        client: SyncMem0Client instance
        messages: List of message dicts with 'role' and 'content'
        user_id: User ID for memory scoping
        metadata: Metadata dict to attach to memory
        
    Returns:
        Result dict from mem0 add operation.
    """
    payload: dict[str, Any] = {
        "messages": messages,
        "user_id": user_id,
        "metadata": metadata,
        "infer": True,
    }
    return client.add(payload)


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


def build_subtype_async_clients(
    credentials: dict[str, Any],
) -> dict[MemorySubtype, AsyncMem0Client]:
    """Create 3 AsyncMem0Client instances with subtype-specific prompts.
    
    Each client is configured with a custom prompt for its memory subtype.
    Clients are lazily initialized (AsyncMemory created on first use via create()).
    
    Note: The config is modified after client creation but before first use.
    This ensures AsyncMemory.from_config() receives the subtype-specific prompts.
    
    Args:
        credentials: Configuration dictionary for Mem0 clients.
        
    Returns:
        Dictionary mapping subtype to AsyncMem0Client instance.
    """
    base = build_local_mem0_config(credentials)
    
    # Extract non-serializable objects (like connection pools) before deepcopy
    connection_pool = None
    vector_store_config = base.get("vector_store", {}).get("config", {})
    if isinstance(vector_store_config, dict) and "connection_pool" in vector_store_config:
        connection_pool = vector_store_config.pop("connection_pool")
    
    clients: dict[MemorySubtype, AsyncMem0Client] = {}
    for subtype in ("semantic", "episodic", "procedural"):
        cfg = copy.deepcopy(base)
        
        # Restore connection pool to each subtype config (shared pool)
        if connection_pool is not None:
            cfg["vector_store"]["config"]["connection_pool"] = connection_pool  # type: ignore[index]
        
        # Set custom prompts for this subtype
        cfg["custom_fact_extraction_prompt"] = _subtype_extraction_prompt(subtype)  # type: ignore[index]
        cfg["custom_update_memory_prompt"] = build_update_memory_prompt(subtype=subtype)  # type: ignore[index]
        
        # Create AsyncMem0Client - it will build config from credentials
        # We override the config after creation but before first use
        client = AsyncMem0Client(credentials)
        # Override config with subtype-specific prompts
        # This config will be used when create() is called
        client.config = cfg
        
        clients[subtype] = client
    
    # Restore connection pool to original base config
    if connection_pool is not None:
        base["vector_store"]["config"]["connection_pool"] = connection_pool  # type: ignore[index]
    
    return clients


async def classify_async_conversation_memory_type(
    *,
    mem: AsyncMemory,
    messages: list[dict[str, str]],
    context: dict[str, Any] | None = None,
) -> tuple[MemorySubtype, bool] | tuple[None, bool]:
    """Async version: Classify conversation and evaluate extraction value.
    
    Uses LLM to analyze conversation content and determine:
    1. Which single memory type (semantic/episodic/procedural) is most dominant
    2. Whether the content is worth extracting as long-term memory
    
    Args:
        mem: AsyncMemory instance (uses its LLM client for classification)
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
        # Note: LLM client may be sync or async, use asyncio.to_thread for sync clients
        if hasattr(llm, "agenerate_response"):
            response = await llm.agenerate_response(
                messages=[
                    {
                        "role": "user",
                        "content": classification_prompt,
                    }
                ],
                response_format={"type": "json_object"},
            )
        else:
            # Fallback: run sync method in thread pool
            import asyncio
            response = await asyncio.to_thread(
                llm.generate_response,
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
            return memory_type, should_extract  # type: ignore[return-value]

        # "NONE" or invalid type - should not extract
        return None, False
        
    except AttributeError as e:
        # Code error: AsyncMemory object doesn't have expected attribute
        logger.error(
            f"Failed to classify conversation memory type: "
            f"AsyncMemory object missing attribute. Error: {e}. "
            "This is likely a code error."
        )
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
        return None, False


async def mem0_async_add_memory(
    *,
    client: AsyncMem0Client,
    messages: list[dict[str, str]],
    user_id: str,
    metadata: dict[str, Any],
    timeout_s: int | None = None,
) -> dict[str, Any]:
    """Async version: Call mem0 add(infer=True) with required ids and metadata.
    
    Uses AsyncMem0Client.add() which provides:
    - Automatic timeout protection
    - Queue overload checking
    - Semaphore-controlled concurrency
    - Detailed timing logs
    
    Args:
        client: AsyncMem0Client instance
        messages: List of message dicts with 'role' and 'content'
        user_id: User ID for memory scoping
        metadata: Metadata dict to attach to memory
        timeout_s: Optional timeout in seconds (defaults to WRITE_OPERATION_TIMEOUT)
        
    Returns:
        Result dict from mem0 add operation.
    """
    payload: dict[str, Any] = {
        "messages": messages,
        "user_id": user_id,
        "metadata": metadata,
        "infer": True,
    }
    return await client.add(payload, timeout_s=timeout_s)

