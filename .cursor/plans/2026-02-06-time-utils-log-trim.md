## Plan

- Extract duration helpers to `utils/time_utils.py`
- Update check_extraction_status to use shared helper
- Trim diagnostic logs in check_extraction_status
- Update unit test to import from utils

## Files to touch

- `utils/time_utils.py`
- `tools/check_extraction_status.py`
- `tests/unit/tools/test_check_extraction_status.py`

