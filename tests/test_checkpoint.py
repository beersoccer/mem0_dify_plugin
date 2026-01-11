from __future__ import annotations

from typing import Any

import pytest

from utils.checkpoint import CHECKPOINT_KEY, checkpoint_filters, checkpoint_metadata
from utils.consolidation import UserCheckpoint


class FakeMemory:
    def __init__(self) -> None:
        self.updated: list[tuple[str, str]] = []
        self.added: list[dict[str, Any]] = []
        self.get_all_calls: list[dict[str, Any]] = []
        self._store: list[dict[str, Any]] = []

    def get_all(self, **kwargs: Any) -> dict[str, Any]:
        self.get_all_calls.append(kwargs)
        # simplistic filter: return all stored
        return {"results": list(self._store)}

    def update(self, memory_id: str, text: str) -> dict[str, Any]:
        self.updated.append((memory_id, text))
        return {"message": "updated"}

    def add(self, text: str, **kwargs: Any) -> dict[str, Any]:
        md = kwargs.get("metadata") or {}
        new_id = f"cp_{len(self._store)+1}"
        self._store.append({"id": new_id, "memory": text, "metadata": md})
        self.added.append({"id": new_id, "text": text, "metadata": md})
        return {"results": [{"id": new_id, "event": "ADD"}]}


def test_checkpoint_metadata_shape() -> None:
    md = checkpoint_metadata(user_id="u1", app_id=None)
    assert md["__internal"] is True
    assert md["internal_type"] == "checkpoint"
    assert md["checkpoint_key"] == CHECKPOINT_KEY
    assert md["user_id"] == "u1"
    assert md["app_id"] == "*"


def test_checkpoint_filters_shape() -> None:
    f = checkpoint_filters(user_id="u1", app_id="a1")
    assert isinstance(f, dict)
    assert "AND" in f


def test_save_checkpoint_add_and_update(monkeypatch: pytest.MonkeyPatch) -> None:
    from utils.checkpoint import load_checkpoint, save_checkpoint

    mem = FakeMemory()
    # no existing
    cp_id, cp = load_checkpoint(mem, user_id="u1", app_id=None)
    assert cp_id is None
    assert cp is None

    # save new
    ok, new_id = save_checkpoint(
        mem,
        checkpoint_id=None,
        user_id="u1",
        app_id=None,
        checkpoint=UserCheckpoint(last_run_at="2025-12-01T00:00:00Z"),
    )
    assert ok is True
    assert new_id is not None
    assert mem.added
    assert mem.added[0]["metadata"]["__internal"] is True

    # update existing
    ok2, same_id = save_checkpoint(
        mem,
        checkpoint_id=new_id,
        user_id="u1",
        app_id=None,
        checkpoint=UserCheckpoint(last_run_at="2025-12-02T00:00:00Z"),
    )
    assert ok2 is True
    assert same_id == new_id
    assert mem.updated


