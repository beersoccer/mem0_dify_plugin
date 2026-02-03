"""Lightweight distributed lock implementation using Mem0 as storage.

This module provides a simple distributed lock mechanism to prevent concurrent
execution of extraction tasks for the same user. The lock is stored as an
internal Mem0 memory.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .helpers import parse_iso_timestamp
from .logger import get_logger

if TYPE_CHECKING:
    from .mem0_client import Memory

logger = get_logger(__name__)

# Import AsyncMemory for async version
try:
    from mem0 import AsyncMemory
except ImportError:
    AsyncMemory = None  # type: ignore


@dataclass
class DistributedLock:
    """Distributed lock data structure."""

    lock_id: str  # Lock identifier
    holder_id: str  # Holder ID (usually run_id)
    acquired_at: str  # Acquisition time (ISO8601)
    ttl_seconds: int  # Timeout in seconds

    def is_expired(self) -> bool:
        """Check if the lock has expired."""
        acquired_dt = parse_iso_timestamp(self.acquired_at)
        if acquired_dt is None:
            return True
        now = datetime.now(UTC)
        elapsed = (now - acquired_dt).total_seconds()
        return elapsed >= self.ttl_seconds


class SyncLockManager:
    """Synchronous lock manager for Memory instances."""

    def __init__(self, mem: Memory) -> None:
        self.mem = mem

    def _lock_filters(self, user_id: str, app_id: str | None) -> dict[str, Any]:
        """Build filter conditions for lock."""
        return {
            "AND": [
                {"__internal": {"eq": True}},
                {"internal_type": {"eq": "distributed_lock"}},
                {"lock_resource": {"eq": "extraction"}},
                {"user_id": {"eq": user_id}},
                {"app_id": {"eq": app_id or "*"}},
            ],
        }

    def _load_lock(
        self, user_id: str, app_id: str | None
    ) -> tuple[str | None, DistributedLock | None]:
        """Load lock from Mem0.

        Returns:
            (memory_id, lock): Lock's memory_id and lock object, (None, None) if not found
        """
        filters = self._lock_filters(user_id, app_id)

        try:
            result = self.mem.get_all(user_id=user_id, limit=1, filters=filters)
            items = result.get("results", []) if isinstance(result, dict) else []

            if not items:
                return None, None

            item = items[0]
            memory_id = str(item.get("id") or "").strip() or None
            lock_data = item.get("memory") or "{}"

            try:
                data = json.loads(lock_data)
                lock = DistributedLock(**data)
                return memory_id, lock
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                logger.warning(f"Failed to parse lock data: {e}")
                return memory_id, None
        except Exception as e:
            logger.error(f"Failed to load lock: {e}")
            return None, None

    def _save_lock(
        self, user_id: str, app_id: str | None, lock: DistributedLock
    ) -> str | None:
        """Save lock to Mem0.

        Returns:
            memory_id: Memory ID of created lock, None on failure
        """
        metadata = {
            "__internal": True,
            "internal_type": "distributed_lock",
            "lock_resource": "extraction",
            "user_id": user_id,
            "app_id": app_id or "*",
        }

        lock_data = asdict(lock)
        text = json.dumps(lock_data, ensure_ascii=False)

        try:
            result = self.mem.add(text, user_id=user_id, metadata=metadata, infer=False)
            if isinstance(result, dict):
                results = result.get("results")
                if isinstance(results, list) and results:
                    return str(results[0].get("id") or "").strip() or None
                if isinstance(results, dict):
                    return str(results.get("id") or "").strip() or None
            return None
        except Exception as e:
            logger.error(f"Failed to save lock: {e}")
            return None

    def _delete_lock(self, memory_id: str) -> bool:
        """Delete lock."""
        try:
            if hasattr(self.mem, "delete"):
                self.mem.delete(memory_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete lock {memory_id}: {e}")
            return False

    def acquire_lock(
        self,
        user_id: str,
        app_id: str | None,
        holder_id: str,
        ttl_seconds: int = 3600,
    ) -> tuple[bool, DistributedLock | None]:
        """Attempt to acquire lock.

        Args:
            user_id: User ID
            app_id: App ID (optional)
            holder_id: Holder ID (usually run_id)
            ttl_seconds: Lock timeout in seconds

        Returns:
            (success, lock): Returns (True, new_lock) on success, (False, existing_lock) on failure
        """
        # 1. Try to read existing lock
        memory_id, existing_lock = self._load_lock(user_id, app_id)

        # 2. Check if existing lock has expired
        if existing_lock:
            if not existing_lock.is_expired():
                time_since_acquired = (
                    datetime.now(UTC) - parse_iso_timestamp(existing_lock.acquired_at)
                ).total_seconds()
                expires_in = existing_lock.ttl_seconds - time_since_acquired
                logger.warning(
                    f"Lock already held by {existing_lock.holder_id} "
                    f"(acquired at {existing_lock.acquired_at}, "
                    f"expires in {expires_in:.0f}s)"
                )
                return False, existing_lock

            # Lock expired, delete old lock
            logger.info(
                f"Existing lock by {existing_lock.holder_id} expired, acquiring new lock"
            )
            if memory_id:
                self._delete_lock(memory_id)

        # 3. Create new lock
        lock_key = f"lock:extraction:{user_id}:{app_id or '*'}"
        new_lock = DistributedLock(
            lock_id=lock_key,
            holder_id=holder_id,
            acquired_at=datetime.now(UTC).isoformat(),
            ttl_seconds=ttl_seconds,
        )

        # 4. Persist lock
        new_memory_id = self._save_lock(user_id, app_id, new_lock)

        if new_memory_id:
            logger.info(
                f"Lock acquired by {holder_id} for user {user_id} (ttl: {ttl_seconds}s)"
            )
            return True, new_lock

        logger.error(f"Failed to persist lock for user {user_id}")
        return False, None

    def release_lock(
        self,
        user_id: str,
        app_id: str | None,
        holder_id: str,
    ) -> bool:
        """Release lock (only holder can release).

        Args:
            user_id: User ID
            app_id: App ID (optional)
            holder_id: Holder ID (must match lock's holder_id)

        Returns:
            True on success, False on failure. Returns False if lock not found.
        """
        memory_id, existing_lock = self._load_lock(user_id, app_id)

        if not existing_lock:
            # Lock not found - cannot release a lock that doesn't exist
            logger.debug(
                f"No lock found for user {user_id} when releasing (holder: {holder_id}). "
                "Cannot release a lock that doesn't exist."
            )
            return False

        if existing_lock.holder_id != holder_id:
            logger.error(
                f"Lock held by {existing_lock.holder_id}, "
                f"cannot release by {holder_id}"
            )
            return False

        if memory_id:
            self._delete_lock(memory_id)

        logger.info(f"Lock released by {holder_id} for user {user_id}")
        return True

    def check_lock(
        self, user_id: str, app_id: str | None
    ) -> tuple[bool, DistributedLock | None]:
        """Check lock status (without acquiring).

        Returns:
            (is_locked, lock): Returns (True, lock) if lock exists and not expired,
                (False, None) otherwise
        """
        _, existing_lock = self._load_lock(user_id, app_id)

        if not existing_lock:
            return False, None

        if existing_lock.is_expired():
            return False, existing_lock

        return True, existing_lock


class AsyncLockManager:
    """Async lock manager based on AsyncMemory."""

    def __init__(self, mem: AsyncMemory) -> None:
        self.mem = mem

    def _lock_filters(self, user_id: str, app_id: str | None) -> dict[str, Any]:
        """Build filter conditions for lock."""
        return {
            "AND": [
                {"__internal": {"eq": True}},
                {"internal_type": {"eq": "distributed_lock"}},
                {"lock_resource": {"eq": "extraction"}},
                {"user_id": {"eq": user_id}},
                {"app_id": {"eq": app_id or "*"}},
            ],
        }

    async def _load_lock(
        self, user_id: str, app_id: str | None
    ) -> tuple[str | None, DistributedLock | None]:
        """Load lock from AsyncMemory.

        Returns:
            (memory_id, lock): Lock's memory_id and lock object, (None, None) if not found
        """
        filters = self._lock_filters(user_id, app_id)

        try:
            result = await self.mem.get_all(user_id=user_id, limit=1, filters=filters)
            items = result.get("results", []) if isinstance(result, dict) else []

            if not items:
                return None, None

            item = items[0]
            memory_id = str(item.get("id") or "").strip() or None
            lock_data = item.get("memory") or "{}"

            try:
                data = json.loads(lock_data)
                lock = DistributedLock(**data)
                return memory_id, lock
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                logger.warning(f"Failed to parse lock data: {e}")
                return memory_id, None
        except Exception as e:
            logger.error(f"Failed to load lock: {e}")
            return None, None

    async def _save_lock(
        self, user_id: str, app_id: str | None, lock: DistributedLock
    ) -> str | None:
        """Save lock to AsyncMemory.

        Returns:
            memory_id: Memory ID of created lock, None on failure
        """
        metadata = {
            "__internal": True,
            "internal_type": "distributed_lock",
            "lock_resource": "extraction",
            "user_id": user_id,
            "app_id": app_id or "*",
        }

        lock_data = asdict(lock)
        text = json.dumps(lock_data, ensure_ascii=False)

        try:
            result = await self.mem.add(text, user_id=user_id, metadata=metadata, infer=False)
            if isinstance(result, dict):
                results = result.get("results")
                if isinstance(results, list) and results:
                    return str(results[0].get("id") or "").strip() or None
                if isinstance(results, dict):
                    return str(results.get("id") or "").strip() or None
            return None
        except Exception as e:
            logger.error(f"Failed to save lock: {e}")
            return None

    async def _delete_lock(self, memory_id: str) -> bool:
        """Delete lock."""
        try:
            if hasattr(self.mem, "delete"):
                await self.mem.delete(memory_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete lock {memory_id}: {e}")
            return False

    async def acquire_lock(
        self,
        user_id: str,
        app_id: str | None,
        holder_id: str,
        ttl_seconds: int = 3600,
    ) -> tuple[bool, DistributedLock | None]:
        """Attempt to acquire lock.

        Args:
            user_id: User ID
            app_id: App ID (optional)
            holder_id: Holder ID (usually run_id)
            ttl_seconds: Lock timeout in seconds

        Returns:
            (success, lock): Returns (True, new_lock) on success, (False, existing_lock) on failure
        """
        # 1. Try to read existing lock
        memory_id, existing_lock = await self._load_lock(user_id, app_id)

        # 2. Check if existing lock has expired
        if existing_lock:
            if not existing_lock.is_expired():
                time_since_acquired = (
                    datetime.now(UTC) - parse_iso_timestamp(existing_lock.acquired_at)
                ).total_seconds()
                expires_in = existing_lock.ttl_seconds - time_since_acquired
                logger.warning(
                    f"Lock already held by {existing_lock.holder_id} "
                    f"(acquired at {existing_lock.acquired_at}, "
                    f"expires in {expires_in:.0f}s)"
                )
                return False, existing_lock

            # Lock expired, delete old lock
            logger.info(
                f"Existing lock by {existing_lock.holder_id} expired, acquiring new lock"
            )
            if memory_id:
                await self._delete_lock(memory_id)

        # 3. Create new lock
        lock_key = f"lock:extraction:{user_id}:{app_id or '*'}"
        new_lock = DistributedLock(
            lock_id=lock_key,
            holder_id=holder_id,
            acquired_at=datetime.now(UTC).isoformat(),
            ttl_seconds=ttl_seconds,
        )

        # 4. Persist lock
        new_memory_id = await self._save_lock(user_id, app_id, new_lock)

        if new_memory_id:
            logger.info(
                f"Lock acquired by {holder_id} for user {user_id} (ttl: {ttl_seconds}s)"
            )
            return True, new_lock

        logger.error(f"Failed to persist lock for user {user_id}")
        return False, None

    async def release_lock(
        self,
        user_id: str,
        app_id: str | None,
        holder_id: str,
    ) -> bool:
        """Release lock (only holder can release).

        Args:
            user_id: User ID
            app_id: App ID (optional)
            holder_id: Holder ID (must match lock's holder_id)

        Returns:
            True on success, False on failure. Returns False if lock not found.
        """
        memory_id, existing_lock = await self._load_lock(user_id, app_id)

        if not existing_lock:
            # Lock not found - cannot release a lock that doesn't exist
            logger.debug(
                f"No lock found for user {user_id} when releasing (holder: {holder_id}). "
                "Cannot release a lock that doesn't exist."
            )
            return False

        if existing_lock.holder_id != holder_id:
            logger.error(
                f"Lock held by {existing_lock.holder_id}, "
                f"cannot release by {holder_id}"
            )
            return False

        if memory_id:
            await self._delete_lock(memory_id)

        logger.info(f"Lock released by {holder_id} for user {user_id}")
        return True

    async def check_lock(
        self, user_id: str, app_id: str | None
    ) -> tuple[bool, DistributedLock | None]:
        """Check lock status (without acquiring).

        Returns:
            (is_locked, lock): Returns (True, lock) if lock exists and not expired,
                (False, None) otherwise
        """
        _, existing_lock = await self._load_lock(user_id, app_id)

        if not existing_lock:
            return False, None

        if existing_lock.is_expired():
            return False, existing_lock

        return True, existing_lock

