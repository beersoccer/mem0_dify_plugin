from __future__ import annotations

from typing import Any

import pytest

from utils.checkpoint import CHECKPOINT_KEY, checkpoint_filters, checkpoint_metadata
from utils.extraction import UserCheckpoint


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
        self.added.append({"id": new_id, "text": text, "metadata": md})
        return {"results": [{"id": new_id, "event": "ADD"}]}

    def delete(self, memory_id: str) -> dict[str, Any]:
        self.deleted.append(memory_id)
        self._store = [x for x in self._store if x.get("id") != memory_id]
        return {"message": "deleted"}


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

    # update existing (uses delete+add, not update)
    ok2, same_id = save_checkpoint(
        mem,
        checkpoint_id=new_id,
        user_id="u1",
        app_id=None,
        checkpoint=UserCheckpoint(last_run_at="2025-12-02T00:00:00Z"),
    )
    assert ok2 is True
    assert same_id == new_id
    # save_checkpoint uses delete+add instead of update to avoid embedding
    assert new_id in mem.deleted  # Old checkpoint deleted
    assert len(mem.added) == 2  # New checkpoint added
