Plan: Ensure cleanup_test_memories releases resources

- Review current cleanup flow and client lifecycle
- Add safe cleanup logic to close client resources on exit
- Keep behavior identical for deletion loop and output
- Add unit test to verify client.close is invoked
- Retain DIFY_USER_IDS parsing tests in same file

Files to touch:
- `tests/e2e/cleanup_test_memories.py`
- `tests/unit/test_cleanup_test_memories.py`

