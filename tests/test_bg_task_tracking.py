"""Test background task tracking for all memory operations (read + write)."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock

import pytest

from utils.mem0_client import AsyncMem0Client


class FakeAsyncMemory:
    """Fake AsyncMemory for testing background task tracking."""

    def __init__(self) -> None:
        self.search_event = asyncio.Event()
        self.get_event = asyncio.Event()
        self.get_all_event = asyncio.Event()
        self.history_event = asyncio.Event()
        self.add_event = asyncio.Event()
        self.update_event = asyncio.Event()
        self.delete_event = asyncio.Event()
        self.delete_all_event = asyncio.Event()
        self.hold_duration = 0.1  # Default hold time for operations

    async def search(self, query: str, **kwargs: object) -> object:  # noqa: ARG002
        self.search_event.set()
        await asyncio.sleep(self.hold_duration)
        return {"results": []}

    async def get(self, memory_id: str) -> dict[str, object]:  # noqa: ARG002
        self.get_event.set()
        await asyncio.sleep(self.hold_duration)
        return {"id": "test", "memory": "test"}

    async def get_all(self, **kwargs: object) -> dict[str, object]:  # noqa: ARG002
        self.get_all_event.set()
        await asyncio.sleep(self.hold_duration)
        return {"results": []}

    async def history(self, memory_id: str) -> list[dict[str, object]]:  # noqa: ARG002
        self.history_event.set()
        await asyncio.sleep(self.hold_duration)
        return []

    async def add(self, messages: object, **kwargs: object) -> dict[str, object]:  # noqa: ARG002
        self.add_event.set()
        await asyncio.sleep(self.hold_duration)
        return {"results": []}

    async def update(self, memory_id: str, text: str) -> dict[str, object]:  # noqa: ARG002
        self.update_event.set()
        await asyncio.sleep(self.hold_duration)
        return {"message": "updated"}

    async def delete(self, memory_id: str) -> dict[str, object]:  # noqa: ARG002
        self.delete_event.set()
        await asyncio.sleep(self.hold_duration)
        return {"message": "deleted"}

    async def delete_all(self, **kwargs: object) -> dict[str, object]:  # noqa: ARG002
        self.delete_all_event.set()
        await asyncio.sleep(self.hold_duration)
        return {"message": "all deleted"}


def test_read_operations_tracked_in_bg_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that read operations (search/get/get_all/history) are tracked in _bg_tasks."""
    import utils.mem0_client as mem0_client

    monkeypatch.setattr(mem0_client, "build_local_mem0_config", lambda _c: {})

    client = AsyncMem0Client({})
    fake_memory = FakeAsyncMemory()
    fake_memory.hold_duration = 0.2  # Hold operations longer to ensure they're tracked

    # Mock create() to return our fake memory
    async def _fake_create() -> FakeAsyncMemory:
        return fake_memory

    monkeypatch.setattr(client, "create", _fake_create)
    client.memory = fake_memory

    # Ensure background loop is running
    loop = client.ensure_bg_loop()

    # Test search operation tracking
    assert client.get_pending_tasks_count() == 0
    future_search = asyncio.run_coroutine_threadsafe(
        client.search({"query": "test", "user_id": "u1"}), loop
    )
    client.track_bg_task(future_search, "test_search")
    # Wait for operation to start
    fake_memory.search_event.wait(timeout=1.0)
    assert client.get_pending_tasks_count() == 1
    # Wait for operation to complete
    future_search.result(timeout=1.0)
    assert client.get_pending_tasks_count() == 0

    # Test get operation tracking
    future_get = asyncio.run_coroutine_threadsafe(client.get("mem_id"), loop)
    client.track_bg_task(future_get, "test_get")
    fake_memory.get_event.wait(timeout=1.0)
    assert client.get_pending_tasks_count() == 1
    future_get.result(timeout=1.0)
    assert client.get_pending_tasks_count() == 0

    # Test get_all operation tracking
    future_get_all = asyncio.run_coroutine_threadsafe(
        client.get_all({"user_id": "u1"}), loop
    )
    client.track_bg_task(future_get_all, "test_get_all")
    fake_memory.get_all_event.wait(timeout=1.0)
    assert client.get_pending_tasks_count() == 1
    future_get_all.result(timeout=1.0)
    assert client.get_pending_tasks_count() == 0

    # Test history operation tracking
    future_history = asyncio.run_coroutine_threadsafe(client.history("mem_id"), loop)
    client.track_bg_task(future_history, "test_history")
    fake_memory.history_event.wait(timeout=1.0)
    assert client.get_pending_tasks_count() == 1
    future_history.result(timeout=1.0)
    assert client.get_pending_tasks_count() == 0


def test_write_operations_tracked_in_bg_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that write operations (add/update/delete/delete_all) are tracked in _bg_tasks."""
    import utils.mem0_client as mem0_client

    monkeypatch.setattr(mem0_client, "build_local_mem0_config", lambda _c: {})

    client = AsyncMem0Client({})
    fake_memory = FakeAsyncMemory()
    fake_memory.hold_duration = 0.2

    async def _fake_create() -> FakeAsyncMemory:
        return fake_memory

    monkeypatch.setattr(client, "create", _fake_create)
    client.memory = fake_memory

    loop = client.ensure_bg_loop()

    # Test add operation tracking
    assert client.get_pending_tasks_count() == 0
    future_add = asyncio.run_coroutine_threadsafe(
        client.add({"messages": [{"role": "user", "content": "test"}], "user_id": "u1"}),
        loop,
    )
    client.track_bg_task(future_add, "test_add")
    fake_memory.add_event.wait(timeout=1.0)
    assert client.get_pending_tasks_count() == 1
    future_add.result(timeout=1.0)
    assert client.get_pending_tasks_count() == 0

    # Test update operation tracking
    future_update = asyncio.run_coroutine_threadsafe(
        client.update("mem_id", {"text": "new text"}), loop
    )
    client.track_bg_task(future_update, "test_update")
    fake_memory.update_event.wait(timeout=1.0)
    assert client.get_pending_tasks_count() == 1
    future_update.result(timeout=1.0)
    assert client.get_pending_tasks_count() == 0

    # Test delete operation tracking
    future_delete = asyncio.run_coroutine_threadsafe(client.delete("mem_id"), loop)
    client.track_bg_task(future_delete, "test_delete")
    fake_memory.delete_event.wait(timeout=1.0)
    assert client.get_pending_tasks_count() == 1
    future_delete.result(timeout=1.0)
    assert client.get_pending_tasks_count() == 0

    # Test delete_all operation tracking
    future_delete_all = asyncio.run_coroutine_threadsafe(
        client.delete_all({"user_id": "u1"}), loop
    )
    client.track_bg_task(future_delete_all, "test_delete_all")
    fake_memory.delete_all_event.wait(timeout=1.0)
    assert client.get_pending_tasks_count() == 1
    future_delete_all.result(timeout=1.0)
    assert client.get_pending_tasks_count() == 0


def test_concurrent_operations_tracked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that multiple concurrent operations are all tracked in _bg_tasks."""
    import utils.mem0_client as mem0_client

    monkeypatch.setattr(mem0_client, "build_local_mem0_config", lambda _c: {})

    client = AsyncMem0Client({})
    fake_memory = FakeAsyncMemory()
    fake_memory.hold_duration = 0.3  # Hold longer to overlap operations

    async def _fake_create() -> FakeAsyncMemory:
        return fake_memory

    monkeypatch.setattr(client, "create", _fake_create)
    client.memory = fake_memory

    loop = client.ensure_bg_loop()

    # Submit multiple operations concurrently
    assert client.get_pending_tasks_count() == 0

    futures = []
    # Submit 2 search, 2 add operations
    for i in range(2):
        f_search = asyncio.run_coroutine_threadsafe(
            client.search({"query": f"q{i}", "user_id": "u1"}), loop
        )
        client.track_bg_task(f_search, f"search_{i}")
        futures.append(f_search)

        f_add = asyncio.run_coroutine_threadsafe(
            client.add(
                {"messages": [{"role": "user", "content": f"msg{i}"}], "user_id": "u1"}
            ),
            loop,
        )
        client.track_bg_task(f_add, f"add_{i}")
        futures.append(f_add)

    # Wait for all operations to start
    fake_memory.search_event.wait(timeout=1.0)
    fake_memory.add_event.wait(timeout=1.0)

    # Should have multiple tasks tracked
    # Note: Due to timing, some might complete quickly, but we should see at least 2
    pending_count = client.get_pending_tasks_count()
    assert pending_count >= 2, f"Expected at least 2 pending tasks, got {pending_count}"

    # Wait for all to complete
    for f in futures:
        f.result(timeout=2.0)

    # All should be cleaned up
    assert client.get_pending_tasks_count() == 0
