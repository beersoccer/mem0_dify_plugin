## Plan
- Normalize Dify base URL in integration tests to always include scheme + `/v1`.
- Reuse the normalization for invalid-key coverage to avoid setup errors.
- Keep behavior compatible with existing defaults and `.env` expectations.
- Set pytest-asyncio default loop scope to silence deprecation warning.
- Avoid touching secrets or runtime logic beyond test setup.

## Files To Touch
- `tests/integration/test_dify_integration.py`
- `pyproject.toml`

