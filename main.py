from __future__ import annotations

import asyncio
import atexit
import contextlib
import os
import signal
import sys
import warnings

# Disable telemetry/analytics to avoid PostHog timeouts in restricted networks
# Must be set before importing mem0 (checked in mem0/memory/telemetry.py)
os.environ.setdefault("MEM0_TELEMETRY", "False")
os.environ.setdefault("POSTHOG_DISABLED", "1")
os.environ.setdefault("DO_NOT_TRACK", "1")

from dify_plugin import DifyPluginEnv, Plugin
from utils.background_loop import BackgroundEventLoop
from utils.constants import MAX_REQUEST_TIMEOUT
from utils.logger import get_logger
from utils.mem0_client import AsyncMem0Client, get_current_async_client

# Suppress gevent fork warning in multi-threaded environments
# This warning is raised when gevent detects fork() in a multi-threaded process.
# In our case, the background threads (heartbeat, event loop) are daemon threads
# and won't cause deadlocks. The warning is preventive and can be safely ignored.
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=".*multi-threaded.*use of fork.*",
)

logger = get_logger(__name__)

plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=MAX_REQUEST_TIMEOUT))

def _graceful_shutdown() -> None:
    logger.info("Initiating graceful shutdown of Mem0 plugin")
    # Cleanup async client resources before shutting down event loop
    async_client = get_current_async_client()
    if async_client is not None:
        loop = BackgroundEventLoop._loop  # noqa: SLF001
        if loop is not None and loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(async_client.aclose(), loop)
            fut.result(timeout=2.0)
    AsyncMem0Client.shutdown(timeout=3.0)
    logger.info("Graceful shutdown completed")

atexit.register(_graceful_shutdown)

def _on_term(signum: int, frame: object | None) -> None:  # noqa: ARG001
    logger.info("Received signal %s, shutting down", signum)
    _graceful_shutdown()
    sys.exit(0)

with contextlib.suppress(Exception):
    signal.signal(signal.SIGTERM, _on_term)

if __name__ == "__main__":
    try:
        logger.info("Starting Mem0 Dify plugin")
        plugin.run()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
        _graceful_shutdown()
        sys.exit(0)
    except Exception:
        logger.exception("Unexpected error occurred during plugin execution")
        raise
