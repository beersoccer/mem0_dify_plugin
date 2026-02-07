## Plan
- Audit time-related helpers and task status timestamps for UTC usage.
- Switch timestamp generation/parsing to local timezone.
- Update any affected helper naming and add unit tests for local tz parsing.

## Files to touch
- `utils/helpers.py`
- `utils/task_status.py`
- `tools/extract_long_term_memory.py`
- `utils/extraction_task.py`
- `utils/mem0_extraction.py`
- `utils/distributed_lock.py`
- `tests/unit/tools/test_extraction_parameters.py`

