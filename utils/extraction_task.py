"""Async extraction task management for long-term memory extraction.

This module provides task state management and background execution for
extraction tasks that exceed Dify's 60-second plugin timeout limit.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from .logger import get_logger

if TYPE_CHECKING:
    from .mem0_client import Memory

logger = get_logger(__name__)


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"  # Task created, not started yet
    RUNNING = "running"  # Task is executing
    COMPLETED = "completed"  # Task finished successfully
    FAILED = "failed"  # Task failed with error
    CANCELLED = "cancelled"  # Task was cancelled


@dataclass
class ExtractionTask:
    """Extraction task state."""

    task_id: str
    status: TaskStatus
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str | None = None

    # Task parameters
    user_ids: list[str] | None = None
    app_id: str | None = None
    start_time: str | None = None
    end_time: str | None = None

    # Progress tracking
    total_users: int = 0
    processed_users: int = 0
    skipped_users: int = 0
    scanned_conversations: int = 0
    scanned_messages: int = 0
    written_memories: dict[str, int] | None = None

    # Result summary
    overall_status: str | None = None  # SUCCESS/PARTIAL_SUCCESS/ERROR
    per_user_results: list[dict[str, Any]] | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Initialize mutable defaults."""
        if self.written_memories is None:
            self.written_memories = {"semantic": 0, "episodic": 0, "procedural": 0}
        if self.per_user_results is None:
            self.per_user_results = []

    @property
    def progress(self) -> float:
        """Calculate progress as a percentage (0.0-1.0)."""
        if self.total_users == 0:
            return 0.0
        return (self.processed_users + self.skipped_users) / self.total_users

    def mark_started(self) -> None:
        """Mark task as started."""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now(UTC).isoformat()
        self.updated_at = self.started_at

    def mark_completed(self, overall_status: str) -> None:
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now(UTC).isoformat()
        self.updated_at = self.completed_at
        self.overall_status = overall_status

    def mark_failed(self, error_message: str, error_details: dict[str, Any] | None = None) -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.completed_at = datetime.now(UTC).isoformat()
        self.updated_at = self.completed_at
        self.error_message = error_message
        self.error_details = error_details or {}

    def update_progress(
        self,
        processed_users: int | None = None,
        skipped_users: int | None = None,
        scanned_conversations: int | None = None,
        scanned_messages: int | None = None,
        written_memories: dict[str, int] | None = None,
    ) -> None:
        """Update task progress."""
        if processed_users is not None:
            self.processed_users = processed_users
        if skipped_users is not None:
            self.skipped_users = skipped_users
        if scanned_conversations is not None:
            self.scanned_conversations = scanned_conversations
        if scanned_messages is not None:
            self.scanned_messages = scanned_messages
        if written_memories is not None:
            self.written_memories = written_memories
        self.updated_at = datetime.now(UTC).isoformat()


class TaskManager:
    """Manager for extraction tasks using Mem0 as storage."""

    def __init__(self, mem: Memory) -> None:
        """Initialize task manager.

        Args:
            mem: Mem0 client for task state storage
        """
        self.mem = mem

    def _task_metadata(self, task_id: str, user_id: str | None = None) -> dict[str, Any]:
        """Build metadata for task storage."""
        return {
            "__internal": True,
            "internal_type": "extraction_task",
            "task_id": task_id,
            "user_id": user_id or "*",  # Use * for multi-user tasks
        }

    def _task_filters(self, task_id: str) -> dict[str, Any]:
        """Build filter conditions for task lookup."""
        return {
            "AND": [
                {"__internal": {"eq": True}},
                {"internal_type": {"eq": "extraction_task"}},
                {"task_id": {"eq": task_id}},
            ],
        }

    def create_task(self, task: ExtractionTask) -> tuple[bool, str | None]:
        """Create a new task in Mem0.

        Args:
            task: Task object to store

        Returns:
            (success, memory_id): Returns (True, memory_id) on success
        """
        task_data = asdict(task)
        # Convert enum to string
        if isinstance(task_data.get("status"), TaskStatus):
            task_data["status"] = task_data["status"].value

        text = json.dumps(task_data, ensure_ascii=False, sort_keys=True)
        metadata = self._task_metadata(task.task_id)

        try:
            result = self.mem.add(text, user_id="*", metadata=metadata, infer=False)
            if isinstance(result, dict):
                results = result.get("results")
                if isinstance(results, list) and results:
                    memory_id = str(results[0].get("id") or "").strip() or None
                    if memory_id:
                        logger.info(f"Task {task.task_id} created with memory_id: {memory_id}")
                        return True, memory_id
                elif isinstance(results, dict):
                    memory_id = str(results.get("id") or "").strip() or None
                    if memory_id:
                        logger.info(f"Task {task.task_id} created with memory_id: {memory_id}")
                        return True, memory_id
            logger.error(f"Failed to create task {task.task_id}: Invalid result format")
            return False, None
        except Exception as e:
            logger.exception(f"Failed to create task {task.task_id}: {e}")
            return False, None

    def load_task(self, task_id: str) -> tuple[str | None, ExtractionTask | None]:
        """Load task from Mem0.

        Args:
            task_id: Task identifier

        Returns:
            (memory_id, task): Task's memory_id and task object, (None, None) if not found
        """
        filters = self._task_filters(task_id)

        try:
            result = self.mem.get_all(user_id="*", limit=1, filters=filters)
            items = result.get("results", []) if isinstance(result, dict) else []

            if not items:
                return None, None

            item = items[0]
            memory_id = str(item.get("id") or "").strip() or None
            task_data = item.get("memory") or "{}"

            try:
                data = json.loads(task_data)
                # Convert status string back to enum
                if "status" in data and isinstance(data["status"], str):
                    data["status"] = TaskStatus(data["status"])
                task = ExtractionTask(**data)
                return memory_id, task
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.warning(f"Failed to parse task data for {task_id}: {e}")
                return memory_id, None
        except Exception as e:
            logger.error(f"Failed to load task {task_id}: {e}")
            return None, None

    def update_task(self, memory_id: str, task: ExtractionTask) -> bool:
        """Update task in Mem0.
        
        Note: We use delete+add instead of update to avoid mem0's embedding
        processing. Task data should be stored as-is without any LLM inference
        or vectorization.

        Args:
            memory_id: Mem0 memory ID
            task: Updated task object

        Returns:
            True on success, False on failure
        """
        task_data = asdict(task)
        # Convert enum to string
        if isinstance(task_data.get("status"), TaskStatus):
            task_data["status"] = task_data["status"].value

        text = json.dumps(task_data, ensure_ascii=False, sort_keys=True)

        try:
            # Delete old task to avoid embedding (mem0's update() calls embedding_model.embed())
            try:
                self.mem.delete(memory_id)
            except Exception:
                logger.warning(f"Failed to delete old task {memory_id}, will add new one")
            
            # Create new task with infer=False to avoid LLM calls and embedding
            metadata = self._task_metadata(task.task_id)
            user_id = task.user_ids[0] if task.user_ids and len(task.user_ids) == 1 else "__system__"
            res = self.mem.add(text, user_id=user_id, metadata=metadata, infer=False)
            
            # Note: The memory_id may change after delete+add, but this is acceptable
            # for internal task tracking
            logger.debug(f"Task {task.task_id} updated")
            return True
        except Exception as e:
            logger.error(f"Failed to update task {task.task_id}: {e}")
            return False

    def delete_task(self, memory_id: str) -> bool:
        """Delete task from Mem0.

        Args:
            memory_id: Mem0 memory ID

        Returns:
            True on success, False on failure
        """
        try:
            if hasattr(self.mem, "delete"):
                self.mem.delete(memory_id)
                logger.info(f"Task deleted (memory_id: {memory_id})")
            return True
        except Exception as e:
            logger.error(f"Failed to delete task (memory_id: {memory_id}): {e}")
            return False


class BackgroundTaskExecutor:
    """Executor for running extraction tasks in background threads."""

    _active_tasks: dict[str, threading.Thread] = {}
    _lock = threading.Lock()

    @classmethod
    def submit_task(
        cls,
        task_id: str,
        target_func: callable,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        """Submit a task for background execution.

        Args:
            task_id: Unique task identifier
            target_func: Function to execute in background
            *args: Positional arguments for target_func
            **kwargs: Keyword arguments for target_func

        Returns:
            True if task was submitted, False if task already running
        """
        with cls._lock:
            if task_id in cls._active_tasks:
                logger.warning(f"Task {task_id} is already running")
                return False

            thread = threading.Thread(
                target=cls._wrapped_task_execution,
                args=(task_id, target_func, args, kwargs),
                name=f"extraction-{task_id[:8]}",
                daemon=True,
            )
            cls._active_tasks[task_id] = thread
            thread.start()
            logger.info(f"Task {task_id} submitted to background thread {thread.name}")
            return True

    @classmethod
    def _wrapped_task_execution(
        cls,
        task_id: str,
        target_func: callable,
        args: tuple,
        kwargs: dict,
    ) -> None:
        """Wrapper for task execution with cleanup."""
        try:
            logger.info(f"Task {task_id} started in background")
            start_time = time.time()
            target_func(*args, **kwargs)
            elapsed = time.time() - start_time
            logger.info(f"Task {task_id} completed in {elapsed:.2f}s")
        except Exception as e:
            logger.exception(f"Task {task_id} failed with exception: {e}")
        finally:
            with cls._lock:
                cls._active_tasks.pop(task_id, None)
                logger.debug(f"Task {task_id} removed from active tasks")

    @classmethod
    def is_task_running(cls, task_id: str) -> bool:
        """Check if a task is currently running.

        Args:
            task_id: Task identifier

        Returns:
            True if task is running, False otherwise
        """
        with cls._lock:
            thread = cls._active_tasks.get(task_id)
            return thread is not None and thread.is_alive()

    @classmethod
    def get_active_task_count(cls) -> int:
        """Get count of active background tasks.

        Returns:
            Number of currently running tasks
        """
        with cls._lock:
            # Clean up dead threads
            dead_tasks = [
                tid for tid, thread in cls._active_tasks.items() if not thread.is_alive()
            ]
            for tid in dead_tasks:
                cls._active_tasks.pop(tid, None)
            return len(cls._active_tasks)

