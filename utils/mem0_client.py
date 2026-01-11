"""Client adapter for Mem0 local mode only."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from mem0 import AsyncMemory, Memory

from .background_loop import BackgroundEventLoop
from .config_builder import build_local_mem0_config
from .connection_keepalive import ConnectionKeepAlive
from .constants import (
    ADD_SKIP_RESULT,
    CUSTOM_PROMPT,
    HEARTBEAT_INTERVAL,
    MAX_CONCURRENT_MEMORY_OPERATIONS,
    MAX_PENDING_TASKS_MULTIPLIER,
    READ_OPERATION_TIMEOUT,
    WRITE_OPERATION_TIMEOUT,
)
from .helpers import parse_positive_int
from .logger import get_logger
from .resource_cleanup import close_memory_resources
from .task_tracker import TaskTracker

logger = get_logger(__name__)

if TYPE_CHECKING:
    from collections.abc import Awaitable

T = TypeVar("T")


def normalize_search_results(results: object) -> list[dict[str, Any]]:
    """Normalize Mem0 search results into a list of dicts.

    Args:
        results: Raw search results from Mem0, which can be:
            - A list of dicts
            - A dict with "results" key containing a list
            - None or empty

    Returns:
        list[dict]: Normalized list of memory search results with consistent structure.

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
        normalized.append(
            {
                "id": r.get("id") or r.get("memory_id") or "",
                "memory": r.get("memory") or r.get("text") or "",
                "score": r.get("score") or r.get("similarity", 0.0),
                "metadata": r.get("metadata") or {},
                "created_at": r.get("created_at") or r.get("timestamp") or "",
            },
        )
    return normalized


class QueueOverloadError(Exception):
    """Raised when the background task queue is overloaded."""


class SyncMem0Client:
    """Synchronous Mem0 client using configured providers."""

    def __init__(self, credentials: dict[str, Any]) -> None:
        """Initialize the SyncMem0Client.

        Args:
            credentials (dict): Configuration for the SyncMem0Client.

        """
        config = build_local_mem0_config(credentials)
        self.memory = Memory.from_config(config)
        self.use_custom_prompt = True
        self.custom_prompt = CUSTOM_PROMPT

        # Initialize connection keep-alive
        # Minimum interval is 30 seconds to ensure reasonable heartbeat frequency
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

        logger.debug("SyncMem0Client initialized")

    def __del__(self) -> None:
        """Cleanup resources when SyncMem0Client is destroyed."""
        if hasattr(self, "_keepalive"):
            with contextlib.suppress(Exception):
                self._keepalive.stop()

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
        if isinstance(filters, dict):
            kwargs["filters"] = filters
        else:
            if payload.get("user_id"):
                kwargs["user_id"] = payload.get("user_id")
            if payload.get("agent_id"):
                kwargs["agent_id"] = payload.get("agent_id")
            if payload.get("run_id"):
                kwargs["run_id"] = payload.get("run_id")

        try:
            results = self.memory.search(query, **kwargs)
            normalized = normalize_search_results(results)
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
        if self.use_custom_prompt:
            kwargs["prompt"] = self.custom_prompt

        # Use messages directly if provided; assume upstream has validated inputs
        messages = payload.get("messages")
        try:
            result = self.memory.add(messages, **kwargs)
        except Exception:
            logger.exception("Error during memory addition")
            raise
        else:
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

        """
        try:
            result = self.memory.delete(memory_id)
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

    def __init__(self, credentials: dict[str, Any]) -> None:
        """Initialize the AsyncMem0Client.

        Args:
            credentials (dict): Configuration for the AsyncMem0Client.

        """
        self.config = build_local_mem0_config(credentials)
        self.memory = None
        # Async lock to protect one-time asynchronous initialization.
        self._create_lock = asyncio.Lock()

        # Parse config value
        self.max_ops = parse_positive_int(
            credentials.get("max_concurrent_memory_operations"),
            MAX_CONCURRENT_MEMORY_OPERATIONS,
            logger=logger,
            config_name="max_concurrent_memory_operations",
        )

        self._semaphore = asyncio.Semaphore(self.max_ops)
        # Toggle whether to use custom prompt
        self.use_custom_prompt = True
        self.custom_prompt = CUSTOM_PROMPT

        # Initialize connection keep-alive
        # Minimum interval is 30 seconds to ensure reasonable heartbeat frequency
        heartbeat_interval = parse_positive_int(
            credentials.get("heartbeat_interval"),
            HEARTBEAT_INTERVAL,
            min_value=30,
            logger=logger,
            config_name="heartbeat_interval",
        )
        self._keepalive: ConnectionKeepAlive | None = None
        self._keepalive_interval = heartbeat_interval

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
                self.memory = await AsyncMemory.from_config(self.config)
                logger.debug("AsyncMemory instance created")

                # Start connection keep-alive after memory is created
                if self._keepalive is None:
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
        if self.memory is None:
            return

        logger.debug("Closing AsyncMemory resources")
        try:
            await close_memory_resources(self.memory)
        except Exception:
            logger.exception("Error during AsyncMemory resource cleanup")
        finally:
            # Stop connection keep-alive
            if hasattr(self, "_keepalive") and self._keepalive is not None:
                try:
                    self._keepalive.stop()
                except Exception:
                    logger.exception("Error stopping connection keep-alive")

            # Clear reference - remaining resources will be cleaned up by __del__ methods
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
        if isinstance(filters, dict):
            kwargs["filters"] = filters
        else:
            if payload.get("user_id"):
                kwargs["user_id"] = payload.get("user_id")
            if payload.get("agent_id"):
                kwargs["agent_id"] = payload.get("agent_id")
            if payload.get("run_id"):
                kwargs["run_id"] = payload.get("run_id")

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
        return normalize_search_results(results)

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
        await self.create()
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
        if self.use_custom_prompt:
            kwargs["prompt"] = self.custom_prompt

        messages = payload.get("messages")
        # Skip add when messages is empty/blank, return response aligned with mem0 add result shape
        if (
            messages is None
            or (isinstance(messages, str) and messages.strip() == "")
            or (isinstance(messages, (list, tuple)) and len(messages) == 0)
        ):
            return ADD_SKIP_RESULT

        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=WRITE_OPERATION_TIMEOUT,
        )

        async def _call() -> object:
            return await self.memory.add(messages, **kwargs)

        return await self._run_with_semaphore(
            "add",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Write operations check queue
        )

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
                if "'NoneType' object has no attribute" in str(e) or "not found" in str(e).lower():
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
            asyncio.TimeoutError: If operation exceeds timeout_s.

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
                logger.info(
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
            except asyncio.TimeoutError:
                logger.warning(
                    "%s operation timed out after %ds (asyncio.TimeoutError)",
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


def cleanup_async_client(client: AsyncMem0Client | None, context: str = "cleanup") -> None:
    """Cleanup AsyncMem0Client resources via background event loop.

    This helper function provides a unified way to cleanup AsyncMem0Client
    instances, avoiding code duplication.

    Args:
        client: The AsyncMem0Client instance to cleanup.
        context: Context string for logging (e.g., "replacement", "reset").

    """
    if client is None:
        return

    loop = BackgroundEventLoop._loop  # noqa: SLF001
    if loop is not None and loop.is_running():
        try:
            fut = asyncio.run_coroutine_threadsafe(client.aclose(), loop)
            # Waiting for cleanup to complete
            fut.result(timeout=2.0)
        except Exception:
            logger.exception(
                "Failed to cleanup async client resources during %s",
                context,
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
        if _cache["sync_client"] is None or _cache["sync_client_config_hash"] != config_hash:
            # SyncMem0Client resources (PGVector, SQLiteManager) have __del__ methods
            # that will be called during GC when the old reference is overwritten.
            # SyncMem0Client doesn't have a close() method, so we rely on __del__
            # methods in mem0 resources for cleanup.
            if _cache["sync_client"] is not None:
                logger.debug("Replacing SyncMem0Client due to config change")
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
        if _cache["async_client"] is None or _cache["async_client_config_hash"] != config_hash:
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
