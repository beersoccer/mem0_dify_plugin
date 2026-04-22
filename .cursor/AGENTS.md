# Project Structure & Architecture

> **Note**: For project rules and conventions, see `.cursor/rules/` directory for organized rule files.

## Project Structure

```
mem0_dify_plugin/
├── main.py                    # Plugin entry point, graceful shutdown handling
├── manifest.yaml              # Dify plugin manifest (version, metadata)
│
├── provider/                  # Tool provider module
│   ├── mem0ai.py             # Mem0Provider: credential validation, tool interface
│   └── mem0ai.yaml           # Provider configuration schema
│
├── tools/                     # 12 Dify tools (each: .py implementation + .yaml definition)
│   ├── add_memory.py/.yaml                  # Add/update memories
│   ├── search_memory.py/.yaml               # Search with filters (AND/OR, top_k)
│   ├── get_memory.py/.yaml                  # Get memory by ID
│   ├── get_all_memories.py/.yaml            # List all with pagination
│   ├── update_memory.py/.yaml               # Update existing memory
│   ├── delete_memory.py/.yaml               # Delete specific memory
│   ├── delete_all_memories.py/.yaml         # Batch delete with filters
│   ├── get_memory_history.py/.yaml          # View change history
│   ├── extract_long_term_memory.py/.yaml    # Extract semantic/episodic/procedural memories from Dify history (async task)
│   ├── check_extraction_status.py/.yaml     # Check status and progress of async extraction tasks
│   ├── get_user_checkpoint.py/.yaml         # Inspect extraction checkpoint state for a user/app
│   └── forget_memories.py/.yaml             # Forget low-retention memories and clean stale checkpoints
│
└── utils/                     # Shared utilities
    ├── mem0_client.py         # Mem0 client adapter (sync/async, connection pooling, keepalive)
    ├── config_builder.py      # Builds Mem0 config from Dify credentials
    ├── constants.py           # Timeouts, concurrency limits, result shapes
    ├── logger.py              # Centralized logging (Dify plugin logger, dynamic log level)
    ├── helpers.py             # Common utilities (timeout parsing, timestamps)
    ├── checkpoint.py          # Checkpoint read/write managers (sync + async, add-first-then-delete)
    ├── distributed_lock.py    # Mem0-backed distributed lock (read-after-write verification, TTL cleanup)
    ├── extraction.py          # UserCheckpoint / ConversationCheckpoint data models
    ├── extraction_task.py     # Async task runner and task status persistence
    ├── extraction_helpers.py  # Shared helpers for extraction pipeline
    ├── mem0_extraction.py     # Smart classification + semantic/episodic/procedural extraction pipeline
    ├── memory_forgetting.py   # EWMA quality + Ebbinghaus retention forgetting curve logic
    ├── access_log.py          # Per-user/per-app access log managers (drives forgetting curve)
    ├── score_utils.py         # Score mode inference (distance vs similarity) and normalization
    ├── task_status.py         # Async task status storage and retrieval
    ├── task_tracker.py        # Background task queue monitoring
    ├── pgvector_config.py     # PGVector connection string and pool configuration
    ├── dify_client.py         # Dify REST API client (conversations, messages, retry)
    ├── message_utils.py       # Message format conversion utilities
    ├── retry.py               # Exponential backoff retry decorator
    ├── resource_cleanup.py    # Vector/graph store and pool cleanup helpers
    ├── connection_keepalive.py # Heartbeat thread preventing TCP silent timeouts
    ├── background_loop.py     # Process-wide asyncio event loop management
    ├── queue_monitor.py       # Background task queue overload monitoring
    ├── prompts.py             # Memory extraction prompts (classification + subtype)
    └── mem0_client_llm_compat.py  # LLM compatibility shim for structured providers
```

## Key Architectural Patterns

### Tools Layer
- Each tool implements `Tool._invoke()` interface
- Supports both sync and async execution modes
- Write ops (Add/Update/Delete) are non-blocking in async mode; Read ops always wait
- Returns structured JSON responses with consistent format

### Client Management
- `mem0_client.py` manages Mem0 client lifecycle (singleton per configuration)
- Connection pooling for async operations (psycopg3 pool with TCP keepalive)
- Background task queue for write operations with overload protection
- `ConnectionKeepAlive` daemon thread prevents TCP silent timeouts to LLM/vector services

### Checkpoint & Lock
- `checkpoint.py` implements add-first-then-delete saves to prevent data loss on failure
- `AsyncCheckpointManager.load()` restores all resume cursor fields (including `resume_conversation_cursor`, `resume_run_at`, `resume_start_time`)
- `distributed_lock.py` uses read-after-write verification after persisting; earliest `acquired_at` wins on contention

### Configuration Flow
1. Dify passes JSON credentials to tool
2. `config_builder.py` converts to Mem0 config format (provider name must be canonical)
3. `pgvector_config.py` normalizes connection string, adds TCP keepalive params
4. Client initialization with connection pooling
5. Config validation before first use

### Error Handling
- All tools return structured error messages with status/results fields
- Operations have mandatory timeouts (Read: 5s default, Write: 15s default)
- Failed operations log details without exposing secrets
- Partial failures return detailed per-item status

## Test Structure

```
tests/
├── conftest.py                # Root conftest (markers, env setup)
├── unit/                      # Pure logic tests, no external services (471 tests as of v0.3.0)
│   ├── provider/
│   │   └── test_mem0_provider_validation.py   # Provider credential validation paths
│   ├── tools/
│   │   ├── test_add_memory_overload_guard.py
│   │   ├── test_check_extraction_status.py
│   │   ├── test_extract_long_term_memory.py
│   │   ├── test_extraction_async.py
│   │   ├── test_extraction_parameters.py
│   │   ├── test_forget_memories.py            # forget_memories tool + lock cleanup
│   │   ├── test_get_user_checkpoint.py
│   │   ├── test_search_with_filters.py
│   │   ├── test_time_range_expansion.py
│   │   ├── test_token_truncation.py
│   │   └── test_update_memory.py
│   └── utils/
│       ├── test_async_local_client_read_timeout.py
│       ├── test_async_memory_init_compat.py
│       ├── test_bg_task_tracking.py
│       ├── test_checkpoint.py                 # 28+ tests; uses _run_async() thread isolation
│       ├── test_config_builder_providers.py   # 117 parametrized tests (provider compat gate + registry validation)
│       ├── test_dify_client.py
│       ├── test_dify_incremental_scan.py
│       ├── test_distributed_lock.py           # 28+ tests (acquire, contention, TTL cleanup)
│       ├── test_mem0_client_config_override.py
│       ├── test_mem0_client_llm_compat.py
│       ├── test_mem0_extraction_logging.py
│       ├── test_memory_forgetting.py
│       ├── test_message_segmentation.py
│       ├── test_message_utils.py
│       ├── test_normalize_search_results.py
│       ├── test_overload_guard_preenqueue.py
│       ├── test_performance_user_ids.py
│       ├── test_pgvector_config_defaults.py
│       ├── test_pgvector_pool_max_waiting_default.py
│       ├── test_prompts.py
│       ├── test_retry.py
│       ├── test_score_utils.py
│       ├── test_task_status_async.py
│       └── test_task_status_filters.py
├── integration/               # Tests hitting real Dify API (requires live env)
│   ├── conftest.py
│   ├── test_dify_integration.py
│   ├── test_dify_seed_api.py
│   └── test_time_range_filtering.py
├── acceptance/                # End-to-end workflow acceptance tests
│   ├── conftest.py
│   ├── test_memory_extraction_quality.py
│   ├── test_workflow_memory_lifecycle.py
│   └── test_workflow_plugin_smoke.py
└── helpers/                   # Shared test utilities
    ├── artifacts.py
    ├── dify_cleanup.py
    ├── dify_env.py
    ├── dify_seed.py
    ├── mem0_cleanup.py
    └── workflow_runner.py
```

### Running Tests

```bash
# All unit tests (no external services required)
conda run -n dify pytest tests/unit/ -q

# Integration tests (requires live Dify env)
conda run -n dify pytest tests/integration/ -q

# Full suite
conda run -n dify pytest -q
```

### Test Design Notes

- **Provider compatibility gate** (`test_config_builder_providers.py`): 89 parametrized tests verify canonical provider name strings and critical config fields across all mainstream mem0 providers. 28 additional registry validation tests cross-check every provider name against mem0's live factory maps — these fail on `mem0ai` upgrades that drop or rename a provider.
- **Checkpoint test isolation** (`test_checkpoint.py`): Uses `_run_async()` helper that spawns a dedicated thread and explicitly clears the inherited running-loop via `asyncio.events._set_running_loop(None)` before creating a fresh event loop. This prevents pytest-asyncio AUTO mode's C-level TSS inheritance from causing "Cannot run the event loop while another loop is running" when async tests run before these tests.
- **Distributed lock tests** (`test_distributed_lock.py`): 28+ tests covering acquire, contention resolution (earliest `acquired_at` wins), TTL expiry, and `_clean_expired_locks()` behaviour.
