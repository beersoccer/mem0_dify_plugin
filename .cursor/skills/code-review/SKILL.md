---
name: code-review
description: Reviews Python code changes for correctness, maintainability, readability, and adherence to project standards (ruff, type hints, async safety, Dify plugin constraints). Supports local git changes (staged or working tree). Use when the user asks for a code review, to review my changes, review this file, or review the diff.
---

# Code Review

## Workflow

### 1. Identify Changes

```bash
git status
git diff              # unstaged
git diff --staged     # staged
```

Read the changed files directly when diffs alone are insufficient for context.

### 2. Pre-Review Checks (optional, ask if substantial changes)

```bash
source .venv/bin/activate
ruff check .          # lint
ruff format --check . # format
pytest tests/unit/ -v # unit tests (see run-tests skill for details)
```

### 3. Analysis Pillars

Review each changed file against:

- **Correctness**: Logic correct, no bugs or off-by-one errors, handles expected inputs.
- **Type Safety**: Public functions have type hints; uses Python 3.12 style (`list[str]`, `X | Y`).
- **Async Safety**: Any async client/background loop exposes `close`/`shutdown`, is idempotent, and has timeouts.
- **Error Handling**: Raises specific exceptions; includes context in logs; no swallowed exceptions.
- **Resource Cleanup**: Uses context managers (`with`) for file/DB/network resources.
- **Security**: No secrets in code or logs; API keys/passwords redacted; no new telemetry enabled without env-var gate.
- **Dify Plugin Constraints**:
  - Plugin metadata source of truth is `manifest.yaml` / `provider/*.yaml` / `tools/*.yaml`; do not invent schema fields.
  - `.difyignore` excludes `.env*`, keys, local caches, tests before packaging.
  - Packaging uses `build_package.sh`; no secrets in packaged artifacts.
- **Testability**: New logic has pytest unit tests; bug fixes have regression tests. Test updates required but do NOT auto-run.
- **Code Style**:
  - Ruff rules: `E, F, I, B, UP`; line length 100; target Python 3.12.
  - All code comments and docstrings in **English**.
  - Config constants belong in `utils/constants.py`.
  - Network calls must have timeouts and retries.

### 4. Feedback Format

**Summary**  
One paragraph: what changed, overall quality.

**Findings**

| Severity | Label | Meaning |
|----------|-------|---------|
| 🔴 | **Critical** | Must fix: bug, security issue, breaking change |
| 🟡 | **Improvement** | Should fix: quality, performance, standards gap |
| 🟢 | **Nitpick** | Optional: minor style, naming |

For each finding, state:  
> `file.py:LINE` — **[Label]** What the issue is and **why** it matters. Suggested fix.

**Test Coverage**  
Call out any new logic lacking tests or bug fixes missing regression tests.

**Conclusion**  
`✅ Approved` or `🔁 Request Changes` — with a one-line rationale.

### 5. Versioning Note

If the changes are user-facing, remind the user to explicitly request a version bump — do **not** update `manifest.yaml`, `CHANGELOG.md`, or `README.md` automatically.
