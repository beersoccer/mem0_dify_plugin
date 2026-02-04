Plan: Fix azure_openai_structured compatibility in plugin only

- Inspect plugin LLM heartbeat and mem0 client creation paths
- Add LLM compatibility shim to provide _parse_response when missing
- Apply shim for both SyncMem0Client and AsyncMem0Client
- Adjust heartbeat to avoid passing max_tokens to strict LLMs
- Add unit test covering compatibility shim behavior
- Run lint check for touched files (no test run)

Files to touch:
- utils/mem0_client.py
- utils/connection_keepalive.py
- tests/unit/utils/test_mem0_client_llm_compat.py

