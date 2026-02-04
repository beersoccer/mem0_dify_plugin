Plan: Gate fact debug LLM calls to avoid slowdown

- Identify debug LLM call path in extraction flow
- Add env-gated helper for fact debug enablement
- Skip preview unless explicitly enabled
- Add unit test for gating helper
- Verify lints for touched files

Files:
- `mem0_dify_plugin/utils/mem0_extraction.py`
- `mem0_dify_plugin/tests/unit/utils/test_mem0_extraction.py`

