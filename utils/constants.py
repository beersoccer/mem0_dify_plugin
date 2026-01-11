"""Project-wide constants for mem0 Dify plugin."""

# Optional custom prompt for Mem0's procedural memory path.
# Notes:
# - `prompt` passed to `Memory.add(..., prompt=...)` is only used by Mem0's
#   procedural memory path. For infer-based fact extraction, Mem0 uses
#   config-level prompts instead.
# - This constant exists for backward compatibility (CHANGELOG v0.0.7) and to
#   avoid import errors in:
#   - `utils/mem0_client.py`
CUSTOM_PROMPT: str = ""

# Standardized add-operation return shapes
ADD_SKIP_RESULT: dict[str, object] = {
    "results": [
        {
            "id": "",
            "memory": "",
            "event": "SKIP",
        },
    ],
}

ADD_ACCEPT_RESULT: dict[str, object] = {
    "results": [
        {
            "id": "",
            "memory": "",
            "event": "ACCEPT",
        },
    ],
}

UPDATE_ACCEPT_RESULT: dict[str, object] = {
    "results": {
        "message": "Memory update has been accepted",
    },
}

DELETE_ACCEPT_RESULT: dict[str, object] = {
    "results": {
        "message": "Memory deletion has been accepted",
    },
}

DELETE_ALL_ACCEPT_RESULT: dict[str, object] = {
    "results": {
        "message": "Batch memory deletion has been accepted",
    },
}

# The maximum timeout (in seconds) for a single request, to avoid long waits or hanging connections.
MAX_REQUEST_TIMEOUT: int = 60

# Operation timeouts (in seconds) for individual Mem0 operations
# These should be less than MAX_REQUEST_TIMEOUT to allow for error handling
# Read operations: unified timeout for all read operations (search, get, get_all, history)
READ_OPERATION_TIMEOUT: int = 15
# Write operations: longer timeout to allow persistence
WRITE_OPERATION_TIMEOUT: int = 30

# Concurrency controls
# Maximum concurrent memory operations.
# Applies to all operations including search/add/get/get_all/update/delete/delete_all/history.
MAX_CONCURRENT_MEMORY_OPERATIONS: int = 40

# Database connection pool settings for pgvector
# These values should align with MAX_CONCURRENT_MEMORY_OPERATIONS to ensure
# sufficient connections.
PGVECTOR_MIN_CONNECTIONS: int = 10  # Minimum number of connections in the pool
# Maximum number of connections in the pool (should match MAX_CONCURRENT_MEMORY_OPERATIONS)
PGVECTOR_MAX_CONNECTIONS: int = 40

# Default top_k for search
SEARCH_DEFAULT_TOP_K: int = 5

# Maximum pending background tasks before rejecting new tasks
# (multiple of MAX_CONCURRENT_MEMORY_OPERATIONS)
# This prevents task queue from growing indefinitely when operations are slower than request rate
MAX_PENDING_TASKS_MULTIPLIER: int = 5

# Heartbeat interval (in seconds)
# Used to prevent TCP connection silent timeout for LLM, embedding, and vector store services
# Default: 120 seconds (2 minutes)
HEARTBEAT_INTERVAL: int = 120
