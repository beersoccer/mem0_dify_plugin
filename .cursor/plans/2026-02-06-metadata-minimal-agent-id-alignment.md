Plan: Minimal metadata + agent_id alignment

- Align long-term extraction writes to pass app_id as agent_id to Mem0
- Simplify extraction metadata to minimal fields + memory_origin
- Remove hardcoded categories/source/schema/timestamps from metadata
- Update build_memory_metadata signature and callers
- Update writer helpers to accept agent_id for add payloads
- Adjust affected unit tests to new metadata shape

Files to touch:
- utils/mem0_extraction.py
- tools/extract_long_term_memory.py
- tests/unit/tools/test_extraction_parameters.py (and any other failing tests)

