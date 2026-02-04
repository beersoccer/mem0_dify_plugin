Plan: Improve prompt JSON stability for long-term memory

- Review current prompt templates vs mem0 defaults for JSON rules
- Tighten JSON output constraints to avoid control characters
- Reduce update-memory prompt verbosity and forbid multiline text
- Allow minimal update response (omit NONE entries)
- Add unit tests for key prompt invariants

Files:
- `mem0_dify_plugin/utils/prompts.py`
- `mem0_dify_plugin/tests/unit/utils/test_prompts.py`

