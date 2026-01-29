# AGENTS.md

## Project snapshot (source of truth)
- Repo type: Dify plugin
- Workspace: /Users/beersoccer/workspace/mem0_dify_plugin
- Entry: main.py
- Plugin manifest: manifest.yaml
- Dependency mgmt: pip + requirements.txt (keep as-is)
- CI: GitHub Actions

## Project structure
```
mem0_dify_plugin/
├── main.py                    # Plugin entry point, graceful shutdown handling
├── manifest.yaml              # Dify plugin manifest
│
├── provider/                  # Tool provider module
│   ├── mem0ai.py             # Mem0Provider: credential validation, tool interface
│   └── mem0ai.yaml           # Provider configuration schema
│
├── tools/                     # 8 Dify tools (each: .py implementation + .yaml definition)
│   ├── add_memory.py/.yaml           # Add/update/delete memories
│   ├── search_memory.py/.yaml        # Search with filters (AND/OR, top_k)
│   ├── get_memory.py/.yaml           # Get memory by ID
│   ├── get_all_memories.py/.yaml     # List all with pagination
│   ├── update_memory.py/.yaml        # Update existing memory
│   ├── delete_memory.py/.yaml        # Delete specific memory
│   ├── delete_all_memories.py/.yaml  # Batch delete with filters
│   └── get_memory_history.py/.yaml   # View change history
│
└── utils/                     # Shared utilities
    ├── mem0_client.py         # Mem0 client adapter (sync/async, connection pooling)
    ├── config_builder.py      # Builds Mem0 config from Dify credentials
    ├── constants.py           # Timeouts, concurrency limits, result shapes
    ├── logger.py              # Centralized logging (Dify plugin logger)
    └── helpers.py             # Common utilities (timeout parsing, timestamps)
```

### Key architectural patterns
- **Tools**: Each tool implements `Tool._invoke()`, supports sync/async modes, handles timeouts gracefully
- **Client management**: `mem0_client.py` manages singleton instances, connection pooling, background task queue
- **Config flow**: `config_builder.py` converts Dify JSON credentials → Mem0 config format
- **Error handling**: All tools return structured error messages, operations have timeouts

## Non-negotiables
- For multi-file changes: use Plan Mode first, then execute step-by-step. Save the plan to .cursor/plans/.
- Any behavior change must include/adjust tests under /tests.
- Keep diffs small and reviewable; prefer multiple small PRs.

## Local commands (standard)
- Activate conda environment: `conda activate dify`
  - Note: If environment doesn't exist, create it with: `conda create -n dify python=3.x && conda activate dify`
- Install runtime deps: `pip install -r requirements.txt`
- Install dev deps: `pip install -r requirements-dev.txt`
- Lint: `ruff check .`
- Format check: `ruff format --check .`
- Test: `pytest -q`

## Cursor collaboration rules
- Before editing: summarize a file-level plan (5–10 bullets) and list files to touch.
- If unsure: ask 1–3 clarifying questions before coding.
- Prefer repo files as truth. Do not invent Dify plugin fields; read manifest.yaml first.