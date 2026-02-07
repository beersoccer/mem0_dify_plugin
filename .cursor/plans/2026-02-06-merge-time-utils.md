## Plan

- Move duration helper into `utils/helpers.py` (reuse parse_iso_timestamp)
- Update check_extraction_status to import from helpers
- Update unit test import path
- Remove `utils/time_utils.py`

## Files to touch

- `utils/helpers.py`
- `tools/check_extraction_status.py`
- `tests/unit/tools/test_check_extraction_status.py`
- `utils/time_utils.py` (delete)

