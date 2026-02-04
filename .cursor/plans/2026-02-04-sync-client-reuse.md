Plan: Avoid manual Memory replacement in sync subtype clients

- Inspect current build_subtype_sync_clients flow and SyncMem0Client init
- Add config override path to SyncMem0Client for prebuilt configs
- Update build_subtype_sync_clients to use config override instead of swapping
- Add unit test to ensure config override bypasses build_local_mem0_config
- Verify lints for touched files

Files to touch:
- utils/mem0_client.py
- utils/mem0_extraction.py
- tests/unit/utils/test_mem0_client_config_override.py

