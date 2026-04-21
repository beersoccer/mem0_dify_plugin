from __future__ import annotations

from typing import Any

import pytest

from utils.checkpoint import (
    CHECKPOINT_VERSION,
    AsyncCheckpointManager,
    SyncCheckpointManager,
    checkpoint_filters,
    checkpoint_metadata,
)
from utils.extraction import ConversationCheckpoint, UserCheckpoint


class FakeMemory:
    def __init__(self) -> None:
        self.updated: list[tuple[str, str]] = []
        self.added: list[dict[str, Any]] = []
        self.get_all_calls: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self._store: list[dict[str, Any]] = []

    def _match(self, md: dict[str, Any], filt: Any) -> bool:
        if not filt:
            return True
        if not isinstance(filt, dict):
            return True
        if "AND" in filt:
            parts = filt.get("AND")
            if not isinstance(parts, list):
                return True
            return all(self._match(md, x) for x in parts)
        if "OR" in filt:
            parts = filt.get("OR")
            if not isinstance(parts, list):
                return True
            return any(self._match(md, x) for x in parts)
        if "NOT" in filt:
            parts = filt.get("NOT")
            if not isinstance(parts, list):
                return True
            return not any(self._match(md, x) for x in parts)
        # leaf: {"key": {"eq": value}} or {"key": value}
        for k, v in filt.items():
            if isinstance(v, dict) and "eq" in v:
                if md.get(k) != v.get("eq"):
                    return False
            else:
                if md.get(k) != v:
                    return False
        return True

    def get_all(self, **kwargs: Any) -> dict[str, Any]:
        self.get_all_calls.append(kwargs)
        filt = kwargs.get("filters")
        out: list[dict[str, Any]] = []
        for item in self._store:
            md = item.get("metadata") or {}
            if not isinstance(md, dict):
                md = {}
            if self._match(md, filt):
                out.append(item)
        return {"results": out}

    def update(self, memory_id: str, text: str) -> dict[str, Any]:
        self.updated.append((memory_id, text))
        return {"message": "updated"}

    def add(self, text: str, **kwargs: Any) -> dict[str, Any]:
        md = kwargs.get("metadata") or {}
        new_id = f"cp_{len(self._store)+1}"
        self._store.append({"id": new_id, "memory": text, "metadata": md})
        self.added.append(
            {
                "id": new_id,
                "text": text,
                "metadata": md,
                "user_id": kwargs.get("user_id"),
                "agent_id": kwargs.get("agent_id"),
            }
        )
        return {"results": [{"id": new_id, "event": "ADD"}]}

    def delete(self, memory_id: str) -> dict[str, Any]:
        self.deleted.append(memory_id)
        self._store = [x for x in self._store if x.get("id") != memory_id]
        return {"message": "deleted"}


def test_checkpoint_metadata_shape() -> None:
    md = checkpoint_metadata()
    assert md["__internal"] == "true"
    assert md["internal_type"] == "checkpoint"
    assert md["version"] == CHECKPOINT_VERSION


def test_checkpoint_filters_shape() -> None:
    f = checkpoint_filters()
    assert isinstance(f, dict)
    assert f["__internal"] == "true"
    assert f["internal_type"] == "checkpoint"
    assert f["version"] == CHECKPOINT_VERSION


def test_save_checkpoint_add_and_update(monkeypatch: pytest.MonkeyPatch) -> None:
    mem = FakeMemory()
    mgr = SyncCheckpointManager(mem)

    # no existing
    cp_id, cp = mgr.load(user_id="u1", app_id=None)
    assert cp_id is None
    assert cp is None
    assert mem.get_all_calls
    assert mem.get_all_calls[0]["user_id"] == "u1"
    assert "agent_id" not in mem.get_all_calls[0]

    # save new
    ok, new_id = mgr.save(
        checkpoint_id=None,
        user_id="u1",
        app_id=None,
        checkpoint=UserCheckpoint(),
    )
    assert ok is True
    assert new_id is not None
    assert mem.added
    assert mem.added[0]["metadata"]["__internal"] == "true"
    assert mem.added[0]["user_id"] == "u1"
    assert mem.added[0]["agent_id"] is None

    # update existing (uses add-first-then-delete)
    ok2, new_id2 = mgr.save(
        checkpoint_id=new_id,
        user_id="u1",
        app_id=None,
        checkpoint=UserCheckpoint(),
    )
    assert ok2 is True
    assert new_id2 is not None
    # save adds new first, then deletes old
    assert new_id in mem.deleted  # Old checkpoint deleted
    assert len(mem.added) == 2  # New checkpoint added


def test_save_add_before_delete_order() -> None:
    """Verify that save() adds the new checkpoint BEFORE deleting the old one."""
    mem = FakeMemory()
    mgr = SyncCheckpointManager(mem)

    # Create initial checkpoint
    ok, initial_id = mgr.save(
        checkpoint_id=None,
        user_id="u1",
        app_id=None,
        checkpoint=UserCheckpoint(),
    )
    assert ok and initial_id

    # Track operation order
    operations: list[str] = []
    original_add = mem.add
    original_delete = mem.delete

    def tracking_add(text: str, **kwargs: Any) -> dict[str, Any]:
        operations.append("add")
        return original_add(text, **kwargs)

    def tracking_delete(memory_id: str) -> dict[str, Any]:
        operations.append("delete")
        return original_delete(memory_id)

    mem.add = tracking_add  # type: ignore[assignment]
    mem.delete = tracking_delete  # type: ignore[assignment]

    # Update checkpoint
    ok2, new_id = mgr.save(
        checkpoint_id=initial_id,
        user_id="u1",
        app_id=None,
        checkpoint=UserCheckpoint(),
    )
    assert ok2 is True
    # add must come before delete
    assert operations == ["add", "delete"]


def test_save_keeps_old_checkpoint_on_add_failure() -> None:
    """If add() fails, old checkpoint should NOT be deleted."""
    mem = FakeMemory()
    mgr = SyncCheckpointManager(mem)

    # Create initial checkpoint
    ok, initial_id = mgr.save(
        checkpoint_id=None,
        user_id="u1",
        app_id=None,
        checkpoint=UserCheckpoint(),
    )
    assert ok and initial_id

    # Make add return no ID (simulating failure)
    mem.add = lambda text, **kwargs: {"results": []}  # type: ignore[assignment]

    ok2, new_id = mgr.save(
        checkpoint_id=initial_id,
        user_id="u1",
        app_id=None,
        checkpoint=UserCheckpoint(),
    )
    # add returned no ID, so old checkpoint must NOT be deleted
    assert initial_id not in mem.deleted


class AsyncFakeMemory:
    """Async-compatible fake Mem0 memory for testing."""

    def __init__(self) -> None:
        self._store: list[dict[str, Any]] = []
        self.added: list[dict[str, Any]] = []
        self.deleted: list[str] = []

    def _match(self, md: dict[str, Any], filt: Any) -> bool:
        if not filt or not isinstance(filt, dict):
            return True
        # Leaf filter: {"key": value} or {"key": {"eq": value}}
        for k, v in filt.items():
            if isinstance(v, dict) and "eq" in v:
                if md.get(k) != v.get("eq"):
                    return False
            else:
                if md.get(k) != v:
                    return False
        return True

    async def get_all(self, **kwargs: Any) -> dict[str, Any]:
        filt = kwargs.get("filters")
        out: list[dict[str, Any]] = []
        for item in self._store:
            md = item.get("metadata") or {}
            if self._match(md, filt):
                out.append(item)
        return {"results": out}

    async def add(self, text: str, **kwargs: Any) -> dict[str, Any]:
        md = kwargs.get("metadata") or {}
        new_id = f"cp_{len(self._store)+1}"
        self._store.append({"id": new_id, "memory": text, "metadata": md})
        self.added.append({"id": new_id, "text": text})
        return {"results": [{"id": new_id, "event": "ADD"}]}

    async def delete(self, memory_id: str) -> dict[str, Any]:
        self.deleted.append(memory_id)
        self._store = [x for x in self._store if x.get("id") != memory_id]
        return {"message": "deleted"}


@pytest.mark.asyncio
@pytest.mark.forked
async def test_async_load_restores_resume_fields() -> None:
    """AsyncCheckpointManager.load() must restore resume_* fields."""
    mem = AsyncFakeMemory()
    mgr = AsyncCheckpointManager(mem)

    # Build a checkpoint with resume fields set
    cp = UserCheckpoint(
        conversations={
            "conv1": ConversationCheckpoint(
                last_processed_message_id="msg-100",
                processed_range_start="2026-01-01T00:00:00Z",
                processed_range_end="2026-01-02T00:00:00Z",
            ),
        },
        resume_conversation_cursor="conv1",
        resume_run_at="2026-04-01T12:00:00Z",
        resume_start_time="2026-03-01T00:00:00Z",
    )

    # Save it
    ok, cp_id = await mgr.save(
        checkpoint_id=None, user_id="u1", app_id=None, checkpoint=cp
    )
    assert ok and cp_id

    # Load it back
    loaded_id, loaded_cp = await mgr.load(user_id="u1", app_id=None)
    assert loaded_id == cp_id
    assert loaded_cp is not None
    assert loaded_cp.resume_conversation_cursor == "conv1"
    assert loaded_cp.resume_run_at == "2026-04-01T12:00:00Z"
    assert loaded_cp.resume_start_time == "2026-03-01T00:00:00Z"
    assert "conv1" in loaded_cp.conversations
    assert loaded_cp.conversations["conv1"].last_processed_message_id == "msg-100"


@pytest.mark.asyncio
@pytest.mark.forked
async def test_async_save_add_before_delete() -> None:
    """Async save() must add new checkpoint before deleting old."""
    mem = AsyncFakeMemory()
    mgr = AsyncCheckpointManager(mem)

    # Create initial
    ok, initial_id = await mgr.save(
        checkpoint_id=None, user_id="u1", app_id=None, checkpoint=UserCheckpoint()
    )
    assert ok and initial_id

    # Track operations
    operations: list[str] = []
    original_add = mem.add
    original_delete = mem.delete

    async def tracking_add(text: str, **kwargs: Any) -> dict[str, Any]:
        operations.append("add")
        return await original_add(text, **kwargs)

    async def tracking_delete(memory_id: str) -> dict[str, Any]:
        operations.append("delete")
        return await original_delete(memory_id)

    mem.add = tracking_add  # type: ignore[assignment]
    mem.delete = tracking_delete  # type: ignore[assignment]

    # Update
    ok2, new_id = await mgr.save(
        checkpoint_id=initial_id, user_id="u1", app_id=None, checkpoint=UserCheckpoint()
    )
    assert ok2 is True
    assert operations == ["add", "delete"]

