"""Client adapter for Mem0 local mode only."""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
from typing import Any

from mem0 import AsyncMemory, Memory

from .config_builder import build_local_mem0_config
from .constants import ADD_SKIP_RESULT, CUSTOM_PROMPT, MAX_CONCURRENT_MEM_ADDS


def _normalize_search_results(results: object) -> list[dict[str, Any]]:
    """Normalize Mem0 search results into a list of dicts."""
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
                "categories": r.get("categories") or [],
                "created_at": r.get("created_at") or r.get("timestamp") or "",
            },
        )
    return normalized


class LocalClient:
    """Local Mem0 client using configured providers."""

    def __init__(self, credentials: dict[str, Any]) -> None:
        config = build_local_mem0_config(credentials)
        self.memory = Memory.from_config(config)
        # Keep behavior aligned with AsyncLocalClient
        self.use_custom_prompt = True
        self.custom_prompt = CUSTOM_PROMPT

    def search(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        query = payload.get("query", "")
        filters = payload.get("filters")
        limit = payload.get("limit")
        # In local mode, ignore any API version settings; support filters when provided
        if isinstance(filters, dict):
            if limit is not None:
                results = self.memory.search(query, filters=filters, limit=limit)
            else:
                results = self.memory.search(query, filters=filters)
        elif limit is not None:
            results = self.memory.search(
                query,
                user_id=payload.get("user_id"),
                agent_id=payload.get("agent_id"),
                run_id=payload.get("run_id"),
                limit=limit,
            )
        else:
            results = self.memory.search(
                query,
                user_id=payload.get("user_id"),
                agent_id=payload.get("agent_id"),
                run_id=payload.get("run_id"),
            )
        normalized = _normalize_search_results(results)
        try:
            lim = int(limit) if limit is not None else None
        except (TypeError, ValueError):
            lim = None
        return normalized[:lim] if lim and lim > 0 else normalized

    def add(self, payload: dict[str, Any]) -> dict[str, Any]:
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
        return self.memory.add(messages, **kwargs)

    def get_all(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        filters = params.get("filters")
        # In local mode, ignore version; support filters directly when provided
        if isinstance(filters, dict):
            # Prefer calling with filters only if supported by mem0
            try:
                results = self.memory.get_all(filters=filters)
            except TypeError:
                # Fallback: if filters signature unsupported, return empty list
                results = []
        else:
            results = self.memory.get_all(
                user_id=params.get("user_id"),
                agent_id=params.get("agent_id"),
                run_id=params.get("run_id"),
            )
        return results or []

    def get(self, memory_id: str) -> dict[str, Any]:
        return self.memory.get(memory_id)

    def update(self, memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.memory.update(memory_id, payload.get("text"))

    def delete(self, memory_id: str) -> dict[str, Any]:
        return self.memory.delete(memory_id)

    def delete_all(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.memory.delete_all(
            user_id=params.get("user_id"),
            agent_id=params.get("agent_id"),
            run_id=params.get("run_id"),
        )

    def history(self, memory_id: str) -> list[dict[str, Any]]:
        return self.memory.history(memory_id)


class AsyncLocalClient:
    """Async local Mem0 client using configured providers."""

    _instance: AsyncLocalClient | None = None
    _instance_lock = threading.Lock()

    def __new__(cls, _credentials: dict[str, Any]) -> AsyncLocalClient:
        """Create or return the singleton instance of AsyncLocalClient.

        Ensures a single process-wide instance guarded by a class-level lock,
        ignoring repeated constructor calls.
        """
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, credentials: dict[str, Any]) -> None:
        # Guard against re-initializing singleton
        if getattr(self, "_initialized", False):
            return
        self.config = build_local_mem0_config(credentials)
        self.memory = None
        # Async lock to protect one-time asynchronous initialization.
        self._create_lock = asyncio.Lock()
        # Semaphore to limit the concurrency of memory operations
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_MEM_ADDS)
        # Toggle whether to use custom prompt
        self.use_custom_prompt = True
        self.custom_prompt = CUSTOM_PROMPT
        self._initialized = True

    async def create(self) -> AsyncMemory:
        """Lazily create AsyncMemory once."""
        if self.memory is not None:
            return self.memory
        async with self._create_lock:
            if self.memory is None:
                self.memory = await AsyncMemory.from_config(self.config)
        return self.memory

    # Background event loop (class-level, process-wide)
    _bg_loop: asyncio.AbstractEventLoop | None = None
    _bg_thread: threading.Thread | None = None
    _bg_ready = threading.Event()
    _bg_lock = threading.Lock()

    @classmethod
    def ensure_bg_loop(cls) -> asyncio.AbstractEventLoop:
        """Ensure that a background asyncio event loop is running in a dedicated thread.

        This method is used to provide a shared process-wide background event loop for
        submitting and running coroutines from synchronous code or from threads that do
        not have a running event loop. It lazily creates the event loop and the thread
        the first time it is needed, and returns the running event loop thereafter.

        Returns:
            asyncio.AbstractEventLoop: The background event loop object.

        Raises:
            RuntimeError: If the background event loop fails to start.

        """
        with cls._bg_lock:
            # Reuse the existing loop if already running
            if cls._bg_loop and cls._bg_thread and cls._bg_thread.is_alive():
                return cls._bg_loop

            # Define the function that runs in the new background thread
            def _runner() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                cls._bg_loop = loop
                cls._bg_ready.set()
                loop.run_forever()  # Run the event loop forever

            # Prepare to start a new background thread
            cls._bg_ready.clear()
            t = threading.Thread(target=_runner, name="mem0-bg-loop", daemon=True)
            t.start()
            cls._bg_thread = t
            cls._bg_ready.wait()  # Wait until the loop is ready

            loop = cls._bg_loop
            if loop is None:
                msg = "Background event loop failed to start"
                raise RuntimeError(msg)
            return loop

    @classmethod
    def shutdown(cls, timeout: float = 3.0) -> None:
        """Best-effort graceful shutdown of the background event loop.

        - Attempts to wait up to `timeout` seconds for pending tasks to finish.
        - Stops the loop and joins the background thread (best-effort).
        - Safe to call multiple times.
        """
        loop = cls._bg_loop
        thread = cls._bg_thread
        if loop is None:
            return

        async def _drain_tasks(t: float) -> None:
            # Exclude the current task and wait for others (best-effort)
            with contextlib.suppress(Exception):
                pending = [tsk for tsk in asyncio.all_tasks() if tsk is not asyncio.current_task()]
                if pending:
                    await asyncio.wait(pending, timeout=t)

        fut = asyncio.run_coroutine_threadsafe(_drain_tasks(timeout), loop)
        with contextlib.suppress(Exception):
            fut.result(timeout=timeout + 1.0)
        with contextlib.suppress(Exception):
            loop.call_soon_threadsafe(loop.stop)
        if thread and thread.is_alive():
            with contextlib.suppress(Exception):
                thread.join(timeout=timeout)
        # Clear references
        cls._bg_loop = None
        cls._bg_thread = None

    async def search(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        await self.create()
        query = payload.get("query", "")
        filters = payload.get("filters")
        # Normalize limit to int when possible
        lim: int | None
        try:
            lim = int(payload.get("limit")) if payload.get("limit") is not None else None
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

        async with self._semaphore:
            results = await self.memory.search(query, **kwargs)

        normalized = _normalize_search_results(results)
        return normalized[:lim] if isinstance(lim, int) and lim > 0 else normalized

    async def add(self, payload: dict[str, Any]) -> dict[str, Any]:
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
        if messages is None or (
            isinstance(messages, str) and messages.strip() == ""
        ) or (
            isinstance(messages, (list, tuple)) and len(messages) == 0
        ):
            return ADD_SKIP_RESULT

        # Limit concurrent add() to avoid exhausting DB connection pool
        async with self._semaphore:
            # Await to ensure persistence before returning
            return await self.memory.add(messages, **kwargs)

    async def get_all(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        await self.create()
        filters = params.get("filters")
        if isinstance(filters, dict):
            try:
                async with self._semaphore:
                    results = await self.memory.get_all(filters=filters)
            except TypeError:
                results = []
        else:
            async with self._semaphore:
                results = await self.memory.get_all(
                    user_id=params.get("user_id"),
                    agent_id=params.get("agent_id"),
                    run_id=params.get("run_id"),
                )
        return results or []

    async def get(self, memory_id: str) -> dict[str, Any]:
        await self.create()
        async with self._semaphore:
            return await self.memory.get(memory_id)

    async def update(self, memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        await self.create()
        async with self._semaphore:
            return await self.memory.update(memory_id, payload.get("text"))

    async def delete(self, memory_id: str) -> dict[str, Any]:
        await self.create()
        async with self._semaphore:
            return await self.memory.delete(memory_id)

    async def delete_all(self, params: dict[str, Any]) -> dict[str, Any]:
        await self.create()
        async with self._semaphore:
            return await self.memory.delete_all(
                user_id=params.get("user_id"),
                agent_id=params.get("agent_id"),
                run_id=params.get("run_id"),
            )

    async def history(self, memory_id: str) -> list[dict[str, Any]]:
        await self.create()
        async with self._semaphore:
            return await self.memory.history(memory_id)
