from __future__ import annotations

import atexit
import contextlib
import os
import signal
import sys

from dify_plugin import DifyPluginEnv, Plugin
from utils.constants import MAX_REQUEST_TIMEOUT
from utils.mem0_client import AsyncLocalClient

# Disable telemetry/analytics to avoid PostHog timeouts in restricted networks
os.environ.setdefault("POSTHOG_DISABLED", "1")
os.environ.setdefault("DO_NOT_TRACK", "1")
# Best-effort vendor-specific opt-outs (safe no-ops if unsupported)
os.environ.setdefault("MEM0_DISABLE_TELEMETRY", "1")
os.environ.setdefault("DIFY_PLUGIN_DISABLE_TELEMETRY", "1")

plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=MAX_REQUEST_TIMEOUT))

def _graceful_shutdown() -> None:
    with contextlib.suppress(Exception):
        AsyncLocalClient.shutdown(timeout=3.0)

atexit.register(_graceful_shutdown)

def _on_term(signum: int, frame: object | None) -> None:  # noqa: ARG001
    _graceful_shutdown()
    with contextlib.suppress(SystemExit):
        sys.exit(0)

with contextlib.suppress(Exception):
    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)

if __name__ == "__main__":
    plugin.run()
