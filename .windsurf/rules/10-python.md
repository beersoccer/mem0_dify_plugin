---
trigger: glob
globs: **/*.py
---
# Rule: Python Standards (Glob: **/*.py)

## Style & correctness
- Prefer clear, explicit code over clever code.
- Use type hints for public functions and key data structures.
- Use Python 3.12 typing (list[str], dict[str, ...], | for unions).
- Keep functions small; extract helpers rather than nesting deeply.
- Prefer explicit error handling: raise specific exceptions and include context in logs/errors.
- Prefer explicit resource cleanup: use context managers (with) for deterministic cleanup.

## Async + threads (project-specific)
- Any async client or background loop must:
  - expose a close/shutdown method
  - be safe to call multiple times (idempotent)
  - have timeouts on blocking waits

## Structure
- Put configuration constants in utils/constants.py (or existing config module).
- Network calls must have timeouts and retries (if applicable), and must surface actionable errors.

## Logging
- Log lifecycle transitions (start/shutdown) once per process.
- Avoid logging secrets; redact API keys/passwords.

## Testing
- For new logic: add pytest tests (unit tests first; integration tests only when needed).
- When fixing a bug: add a regression test reproducing the failure.
