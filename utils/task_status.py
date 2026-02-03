"""Task status storage for async extraction tasks.

This module provides storage and retrieval of extraction task status in Mem0,
similar to checkpoint storage but for task tracking.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .logger import get_logger
from .mem0_client import Memory

if TYPE_CHECKING:
    from mem0 import AsyncMemory
else:
    AsyncMemory = None  # type: ignore

logger = get_logger(__name__)
TASK_STATUS_KEY = "extraction_task_v1"


@dataclass
class ExtractionTaskStatus:
    """Status of an extraction task."""

    task_id: str
    run_id: str
    status: str  # "running", "completed", "failed"
    started_at: str  # ISO8601 timestamp
    updated_at: str  # ISO8601 timestamp
    progress: float  # 0.0-1.0
    user_count: int
    processed_users: int
    skipped_users: int
    scanned_conversations: int
    scanned_messages: int
    written_memories: dict[str, int]  # {"semantic": 0, "episodic": 0, "procedural": 0}
    error: str | None = None
    final_report: dict[str, Any] | None = None  # Full report when completed


def task_status_metadata(*, task_id: str) -> dict[str, Any]:
    """Build metadata for task status storage."""
    return {
        "__internal": True,
        "internal_type": "extraction_task",
        "task_key": TASK_STATUS_KEY,
        "task_id": task_id,
    }


def task_status_filters(*, task_id: str) -> dict[str, Any]:
    """Build filters for task status retrieval."""
    md = task_status_metadata(task_id=task_id)
    return {
        "AND": [
            {"__internal": {"eq": True}},
            {"internal_type": {"eq": "extraction_task"}},
            {"task_key": {"eq": md["task_key"]}},
            {"task_id": {"eq": md["task_id"]}},
        ],
    }


class SyncTaskStatusManager:
    """Synchronous task status manager for Memory instances."""

    def __init__(self, mem: Memory) -> None:
        """Initialize task status manager.

        Args:
            mem: Synchronous Memory instance
        """
        self.mem = mem

    def save(
        self,
        *,
        task_status: ExtractionTaskStatus,
    ) -> tuple[bool, str | None]:
        """Save or update task status in Mem0.

        Note: We use delete+add instead of update to avoid mem0's embedding
        processing. Task status data should be stored as-is without any LLM
        inference or vectorization.

        Args:
            task_status: Task status object

        Returns:
            (success, memory_id): Returns (True, id) on success, (False, None) on failure
        """
        try:
            # Check if task status already exists
            filters = task_status_filters(task_id=task_status.task_id)
            result = self.mem.get_all(user_id="__system__", limit=1, filters=filters)
            items = result.get("results", []) if isinstance(result, dict) else []

            payload = asdict(task_status)
            text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            md = task_status_metadata(task_id=task_status.task_id)

            # If task status exists, delete it first to avoid embedding
            # mem0's update() method calls embedding_model.embed() which is unnecessary
            # for internal metadata that should be stored as-is
            if items and isinstance(items, list) and items:
                existing_id = str(items[0].get("id") or "").strip()
                if existing_id:
                    try:
                        self.mem.delete(existing_id)
                    except Exception:
                        # If delete fails, log and continue to add new one
                        logger.warning(
                            f"Failed to delete old task status {existing_id}, will add new one"
                        )

            # Create new internal memory; infer=False to avoid LLM calls and embedding
            res = self.mem.add(text, user_id="__system__", metadata=md, infer=False)
            new_id: str | None = None
            if isinstance(res, dict):
                results = res.get("results")
                if isinstance(results, list) and results:
                    new_id = str(results[0].get("id") or "").strip() or None
                elif isinstance(results, dict):
                    new_id = str(results.get("id") or "").strip() or None
            return True, new_id
        except Exception as e:
            logger.error(f"Failed to save task status: {e}")
            return False, None

    def load(
        self,
        *,
        task_id: str,
    ) -> tuple[str | None, ExtractionTaskStatus | None]:
        """Load task status from Mem0.

        Args:
            task_id: Task ID

        Returns:
            (memory_id, task_status): Returns (id, status) if found, (None, None) otherwise
        """
        try:
            filters = task_status_filters(task_id=task_id)
            result = self.mem.get_all(user_id="__system__", limit=1, filters=filters)
            items = result.get("results", []) if isinstance(result, dict) else []

            if not items or not isinstance(items, list) or not items:
                return None, None

            item = items[0]
            memory_id = str(item.get("id") or "").strip() or None
            raw = str(item.get("memory") or item.get("text") or "").strip()

            if not raw:
                return memory_id, None

            try:
                data = json.loads(raw)
                status = ExtractionTaskStatus(**data)
                return memory_id, status
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                logger.warning(f"Failed to parse task status: {e}")
                return memory_id, None
        except Exception as e:
            logger.error(f"Failed to load task status: {e}")
            return None, None

    def update_progress(
        self,
        *,
        task_id: str,
        processed_users: int,
        total_users: int,
        scanned_conversations: int = 0,
        scanned_messages: int = 0,
        written_memories: dict[str, int] | None = None,
    ) -> bool:
        """Update task progress.

        Args:
            task_id: Task ID
            processed_users: Number of users processed so far
            total_users: Total number of users
            scanned_conversations: Number of conversations scanned
            scanned_messages: Number of messages scanned
            written_memories: Memory counts by type

        Returns:
            True on success, False on failure
        """
        _, status = self.load(task_id=task_id)
        if not status:
            return False

        status.processed_users = processed_users
        status.progress = processed_users / total_users if total_users > 0 else 0.0
        status.scanned_conversations = scanned_conversations
        status.scanned_messages = scanned_messages
        if written_memories:
            status.written_memories = written_memories
        status.updated_at = datetime.now(UTC).isoformat()

        ok, _ = self.save(task_status=status)
        return ok

    def mark_completed(
        self,
        *,
        task_id: str,
        final_report: dict[str, Any],
    ) -> bool:
        """Mark task as completed with final report.

        Args:
            task_id: Task ID
            final_report: Final extraction report

        Returns:
            True on success, False on failure
        """
        _, status = self.load(task_id=task_id)
        if not status:
            return False

        status.status = "completed"
        status.progress = 1.0
        status.final_report = final_report
        status.updated_at = datetime.now(UTC).isoformat()

        # Update counts from final report
        if isinstance(final_report, dict):
            summary = final_report.get("summary", {})
            if isinstance(summary, dict):
                status.processed_users = summary.get("processed_users", 0)
                status.skipped_users = summary.get("skipped_users", 0)
                status.scanned_conversations = summary.get("scanned_conversations", 0)
                status.scanned_messages = summary.get("scanned_messages", 0)
                written = summary.get("written_memories")
                if isinstance(written, dict):
                    status.written_memories = written

        ok, _ = self.save(task_status=status)
        return ok

    def mark_failed(
        self,
        *,
        task_id: str,
        error: str,
    ) -> bool:
        """Mark task as failed.

        Args:
            task_id: Task ID
            error: Error message

        Returns:
            True on success, False on failure
        """
        _, status = self.load(task_id=task_id)
        if not status:
            return False

        status.status = "failed"
        status.error = error[:500] if error else None  # Limit error message length
        status.updated_at = datetime.now(UTC).isoformat()

        ok, _ = self.save(task_status=status)
        return ok


class AsyncTaskStatusManager:
    """Asynchronous task status manager for AsyncMemory instances."""

    def __init__(self, mem: AsyncMemory) -> None:
        """Initialize async task status manager.

        Args:
            mem: Asynchronous AsyncMemory instance
        """
        self.mem = mem

    async def save(
        self,
        *,
        task_status: ExtractionTaskStatus,
    ) -> tuple[bool, str | None]:
        """Save or update task status in Mem0.

        Note: We use delete+add instead of update to avoid mem0's embedding
        processing. Task status data should be stored as-is without any LLM
        inference or vectorization.

        Args:
            task_status: Task status object

        Returns:
            (success, memory_id): Returns (True, id) on success, (False, None) on failure
        """
        try:
            # Check if task status already exists
            filters = task_status_filters(task_id=task_status.task_id)
            result = await self.mem.get_all(user_id="__system__", limit=1, filters=filters)
            items = result.get("results", []) if isinstance(result, dict) else []

            payload = asdict(task_status)
            text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            md = task_status_metadata(task_id=task_status.task_id)

            # If task status exists, delete it first to avoid embedding
            # mem0's update() method calls embedding_model.embed() which is unnecessary
            # for internal metadata that should be stored as-is
            if items and isinstance(items, list) and items:
                existing_id = str(items[0].get("id") or "").strip()
                if existing_id:
                    try:
                        await self.mem.delete(existing_id)
                    except Exception:
                        # If delete fails, log and continue to add new one
                        logger.warning(
                            f"Failed to delete old task status {existing_id}, will add new one"
                        )

            # Create new internal memory; infer=False to avoid LLM calls and embedding
            res = await self.mem.add(text, user_id="__system__", metadata=md, infer=False)
            new_id: str | None = None
            if isinstance(res, dict):
                results = res.get("results")
                if isinstance(results, list) and results:
                    new_id = str(results[0].get("id") or "").strip() or None
                elif isinstance(results, dict):
                    new_id = str(results.get("id") or "").strip() or None
            return True, new_id
        except Exception as e:
            logger.error(f"Failed to save task status: {e}")
            return False, None

    async def load(
        self,
        *,
        task_id: str,
    ) -> tuple[str | None, ExtractionTaskStatus | None]:
        """Load task status from Mem0.

        Args:
            task_id: Task ID

        Returns:
            (memory_id, task_status): Returns (id, status) if found, (None, None) otherwise
        """
        try:
            filters = task_status_filters(task_id=task_id)
            result = await self.mem.get_all(user_id="__system__", limit=1, filters=filters)
            items = result.get("results", []) if isinstance(result, dict) else []

            if not items or not isinstance(items, list) or not items:
                return None, None

            item = items[0]
            memory_id = str(item.get("id") or "").strip() or None
            raw = str(item.get("memory") or item.get("text") or "").strip()

            if not raw:
                return memory_id, None

            try:
                data = json.loads(raw)
                status = ExtractionTaskStatus(**data)
                return memory_id, status
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                logger.warning(f"Failed to parse task status: {e}")
                return memory_id, None
        except Exception as e:
            logger.error(f"Failed to load task status: {e}")
            return None, None

    async def update_progress(
        self,
        *,
        task_id: str,
        processed_users: int,
        total_users: int,
        scanned_conversations: int = 0,
        scanned_messages: int = 0,
        written_memories: dict[str, int] | None = None,
    ) -> bool:
        """Update task progress.

        Args:
            task_id: Task ID
            processed_users: Number of users processed so far
            total_users: Total number of users
            scanned_conversations: Number of conversations scanned
            scanned_messages: Number of messages scanned
            written_memories: Memory counts by type

        Returns:
            True on success, False on failure
        """
        _, status = await self.load(task_id=task_id)
        if not status:
            return False

        status.processed_users = processed_users
        status.progress = processed_users / total_users if total_users > 0 else 0.0
        status.scanned_conversations = scanned_conversations
        status.scanned_messages = scanned_messages
        if written_memories:
            status.written_memories = written_memories
        status.updated_at = datetime.now(UTC).isoformat()

        ok, _ = await self.save(task_status=status)
        return ok

    async def mark_completed(
        self,
        *,
        task_id: str,
        final_report: dict[str, Any],
    ) -> bool:
        """Mark task as completed with final report.

        Args:
            task_id: Task ID
            final_report: Final extraction report

        Returns:
            True on success, False on failure
        """
        _, status = await self.load(task_id=task_id)
        if not status:
            return False

        status.status = "completed"
        status.progress = 1.0
        status.final_report = final_report
        status.updated_at = datetime.now(UTC).isoformat()

        # Update counts from final report
        if isinstance(final_report, dict):
            summary = final_report.get("summary", {})
            if isinstance(summary, dict):
                status.processed_users = summary.get("processed_users", 0)
                status.skipped_users = summary.get("skipped_users", 0)
                status.scanned_conversations = summary.get("scanned_conversations", 0)
                status.scanned_messages = summary.get("scanned_messages", 0)
                written = summary.get("written_memories")
                if isinstance(written, dict):
                    status.written_memories = written

        ok, _ = await self.save(task_status=status)
        return ok

    async def mark_failed(
        self,
        *,
        task_id: str,
        error: str,
    ) -> bool:
        """Mark task as failed.

        Args:
            task_id: Task ID
            error: Error message

        Returns:
            True on success, False on failure
        """
        _, status = await self.load(task_id=task_id)
        if not status:
            return False

        status.status = "failed"
        status.error = error[:500] if error else None  # Limit error message length
        status.updated_at = datetime.now(UTC).isoformat()

        ok, _ = await self.save(task_status=status)
        return ok
