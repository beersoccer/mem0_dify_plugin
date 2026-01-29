# Workflow: Quickcheck (lint + format check + tests)

1) Ensure venv is active
   - source .venv/bin/activate
2) Install deps:
   - uv sync
3) Run:
   - uv run ruff check .
   - uv run ruff format --check .
   - uv run pytest -q
4) If any step fails:
   - paste the error output into Cascade
   - request a minimal fix + a regression test if applicable
