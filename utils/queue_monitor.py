"""Background task queue monitor for async operations."""

import threading
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from collections.abc import Callable

from .logger import get_logger

logger = get_logger(__name__)


class QueueMonitor:
    """Monitor background task queue and log statistics periodically.

    This monitor logs system throughput metrics including completed tasks,
    pending tasks, and average processing time over a configurable interval.
    """

    _instance: ClassVar["QueueMonitor | None"] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, interval_seconds: int = 300) -> None:
        """Initialize queue monitor.

        Args:
            interval_seconds: Monitoring interval in seconds (default 300 = 5 minutes).
                             Set to 0 to disable monitoring.

        """
        self.interval = interval_seconds
        self.enabled = interval_seconds > 0
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @classmethod
    def get_instance(cls, interval_seconds: int = 300) -> "QueueMonitor":
        """Get or create singleton instance.

        Args:
            interval_seconds: Monitoring interval in seconds.

        Returns:
            QueueMonitor instance.

        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = QueueMonitor(interval_seconds)
        return cls._instance

    def is_running(self) -> bool:
        """Check if monitoring thread is running.

        Returns:
            bool: True if monitoring thread is running, False otherwise.

        """
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        get_pending_count_fn: "Callable[[], int]",
        get_completed_stats_fn: "Callable[[], tuple[int, float]]",
    ) -> bool:
        """Start monitoring thread.

        Args:
            get_pending_count_fn: Function to get current pending task count.
            get_completed_stats_fn: Function to get (completed_count, avg_duration).

        Returns:
            bool: True if thread was started, False if already running or disabled.

        """
        if not self.enabled or self._thread is not None:
            return False

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            args=(get_pending_count_fn, get_completed_stats_fn),
            name="queue-monitor",
            daemon=True,
        )
        self._thread.start()
        logger.debug("Queue monitor started (interval: %ds)", self.interval)
        return True

    def stop(self) -> None:
        """Stop monitoring thread."""
        if self._thread is None:
            return

        self._stop_event.set()
        self._thread.join(timeout=5.0)
        self._thread = None
        logger.debug("Queue monitor stopped")

    def _collect_and_log_stats(
        self,
        get_pending_count_fn: "Callable[[], int]",
        get_completed_stats_fn: "Callable[[], tuple[int, float]]",
    ) -> None:
        """Collect statistics and log them, handling any exceptions.

        Args:
            get_pending_count_fn: Function to get current pending task count.
            get_completed_stats_fn: Function to get (completed_count, avg_duration).

        """
        try:
            pending = get_pending_count_fn()
            completed, avg_duration = get_completed_stats_fn()

            logger.debug(
                "Task queue status: pending=%d, completed_last_period=%d, avg_duration=%.2fs",
                pending,
                completed,
                avg_duration,
            )
        except Exception:
            logger.exception("Error in queue monitor loop")

    def _monitor_loop(
        self,
        get_pending_count_fn: "Callable[[], int]",
        get_completed_stats_fn: "Callable[[], tuple[int, float]]",
    ) -> None:
        """Background monitoring loop.

        Args:
            get_pending_count_fn: Function to get current pending task count.
            get_completed_stats_fn: Function to get (completed_count, avg_duration).

        """
        while not self._stop_event.wait(self.interval):
            self._collect_and_log_stats(get_pending_count_fn, get_completed_stats_fn)
