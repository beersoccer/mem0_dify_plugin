---
trigger: always_on
---
# Rule: Runtime Lifecycle Contract (Always On)

This repository relies on a strict startup/shutdown order.

## Startup contract (main.py)
- Environment variables disabling telemetry MUST be set before importing mem0:
  - MEM0_TELEMETRY=False
  - POSTHOG_DISABLED=1
  - DO_NOT_TRACK=1
- Plugin is created as:
  - plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=MAX_REQUEST_TIMEOUT))

## Shutdown contract
- _graceful_shutdown() must:
  1) log start
  2) close current async client if present (via BackgroundEventLoop loop if running)
  3) call AsyncMem0Client.shutdown(timeout=3.0)
  4) log completion
- Shutdown must be invoked on:
  - atexit
  - SIGTERM handler
  - KeyboardInterrupt path

## Change policy
- Any changes to startup env vars, signal handling, background loop, or async client shutdown:
  - MUST include a regression test covering the relevant path.
- Avoid altering timeouts without justification:
  - keep fut.result(timeout=2.0) and shutdown(timeout=3.0) unless you add tests/metrics.
