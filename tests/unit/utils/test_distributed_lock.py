"""Tests for distributed lock."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from utils.distributed_lock import DistributedLock, LockManager


class FakeMemory:
    """Fake Mem0 client for testing."""

    def __init__(self) -> None:
        self._store: list[dict[str, Any]] = []
        self.get_all_calls: list[dict[str, Any]] = []
        self.add_calls: list[dict[str, Any]] = []
        self.delete_calls: list[str] = []

    def _match_filter(self, metadata: dict[str, Any], filters: Any) -> bool:
        """Simple filter matching for testing."""
        if not isinstance(filters, dict):
            return True

        if "AND" in filters:
            parts = filters.get("AND", [])
            return all(self._match_filter(metadata, f) for f in parts)

        # Leaf filter: {"key": {"eq": value}}
        for key, condition in filters.items():
            if isinstance(condition, dict) and "eq" in condition:
                if metadata.get(key) != condition["eq"]:
                    return False
            else:
                if metadata.get(key) != condition:
                    return False
        return True

    def get_all(self, **kwargs: Any) -> dict[str, Any]:
        """Mock get_all."""
        self.get_all_calls.append(kwargs)
        filters = kwargs.get("filters")
        results = []

        for item in self._store:
            if self._match_filter(item.get("metadata", {}), filters):
                results.append(item)

        return {"results": results}

    def add(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Mock add."""
        memory_id = f"mem_{len(self._store) + 1}"
        item = {
            "id": memory_id,
            "memory": text,
            "metadata": kwargs.get("metadata", {}),
        }
        self._store.append(item)
        self.add_calls.append(kwargs)
        return {"results": [{"id": memory_id, "event": "ADD"}]}

    def delete(self, memory_id: str) -> None:
        """Mock delete."""
        self.delete_calls.append(memory_id)
        self._store = [item for item in self._store if item.get("id") != memory_id]


class TestDistributedLock:
    """Test DistributedLock dataclass."""

    def test_lock_not_expired(self) -> None:
        """Test lock is not expired within TTL."""
        now = datetime.now(UTC)
        lock = DistributedLock(
            lock_id="test_lock",
            holder_id="holder_1",
            acquired_at=now.isoformat(),
            ttl_seconds=60,
        )
        assert not lock.is_expired()

    def test_lock_expired(self) -> None:
        """Test lock is expired after TTL."""
        past = datetime.now(UTC) - timedelta(seconds=120)
        lock = DistributedLock(
            lock_id="test_lock",
            holder_id="holder_1",
            acquired_at=past.isoformat(),
            ttl_seconds=60,
        )
        assert lock.is_expired()

    def test_lock_expired_with_invalid_time(self) -> None:
        """Test lock is considered expired with invalid timestamp."""
        lock = DistributedLock(
            lock_id="test_lock",
            holder_id="holder_1",
            acquired_at="invalid_timestamp",
            ttl_seconds=60,
        )
        assert lock.is_expired()


class TestLockManager:
    """Test LockManager."""

    def test_acquire_lock_first_time(self) -> None:
        """Test acquiring lock for the first time."""
        mem = FakeMemory()
        manager = LockManager(mem)

        success, lock = manager.acquire_lock(
            user_id="user1", app_id=None, holder_id="run1", ttl_seconds=60
        )

        assert success
        assert lock is not None
        assert lock.holder_id == "run1"
        assert len(mem.add_calls) == 1

    def test_acquire_lock_already_held(self) -> None:
        """Test acquiring lock when already held by another."""
        mem = FakeMemory()
        manager = LockManager(mem)

        # First acquisition
        success1, lock1 = manager.acquire_lock(
            user_id="user1", app_id=None, holder_id="run1", ttl_seconds=60
        )
        assert success1

        # Second acquisition (should fail)
        success2, lock2 = manager.acquire_lock(
            user_id="user1", app_id=None, holder_id="run2", ttl_seconds=60
        )
        assert not success2
        assert lock2 is not None
        assert lock2.holder_id == "run1"

    def test_acquire_lock_after_expiry(self) -> None:
        """Test acquiring lock after previous lock expired."""
        mem = FakeMemory()
        manager = LockManager(mem)

        # First acquisition with expired time
        past = datetime.now(UTC) - timedelta(seconds=120)
        success1, lock1 = manager.acquire_lock(
            user_id="user1", app_id=None, holder_id="run1", ttl_seconds=60
        )
        assert success1

        # Manually expire the lock by modifying the JSON
        lock_data = json.loads(mem._store[0]["memory"])
        lock_data["acquired_at"] = past.isoformat()
        mem._store[0]["memory"] = json.dumps(lock_data, ensure_ascii=False)

        # Second acquisition (should succeed after expiry)
        success2, lock2 = manager.acquire_lock(
            user_id="user1", app_id=None, holder_id="run2", ttl_seconds=60
        )
        assert success2
        assert lock2 is not None
        assert lock2.holder_id == "run2"
        assert len(mem.delete_calls) == 1  # Old lock deleted

    def test_release_lock_success(self) -> None:
        """Test releasing lock by holder."""
        mem = FakeMemory()
        manager = LockManager(mem)

        # Acquire lock
        success, lock = manager.acquire_lock(
            user_id="user1", app_id=None, holder_id="run1", ttl_seconds=60
        )
        assert success

        # Release lock
        released = manager.release_lock(user_id="user1", app_id=None, holder_id="run1")
        assert released
        assert len(mem.delete_calls) == 1

    def test_release_lock_by_non_holder(self) -> None:
        """Test releasing lock by non-holder fails."""
        mem = FakeMemory()
        manager = LockManager(mem)

        # Acquire lock
        success, lock = manager.acquire_lock(
            user_id="user1", app_id=None, holder_id="run1", ttl_seconds=60
        )
        assert success

        # Try to release by different holder
        released = manager.release_lock(user_id="user1", app_id=None, holder_id="run2")
        assert not released
        assert len(mem.delete_calls) == 0

    def test_release_lock_nonexistent(self) -> None:
        """Test releasing non-existent lock."""
        mem = FakeMemory()
        manager = LockManager(mem)

        released = manager.release_lock(user_id="user1", app_id=None, holder_id="run1")
        assert not released

    def test_check_lock_held(self) -> None:
        """Test checking lock status when held."""
        mem = FakeMemory()
        manager = LockManager(mem)

        # Acquire lock
        manager.acquire_lock(
            user_id="user1", app_id=None, holder_id="run1", ttl_seconds=60
        )

        # Check lock
        is_locked, lock = manager.check_lock(user_id="user1", app_id=None)
        assert is_locked
        assert lock is not None
        assert lock.holder_id == "run1"

    def test_check_lock_not_held(self) -> None:
        """Test checking lock status when not held."""
        mem = FakeMemory()
        manager = LockManager(mem)

        is_locked, lock = manager.check_lock(user_id="user1", app_id=None)
        assert not is_locked
        assert lock is None

    def test_check_lock_expired(self) -> None:
        """Test checking lock status when expired."""
        mem = FakeMemory()
        manager = LockManager(mem)

        # Acquire lock with expired time
        past = datetime.now(UTC) - timedelta(seconds=120)
        manager.acquire_lock(
            user_id="user1", app_id=None, holder_id="run1", ttl_seconds=60
        )

        # Manually expire the lock by modifying the JSON
        lock_data = json.loads(mem._store[0]["memory"])
        lock_data["acquired_at"] = past.isoformat()
        mem._store[0]["memory"] = json.dumps(lock_data, ensure_ascii=False)

        # Check lock
        is_locked, lock = manager.check_lock(user_id="user1", app_id=None)
        assert not is_locked
        assert lock is not None  # Lock exists but expired
        assert lock.is_expired()

