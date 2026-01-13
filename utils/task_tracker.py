"""Task tracking and statistics for background operations."""

import asyncio
import concurrent.futures
import threading
import time
from typing import ClassVar

from .logger import get_logger

logger = get_logger(__name__)


class TaskTracker:
    """Tracks background tasks and provides statistics for queue monitoring.

    This class manages lifecycle tracking for all memory operations submitted
    to the background event loop, regardless of whether they are fire-and-forget
    (write ops) or awaited (read ops).
    """

    # Class-level tracking of all background tasks submitted to the event loop
    # (includes both read operations that wait for results and write operations
    # that are fire-and-forget). Used for global flow control and monitoring.
    _bg_tasks: ClassVar[set[asyncio.Future]] = set()
    _bg_tasks_lock: ClassVar[threading.Lock] = threading.Lock()

    # Statistics tracking for queue monitoring
    _completed_tasks: ClassVar[int] = 0
    _total_task_duration: ClassVar[float] = 0.0
    _stats_lock: ClassVar[threading.Lock] = threading.Lock()

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
        with cls._bg_tasks_lock:
            return len(cls._bg_tasks)

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
        with cls._stats_lock:
            completed = cls._completed_tasks
            avg_duration = cls._total_task_duration / completed if completed > 0 else 0.0
            # Reset counters for next monitoring period
            cls._completed_tasks = 0
            cls._total_task_duration = 0.0
        return completed, avg_duration

    @classmethod
    def track_bg_task(cls, future: asyncio.Future, task_name: str = "unknown") -> None:
        """Track a background task and log completion/errors.

        This method tracks all memory operations submitted to the background event loop,
        regardless of whether they are fire-and-forget (write ops) or awaited (read ops).

        Args:
            future: The future object returned by run_coroutine_threadsafe.
            task_name: Name of the task for logging (format: "operation(params, req_id=xxx)").

        """
        start_time = time.time()

        with cls._bg_tasks_lock:
            cls._bg_tasks.add(future)

        def _done_callback(f: asyncio.Future) -> None:
            """Task completion callback for background operations.

            This callback's sole purpose is lifecycle management:
            1. Remove task from tracking set
            2. Update statistics for queue monitoring

            Logging strategy:
            - SUCCESS: No logging (already logged by operation layer)
            - TIMEOUT: No logging (already logged by operation layer)
            - QUEUE_OVERLOAD: No logging (already logged by operation layer)
            - OTHER EXCEPTIONS: No logging here; tool layer logs with business context

            The pass statements are INTENTIONAL to avoid duplicate logging.
            """
            duration = time.time() - start_time

            # Remove from tracking set
            with cls._bg_tasks_lock:
                cls._bg_tasks.discard(f)

            # Update statistics for queue monitoring (regardless of success/failure)
            with cls._stats_lock:
                cls._completed_tasks += 1
                cls._total_task_duration += duration

            # Check task result but avoid duplicate logging
            try:
                f.result()  # This will raise if the coroutine raised
            except (asyncio.CancelledError, concurrent.futures.CancelledError) as e:
                # Cancellation is expected in some flows (e.g. failsafe timeouts)
                # Log at warning level to track task cancellations
                logger.warning(
                    "Background task '%s' was cancelled (duration: %.2fs): %s",
                    task_name,
                    duration,
                    type(e).__name__,
                )
            except ValueError as e:
                # ValueError for "not found" is expected in some scenarios
                # (e.g., memory already deleted, concurrent operations)
                # Log at warning level without stack trace
                error_msg = str(e)
                if "not found" in error_msg.lower() or "already been deleted" in error_msg.lower():
                    logger.warning(
                        "Background task '%s' completed with expected error (duration: %.2fs): %s",
                        task_name,
                        duration,
                        error_msg,
                    )
                else:
                    # Other ValueErrors are unexpected, log at warning level without stack trace
                    logger.warning(
                        "Background task '%s' completed with exception (duration: %.2fs): %s",
                        task_name,
                        duration,
                        type(e).__name__,
                    )
            except Exception as e:
                # All other exceptions (TimeoutError, QueueOverloadError, etc.)
                # are already logged by operation layer or tool layer.
                # Log here for completeness and to track duration.
                logger.exception(
                    "Background task '%s' completed with exception (duration: %.2fs): %s",
                    task_name,
                    duration,
                    type(e).__name__,
                )

        future.add_done_callback(_done_callback)

