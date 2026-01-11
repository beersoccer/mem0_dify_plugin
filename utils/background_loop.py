"""Background event loop management for async operations."""

import asyncio
import contextlib
import threading

from .logger import get_logger

logger = get_logger(__name__)


class BackgroundEventLoop:
    """Manages a long-lived background asyncio event loop in a dedicated thread.

    This class provides a process-wide, reusable background event loop for submitting
    and running coroutines from synchronous code or from threads that do not have
    a running event loop.
    """

    _loop: asyncio.AbstractEventLoop | None = None
    _thread: threading.Thread | None = None
    _ready = threading.Event()
    _lock = threading.Lock()

    @classmethod
    def ensure_loop(cls) -> asyncio.AbstractEventLoop:
        """Ensure that a background asyncio event loop is running in a dedicated thread.

        This method provides a long-lived, reusable, process-wide background event loop
        for submitting and running coroutines from synchronous code or from threads that
        do not have a running event loop. The loop is created once and reused for the
        entire plugin lifecycle, ensuring efficient resource usage and avoiding the
        overhead of creating new loops for each operation.

        The event loop runs in a dedicated daemon thread and persists until the plugin
        is shut down via shutdown(). This design ensures:
        - Long lifecycle: Loop exists for the entire plugin runtime
        - Reusability: Same loop instance is returned for all operations
        - Thread safety: Access is guarded by a class-level lock
        - Resource efficiency: No per-operation loop creation overhead

        Returns:
            asyncio.AbstractEventLoop: The long-lived, reusable background event loop object.

        Raises:
            RuntimeError: If the background event loop fails to start.

        """
        with cls._lock:
            # Reuse the existing long-lived loop if already running
            if cls._loop and cls._thread and cls._thread.is_alive():
                logger.debug("Reusing existing long-lived background event loop")
                return cls._loop

            logger.debug("Starting new long-lived background event loop")

            # Define the function that runs in the new background thread
            def _runner() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                cls._loop = loop
                cls._ready.set()
                logger.debug("Background event loop started (long-lived)")
                loop.run_forever()  # Run the event loop forever (long lifecycle)

            # Prepare to start a new background thread
            cls._ready.clear()
            t = threading.Thread(target=_runner, name="mem0-bg-loop", daemon=True)
            t.start()
            cls._thread = t
            cls._ready.wait()  # Wait until the loop is ready

            loop = cls._loop
            if loop is None:
                msg = "Background event loop failed to start"
                logger.error(msg)
                raise RuntimeError(msg)
            logger.debug("Background event loop ready (long-lived, reusable)")
            return loop

    @classmethod
    def shutdown(cls, timeout: float = 3.0) -> None:
        """Best-effort graceful shutdown of the background event loop.

        - Attempts to wait up to `timeout` seconds for pending tasks to finish.
        - Stops the loop and joins the background thread (best-effort).
        - Safe to call multiple times.

        Args:
            timeout: Maximum time to wait for pending tasks to complete.

        """
        loop = cls._loop
        thread = cls._thread
        if loop is None:
            logger.debug("No background event loop to shutdown")
            return

        logger.debug("Shutting down background event loop (timeout: %s)", timeout)

        async def _drain_tasks(t: float) -> None:
            # Exclude the current task and wait for others (best-effort)
            with contextlib.suppress(Exception):
                pending = [
                    tsk
                    for tsk in asyncio.all_tasks()
                    if tsk is not asyncio.current_task()
                ]
                if pending:
                    logger.debug(
                        "Waiting for %d pending tasks to complete",
                        len(pending),
                    )
                    await asyncio.wait(pending, timeout=t)

        fut = asyncio.run_coroutine_threadsafe(_drain_tasks(timeout), loop)
        with contextlib.suppress(Exception):
            fut.result(timeout=timeout + 1.0)
        with contextlib.suppress(Exception):
            loop.call_soon_threadsafe(loop.stop)
        if thread and thread.is_alive():
            with contextlib.suppress(Exception):
                thread.join(timeout=timeout)
        # Clear references
        cls._loop = None
        cls._thread = None
        logger.debug("Background event loop shutdown completed")

