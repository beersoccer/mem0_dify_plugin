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


def _is_pool_closed(pool: object) -> bool:
    """Check if a connection pool is closed.
    
    Args:
        pool: Connection pool object (psycopg3 ConnectionPool or psycopg2 ThreadedConnectionPool)
        
    Returns:
        True if pool is closed or cannot be determined, False if pool is open.
    """
    if pool is None:
        return True
    
    try:
        # Check for psycopg3 ConnectionPool
        if hasattr(pool, "closed"):
            return pool.closed
        # For psycopg2 ThreadedConnectionPool, there's no direct closed property
        # We can't easily check, so assume it's open if it exists
        # The actual check will happen when trying to use it
        return False
    except Exception:
        # If we can't check, assume it's closed to be safe
        logger.debug("Could not check pool status, assuming closed")
        return True


def build_subtype_sync_clients(
    credentials: dict[str, Any],
    base_client: SyncMem0Client | None = None,
) -> dict[MemorySubtype, SyncMem0Client]:
    """Create 3 SyncMem0Client instances with subtype-specific prompts.
    
    Subtype clients share connection pool from base_client for resource isolation.
    Each client has its own Memory instance with custom prompts.
    
    Args:
        credentials: Configuration dictionary for Mem0 clients.
        base_client: Base client to share connection pool from (required for
            resource isolation). If None, each subtype client will create its
            own connection pool.
        
    Returns:
        Dictionary mapping subtype to SyncMem0Client instance.
    """
    base = build_local_mem0_config(credentials)
    
    # Remove connection_pool from base config before deepcopy (pools contain locks)
    if "vector_store" in base and isinstance(base["vector_store"], dict):
        vs_config = base["vector_store"].get("config", {})
        if isinstance(vs_config, dict) and "connection_pool" in vs_config:
            vs_config.pop("connection_pool")
    
    # Get connection pool from base_client (required for resource isolation)
    connection_pool = None
    if base_client is not None:
        try:
            base_mem = base_client.memory
            if hasattr(base_mem, "vector_store"):
                vs = base_mem.vector_store
                if hasattr(vs, "connection_pool") and vs.connection_pool is not None:
                    pool = vs.connection_pool
                    if not _is_pool_closed(pool):
                        connection_pool = pool
        except Exception:
            pass
    
    clients: dict[MemorySubtype, SyncMem0Client] = {}
    for subtype in ("semantic", "episodic", "procedural"):
        cfg = copy.deepcopy(base)
        
        if connection_pool is not None:
            cfg["vector_store"]["config"]["connection_pool"] = connection_pool  # type: ignore[index]
        
        cfg["custom_fact_extraction_prompt"] = _subtype_extraction_prompt(subtype)  # type: ignore[index]
        cfg["custom_update_memory_prompt"] = build_update_memory_prompt(subtype=subtype)  # type: ignore[index]
        
        client = SyncMem0Client(
            credentials,
            enable_keepalive=False,
            config_override=cfg,
        )
        memory_instance = client.memory
        
        if connection_pool is not None and base_client is not None:
            client._is_sharing_pool = True  # type: ignore[attr-defined]
        else:
            client._is_sharing_pool = False  # type: ignore[attr-defined]
        
        if not memory_instance.config.custom_fact_extraction_prompt:
            raise ValueError(
                f"Failed to load custom_fact_extraction_prompt for {subtype} memory"
            )
        
        clients[subtype] = client
    
    return clients


class SyncMemoryClassificationManager:
    """Synchronous memory classification manager for Memory instances."""

    def __init__(self, mem: Memory) -> None:
        """Initialize memory classification manager.

        Args:
            mem: Synchronous Memory instance
        """
        self.mem = mem

    def classify(
        self,
        *,
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
            llm = self.mem.llm
            
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

            logger.debug(
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


class AsyncMemoryClassificationManager:
    """Asynchronous memory classification manager for AsyncMemory instances."""

    def __init__(self, mem: AsyncMemory) -> None:
        """Initialize async memory classification manager.

        Args:
            mem: Asynchronous AsyncMemory instance
        """
        self.mem = mem

    async def classify(
        self,
        *,
        messages: list[dict[str, str]],
        context: dict[str, Any] | None = None,
    ) -> tuple[MemorySubtype, bool] | tuple[None, bool]:
        """Classify conversation and evaluate extraction value.
        
        Uses LLM to analyze conversation content and determine:
        1. Which single memory type (semantic/episodic/procedural) is most dominant
        2. Whether the content is worth extracting as long-term memory
        
        Args:
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
            llm = self.mem.llm
            
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

            logger.debug(
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


class SyncMemoryWriter:
    """Synchronous memory writer for SyncMem0Client instances."""

    def __init__(self, client: SyncMem0Client) -> None:
        """Initialize synchronous memory writer.

        Args:
            client: SyncMem0Client instance
        """
        self.client = client

    def add_memory(
        self,
        *,
        messages: list[dict[str, str]],
        user_id: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Call mem0 add(infer=True) using SyncMem0Client.
        
        Uses SyncMem0Client.add() which provides the same interface as other tools.
        
        Args:
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
        return self.client.add(payload)


class AsyncMemoryWriter:
    """Asynchronous memory writer for AsyncMem0Client instances."""

    def __init__(self, client: AsyncMem0Client) -> None:
        """Initialize asynchronous memory writer.

        Args:
            client: AsyncMem0Client instance
        """
        self.client = client

    async def add_memory(
        self,
        *,
        messages: list[dict[str, str]],
        user_id: str,
        metadata: dict[str, Any],
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        """Call mem0 add(infer=True) with required ids and metadata.
        
        Uses AsyncMem0Client.add() which provides:
        - Automatic timeout protection
        - Queue overload checking
        - Semaphore-controlled concurrency
        - Detailed timing logs
        
        Args:
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
        return await self.client.add(payload, timeout_s=timeout_s)




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


async def build_subtype_async_clients(
    credentials: dict[str, Any],
    base_client: AsyncMem0Client | None = None,
) -> dict[MemorySubtype, AsyncMem0Client]:
    """Create 3 AsyncMem0Client instances with subtype-specific prompts.
    
    Subtype clients share connection pool from base_client for resource isolation.
    Each client is immediately initialized (not lazy) since extraction tasks always execute.
    
    Args:
        credentials: Configuration dictionary for Mem0 clients.
        base_client: Base client to share connection pool from (required for
            resource isolation). If None, each subtype client will create its
            own connection pool.
        
    Returns:
        Dictionary mapping subtype to AsyncMem0Client instance.
    """
    base = build_local_mem0_config(credentials)
    
    # Remove connection_pool from base config before deepcopy (pools contain locks)
    if "vector_store" in base and isinstance(base["vector_store"], dict):
        vs_config = base["vector_store"].get("config", {})
        if isinstance(vs_config, dict) and "connection_pool" in vs_config:
            vs_config.pop("connection_pool")
    
    # Get connection pool from base_client (required for resource isolation)
    connection_pool = None
    if base_client is not None and base_client.memory is not None:
        try:
            base_mem = base_client.memory
            if hasattr(base_mem, "vector_store"):
                vs = base_mem.vector_store
                if hasattr(vs, "connection_pool") and vs.connection_pool is not None:
                    pool = vs.connection_pool
                    if not _is_pool_closed(pool):
                        connection_pool = pool
        except Exception:
            pass
    
    clients: dict[MemorySubtype, AsyncMem0Client] = {}
    for subtype in ("semantic", "episodic", "procedural"):
        cfg = copy.deepcopy(base)
        
        if connection_pool is not None:
            cfg["vector_store"]["config"]["connection_pool"] = connection_pool  # type: ignore[index]
        
        cfg["custom_fact_extraction_prompt"] = _subtype_extraction_prompt(subtype)  # type: ignore[index]
        cfg["custom_update_memory_prompt"] = build_update_memory_prompt(subtype=subtype)  # type: ignore[index]
        
        client = AsyncMem0Client(credentials, enable_keepalive=False)
        client.config = cfg
        
        await client.create()
        
        if connection_pool is not None and base_client is not None:
            client._is_sharing_pool = True  # type: ignore[attr-defined]
        else:
            client._is_sharing_pool = False  # type: ignore[attr-defined]
        
        clients[subtype] = client
    
    return clients



