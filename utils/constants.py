"""Project-wide constants for mem0 Dify plugin."""

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

# Dify API pagination constraints
# Maximum items (conversations or messages) that can be fetched in a single API request
# This is a Dify API technical constraint and cannot be changed
DIFY_API_MAX_ITEMS_PER_REQUEST: int = 100

# Extraction conversation limits (business logic, configurable)
# Default maximum conversations to process per user per execution
# This prevents malicious users from generating excessive conversations
# and consuming too much processing time.
# Default: 20 conversations (suitable for 1-day execution cycle)
# - Light users: ~5 conversations (3-5 per day)
# - Normal users: ~10-15 conversations (10-15 per day)
# - Heavy users: ~20-30 conversations (20-30 per day)
# Setting to 20 balances coverage for typical users while preventing abuse
EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT: int = 20

# Extraction operation timeouts (for batch memory extraction)
# These are significantly longer than standard operations due to:
# - Multiple API calls to Dify (conversations + messages)
# - Multiple Mem0 add operations (3 types per message segment)
# - LLM inference for each memory extraction
# Time budget: 60 minutes (suitable for large batch jobs processing 1000+ users)
# With 5 concurrent users, can process ~300 users per hour (assuming 6s/user)
EXTRACTION_TIME_BUDGET: int = 3600  # 60 minutes
# Lock TTL: longer than time budget for safety margin (prevents deadlock if task crashes)
# Safety margin: 15 minutes (25% of time budget) ensures lock expires even if task
# completes slightly after time budget or if task crashes
EXTRACTION_LOCK_TTL: int = 4500  # 75 minutes
# Dify API timeout: per-request timeout for conversation/message listing
EXTRACTION_DIFY_TIMEOUT: float = 30.0  # 30 seconds per API call
# Max concurrent users for parallel processing
# With 5 concurrent users, achieves ~3-4x speedup over sequential processing
EXTRACTION_MAX_CONCURRENT_USERS: int = 5  # Process up to 5 users concurrently

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

# Extraction conversation processing limits
# Maximum tokens per conversation for memory extraction.
# The value is expressed in thousands of tokens (K) for consistency with tool parameters.
# Default: 64K tokens - suitable for most modern LLMs:
# - GPT-4o: 128K context window
# - Claude 3.5: 200K context window
# - GPT-4 Turbo: 128K context window
# This is a configurable parameter that can be adjusted based on the actual LLM used.
# If a conversation exceeds the limit, only the most recent messages within the limit are processed.
EXTRACTION_DEFAULT_MAX_TOKENS: int = 64  # 64K tokens (value is in K)

# Default tiktoken encoding model for token counting
# Using "cl100k_base" which is used by:
# - GPT-4, GPT-4o, GPT-3.5-turbo
# - text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002
# This is accurate for most OpenAI and compatible models
EXTRACTION_DEFAULT_ENCODING: str = "cl100k_base"
