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
├── tools/                     # 9 Dify tools (each: .py implementation + .yaml definition)
│   ├── add_memory.py/.yaml                  # Add/update memories
│   ├── search_memory.py/.yaml               # Search with filters (AND/OR, top_k)
│   ├── get_memory.py/.yaml                  # Get memory by ID
│   ├── get_all_memories.py/.yaml            # List all with pagination
│   ├── update_memory.py/.yaml               # Update existing memory
│   ├── delete_memory.py/.yaml               # Delete specific memory
│   ├── delete_all_memories.py/.yaml         # Batch delete with filters
│   ├── get_memory_history.py/.yaml          # View change history
│   └── consolidate_long_term_memory.py/.yaml # Extract semantic/episodic/procedural memories from Dify history
│
└── utils/                     # Shared utilities
    ├── mem0_client.py         # Mem0 client adapter (sync/async, connection pooling)
    ├── config_builder.py      # Builds Mem0 config from Dify credentials
    ├── constants.py           # Timeouts, concurrency limits, result shapes
    ├── logger.py              # Centralized logging (Dify plugin logger)
    └── helpers.py             # Common utilities (timeout parsing, timestamps)
```

## Key Architectural Patterns

### Tools Layer
- Each tool implements `Tool._invoke()` interface
- Supports both sync and async execution modes
- Handles timeouts gracefully (default: 30s, configurable)
- Returns structured JSON responses with consistent error format

### Client Management
- `mem0_client.py` manages Mem0 client lifecycle
- Singleton instances per configuration
- Connection pooling for async operations
- Background task queue for write operations
- Graceful shutdown with timeout handling

### Configuration Flow
1. Dify passes JSON credentials to tool
2. `config_builder.py` converts to Mem0 config format
3. Client initialization with connection pooling
4. Config validation before first use

### Error Handling
- All tools return structured error messages:
  ```json
  {
    "success": false,
    "error": "Description",
    "error_code": "ERROR_TYPE"
  }
  ```
- Operations have mandatory timeouts
- Failed operations log details without exposing secrets
- Partial failures return detailed per-item status