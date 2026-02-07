## Plan
- Review current `check_extraction_status` text output formatting.
- Add a helper to format task start/end timestamps for display.
- Include start/end time line in the human-readable status message.
- Extend unit tests to cover the new time range formatter.

## Files to touch
- `utils/helpers.py`
- `tools/check_extraction_status.py`
- `tests/unit/tools/test_check_extraction_status.py`

