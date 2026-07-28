"""Client adapter for Mem0 local mode only."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable
from types import MethodType
from typing import TYPE_CHECKING, Any, TypeVar

from mem0 import AsyncMemory, Memory

from .background_loop import BackgroundEventLoop
from .config_builder import build_local_mem0_config
from .connection_keepalive import ConnectionKeepAlive
from .constants import (
    ADD_SKIP_RESULT,
    HEARTBEAT_INTERVAL,
    MAX_CONCURRENT_MEMORY_OPERATIONS,
    MAX_PENDING_TASKS_MULTIPLIER,
    READ_OPERATION_TIMEOUT,
    WRITE_OPERATION_TIMEOUT,
)
from .helpers import parse_positive_int
from .logger import get_logger
from .resource_cleanup import close_memory_resources
from .score_utils import get_score_mode
from .task_tracker import TaskTracker

logger = get_logger(__name__)

# Process-level lock that serialises all Memory.from_config() / AsyncMemory.from_config()
# calls. pgvector's create_col() issues "CREATE EXTENSION IF NOT EXISTS vector" which is
# not fully idempotent under concurrent PostgreSQL sessions — two concurrent executions
# can race on registering the extension's internal pg_type entries, producing a
# UniqueViolation on "pg_type_typname_nsp_index". Serialising initialisation within
# the process eliminates this race without patching the third-party library.
_mem0_init_lock = threading.Lock()


async def _resolve_async_memory_from_config(config: dict[str, Any]) -> AsyncMemory:
    """Support both old and new mem0 AsyncMemory.from_config semantics.

    Older mem0 releases exposed ``AsyncMemory.from_config`` as an async
    classmethod, while newer releases return an ``AsyncMemory`` instance
    directly.  Dify's async validation path always calls ``create()``, so we
    normalize both forms here and keep the rest of the client code unchanged.
    """
    memory_or_awaitable = AsyncMemory.from_config(config)
    if asyncio.iscoroutine(memory_or_awaitable):
        return await memory_or_awaitable
    return memory_or_awaitable


def _patch_llm_compat(llm: Any) -> None:
    """Patch LLM instances that lack _parse_response (e.g., structured providers)."""
    if llm is None or hasattr(llm, "_parse_response"):
        return

    try:
        from mem0.memory.utils import extract_json
    except Exception:  # pragma: no cover - defensive fallback
        extract_json = None  # type: ignore[assignment]

    def _parse_response(self, response, tools):  # noqa: ANN001
        if tools:
            processed_response = {
                "content": response.choices[0].message.content,
                "tool_calls": [],
            }
            tool_calls = getattr(response.choices[0].message, "tool_calls", None)
            if tool_calls:
                for tool_call in tool_calls:
                    raw_args = tool_call.function.arguments
                    if extract_json is not None:
                        try:
                            parsed_args = json.loads(extract_json(raw_args))
                        except Exception:
                            parsed_args = raw_args
                    else:
                        parsed_args = raw_args
                    processed_response["tool_calls"].append(
                        {"name": tool_call.function.name, "arguments": parsed_args}
                    )
            return processed_response
        return response.choices[0].message.content

    llm._parse_response = MethodType(_parse_response, llm)


def _clone_memory_with_fact_extraction_prompt(memory: Any, prompt: str) -> Any:
    """Clone a Mem0 facade with a per-call fact extraction prompt.

    Mem0 reads ``custom_fact_extraction_prompt`` from the memory config during
    infer-based adds. A shallow facade copy keeps the expensive LLM, embedder,
    stores, and history resources shared while isolating the prompt config from
    other concurrent add requests.
    """
    cloned_memory = copy.copy(memory)
    original_config = getattr(memory, "config", None)
    if original_config is None:
        raise ValueError("Mem0 memory config is unavailable for prompt override")

    if isinstance(original_config, dict):
        cloned_config = original_config.copy()
        cloned_config["custom_fact_extraction_prompt"] = prompt
    else:
        model_copy = getattr(original_config, "model_copy", None)
        legacy_copy = getattr(original_config, "copy", None)
        if callable(model_copy):
            cloned_config = model_copy(
                update={"custom_fact_extraction_prompt": prompt}
            )
        elif callable(legacy_copy):
            try:
                cloned_config = legacy_copy(
                    update={"custom_fact_extraction_prompt": prompt}
                )
            except TypeError:
                cloned_config = copy.copy(original_config)
                cloned_config.custom_fact_extraction_prompt = prompt
        else:
            cloned_config = copy.copy(original_config)
            cloned_config.custom_fact_extraction_prompt = prompt

    cloned_memory.config = cloned_config
    if hasattr(cloned_memory, "custom_fact_extraction_prompt"):
        cloned_memory.custom_fact_extraction_prompt = prompt
    return cloned_memory


def _get_custom_fact_extraction_prompt(payload: dict[str, Any]) -> str | None:
    """Return a normalized per-call prompt override."""
    raw_prompt = payload.get("custom_fact_extraction_prompt")
    if not isinstance(raw_prompt, str):
        return None
    prompt = raw_prompt.strip()
    return prompt or None


if TYPE_CHECKING:
    from collections.abc import Awaitable

T = TypeVar("T")


def normalize_search_results(
    results: object,
    score_mode: str = "distance",
) -> list[dict[str, Any]]:
    """Normalize Mem0 search results into a list of dicts.

    Args:
        results: Raw search results from Mem0, which can be:
            - A list of dicts
            - A dict with "results" key containing a list
            - None or empty
        score_mode: How to interpret the raw ``score`` field returned by the
            vector store.  Use ``'distance'`` when the raw score is a
            distance value (lower = more similar, e.g. pgvector cosine
            distance, Milvus L2, FAISS euclidean).  Use ``'similarity'``
            when the raw score already represents relevance (higher =
            better, e.g. Elasticsearch _score, Azure AI Search
            @search.score, Qdrant, Milvus COSINE/IP, FAISS inner-product).
            Determined at client init time via ``get_score_mode()``.
            Defaults to ``'distance'`` for backward compatibility.

    Returns:
        list[dict]: Normalized list of memory search results with consistent
            structure.  Each entry includes:
            - id, memory, metadata, created_at: standard fields
            - score: 0–1 similarity signal; higher = more relevant.
              Equals ``rerank_score`` when a reranker is active, otherwise
              derived from the raw vector store score according to
              *score_mode*.
            - vector_distance: 0–1 distance value; lower = more similar.
              For distance-type backends this is the raw score (clamped to
              [0, 1]).  For similarity-type backends and reranker results
              this is the synthetic complement ``1 - score``.
            - rerank_score: relevance score added by the reranker (0–1,
              higher = more relevant); None when no reranker is configured.

    """
    normalized: list[dict[str, Any]] = []
    if not results:
        return normalized

    items = results
    if isinstance(results, dict) and "results" in results:
        items = results["results"]

    for r in items or []:
        if not isinstance(r, dict):
            continue
        raw_score = float(r.get("score") or r.get("similarity", 0.0))
        rerank_score = r.get("rerank_score")  # None when reranker is not used

        if rerank_score is not None:
            raw_rerank = float(rerank_score)
            if raw_rerank < 0.0 or raw_rerank > 1.0:
                logger.warning(
                    "mem0_client.normalize_search_results: rerank_score %.6f is "
                    "outside [0, 1]; clamping to [0, 1]. score_mode=%s, raw_score=%.6f",
                    raw_rerank,
                    score_mode,
                    raw_score,
                )
            # Reranker always produces 0-1 similarity; highest priority.
            score = max(0.0, min(1.0, raw_rerank))
            vector_distance = max(0.0, 1.0 - score)
        elif score_mode == "distance":
            # pgvector / Milvus-L2 / FAISS-euclidean: raw score is a distance.
            vector_distance = float(raw_score)
            if vector_distance < 0.0 or vector_distance > 1.0:
                logger.warning(
                    "mem0_client.normalize_search_results: distance score %.6f is "
                    "outside [0, 1]; downstream logic will clamp derived similarity. "
                    "score_mode=%s",
                    vector_distance,
                    score_mode,
                )
            score = max(0.0, 1.0 - vector_distance)
        else:
            # Elasticsearch / Azure AI Search / Qdrant / Milvus-COSINE / etc.:
            # raw score is already a relevance/similarity value.
            if raw_score < 0.0 or raw_score > 1.0:
                logger.warning(
                    "mem0_client.normalize_search_results: similarity score %.6f is "
                    "outside [0, 1]; clamping to [0, 1]. score_mode=%s",
                    raw_score,
                    score_mode,
                )
            score = max(0.0, min(1.0, float(raw_score)))
            vector_distance = max(0.0, 1.0 - score)

        normalized.append(
            {
                "id": r.get("id") or r.get("memory_id") or "",
                "memory": r.get("memory") or r.get("text") or "",
                "score": score,
                "vector_distance": vector_distance,
                "rerank_score": rerank_score,
                "metadata": r.get("metadata") or {},
                "created_at": r.get("created_at") or r.get("timestamp") or "",
            },
        )
    return normalized


def _summarize_ids(kwargs: dict[str, Any]) -> dict[str, str]:
    """Summarize ID scope for logging without leaking content."""
    summary: dict[str, str] = {}
    for key in ("user_id", "agent_id", "run_id"):
        val = kwargs.get(key)
        if isinstance(val, str) and val:
            summary[key] = val
    return summary


def _summarize_messages(messages: object) -> dict[str, Any]:
    """Summarize message payload for debug logging (no raw content)."""
    if messages is None:
        return {"type": "none"}
    if isinstance(messages, str):
        return {"type": "str", "length": len(messages)}
    if isinstance(messages, list | tuple):
        role_counts: dict[str, int] = {}
        total_chars = 0
        empty_count = 0
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "unknown").lower()
            role_counts[role] = role_counts.get(role, 0) + 1
            content = item.get("content")
            if isinstance(content, str):
                total_chars += len(content)
                if not content.strip():
                    empty_count += 1
            elif content is None:
                empty_count += 1
        return {
            "type": "list",
            "count": len(messages),
            "roles": role_counts,
            "total_chars": total_chars,
            "empty_contents": empty_count,
        }
    return {"type": type(messages).__name__}


def _summarize_add_result(result: object) -> dict[str, Any]:
    """Summarize mem0 add() response without leaking memory content."""
    if not isinstance(result, dict):
        return {"type": type(result).__name__}
    results = result.get("results")
    event_counts: dict[str, int] = {}
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            event = str(item.get("event") or "unknown").upper()
            event_counts[event] = event_counts.get(event, 0) + 1
    return {
        "keys": sorted(result.keys()),
        "results_count": len(results) if isinstance(results, list) else 0,
        "event_counts": event_counts,
    }


class QueueOverloadError(Exception):
    """Raised when the background task queue is overloaded."""


class SyncMem0Client:
    """Synchronous Mem0 client using configured providers."""

    def __init__(
        self,
        credentials: dict[str, Any],
        enable_keepalive: bool = True,
        *,
        config_override: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the SyncMem0Client.

        Args:
            credentials (dict): Configuration for the SyncMem0Client.
            enable_keepalive (bool): Whether to enable connection keep-alive.
                                    Defaults to True.
            config_override (dict | None): Optional prebuilt Mem0 config. When set,
                it bypasses build_local_mem0_config() and is used directly.
                The caller is responsible for ensuring the config already contains
                a connection pool if one is desired (e.g. via attach_pgvector_pool).

        """
        import copy

        from .pgvector_config import attach_pgvector_pool

        if config_override is not None:
            config = config_override
        else:
            # The global config cache stores static parameters only (no pool).
            # Deep-copy so we can attach an independent pool without touching the cache.
            config = copy.deepcopy(build_local_mem0_config(credentials))
            if "vector_store" in config and isinstance(config["vector_store"], dict):
                vs_cfg = config["vector_store"].get("config")
                if isinstance(vs_cfg, dict):
                    attach_pgvector_pool(vs_cfg)

        with _mem0_init_lock:
            self.memory = Memory.from_config(config)
        _patch_llm_compat(getattr(self.memory, "llm", None))

        # Determine how raw vector store scores should be interpreted.
        self.score_mode: str = get_score_mode(credentials)
        logger.debug("SyncMem0Client score_mode=%s", self.score_mode)

        # Initialize connection keep-alive
        if enable_keepalive:
            heartbeat_interval = parse_positive_int(
                credentials.get("heartbeat_interval"),
                HEARTBEAT_INTERVAL,
                min_value=30,
                logger=logger,
                config_name="heartbeat_interval",
            )
            self._keepalive = ConnectionKeepAlive(
                memory=self.memory,
                interval=heartbeat_interval,
            )
            self._keepalive.start()
        else:
            self._keepalive = None

        logger.debug("SyncMem0Client initialized")

    def __del__(self) -> None:
        """Cleanup resources when SyncMem0Client is destroyed."""
        if hasattr(self, "_keepalive"):
            with contextlib.suppress(Exception):
                self._keepalive.stop()

    def close(self) -> None:
        """Close and cleanup resources held by SyncMem0Client.
        
        This method explicitly closes critical resources (connection pools, database
        connections) and stops connection keep-alive to prevent resource leaks.
        
        Note: This is primarily used by long-term memory extraction tool which
        creates independent clients for each task execution.
        """
        # Stop connection keep-alive first
        if hasattr(self, "_keepalive") and self._keepalive is not None:
            try:
                self._keepalive.stop()
            except Exception:
                logger.exception("Error stopping connection keep-alive")
        
        # Close vector store connection pool
        if self.memory is not None:
            try:
                vs = getattr(self.memory, "vector_store", None)
                if vs and hasattr(vs, "connection_pool") and vs.connection_pool is not None:
                    pool = vs.connection_pool
                    if hasattr(pool, "close"):
                        pool.close()
                    elif hasattr(pool, "closeall"):
                        pool.closeall()
            except Exception:
                logger.exception("Error closing vector store connection pool")
            
            # Close graph store if present
            try:
                graph = getattr(self.memory, "graph", None)
                if graph:
                    graph_close = getattr(graph, "close", None)
                    if callable(graph_close):
                        graph_close()
                    elif hasattr(graph, "driver") and hasattr(graph.driver, "close"):
                        graph.driver.close()
            except Exception:
                logger.exception("Error closing graph store")
            
            # Close database connection if present
            try:
                db = getattr(self.memory, "db", None)
                if db and hasattr(db, "close"):
                    db.close()
            except Exception:
                logger.exception("Error closing database connection")
        
        logger.debug("SyncMem0Client resources closed")

    def search(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Search for memories based on a query.

        Args:
            payload (dict): Search parameters. Supported keys:
                - query (str): Query to search for.
                - user_id (str, optional): ID of the user.
                - agent_id (str, optional): ID of the agent.
                - run_id (str, optional): ID of the run.
                - limit (int, optional): Max number of results.
                - filters (dict, optional): Metadata filters, supporting:
                    * {"key": "value"} (exact match)
                    * {"key": {"eq"/"ne"/"in"/"nin"/"gt"/"gte"/"lt"/"lte"/"contains"/"icontains"}: ...}
                    * {"key": "*"} (wildcard)
                    * {"AND"/"OR"/"NOT": [filters,...]} (logic ops)
                - threshold (float, optional): Minimum score (not used in local mode).

        Returns:
            list[dict]: List of memory search results.

        """  # noqa: E501
        query = payload.get("query", "")
        filters = payload.get("filters")
        limit = payload.get("limit")

        # Normalize limit to int when possible
        try:
            lim = int(limit) if limit is not None else None
        except (TypeError, ValueError):
            lim = None

        # Build kwargs with non-empty args to simplify branching
        kwargs: dict[str, Any] = {}
        if lim is not None:
            kwargs["limit"] = lim
        
        # Always extract user_id/agent_id/run_id from payload (required by mem0)
        # These are needed even when filters are provided, as mem0's search requires
        # at least one of these IDs for scoping, and filters are merged with them
        if payload.get("user_id"):
            kwargs["user_id"] = payload.get("user_id")
        if payload.get("agent_id"):
            kwargs["agent_id"] = payload.get("agent_id")
        if payload.get("run_id"):
            kwargs["run_id"] = payload.get("run_id")
        
        # Add filters if provided (will be merged with user_id/agent_id/run_id by mem0)
        if isinstance(filters, dict):
            kwargs["filters"] = filters

        try:
            results = self.memory.search(query, **kwargs)
            normalized = normalize_search_results(results, score_mode=self.score_mode)
        except Exception:
            logger.exception("Error during memory search")
            raise
        else:
            return normalized

    def add(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new memory.

        Adds new memories scoped to a single session id (e.g. user_id, agent_id, or run_id).
        One of those ids is required.

        Args:
            payload (dict): A dictionary containing all parameters for adding a memory, including:
                - messages (str or list[dict[str, str]]): The message content or list of messages
                  (e.g., [{"role": "user", "content": "Hello"}, ...]) to process and store.
                - user_id (str, optional): ID of the user creating the memory.
                - agent_id (str, optional): ID of the agent creating the memory.
                - run_id (str, optional): ID of the run creating the memory.
                - metadata (dict or str, optional): Metadata to store with the memory.
                  Can be a dict or a JSON string.
                - infer (bool, optional): If True (default), uses LLM to extract key facts
                  and manage memories.
                - custom_fact_extraction_prompt (str, optional): Per-call prompt used
                  for fact extraction when infer=True.
                - memory_type (str, optional): Type of memory. Defaults to conversational or factual.
                  Use "procedural_memory" for procedural type.
                - prompt (str, optional): Custom prompt to use for memory creation.

        Returns:
            dict: Result of the memory addition, typically with items added/updated (in "results"),
            and possibly "relations" if graph store is enabled.

        """  # noqa: E501
        metadata = payload.get("metadata")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = None

        # Build kwargs only with provided fields (ignore app_id in local)
        kwargs: dict[str, Any] = {}
        if payload.get("user_id"):
            kwargs["user_id"] = payload.get("user_id")
        if payload.get("agent_id"):
            kwargs["agent_id"] = payload.get("agent_id")
        if payload.get("run_id"):
            kwargs["run_id"] = payload.get("run_id")
        if metadata is not None:
            kwargs["metadata"] = metadata
        
        # Explicitly pass infer parameter if provided, default to True
        # This ensures memory extraction happens even if Mem0's default behavior changes
        infer = payload.get("infer", True)
        kwargs["infer"] = infer
        custom_prompt = (
            _get_custom_fact_extraction_prompt(payload) if infer else None
        )

        # Use messages directly if provided; assume upstream has validated inputs
        messages = payload.get("messages")
        if logger.isEnabledFor(logging.DEBUG):
            metadata_keys = (
                sorted(metadata.keys()) if isinstance(metadata, dict) else None
            )
            logger.debug(
                "Mem0 add request summary (sync): ids=%s infer=%s custom_prompt=%s "
                "metadata_keys=%s messages=%s",
                _summarize_ids(kwargs),
                infer,
                bool(custom_prompt),
                metadata_keys,
                _summarize_messages(messages),
            )
        try:
            memory = (
                _clone_memory_with_fact_extraction_prompt(self.memory, custom_prompt)
                if custom_prompt
                else self.memory
            )
            result = memory.add(messages, **kwargs)
        except Exception:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Mem0 add failed (sync) request summary: ids=%s infer=%s",
                    _summarize_ids(kwargs),
                    infer,
                )
            logger.exception("Error during memory addition")
            raise
        else:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Mem0 add result summary (sync): %s",
                    _summarize_add_result(result),
                )
            return result

    def get_all(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Get all memories based on user/agent/run identifiers with optional filters.

        Args:
            params (dict): Parameters including:
                - user_id (str, optional): User ID to filter by.
                - agent_id (str, optional): Agent ID to filter by.
                - run_id (str, optional): Run ID to filter by.
                - limit (int, optional): Maximum number of results to return.
                - filters (dict, optional): Advanced metadata filters.

        Returns:
            list[dict]: List of memory objects.

        """
        # Build kwargs with all provided parameters
        kwargs: dict[str, Any] = {}

        # Add entity IDs if provided
        if params.get("user_id"):
            kwargs["user_id"] = params.get("user_id")
        if params.get("agent_id"):
            kwargs["agent_id"] = params.get("agent_id")
        if params.get("run_id"):
            kwargs["run_id"] = params.get("run_id")

        # Add optional parameters
        limit = params.get("limit")
        if limit is not None:
            with contextlib.suppress(TypeError, ValueError):
                kwargs["limit"] = int(limit)

        filters = params.get("filters")
        if isinstance(filters, dict):
            kwargs["filters"] = filters

        # Mem0's get_all always returns {"results": [...]} format
        try:
            result = self.memory.get_all(**kwargs)
            memories = result.get("results", []) if isinstance(result, dict) else []
        except Exception:
            logger.exception("Error during get_all operation")
            raise
        else:
            return memories

    def get(self, memory_id: str) -> dict[str, Any]:
        """Get a single memory by ID.

        Args:
            memory_id (str): The ID of the memory to retrieve.

        Returns:
            dict: Memory object with id, memory, metadata, created_at, updated_at, etc.

        """
        try:
            result = self.memory.get(memory_id)
        except Exception:
            logger.exception("Error retrieving memory %s", memory_id)
            raise
        else:
            return result

    def update(self, memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Update a memory by ID.

        Args:
            memory_id (str): ID of the memory to update.
            payload (dict): Dictionary containing new content under the "text" key.

        Returns:
            dict: Success message indicating the memory was updated.

        """
        try:
            result = self.memory.update(memory_id, payload.get("text"))
        except (AttributeError, ValueError) as e:
            # Catch AttributeError from mem0 when existing_memory is None
            # or ValueError when memory not found
            # Convert to a consistent ValueError without logging stack trace
            error_str = str(e)
            if (
                "'NoneType' object has no attribute 'payload'" in error_str
                or "not found" in error_str.lower()
            ):
                error_msg = (
                    f"Memory with ID {memory_id} not found. "
                    "It may have already been deleted or never existed."
                )
                raise ValueError(error_msg) from e
            # Re-raise other AttributeErrors/ValueErrors
            raise
        except Exception:
            logger.exception("Error updating memory %s", memory_id)
            raise
        else:
            return result

    def delete(self, memory_id: str) -> dict[str, Any]:
        """Delete a memory by ID.

        Args:
            memory_id (str): The ID of the memory to delete.

        Returns:
            dict: Success message, typically {"message": "Memory deleted successfully!"}.

        Raises:
            ValueError: If memory is not found.
            AttributeError: If memory is not found (some vector stores raise this).

        """
        try:
            result = self.memory.delete(memory_id)
        except (ValueError, AttributeError):
            # Memory not found - let caller handle logging
            raise
        except Exception:
            logger.exception("Error deleting memory %s", memory_id)
            raise
        else:
            return result

    def delete_all(self, params: dict[str, Any]) -> dict[str, Any]:
        """Delete all memories matching the given filters.

        Args:
            params (dict): Parameters including:
                - user_id (str, optional): User ID to filter by.
                - agent_id (str, optional): Agent ID to filter by.
                - run_id (str, optional): Run ID to filter by.

        Returns:
            dict: Result of the deletion operation.

        """
        try:
            result = self.memory.delete_all(
                user_id=params.get("user_id"),
                agent_id=params.get("agent_id"),
                run_id=params.get("run_id"),
            )
        except Exception:
            logger.exception("Error during delete_all operation")
            raise
        else:
            return result

    def history(self, memory_id: str) -> list[dict[str, Any]]:
        """Get the history of changes for a specific memory.

        Args:
            memory_id (str): The ID of the memory to get history for.

        Returns:
            list[dict]: List of history records with old_memory, new_memory, event, created_at, etc.

        """
        try:
            result = self.memory.history(memory_id)
        except Exception:
            logger.exception("Error retrieving history for memory %s", memory_id)
            raise
        else:
            return result


class AsyncMem0Client:
    """Asynchronous Mem0 client using configured providers."""

    def __init__(
        self,
        credentials: dict[str, Any],
        enable_keepalive: bool = True,
        *,
        config_override: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the AsyncMem0Client.

        Args:
            credentials (dict): Configuration for the AsyncMem0Client.
            enable_keepalive (bool): Whether to enable connection keep-alive.
                                    Defaults to True.
            config_override (dict | None): Optional prebuilt Mem0 config. When set,
                it bypasses build_local_mem0_config() and is used directly.
                The caller is responsible for ensuring the config already contains
                a connection pool if one is desired (e.g. via attach_pgvector_pool).
                Pool creation is skipped inside create() when a pool is already present.

        """
        import copy

        if config_override is not None:
            self.config = config_override
        else:
            # Deep-copy the cached static config so each AsyncMem0Client instance owns
            # its own independent pool (created lazily in create()).
            self.config = copy.deepcopy(build_local_mem0_config(credentials))
        self.memory = None
        # Async lock to protect one-time asynchronous initialization.
        self._create_lock = asyncio.Lock()

        # Determine how raw vector store scores should be interpreted.
        self.score_mode: str = get_score_mode(credentials)
        logger.debug("AsyncMem0Client score_mode=%s", self.score_mode)

        # Parse config value
        self.max_ops = parse_positive_int(
            credentials.get("max_concurrent_memory_operations"),
            MAX_CONCURRENT_MEMORY_OPERATIONS,
            logger=logger,
            config_name="max_concurrent_memory_operations",
        )

        self._semaphore = asyncio.Semaphore(self.max_ops)

        # Initialize connection keep-alive
        self._enable_keepalive = enable_keepalive
        if enable_keepalive:
            heartbeat_interval = parse_positive_int(
                credentials.get("heartbeat_interval"),
                HEARTBEAT_INTERVAL,
                min_value=30,
                logger=logger,
                config_name="heartbeat_interval",
            )
            self._keepalive_interval = heartbeat_interval
        else:
            self._keepalive_interval = None
        self._keepalive: ConnectionKeepAlive | None = None

        logger.debug("AsyncMem0Client initialized")

    def __del__(self) -> None:
        """Cleanup resources when AsyncMem0Client is destroyed.

        Note: This provides a safety net for cleanup. The preferred way to cleanup
        is via aclose(), which properly handles async resources. However, this method
        ensures that the heartbeat thread is stopped even if aclose() is not called.

        The heartbeat thread is daemon=True, so it will terminate when the process
        exits. This method provides explicit cleanup for better resource management.
        """
        if hasattr(self, "_keepalive") and self._keepalive is not None:
            with contextlib.suppress(Exception):
                self._keepalive.stop()

    @classmethod
    def get_pending_tasks_count(cls) -> int:
        """Get the number of pending background tasks (read + write operations).

        This includes all memory operations submitted to the background event loop:
        - Read operations (search, get, get_all, history): submitted and awaited
        - Write operations (add, update, delete, delete_all): fire-and-forget

        Returns:
            int: Number of pending tasks across all operation types.

        Note:
            Tasks are automatically removed from _bg_tasks when they complete
            via the callback registered in track_bg_task(). This method simply
            returns the current count without additional cleanup.

        """
        return TaskTracker.get_pending_tasks_count()

    @classmethod
    def get_completed_stats(cls) -> tuple[int, float]:
        """Get and reset completed task statistics for queue monitoring.

        Returns:
            tuple[int, float]: (completed_count, avg_duration_seconds) since last call.
                              Returns (0, 0.0) if no tasks completed.

        Note:
            This method resets the internal counters after reading, so each call
            returns stats for the period since the last call (suitable for periodic
            monitoring).

        """
        return TaskTracker.get_completed_stats()

    @classmethod
    def track_bg_task(cls, future: asyncio.Future, task_name: str = "unknown") -> None:
        """Track a background task and log completion/errors.

        This method tracks all memory operations submitted to the background event loop,
        regardless of whether they are fire-and-forget (write ops) or awaited (read ops).

        Args:
            future: The future object returned by run_coroutine_threadsafe.
            task_name: Name of the task for logging (format: "operation(params, req_id=xxx)").

        """
        TaskTracker.track_bg_task(future, task_name)

    async def create(self) -> AsyncMemory:
        """Lazily create AsyncMemory once."""
        if self.memory is not None:
            return self.memory
        async with self._create_lock:
            if self.memory is None:
                # Attach an independent connection pool to this instance's config copy
                # before handing it to AsyncMemory.from_config().  The pool is owned
                # exclusively by this client instance and is closed in aclose().
                from .pgvector_config import attach_pgvector_pool

                if "vector_store" in self.config and isinstance(
                    self.config["vector_store"], dict
                ):
                    vs_cfg = self.config["vector_store"].get("config")
                    if isinstance(vs_cfg, dict):
                        attach_pgvector_pool(vs_cfg)

                # Acquire the process-level init lock in a thread to avoid blocking
                # the event loop. This serialises concurrent from_config() calls and
                # prevents pgvector's CREATE EXTENSION from racing across sessions.
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _mem0_init_lock.acquire)
                try:
                    self.memory = await _resolve_async_memory_from_config(self.config)
                finally:
                    _mem0_init_lock.release()
                _patch_llm_compat(getattr(self.memory, "llm", None))
                logger.debug("AsyncMemory instance created")

                # Start connection keep-alive after memory is created
                if self._enable_keepalive and self._keepalive is None:
                    # Note: ConnectionKeepAlive works with both Memory and AsyncMemory
                    # as it accesses the underlying clients directly
                    self._keepalive = ConnectionKeepAlive(
                        memory=self.memory,
                        interval=self._keepalive_interval,
                    )
                    self._keepalive.start()
        return self.memory

    async def aclose(self) -> None:
        """Close and cleanup resources held by AsyncMemory.

        Mem0's resources (PGVector, SQLiteManager, etc.) all implement __del__
        methods that automatically clean up when objects are garbage collected.
        However, for long-running processes, explicit cleanup is recommended.

        This method explicitly closes critical resources (connection pools, database
        connections) and then clears the reference to allow GC to handle the rest.

        Note: Designed to be called from the background event loop via
        `asyncio.run_coroutine_threadsafe()`.

        """
        # Stop connection keep-alive first regardless of whether memory was created.
        if hasattr(self, "_keepalive") and self._keepalive is not None:
            try:
                self._keepalive.stop()
            except Exception:
                logger.exception("Error stopping connection keep-alive")

        if self.memory is None:
            # Memory was never successfully created, but a connection pool may have
            # been attached to self.config already (via config_override or create()).
            # Close it explicitly; psycopg3 ConnectionPool owns background threads that
            # should not be left running when the client is discarded.
            try:
                vs_cfg = (self.config.get("vector_store") or {}).get("config") or {}
                pool = vs_cfg.get("connection_pool")
                if pool is not None:
                    loop = asyncio.get_running_loop()
                    if hasattr(pool, "close"):
                        await loop.run_in_executor(None, pool.close)
                    elif hasattr(pool, "closeall"):
                        await loop.run_in_executor(None, pool.closeall)
            except Exception:
                logger.exception(
                    "Error closing connection pool (AsyncMemory was not initialized)"
                )
            return

        logger.debug("Closing AsyncMemory resources")
        try:
            await close_memory_resources(self.memory, client=self)
        except Exception:
            logger.exception("Error during AsyncMemory resource cleanup")
        finally:
            # Always clear reference to allow GC and __del__ methods to handle cleanup
            self.memory = None
            logger.debug("AsyncMemory resources closed")

    @classmethod
    def ensure_bg_loop(cls) -> asyncio.AbstractEventLoop:
        """Ensure that a background asyncio event loop is running in a dedicated thread.

        This method provides a long-lived, reusable, process-wide background event loop
        for submitting and running coroutines from synchronous code or from threads that
        do not have a running event loop. The loop is created once and reused for the
        entire plugin lifecycle, ensuring efficient resource usage and avoiding the
        overhead of creating new loops for each operation.

        The event loop runs in a dedicated daemon thread and persists until the plugin
        is shut down via shutdown(). This design ensures:
        - Long lifecycle: Loop exists for the entire plugin runtime
        - Reusability: Same loop instance is returned for all operations
        - Thread safety: Access is guarded by a class-level lock
        - Resource efficiency: No per-operation loop creation overhead

        Returns:
            asyncio.AbstractEventLoop: The long-lived, reusable background event loop object.

        Raises:
            RuntimeError: If the background event loop fails to start.

        """
        return BackgroundEventLoop.ensure_loop()

    @classmethod
    def shutdown(cls, timeout: float = 3.0) -> None:
        """Best-effort graceful shutdown of the background event loop.

        - Attempts to wait up to `timeout` seconds for pending tasks to finish.
        - Stops the loop and joins the background thread (best-effort).
        - Safe to call multiple times.

        Args:
            timeout: Maximum time to wait for pending tasks to complete.

        """
        BackgroundEventLoop.shutdown(timeout)

    async def search(
        self,
        payload: dict[str, Any],
        timeout_s: int | None = None,
    ) -> list[dict[str, Any]]:
        """Search for memories based on a query.

        Args:
            payload (dict): Search parameters. Supported keys:
                - query (str): Query to search for.
                - user_id (str, optional): ID of the user.
                - agent_id (str, optional): ID of the agent.
                - run_id (str, optional): ID of the run.
                - limit (int, optional): Max number of results.
                - filters (dict, optional): Metadata filters, supporting:
                    * {"key": "value"} (exact match)
                    * {"key": {"eq"/"ne"/"in"/"nin"/"gt"/"gte"/"lt"/"lte"/"contains"/"icontains"}: ...}
                    * {"key": "*"} (wildcard)
                    * {"AND"/"OR"/"NOT": [filters,...]} (logic ops)
                - threshold (float, optional): Minimum score (not used in local mode).
            timeout_s (int | None, optional): Timeout seconds for this read operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to READ_OPERATION_TIMEOUT.

        Returns:
            list[dict]: List of memory search results.

        """  # noqa: E501
        query = payload.get("query", "")
        filters = payload.get("filters")
        limit = payload.get("limit")

        # Normalize limit to int when possible
        lim: int | None
        try:
            lim = int(limit) if limit is not None else None
        except (TypeError, ValueError):
            lim = None

        # Build kwargs with non-empty args to simplify branching
        kwargs: dict[str, Any] = {}
        if lim is not None:
            kwargs["limit"] = lim
        
        # Always extract user_id/agent_id/run_id from payload (required by mem0)
        if payload.get("user_id"):
            kwargs["user_id"] = payload.get("user_id")
        if payload.get("agent_id"):
            kwargs["agent_id"] = payload.get("agent_id")
        if payload.get("run_id"):
            kwargs["run_id"] = payload.get("run_id")
        
        # Add filters if provided
        if isinstance(filters, dict):
            kwargs["filters"] = filters

        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=READ_OPERATION_TIMEOUT,
        )

        async def _call() -> object:
            return await self.memory.search(query, **kwargs)

        results = await self._run_with_semaphore(
            "search",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Read operations check queue
        )
        return normalize_search_results(results, score_mode=self.score_mode)

    async def add(
        self,
        payload: dict[str, Any],
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        """Create a new memory.

        Adds new memories scoped to a single session id (e.g. user_id, agent_id, or run_id).
        One of those ids is required.

        Args:
            payload (dict): A dictionary containing all parameters for adding a memory, including:
                - messages (str or list[dict[str, str]]): The message content or list of messages
                  (e.g., [{"role": "user", "content": "Hello"}, ...]) to process and store.
                - user_id (str, optional): ID of the user creating the memory.
                - agent_id (str, optional): ID of the agent creating the memory.
                - run_id (str, optional): ID of the run creating the memory.
                - metadata (dict or str, optional): Metadata to store with the memory.
                  Can be a dict or a JSON string.
                - infer (bool, optional): If True (default), uses LLM to extract key facts
                  and manage memories.
                - custom_fact_extraction_prompt (str, optional): Per-call prompt used
                  for fact extraction when infer=True.
                - memory_type (str, optional): Type of memory. Defaults to conversational or factual.
                  Use "procedural_memory" for procedural type.
                - prompt (str, optional): Custom prompt to use for memory creation.
            timeout_s (int | None, optional): Timeout seconds for this write operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to WRITE_OPERATION_TIMEOUT.

        Returns:
            dict: Result of the memory addition, typically with items added/updated (in "results"),
            and possibly "relations" if graph store is enabled.

        """  # noqa: E501
        metadata = payload.get("metadata")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = None

        kwargs: dict[str, Any] = {}
        if payload.get("user_id"):
            kwargs["user_id"] = payload.get("user_id")
        if payload.get("agent_id"):
            kwargs["agent_id"] = payload.get("agent_id")
        if payload.get("run_id"):
            kwargs["run_id"] = payload.get("run_id")
        if metadata is not None:
            kwargs["metadata"] = metadata
        
        # Explicitly pass infer parameter if provided, default to True
        # This ensures memory extraction happens even if Mem0's default behavior changes
        infer = payload.get("infer", True)
        kwargs["infer"] = infer
        custom_prompt = (
            _get_custom_fact_extraction_prompt(payload) if infer else None
        )

        messages = payload.get("messages")
        # Skip add when messages is empty/blank, return response aligned with mem0 add result shape
        if (
            messages is None
            or (isinstance(messages, str) and messages.strip() == "")
            or (isinstance(messages, list | tuple) and len(messages) == 0)
        ):
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Mem0 add skipped (async): empty messages, ids=%s infer=%s",
                    _summarize_ids(kwargs),
                    infer,
                )
            return ADD_SKIP_RESULT

        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=WRITE_OPERATION_TIMEOUT,
        )

        async def _call() -> object:
            memory = (
                _clone_memory_with_fact_extraction_prompt(self.memory, custom_prompt)
                if custom_prompt
                else self.memory
            )
            return await memory.add(messages, **kwargs)

        if logger.isEnabledFor(logging.DEBUG):
            metadata_keys = (
                sorted(metadata.keys()) if isinstance(metadata, dict) else None
            )
            logger.debug(
                "Mem0 add request summary (async): ids=%s infer=%s custom_prompt=%s "
                "metadata_keys=%s messages=%s timeout_s=%s",
                _summarize_ids(kwargs),
                infer,
                bool(custom_prompt),
                metadata_keys,
                _summarize_messages(messages),
                timeout,
            )
        result = await self._run_with_semaphore(
            "add",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Write operations check queue
        )
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Mem0 add result summary (async): %s",
                _summarize_add_result(result),
            )
        return result

    async def get_all(
        self,
        params: dict[str, Any],
        timeout_s: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get all memories based on user/agent/run identifiers with optional filters.

        Args:
            params (dict): Parameters including:
                - user_id (str, optional): User ID to filter by.
                - agent_id (str, optional): Agent ID to filter by.
                - run_id (str, optional): Run ID to filter by.
                - limit (int, optional): Maximum number of results to return.
                - filters (dict, optional): Advanced metadata filters.
            timeout_s (int | None, optional): Timeout seconds for this read operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to READ_OPERATION_TIMEOUT.

        Returns:
            list[dict]: List of memory objects.

        """
        # Build kwargs with all provided parameters
        kwargs: dict[str, Any] = {}

        # Add entity IDs if provided
        if params.get("user_id"):
            kwargs["user_id"] = params.get("user_id")
        if params.get("agent_id"):
            kwargs["agent_id"] = params.get("agent_id")
        if params.get("run_id"):
            kwargs["run_id"] = params.get("run_id")

        # Add optional parameters
        limit = params.get("limit")
        if limit is not None:
            with contextlib.suppress(TypeError, ValueError):
                kwargs["limit"] = int(limit)

        filters = params.get("filters")
        if isinstance(filters, dict):
            kwargs["filters"] = filters

        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=READ_OPERATION_TIMEOUT,
        )

        async def _call() -> dict[str, Any]:
            return await self.memory.get_all(**kwargs)

        # Mem0's get_all always returns {"results": [...]} format
        result = await self._run_with_semaphore(
            "get_all",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Read operations check queue
        )
        return result.get("results", []) if isinstance(result, dict) else []

    async def get(
        self,
        memory_id: str,
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        """Get a single memory by ID.

        Args:
            memory_id (str): The ID of the memory to retrieve.
            timeout_s (int | None, optional): Timeout seconds for this read operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to READ_OPERATION_TIMEOUT.

        Returns:
            dict: Memory object with id, memory, metadata, created_at, updated_at, etc.

        """
        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=READ_OPERATION_TIMEOUT,
        )

        async def _call() -> dict[str, Any]:
            try:
                return await self.memory.get(memory_id)
            except (AttributeError, ValueError) as e:
                # Catch AttributeError from mem0 when existing_memory is None
                # or ValueError when memory not found
                # Convert to a consistent ValueError
                if (
                    "'NoneType' object has no attribute" in str(e)
                    or "not found" in str(e).lower()
                ):
                    error_msg = (
                        f"Memory with ID {memory_id} not found. "
                        "Please provide a valid 'memory_id'"
                    )
                    raise ValueError(error_msg) from e
                # Re-raise other AttributeErrors/ValueErrors
                raise

        return await self._run_with_semaphore(
            "get",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Read operations check queue
        )

    async def update(
        self,
        memory_id: str,
        payload: dict[str, Any],
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        """Update a memory by ID.

        Args:
            memory_id (str): ID of the memory to update.
            payload (dict): Dictionary containing new content under the "text" key.
            timeout_s (int | None, optional): Timeout seconds for this write operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to WRITE_OPERATION_TIMEOUT.

        Returns:
            dict: Success message indicating the memory was updated.

        """
        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=WRITE_OPERATION_TIMEOUT,
        )

        async def _call() -> dict[str, Any]:
            try:
                return await self.memory.update(memory_id, payload.get("text"))
            except (AttributeError, ValueError) as e:
                # Catch AttributeError from mem0 when existing_memory is None
                # or ValueError when memory not found
                # Convert to a consistent ValueError
                error_str = str(e)
                if (
                    "'NoneType' object has no attribute 'payload'" in error_str
                    or "not found" in error_str.lower()
                ):
                    error_msg = (
                        f"Memory with ID {memory_id} not found. "
                        "It may have already been deleted or never existed."
                    )
                    raise ValueError(error_msg) from e
                # Re-raise other AttributeErrors/ValueErrors
                raise

        return await self._run_with_semaphore(
            "update",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Write operations check queue
        )

    async def delete(
        self,
        memory_id: str,
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        """Delete a memory by ID.

        Args:
            memory_id (str): The ID of the memory to delete.
            timeout_s (int | None, optional): Timeout seconds for this write operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to WRITE_OPERATION_TIMEOUT.

        Returns:
            dict: Success message, typically {"message": "Memory deleted successfully!"}.

        """
        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=WRITE_OPERATION_TIMEOUT,
        )

        async def _call() -> dict[str, Any]:
            try:
                return await self.memory.delete(memory_id)
            except (AttributeError, ValueError) as e:
                # Catch AttributeError from mem0 when existing_memory is None
                # or ValueError when memory not found
                # This can happen if the memory was already deleted or doesn't exist
                # Convert to a consistent ValueError
                error_str = str(e)
                if (
                    "'NoneType' object has no attribute 'payload'" in error_str
                    or "not found" in error_str.lower()
                ):
                    error_msg = (
                        f"Memory with ID {memory_id} not found. "
                        "It may have already been deleted or never existed."
                    )
                    raise ValueError(error_msg) from e
                # Re-raise other AttributeErrors/ValueErrors
                raise

        return await self._run_with_semaphore(
            "delete",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Write operations check queue
        )

    async def delete_all(
        self,
        params: dict[str, Any],
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        """Delete all memories matching the given filters.

        Args:
            params (dict): Parameters including:
                - user_id (str, optional): User ID to filter by.
                - agent_id (str, optional): Agent ID to filter by.
                - run_id (str, optional): Run ID to filter by.
            timeout_s (int | None, optional): Timeout seconds for this write operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to WRITE_OPERATION_TIMEOUT.

        Returns:
            dict: Result of the deletion operation.

        """
        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=WRITE_OPERATION_TIMEOUT,
        )

        async def _call() -> dict[str, Any]:
            return await self.memory.delete_all(
                user_id=params.get("user_id"),
                agent_id=params.get("agent_id"),
                run_id=params.get("run_id"),
            )

        return await self._run_with_semaphore(
            "delete_all",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Write operations check queue
        )

    async def history(
        self,
        memory_id: str,
        timeout_s: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get the history of changes for a specific memory.

        Args:
            memory_id (str): The ID of the memory to get history for.
            timeout_s (int | None, optional): Timeout seconds for this read operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to READ_OPERATION_TIMEOUT.

        Returns:
            list[dict]: List of history records with old_memory, new_memory, event, created_at, etc.

        """
        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=READ_OPERATION_TIMEOUT,
        )

        async def _call() -> list[dict[str, Any]]:
            return await self.memory.history(memory_id)

        return await self._run_with_semaphore(
            "history",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Read operations check queue
        )

    def _get_operation_timeout_s(
        self,
        timeout_s: int | None,
        default_s: int,
    ) -> int:
        """Resolve a safe timeout for async operations (read or write).

        Args:
            timeout_s: Optional timeout in seconds (int). If None, uses default_s.
            default_s: Default timeout in seconds (int).

        Returns:
            int: Valid timeout value in seconds.

        """
        if timeout_s is None:
            return default_s
        # Ensure is valid non-negative integer
        try:
            int_value = int(timeout_s)
        except (TypeError, ValueError):
            return default_s
        if int_value < 0:
            return default_s
        return int_value

    async def _run_with_semaphore(
        self,
        op_name: str,
        fn: Callable[[], Awaitable[T]],
        timeout_s: int | None = None,
        *,
        check_queue: bool = True,
    ) -> T:
        """Unified method to run async operations with queue check, semaphore, and timeout.

        This method provides:
        1. Optional queue overload check before execution
        2. Semaphore-controlled concurrency
        3. Detailed timing logs (wait time + execution time)
        4. Optional timeout protection

        Logging strategy:
        - Queue overload: Logged here with technical details
        - Timeout: Logged here with technical details
        - Tool layer should NOT duplicate these logs, but should enhance return results
          with error context for upstream applications

        Args:
            op_name: Operation name for logging (e.g., "search", "add").
            fn: Async function to execute within semaphore.
            timeout_s: Optional timeout in seconds (int). If None, no timeout limit.
            check_queue: Whether to check queue length before execution.

        Returns:
            Result from fn().

        Raises:
            QueueOverloadError: If queue is overloaded and check_queue is True.
            TimeoutError: If operation exceeds timeout_s.

        """
        # 1. Queue overload check (optional, for both read and write operations)
        # Log at first occurrence - tool layer should NOT duplicate this log
        if check_queue:
            pending = TaskTracker.get_pending_tasks_count()
            if pending > self.max_ops * MAX_PENDING_TASKS_MULTIPLIER:
                logger.warning(
                    "%s operation rejected: queue overloaded (%d pending tasks, max: %d)",
                    op_name.capitalize(),
                    pending,
                    self.max_ops * MAX_PENDING_TASKS_MULTIPLIER,
                )
                error_msg = (
                    f"Queue overloaded: {pending} pending tasks "
                    f"(max: {self.max_ops * MAX_PENDING_TASKS_MULTIPLIER})"
                )
                raise QueueOverloadError(error_msg)

        # 2. Execute operation with timing and semaphore control
        async def _inner() -> T:
            await self.create()

            # Record semaphore wait time
            wait_start = time.time()
            async with self._semaphore:
                wait_time = time.time() - wait_start

                # Record Mem0 execution time
                exec_start = time.time()
                result = await fn()
                exec_time = time.time() - exec_start

                # Log timing breakdown
                logger.debug(
                    "%s operation timing: wait=%.3fs, exec=%.3fs, total=%.3fs",
                    op_name.capitalize(),
                    wait_time,
                    exec_time,
                    wait_time + exec_time,
                )

                return result

        # 3. Apply timeout protection if specified
        # Log timeout at first occurrence - tool layer should NOT duplicate this log
        if timeout_s is not None:
            try:
                return await asyncio.wait_for(_inner(), timeout=timeout_s)
            except TimeoutError:
                logger.warning(
                    "%s operation timed out after %ds (TimeoutError)",
                    op_name.capitalize(),
                    timeout_s,
                )
                raise
        else:
            # No timeout limit
            return await _inner()


def _get_config_hash(credentials: dict[str, Any]) -> str:
    """Generate a hash from credentials for cache key.

    This function creates a hash of the credentials to detect configuration changes.
    The hash is used only for in-memory comparison and is never logged or included
    in exception messages to avoid exposing sensitive information.

    Security notes:
    - Uses SHA256 (one-way hash) - credentials cannot be recovered from the hash
    - Hash value is only stored in memory, never logged or printed
    - Hash includes all credential fields (including sensitive ones like api_key,
      password, token) but the hash itself is safe to use for comparison

    Args:
        credentials: Configuration dictionary (may contain sensitive fields like
            api_key, password, token, etc.).

    Returns:
        str: SHA256 hash of the serialized credentials (hex digest).

    """
    try:
        cred_str = json.dumps(credentials, sort_keys=True)
        return hashlib.sha256(cred_str.encode()).hexdigest()
    except Exception as e:
        # If serialization fails, log the error and return empty string to disable caching
        logger.exception(
            "Failed to generate config hash from credentials: %s",
            type(e).__name__,
        )
        return ""


def cleanup_async_client(
    client: AsyncMem0Client | None, context: str = "cleanup"
) -> None:
    """Cleanup AsyncMem0Client resources via background event loop.

    This helper function provides a unified way to cleanup AsyncMem0Client
    instances, avoiding code duplication.

    Args:
        client: The AsyncMem0Client instance to cleanup.
        context: Context string for logging (e.g., "replacement", "reset").

    """
    if client is None:
        return

    # Stop keepalive first (synchronous operation, doesn't require event loop)
    # This prevents keepalive from accessing closed resources
    if hasattr(client, "_keepalive") and client._keepalive is not None:
        try:
            client._keepalive.stop()
            logger.debug("Stopped keepalive for AsyncMem0Client during %s", context)
        except Exception:
            logger.exception("Error stopping keepalive for AsyncMem0Client during %s", context)

    loop = BackgroundEventLoop._loop  # noqa: SLF001
    if loop is not None and loop.is_running():
        try:
            fut = asyncio.run_coroutine_threadsafe(client.aclose(), loop)
            try:
                fut.result(timeout=2.0)
            except TimeoutError:
                logger.warning(
                    "Async client cleanup timed out during %s",
                    context,
                )
            except Exception as e:
                logger.debug(
                    "Async client cleanup failed during %s: %s",
                    context,
                    e,
                )
        except Exception as e:
            logger.debug(
                "Could not submit async cleanup during %s: %s",
                context,
                e,
            )
    else:
        logger.debug(
            "No background loop available for async cleanup during %s",
            context,
        )


# Module-level client instances and locks for thread-safe caching
# Using a dictionary to hold state, avoiding global statements
_cache: dict[str, Any] = {
    "sync_client": None,
    "sync_client_config_hash": None,
    "sync_client_lock": threading.Lock(),
    "async_client": None,
    "async_client_config_hash": None,
    "async_client_lock": threading.Lock(),
}


def _init_queue_monitor(_credentials: dict[str, Any]) -> None:
    """Initialize queue monitor with default interval.

    Args:
        _credentials: Configuration dictionary (unused, kept for compatibility).

    Note:
        queue_monitor_interval configuration has been removed.
        Queue monitor now uses a fixed default interval of 300 seconds (5 minutes).

    This function is called whenever a new async client is created.
    QueueMonitor.start() will return early if the monitor is already running,
    so it's safe to call this multiple times.

    """
    try:
        # Use fixed default interval (300 seconds = 5 minutes)
        # queue_monitor_interval configuration has been removed from credentials
        interval = 300

        if interval > 0:
            from .queue_monitor import QueueMonitor

            monitor = QueueMonitor.get_instance(interval)
            # start() returns True if thread was started, False if already running
            was_started = monitor.start(
                AsyncMem0Client.get_pending_tasks_count,
                AsyncMem0Client.get_completed_stats,
            )
            # Only log if monitor was actually started (not already running)
            if was_started:
                logger.debug("Queue monitor initialized (interval: %ds)", interval)
        else:
            logger.debug("Queue monitor disabled (interval: 0)")
    except Exception:
        logger.exception("Failed to initialize queue monitor, continuing without it")


def get_sync_client(credentials: dict[str, Any]) -> SyncMem0Client:
    """Get or create SyncMem0Client instance, recreating if config changed.

    This function provides a module-level factory for SyncMem0Client instances,
    ensuring resource reuse while supporting configuration changes.

    All reads and writes to module-level variables are protected by
    threading.Lock to ensure thread safety in multi-threaded environments.

    Args:
        credentials: Configuration dictionary for the SyncMem0Client.

    Returns:
        SyncMem0Client: The SyncMem0Client instance, reused if config unchanged.

    """
    config_hash = _get_config_hash(credentials)

    # All reads and writes are protected by lock to ensure thread safety
    with _cache["sync_client_lock"]:
        # If config changed or client doesn't exist, create new instance
        if (
            _cache["sync_client"] is None
            or _cache["sync_client_config_hash"] != config_hash
        ):
            # Cleanup old client before creating new one to prevent resource leaks
            old_client = _cache["sync_client"]
            if old_client is not None:
                logger.debug(
                    "Replacing SyncMem0Client due to config change, cleaning up old instance"
                )
                # Stop keepalive first to prevent accessing closed resources
                if hasattr(old_client, "_keepalive") and old_client._keepalive is not None:
                    try:
                        old_client._keepalive.stop()
                        logger.debug("Stopped keepalive for old SyncMem0Client")
                    except Exception:
                        logger.exception(
                            "Error stopping keepalive for old SyncMem0Client"
                        )
                # Close resources explicitly
                try:
                    old_client.close()
                except Exception:
                    logger.exception(
                        "Error closing old SyncMem0Client, relying on __del__ for cleanup"
                    )
            
            _cache["sync_client"] = SyncMem0Client(credentials)
            _cache["sync_client_config_hash"] = config_hash
        return _cache["sync_client"]


def get_async_client(credentials: dict[str, Any]) -> AsyncMem0Client:
    """Get or create AsyncMem0Client instance, recreating if config changed.

    This function provides a module-level factory for AsyncMem0Client instances,
    ensuring resource reuse while supporting configuration changes.

    All reads and writes to module-level variables are protected by
    threading.Lock to ensure thread safety in multi-threaded environments.

    Args:
        credentials: Configuration dictionary for the AsyncMem0Client.

    Returns:
        AsyncMem0Client: The AsyncMem0Client instance, reused if config unchanged.

    """
    config_hash = _get_config_hash(credentials)

    # All reads and writes are protected by lock to ensure thread safety
    with _cache["async_client_lock"]:
        # If config changed or client doesn't exist, create new instance
        if (
            _cache["async_client"] is None
            or _cache["async_client_config_hash"] != config_hash
        ):
            # Cleanup old client before creating new one to prevent resource leaks
            old_client = _cache["async_client"]
            if old_client is not None:
                logger.debug(
                    "Replacing AsyncMem0Client due to config change, cleaning up old instance",
                )
                cleanup_async_client(old_client, context="replacement")
            _cache["async_client"] = AsyncMem0Client(credentials)
            _cache["async_client_config_hash"] = config_hash

            # Initialize queue monitor whenever a new client is created
            _init_queue_monitor(credentials)

    return _cache["async_client"]


def reset_clients() -> None:
    """Reset client instances (useful for testing).

    This function clears the cached client instances, forcing new instances
    to be created on the next call to get_sync_client() or get_async_client().

    For AsyncMem0Client, this also attempts to cleanup resources (HTTP sessions,
    database connections, etc.) to prevent resource leaks.

    """
    with _cache["sync_client_lock"]:
        _cache["sync_client"] = None
        _cache["sync_client_config_hash"] = None

    with _cache["async_client_lock"]:
        # Cleanup async client resources before resetting
        old_client = _cache["async_client"]
        if old_client is not None:
            cleanup_async_client(old_client, context="reset")

        _cache["async_client"] = None
        _cache["async_client_config_hash"] = None


def get_current_async_client() -> AsyncMem0Client | None:
    """Get the current cached async client instance (if any).

    This is used for cleanup operations where we need to access the current
    client instance without credentials.

    Returns:
        AsyncMem0Client | None: The current async client instance, or None if not created.

    """
    with _cache["async_client_lock"]:
        return _cache["async_client"]
