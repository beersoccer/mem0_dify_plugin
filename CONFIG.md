# Mem0 Dify Plugin - Configuration Guide

Last updated: 2026-03-23

This guide provides detailed installation and configuration instructions for the Mem0 Dify Plugin.

## Table of Contents

- [Installation](#installation)
- [Configuration Steps](#configuration-steps)
- [Configuration Examples](#configuration-examples)
- [Quick Start: Testing Your Configuration](#quick-start-testing-your-configuration)
- [Usage Examples](#usage-examples)
- [Runtime Behavior](#runtime-behavior)
- [Connection Stability & Resource Management](#connection-stability--resource-management)
- [Important Operational Notes](#important-operational-notes)
- [Upgrade Guide](#upgrade-guide)
- [Troubleshooting](#troubleshooting)
- [Additional Resources](#additional-resources)

## Installation

### Step 1: Access Plugin Management

1. **Log in to Dify Dashboard**
   - Access your Dify instance (self-hosted or Dify Cloud)
   - Example: `https://your-dify-instance.com` or `https://cloud.dify.ai`

2. **Navigate to Plugins**
   - Go to `Settings` → `Plugins`
   - Or directly access `/plugins` path

### Step 2: Install the Plugin

**Option A: Install from GitHub (Recommended)**
1. Click `Install from GitHub` button
2. Enter your repository URL: `https://github.com/yourusername/mem0_dify_plugin`
3. Click `Install`
4. Wait for installation to complete

**Option B: Install from Package**
1. Click `Upload Plugin` button
2. Select the `.difypkg` file (e.g., `mem0ai-0.1.8.difypkg`)
3. Wait for upload and installation to complete

### Step 3: Verify Installation

After installation, you should see the `mem0ai` plugin in your plugins list. The plugin provides 12 tools:
- `add_memory`, `search_memory`, `get_all_memories`, `get_memory`
- `update_memory`, `delete_memory`, `delete_all_memories`, `get_memory_history`
- `extract_long_term_memory` (extract semantic/episodic/procedural memories from Dify conversation history)
- `check_extraction_status` (check the status and progress of async extraction tasks)
- `get_user_checkpoint` (inspect checkpoint state for a user/app)
- `forget_memories` (forget low-retention memories and clean old checkpoints)

## Configuration Steps

### Step 1: Choose Operation Mode

First, select the operation mode in plugin credentials:

- **Async Mode** (`async_mode=true`, default)
  - Recommended for production environments
  - Supports high concurrency
  - Write operations (Add/Update/Delete/Delete_All): non-blocking, return ACCEPT status immediately
  - Read operations (Search/Get/Get_All/History): wait for results with timeout protection (default: 5s)

- **Sync Mode** (`async_mode=false`)
  - Recommended for testing environments
  - All operations block until completion
  - You can see the actual results of each memory operation immediately
  - **Note**: Sync mode has no timeout protection. If timeout protection is needed, use `async_mode=true`
  
**Special Note for `extract_long_term_memory` Tool:**
- See **Extract Long-Term Memory** → **Mode Selection** for use cases and batch processing behavior.

### Step 2: Configure Models and Databases

After installation, click on the `mem0ai` plugin to configure it. You'll see credential fields that need to be filled.

**Important Notes:**
- **For New Installations**: Use the `*_secret` fields (e.g., `local_llm_json_secret`, `local_embedder_json_secret`) with `secret-input` type (encrypted fields) for better security
- **Deprecated Fields Removed**: Legacy `*_json` fields (e.g., `local_llm_json`, `local_embedder_json`) are no longer shown in the configuration UI. If you encounter configuration issues after upgrade, please delete old credentials and reconfigure using the new `*_secret` fields
- **For Upgrades from v0.1.3**: See [Upgrade Guide](#upgrade-guide) for detailed upgrade instructions
- All JSON configuration fields are displayed as **password fields** (hidden input) in the Dify UI to protect sensitive information
- Each JSON must be a valid JSON object with the structure: `{ "provider": "<provider_name>", "config": { ... } }`
- For detailed configuration options and supported providers, refer to the [Mem0 Official Configuration Documentation](https://docs.mem0.ai/open-source/configuration)

**Required Fields:**
- `local_llm_json_secret` - LLM provider configuration (JSON string, encrypted)
- `local_embedder_json_secret` - Embedding model configuration (JSON string, encrypted)
- `local_vector_db_json_secret` - Vector database configuration (JSON string, encrypted)

**Optional Fields:**
- `local_graph_db_json_secret` - Graph database configuration (JSON string, e.g., Neo4j, encrypted)
- `local_reranker_json_secret` - Reranker configuration (JSON string, encrypted)
- `log_level` - Log level for memory operations (INFO/DEBUG/WARNING/ERROR, default: INFO). Can be changed online without redeployment
- `memory_ttl_days` - Optional hard max age for memories in days (empty by default; when set, old memories are force-deleted regardless of recall history)
- `checkpoint_ttl_days` - Checkpoint retention TTL in days for cleanup by `forget_memories` (default: 90)

**How to Fill JSON Fields:**
1. Copy the JSON example from the [Configuration Examples](#configuration-examples) section below
2. Replace placeholder values (like `your-api-key`, `your-deployment-name`) with your actual values
3. **Validate your JSON** using an online JSON validator before pasting
4. Paste the complete JSON string into the corresponding field in Dify UI
5. Ensure the JSON is valid (no trailing commas, proper quotes, matching braces)
6. Click outside the field to trigger validation (Dify will show errors if JSON is invalid)

**Common Mistakes to Avoid:**
- ❌ Trailing commas: `{"key": "value",}` (wrong)
- ✅ Correct: `{"key": "value"}` (right)
- ❌ Single quotes: `{'key': 'value'}` (wrong, JSON requires double quotes)
- ✅ Correct: `{"key": "value"}` (right)
- ❌ Missing quotes around keys: `{key: "value"}` (wrong)
- ✅ Correct: `{"key": "value"}` (right)

### Step 3: Configure Performance Parameters (Optional, Recommended for Production)

You can configure the following performance parameters in plugin settings to optimize concurrency and database connections for production environments:

**Performance Parameters:**
- `max_concurrent_memory_operations` - Maximum concurrent memory operations (default: 20)
  - Applies to all operations including search/add/get/get_all/update/delete/delete_all/history
  - Must be a positive integer (>= 1)
  - Invalid values (<= 0 or cannot be converted to integer) will use default value 20 with warning logs

**Concurrency Configuration Logic:**
- **`max_concurrent_memory_operations` configured**: Uses the configured value directly
- **Not configured**: Uses default value (20)
- **Invalid values** (cannot be converted to positive integers): Uses default values and logs a warning
- **Unset or empty values**: Uses default values and logs a warning

**Notes:**
- If performance parameters are not configured, default values will be used
- PGVector connection pool settings should be configured in the vector store JSON config (see Vector Store Configuration section below)
  - For basic pool sizing: `minconn` / `maxconn`
  - For advanced psycopg3 tuning: `pool_timeout` / `pool_max_waiting` / `pool_max_idle` / `pool_reconnect_timeout`
- Invalid or unset values trigger warning logs for better observability

## Configuration Examples

> **📚 Reference**: For detailed configuration options and supported providers, please refer to the [Mem0 Official Configuration Documentation](https://docs.mem0.ai/open-source/configuration).

### LLM Configuration (`local_llm_json_secret`)

**Azure OpenAI Structured Example (Recommended):**

> **Why recommended**: `azure_openai_structured` provides stricter schema handling and more reliable parsing for structured outputs. It aligns with the plugin's LLM compatibility improvements (reduced parsing errors and safer defaults for strict clients).

```json
{
  "provider": "azure_openai_structured",
  "config": {
    "model": "gpt-4.1-mini",
    "temperature": 0.1,
    "max_tokens": 2048,
    "azure_kwargs": {
      "azure_deployment": "gpt-4.1-mini",
      "api_version": "2024-12-01-preview",
      "azure_endpoint": "https://<your-resource>.openai.azure.com/",
      "api_key": "<your-azure-openai-api-key>",
      "default_headers": {
        "CustomHeader": "Mem0_Dify_Plugin"
      }
    }
  }
}
```

**Azure OpenAI Example (Standard / Legacy):**

```json
{
  "provider": "azure_openai",
  "config": {
    "model": "gpt-4o-mini",
    "temperature": 0.1,
    "max_tokens": 256,
    "azure_kwargs": {
      "azure_deployment": "gpt-4o-mini",
      "api_version": "2024-10-21",
      "azure_endpoint": "https://<your-resource>.openai.azure.com/",
      "api_key": "<your-azure-openai-api-key>",
      "default_headers": {
        "CustomHeader": "Mem0_Dify_Plugin"
      }
    }
  }
}
```

**OpenAI Example:**

```json
{
  "provider": "openai",
  "config": {
    "model": "gpt-4o-mini",
    "temperature": 0.1,
    "max_tokens": 256,
    "api_key": "<your-openai-api-key>"
  }
}
```

**Ollama Example (Local):**

```json
{
  "provider": "ollama",
  "config": {
    "model": "llama3.1:8b",
    "ollama_base_url": "http://localhost:11434",
    "temperature": 0.1,
    "max_tokens": 256
  }
}
```

### Embedder Configuration (`local_embedder_json_secret`)

**Azure OpenAI Example:**

```json
{
  "provider": "azure_openai",
  "config": {
    "model": "text-embedding-3-small",
    "azure_kwargs": {
      "api_version": "2024-10-21",
      "azure_deployment": "text-embedding-3-small",
    "azure_endpoint": "https://<your-resource>.openai.azure.com/",
    "api_key": "<your-azure-openai-api-key>",
      "default_headers": {
        "CustomHeader": "Mem0_Dify_Plugin"
      }
    }
  }
}
```

**OpenAI Example:**

```json
{
  "provider": "openai",
  "config": {
    "model": "text-embedding-3-small",
    "api_key": "<your-openai-api-key>"
  }
}
```

**HuggingFace Example (Local, requires sentence-transformers):**

```json
{
  "provider": "huggingface",
  "config": {
    "model": "multi-qa-MiniLM-L6-cos-v1"
  }
}
```

**Note**: HuggingFace embedding models are automatically cached locally after first download.

### Vector Store Configuration (`local_vector_db_json_secret`)

> **📚 Important**: For production environments, we strongly recommend using the psycopg3 connection pool with a `connection_string` to prevent TCP connection silent timeouts and connection pool memory leaks. See [Connection Stability & Resource Management](#connection-stability--resource-management) section for details.

**Recommended Configuration Method 1: Using Connection String + psycopg3 Connection Pool (Recommended for production)**

The plugin automatically creates a psycopg3 ConnectionPool when `connection_string` is provided. You can configure pool parameters to optimize connection management and prevent connection pool exhaustion:

```json
{
  "provider": "pgvector",
  "config": {
    "connection_string": "postgresql://<user>:<password>@<host>:<port>/<db>?sslmode=disable&keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=3&connect_timeout=5",
    "collection_name": "mem0",
    "embedding_model_dims": 1536,
    "minconn": 10,
    "maxconn": 20
  }
}
```

**Note**:
- Replace `<user>`, `<password>`, `<host>`, `<port>`, `<db>` with your actual database credentials
- TCP keepalive parameters are included in the connection string to prevent silent timeouts
- The plugin automatically creates a psycopg3 ConnectionPool with best practice defaults
- Individual parameters (user, password, host, etc.) are ignored when `connection_string` is provided

**Recommended Configuration Method 2: Using Individual Parameters with TCP Keepalive (Recommended for beginners)**

The plugin automatically adds TCP keepalive parameters to prevent connection silent timeouts:

```json
{
  "provider": "pgvector",
  "config": {
    "dbname": "<db>",
    "user": "<user>",
    "password": "<password>",
    "host": "<host>",
    "port": "<port>",
    "sslmode": "disable",
    "minconn": 10,
    "maxconn": 20
  }
}
```

**Note**: 
- Replace `<db>`, `<user>`, `<password>`, `<host>`, `<port>` with your actual database credentials
- The plugin will automatically build a `connection_string` from these parameters
- TCP keepalive parameters (`keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=3&connect_timeout=5`) are automatically added to the connection string
- Connection pool settings (`minconn`, `maxconn`) can be specified in the config
- If not specified, defaults to 10 (min) and 20 (max)

**Alternative Method: Using Connection String with TCP Keepalive (No pool tuning)**

If you already have a PostgreSQL connection string, you can use it directly with TCP keepalive parameters:

```json
{
  "provider": "pgvector",
  "config": {
    "connection_string": "postgresql://<user>:<password>@<host>:<port>/<db>?sslmode=disable&keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=3&connect_timeout=5",
    "minconn": 10,
    "maxconn": 20
  }
}
```

**Note**: 
- Replace `<user>`, `<password>`, `<host>`, `<port>`, `<db>` with your actual database credentials
- TCP keepalive parameters are included in the connection string to prevent silent timeouts
- If TCP keepalive parameters are not present in the connection string, the plugin will automatically add them
- The plugin automatically creates a psycopg3 ConnectionPool with best practice defaults
- Individual parameters (user, password, host, etc.) are ignored when `connection_string` is provided

**Option 3: Advanced psycopg3 pool tuning (Optional)**

If you need fine-grained control over pool sizing and lifecycle, you can add the optional psycopg3 pool parameters:

```json
{
  "provider": "pgvector",
  "config": {
    "connection_string": "postgresql://<user>:<password>@<host>:<port>/<db>?sslmode=disable&keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=3&connect_timeout=5",
    "collection_name": "mem0",
    "embedding_model_dims": 1536,
    "minconn": 10,
    "maxconn": 20,
    "pool_max_lifetime": 3600,
    "pool_max_idle": 600,
    "pool_timeout": 1,
    "pool_reconnect_timeout": 300,
    "pool_max_waiting": 20,
    "pool_open": true
  }
}
```

**Connection Pool Parameters (Optional):**
- `minconn` (int, default: 10): Minimum number of connections in the pool
- `maxconn` (int, default: 20): Maximum number of connections in the pool
- `pool_max_lifetime` (float, default: 3600.0): Connection maximum lifetime in seconds (1 hour)
- `pool_max_idle` (float, default: 600.0): Connection maximum idle time in seconds (10 minutes)
- `pool_timeout` (float, default: 30.0): Timeout in seconds to get a connection from the pool (recommend: 1-2s for read timeout=5s)
- `pool_reconnect_timeout` (float, default: 300.0): Reconnection timeout in seconds (5 minutes)
- `pool_max_waiting` (int, default: derived): Maximum number of requests waiting for a connection (set 0 for unlimited)
- `pool_open` (bool, default: true): Whether to open the pool immediately
- `pool_check` (callable/None, default: ConnectionPool.check_connection): Connection health check callback

**Note**:
- The plugin automatically creates a psycopg3 ConnectionPool when `connection_string` is provided
- TCP keepalive parameters are automatically added to connection strings if not present (when using individual parameters)
- If `psycopg[pool]` is not installed, the plugin falls back to using `connection_string` only
- Connection pool parameters are only used when creating a psycopg3 ConnectionPool
- **Recommendation for low-latency search (e.g., read timeout=5s)**:
  - Set `pool_timeout` to **1-2 seconds** to avoid spending most of the SLA waiting for a pooled connection.
  - Set `pool_max_waiting` to a **finite value** aligned with your overload threshold (e.g., `max_pending - maxconn`, where `max_pending = maxconn * MAX_PENDING_TASKS_MULTIPLIER`).
- Parameter priority: `connection_pool` > `connection_string` > individual parameters

**Option 4: Using Pre-configured Connection Pool (Most Advanced)**

If you have a pre-configured psycopg3 ConnectionPool object, you can pass it directly. This requires custom Python code and is not recommended for Dify plugin usage.

**Important Notes:**
- If using individual parameters, `user` is required
- Connection pool defaults (`minconn`, `maxconn`) should be specified in the vector store config JSON
- The plugin automatically sets `minconn` and `maxconn` (defaults: 10 and 20)
- **Production recommendation**: Set `maxconn` to match `max_concurrent_memory_operations` for optimal performance
- Parameter priority: `connection_pool` > `connection_string` > individual parameters
- If you provide both `connection_string` and individual parameters, `connection_string` takes precedence

### Graph Store Configuration (`local_graph_db_json_secret`) - Optional

**Neo4j Example:**

```json
{
  "provider": "neo4j",
  "config": {
    "url": "bolt://localhost:7687",
    "username": "neo4j",
    "password": "<your-neo4j-password>",
    "database": "neo4j"
  }
}
```

**For Neo4j Cloud (AuraDB):**

```json
{
  "provider": "neo4j",
  "config": {
    "url": "neo4j+s://<your-instance-id>.databases.neo4j.io",
    "username": "neo4j",
    "password": "<your-neo4j-password>"
  }
}
```

**Note**: Graph database is optional. If not configured, the plugin will work without graph memory features.

### Reranker Configuration (`local_reranker_json_secret`) - Optional

**Option 1: Cohere Reranker (API-based)**

```json
{
  "provider": "cohere",
  "config": {
    "model": "rerank-english-v3.0",
    "api_key": "<your-cohere-api-key>",
    "top_k": 5
  }
}
```

**Option 2: HuggingFace Reranker (Local model, requires manual installation)**

> ⚠️ **Important**: Starting from v0.1.7, `transformers` and `torch` are **not included** in default dependencies to keep installation fast (~22 seconds instead of ~2 minutes 25 seconds). If you want to use HuggingFace reranker, you must manually install these dependencies. See [README.md - Upgrade Guide](https://github.com/beersoccer/mem0_dify_plugin/blob/main/README.md#-upgrade-guide) for installation steps.

```json
{
  "provider": "huggingface",
  "config": {
    "model": "BAAI/bge-reranker-v2-m3",
    "device": "cpu",
    "top_k": 5,
    "batch_size": 32,
    "max_length": 512
  }
}
```

**Note**: 
- HuggingFace models are automatically cached locally after first download
- This only affects users who want to use **local reranker models**
- If you use **cloud-based rerankers** (e.g., Cohere API), no additional installation is needed

**Option 3: Sentence Transformer Reranker (Local model, requires sentence-transformers library)**

```json
{
  "provider": "sentence_transformer",
  "config": {
    "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "device": "cpu",
    "top_k": 5,
    "batch_size": 32,
    "show_progress_bar": false
  }
}
```

**Note**: Sentence Transformer models are automatically cached locally after first download. The `sentence-transformers` library is included in default dependencies, so no manual installation is needed.

### Log Level Configuration (`log_level`) - Optional

The `log_level` field allows you to control the verbosity of memory operation logs without redeploying the plugin:

- **INFO** (default): Standard logging level, shows important information and errors
- **DEBUG**: Detailed logging for troubleshooting, includes request IDs and operation details
- **WARNING**: Only shows warnings and errors
- **ERROR**: Only shows errors

**Important**: This setting can be changed online in the plugin credentials without requiring plugin redeployment. Changes take effect immediately for all subsequent operations.

### Memory Retention Controls (`memory_ttl_days`, `checkpoint_ttl_days`) - Optional

These two fields control maintenance behavior used by the `forget_memories` tool:

- `memory_ttl_days`:
  - Default is empty (disabled), meaning retention is decided only by the forgetting curve
  - If set to a positive integer, any memory older than this age is deleted even if recall quality is high
- `checkpoint_ttl_days`:
  - Default is `90`
  - Checkpoints older than this threshold are treated as expired and cleaned during `forget_memories`

Recommended practice:
- Keep `memory_ttl_days` empty first, then enable hard TTL only when you need strict upper bounds for compliance or storage control
- Run `forget_memories` weekly or bi-weekly with `dry_run=true` for preview before enabling actual deletion

## Quick Start: Testing Your Configuration

After completing the configuration steps above, test your setup:

1. **Create a Test Workflow**
   - Go to `Workflows` in Dify Dashboard
   - Create a new workflow
   - Add the `add_memory` tool to your workflow

2. **Test Add Memory**
   - Use parameters: `{"user": "I love Italian food", "assistant": "Great! I'll remember that.", "user_id": "test_user_001"}`
   - **Expected Result**:
     - In **async mode**: Returns `{"status": "ACCEPT", "results": [{"id": "", "memory": "", "event": "ACCEPT"}]}`
     - In **sync mode**: Returns the actual memory object with `id` and `memory` fields

3. **Test Search Memory**
   - Add the `search_memory` tool and use: `{"query": "What food does the user like?", "user_id": "test_user_001", "top_k": 5}`
   - **Expected Result**: Returns a list of memories with `id`, `memory`, `score` (0-1 similarity), `vector_distance`, `rerank_score` (if reranker enabled), `metadata`, and `timestamp` (if available)

4. **Verify Configuration**
   - If tools work correctly, your configuration is valid
   - If you encounter errors, check the [Troubleshooting](#troubleshooting) section

For detailed usage examples, see the [Usage Examples](#usage-examples) section below.

## Usage Examples

This section provides complete usage examples for all 12 tools. For a quick overview, see [README.md - Usage Examples](https://github.com/beersoccer/mem0_dify_plugin/blob/main/README.md#-usage-examples).

### Add Memory

In Dify workflow, add the `add_memory` tool and configure the following parameters:

![Add Memory Tool Configuration](images/add_memory.png)

**Required Parameters:**
- `user`: User message (e.g., "I love Italian food")
- `user_id`: User identifier (e.g., "alex")

**Optional Parameters:**
- `assistant`: Assistant response (e.g., "Great! I'll remember that.")
- `agent_id`: Agent identifier for scoping (recommended to use Dify's `app_id` for stable scoping)
- `run_id`: Workflow run ID for tracing (recommended to use Dify's `workflow_run_id`)
- `metadata`: Custom JSON metadata string (e.g., `{"type": "preference", "priority": "high"}`)

### Search Memory

In Dify workflow, add the `search_memory` tool and configure the following parameters:

![Search Memory Tool Configuration](images/search_memory.png)

**Required Parameters:**
- `query`: Search query (e.g., "What food does alex like?")
- `user_id`: User identifier (e.g., "alex")

**Optional Parameters:**
- `top_k`: Maximum number of results (default: 5)
- `filters`: JSON filter string for advanced filtering (e.g., `{"AND": [{"user_id": "alex"}, {"agent_id": "scheduler"}]}`)
- `agent_id`: Agent identifier for scoping
- `run_id`: Workflow run ID for tracing

**Search with Filters Example:**

![Search Memory with Filters](images/search_memory_filters.png)

Configure the `filters` parameter with a JSON string for advanced filtering:
- Example: `{"categories": {"contains": "diet"}}`

**Output score semantics:**
- `score`: unified 0-1 similarity (higher means more relevant)
- `vector_distance`: 0-1 distance (lower means more similar). For similarity-native backends, this is synthesized as `1 - score`
- `rerank_score`: reranker relevance score (0-1) when reranker is configured; this signal has highest priority for ranking/quality

### Get All Memories

In Dify workflow, add the `get_all_memories` tool and configure the following parameters:

![Get All Memories Tool Configuration](images/get_all_memories.png)

**Required Parameters:**
- `user_id`: User identifier (e.g., "alex")

**Optional Parameters:**
- `agent_id`: Agent identifier for scoping
- `limit`: Maximum number of memories to return (default: 100)
- `filters`: Advanced metadata filters as JSON string
- `run_id`: Workflow run ID for tracing

### Get Memory

In Dify workflow, add the `get_memory` tool and configure the following parameters:

![Get Memory Tool Configuration](images/get_memory.png)

**Required Parameters:**
- `memory_id`: Memory ID (UUID format, e.g., "memory-uuid-here")

**Optional Parameters:**
- `run_id`: Workflow run ID for tracing

### Update Memory

In Dify workflow, add the `update_memory` tool and configure the following parameters:

![Update Memory Tool Configuration](images/update_memory.png)

**Required Parameters:**
- `memory_id`: Memory ID (UUID format, e.g., "memory-uuid-here")
- `text`: New memory content (e.g., "I love Italian and French food")

**Optional Parameters:**
- `run_id`: Workflow run ID for tracing

### Delete Memory

In Dify workflow, add the `delete_memory` tool and configure the following parameters:

![Delete Memory Tool Configuration](images/delete_memory.png)

**Required Parameters:**
- `memory_id`: Memory ID (UUID format, e.g., "memory-uuid-here")

**Optional Parameters:**
- `run_id`: Workflow run ID for tracing

### Delete All Memories

In Dify workflow, add the `delete_all_memories` tool and configure the following parameters:

![Delete All Memories Tool Configuration](images/delete_all_memories.png)

**Required Parameters:**
- `user_id`: User identifier (e.g., "alex")

**Optional Parameters:**
- `agent_id`: Agent identifier for filtering
- `run_id`: Workflow run ID for tracing (recommended to use Dify's `workflow_run_id`)

**Note**: This operation will automatically reset the vector index (normal behavior).

### Get Memory History

In Dify workflow, add the `get_memory_history` tool and configure the following parameters:

![Get Memory History Tool Configuration](images/get_memory_history.png)

**Required Parameters:**
- `memory_id`: Memory ID (UUID format, e.g., "memory-uuid-here")

**Optional Parameters:**
- `run_id`: Workflow run ID for tracing

### Extract Long-Term Memory

In Dify workflow, add the `extract_long_term_memory` tool to automatically extract semantic, episodic, and procedural memories from your Dify conversation history.

#### Tool Configuration

![Extract Long-Term Memory Tool Configuration](images/extract_long_term_memory.png)

Use the parameters below to configure the extraction scope, limits, and Dify API access for each run.

**Mode Selection:**
- **Async Mode (async_mode=true, recommended)**: Best for production and batch jobs (10+ users). `user_ids` are processed in batches of size `EXTRACTION_MAX_CONCURRENT_USERS` with concurrent execution per batch (semaphore-limited), then batches run sequentially.
- **Sync Mode (async_mode=false)**: Best for testing, small batches, or debugging. Users are processed sequentially and block until completion. No timeout protection; **for production, use async_mode=true.**

**Required Parameters:**
- `user_ids`: User IDs to process (JSON array string, e.g., `["user1", "user2"]`)
- `app_id`: Dify App ID for memory isolation. Each app maintains separate memory space for the same user. This ensures memories are scoped to specific applications
- `dify_base_url`: Dify API base URL (standard format: `https://<your-dify-host>/v1`)
- `dify_api_key`: Dify API key with access to conversations/messages APIs

**Optional Parameters:**
- `run_id`: Unique identifier for tracking the entire memory operation call chain. Recommended to use Dify's workflow_run_id to link multiple memory operations in the same workflow. **Note**: This parameter is **only for tracing the call chain** and is **NOT used as a condition for memory layering or filtering**
- `days_back`: Number of days to look back for extracting conversation history (1-7, default: 1). For example, `days_back=2` extracts yesterday and the day before yesterday. The time range is automatically calculated as:
  - `start_time`: (today - days_back) at 00:00:00
  - `end_time`: today at 00:00:00
- `conversations_limit`: Maximum conversations to process per user per execution (10-500, default: 20). This limit applies to the total conversations within the configured `days_back` time range. This prevents malicious users from generating excessive conversations and consuming too much processing time. For 1-day cycle: light users ~5, normal users ~10-15, heavy users ~20-30. Adjust based on your execution cycle.
- `max_tokens_per_conversation`: Maximum tokens per conversation for memory extraction in thousands (1-200, default: 64K, same as EXTRACTION_DEFAULT_MAX_TOKENS). Token limiting is applied during data fetching to optimize network transfer. If a conversation exceeds this limit, pagination stops early and only the most recent messages are fetched. Adjust based on your LLM's context window (e.g., GPT-4: 128K, Claude 3.5: 200K).
- `time_budget`: Maximum time budget in minutes for the extraction task (suggested: 5-120 minutes, default: 60 minutes, same as EXTRACTION_TIME_BUDGET). The lock TTL is automatically calculated as 1.2 times the time budget (rounded up). No upper limit enforced - adjust based on your batch size and processing requirements. For large batch jobs processing 1000+ users, consider increasing this value.

**Example Configuration:**
```json
{
  "user_ids": "[\"alice\", \"bob\"]",
  "app_id": "my-chatbot-app",
  "run_id": "workflow_run_12345",
  "days_back": 1,
  "conversations_limit": 20,
  "max_tokens_per_conversation": 64,
  "time_budget": 60,
  "dify_base_url": "https://<your-dify-host>/v1",
  "dify_api_key": "<your-dify-api-key>"
}
```

**Important Notes:**
- The tool runs asynchronously and returns a `task_id` immediately. Use `check_extraction_status` to monitor task progress.
- The tool uses smart memory classification to reduce LLM calls by 33% (from 3 per conversation to 2: 1 classification + 1 extraction).
- Token-aware processing uses tiktoken for accurate token counting and applies limits during API pagination to optimize network transfer.

**Memory Isolation with app_id:**

The `app_id` parameter provides application-level memory isolation following Mem0 best practices:

1. **Write (Consolidation)**: Each app writes memories with its `app_id` in metadata
   - Ensures memories are tagged with their source application
   - Prevents memory pollution between different apps

2. **Read (Search/Get)**: `app_id` is OPTIONAL in search operations
   - **With app_id**: Returns only memories from that specific app
   - **Without app_id**: Returns all user memories across all apps (cross-app memory sharing)

3. **Checkpoint Isolation**: Each (user_id, app_id) pair has its own checkpoint
   - Different apps can independently process the same user's conversations
   - Prevents checkpoint conflicts between apps

**Use Cases:**
- **Isolated Apps**: Set `app_id` in both consolidation and search for strict app boundaries
- **Shared Knowledge**: Omit `app_id` in search to access user's memories across all apps
- **Multi-tenant**: Use different `app_id` values for different tenants/customers

**Time Range Examples:**

If today is January 25, 2026:
- `days_back=1`: Extracts [Jan 24 00:00:00, Jan 25 00:00:00) - yesterday only (default)
- `days_back=3`: Extracts [Jan 22 00:00:00, Jan 25 00:00:00) - last 3 days
- `days_back=7`: Extracts [Jan 18 00:00:00, Jan 25 00:00:00) - last week

**Output:**
The tool immediately returns a `task_id` for async task tracking:
```json
{
  "status": "ACCEPTED",
  "task_id": "extraction_task_12345",
  "message": "Extraction task accepted and queued for processing"
}
```

Use `check_extraction_status` with the returned `task_id` to query:
- `status`: SUCCESS/NOT_FOUND/ERROR
- `task_status`: running/completed/failed
- `progress`: Progress percentage (0.0-1.0)
- `user_count`: Total number of users to process
- `processed_users`: Number of users already processed
- `scanned_conversations`: Total conversations scanned
- `scanned_messages`: Total messages scanned
- `written_memories`: Total memories written (by type: semantic/episodic/procedural)
- `final_report`: Final processing report (if task completed)

**Memory Types:**
- **Semantic**: Long-term facts, preferences, and constraints that remain valid over time
- **Episodic**: Key events and experiences with temporal context
- **Procedural**: Reusable workflows, rules, and step-by-step procedures

**Features:**
- ✅ **Async Task Pattern**: Returns task_id immediately, processes in background (solves Dify 60s timeout limit)
- ✅ **Smart Classification**: Intelligently classifies each conversation to determine the most relevant memory type, reduces LLM calls by 33%
- ✅ **Token-Aware Processing**: Uses tiktoken for accurate token counting, applies limits during API pagination
- ✅ **Idempotent**: Safe to run multiple times (checkpoint-based)
- ✅ **Incremental**: Only processes new messages since last run
- ✅ **Robust**: Automatic retry on transient failures (3 attempts with exponential backoff)
- ✅ **Concurrent-safe**: Distributed lock prevents multiple tasks from processing the same user (supports up to 5 concurrent users)
- ✅ **Atomic checkpoint**: Saves progress atomically with automatic rollback on failure
- ✅ **Time Range Aware**: Enhanced checkpoint prevents data loss when time range expands backward

For detailed implementation and design, see the tool documentation in `tools/extract_long_term_memory.py`.

### Check Extraction Status

In Dify workflow, add the `check_extraction_status` tool to query the status and progress of an async extraction task. Use this tool after calling `extract_long_term_memory` to monitor task progress.

#### Tool Configuration

![Check Extraction Status Tool Configuration](images/check_extraction_status.png)

**Configuration Notes:**
- Provide the `task_id` returned by `extract_long_term_memory`
- No other parameters are required or supported for this tool

**Required Parameters:**
- `task_id`: The task ID returned by `extract_long_term_memory` tool when the task was accepted

**Example Configuration:**
```json
{
  "task_id": "extraction_task_12345"
}
```

**Output:**
The tool returns a structured JSON response with:
- `status`: SUCCESS/NOT_FOUND/ERROR
- `task_id`: The task ID being queried
- `run_id`: Unique execution identifier (if available)
- `task_status`: Current task status (running/completed/failed)
- `progress`: Progress percentage (0.0-1.0, rounded to 2 decimal places)
- `started_at`: Task start timestamp
- `updated_at`: Last update timestamp
- `range_start`: Conversation time range start (ISO8601)
- `range_end`: Conversation time range end (ISO8601)
- `time_range_display`: Human-readable time range (local time)
- `duration_seconds`: Task duration in seconds
- `duration_display`: Task duration display (mm:ss or hh:mm:ss)
- `user_count`: Total number of users to process
- `processed_users`: Number of users already processed
- `skipped_users`: Number of users skipped
- `scanned_conversations`: Total conversations scanned
- `scanned_messages`: Total messages scanned
- `processed_conversations`: Conversations that actually contained messages in range
- `processed_messages`: Messages within the time range
- `written_memories`: Total memories written
- `error`: Error message (if task failed)
- `final_report`: Final processing report (if task completed)

**Task Status Values:**
- `running`: Task is currently in progress
- `completed`: Task has finished successfully
- `failed`: Task encountered an error

**Usage Workflow:**
1. Call `extract_long_term_memory` tool to start an extraction task
2. The tool returns immediately with a `task_id`
3. Use `check_extraction_status` with the returned `task_id` to monitor progress
4. Poll periodically until `task_status` is `completed` or `failed`

**Example Response (Running Task):**
```json
{
  "status": "SUCCESS",
  "task_id": "extraction_task_12345",
  "run_id": "workflow_run_12345",
  "task_status": "running",
  "progress": 0.65,
  "started_at": "2026-01-25T10:00:00+08:00",
  "updated_at": "2026-01-25T10:05:00+08:00",
  "range_start": "2026-01-24T00:00:00+08:00",
  "range_end": "2026-01-25T00:00:00+08:00",
  "time_range_display": "2026-01-24 -> 2026-01-25",
  "duration_seconds": 300,
  "duration_display": "05:00",
  "user_count": 10,
  "processed_users": 6,
  "skipped_users": 1,
  "scanned_conversations": 45,
  "scanned_messages": 320,
  "processed_conversations": 38,
  "processed_messages": 285,
  "written_memories": 28
}
```

**Example Response (Completed Task):**
```json
{
  "status": "SUCCESS",
  "task_id": "extraction_task_12345",
  "run_id": "workflow_run_12345",
  "task_status": "completed",
  "progress": 1.0,
  "started_at": "2026-01-25T10:00:00+08:00",
  "updated_at": "2026-01-25T10:10:00+08:00",
  "range_start": "2026-01-24T00:00:00+08:00",
  "range_end": "2026-01-25T00:00:00+08:00",
  "time_range_display": "2026-01-24 -> 2026-01-25",
  "duration_seconds": 600,
  "duration_display": "10:00",
  "user_count": 10,
  "processed_users": 10,
  "skipped_users": 0,
  "scanned_conversations": 78,
  "scanned_messages": 542,
  "processed_conversations": 72,
  "processed_messages": 510,
  "written_memories": 45,
  "final_report": {
    "status": "SUCCESS",
    "summary": {
      "users_processed": 10,
      "memories_written": {
        "semantic": 20,
        "episodic": 15,
        "procedural": 10
      }
    }
  }
}
```

**Example Response (Task Not Found):**
```json
{
  "status": "NOT_FOUND",
  "task_id": "extraction_task_12345",
  "message": "Task extraction_task_12345 not found. It may have been completed and cleaned up, or never existed."
}
```

### Get User Checkpoint

Use `get_user_checkpoint` to inspect the extraction checkpoint for a user, optionally scoped by app.

**Required Parameters:**
- `user_id`: User identifier (e.g., "alex")

**Optional Parameters:**
- `app_id`: Dify App ID for checkpoint isolation (omit to fetch the latest user checkpoint across apps)

**Example Configuration:**
```json
{
  "user_id": "alex",
  "app_id": "my-chatbot-app"
}
```

**Output:**
- `status`: SUCCESS/NOT_FOUND/ERROR
- `checkpoint_id`: Internal checkpoint memory id (if found)
- `checkpoint`: Checkpoint payload (conversation map + resume cursor info)
- `conversations_count`: Number of conversations tracked in checkpoint

### Forget Memories

Use `forget_memories` to periodically clean stale user memories and old extraction checkpoints.

**Required Parameters:**
- `user_id`: User identifier (e.g., "alex")

**Optional Parameters:**
- `app_id`: App scope (maps to `agent_id`). Leave empty to process all apps for the user
- `dry_run`: If `true`, only returns what would be deleted and does not perform deletion

**Example Configuration (Preview):**
```json
{
  "user_id": "alex",
  "app_id": "my-chatbot-app",
  "dry_run": true
}
```

**Output:**
- `deleted_count`: Number of memories deleted (or would delete in dry-run)
- `retained_count`: Number of memories retained
- `checkpoints_cleaned`: Number of stale checkpoints cleaned
- `dry_run`: Whether execution is preview mode
- `would_delete`: Detailed candidate list (only when `dry_run=true`)

**Important Notes:**
- The `task_id` is returned by `extract_long_term_memory` when the task is accepted
- Tasks may be cleaned up after completion, so querying a completed task may return `NOT_FOUND`
- Use this tool in a polling loop to monitor long-running extraction tasks
- The `progress` field provides a percentage (0.0-1.0) of task completion
- If the task failed, check the `error` field for details

**Important Notes:**
- `user_id` is **required** for `add_memory`, `search_memory`, and `get_all_memories`
- `filters` and `metadata` must be valid JSON strings when provided (the client will automatically parse them)
- `top_k` defaults to 5 if not specified for `search_memory`
- All tool parameters are case-sensitive
- **`run_id` Parameter** (optional): Recommended to use Dify's `workflow_run_id` to link multiple memory operations in the same workflow. **Important**: This parameter is only used for request tracing and logging; it is NOT used as a condition for memory layering or filtering
- **`agent_id` Parameter**: When using `agent_id` in Dify workflows, you should use the **Dify application's `app_id`** (not `workflow_id`). This is because `workflow_id` changes every time you publish a workflow, while `app_id` remains stable and allows you to scope memories consistently across workflow versions
- **`app_id` Parameter** (for `extract_long_term_memory`): Required for memory isolation. Each app maintains separate memory space for the same user. This ensures memories are scoped to specific applications
- **`memory_ttl_days` / `checkpoint_ttl_days`**: Optional maintenance controls used by `forget_memories`; leave `memory_ttl_days` empty to rely on forgetting curve only
- **`days_back` Parameter** (for `extract_long_term_memory`): Number of days to look back for extracting conversation history (1-7, default: 1). For example, `days_back=2` extracts yesterday and the day before yesterday. The time range is automatically calculated as `start_time = (today - days_back) 00:00:00` and `end_time = today 00:00:00`
- For runtime behavior details (async vs sync mode), see [Runtime Behavior](#runtime-behavior) section

## Runtime Behavior

### Async Mode (`async_mode=true`, default)

- **Write Operations** (Add/Update/Delete/Delete_All):
  - Non-blocking, return ACCEPT status immediately
  - Operations are performed in the background
  - Best for production environments with high traffic

- **Read Operations** (Search/Get/Get_All/History):
  - Wait for results and return actual data
  - **Timeout protection**: All async read operations have timeout mechanisms (default: 5s, configurable)
  - On timeout or error: logs event, cancels background tasks, returns default/empty results

### Sync Mode (`async_mode=false`)

- **All Operations**:
  - Block until completion
  - You can see the actual results of each operation immediately
  - Best for testing and debugging
  - **Note**: No timeout protection. If timeout protection is needed, use `async_mode=true`

### Service Degradation

When operations timeout or encounter errors:
- The event is logged with full exception details
- Background tasks are cancelled to prevent resource leaks (async mode only)
- Default/empty results are returned (empty list `[]` for Search/Get_All/History, `None` for Get)
- Dify workflow continues execution without interruption

### Configurable Timeout (v0.1.2+)

All read operations (Search/Get/Get_All/History) support user-configurable timeout values:
- Timeout parameters are available in the Dify plugin configuration interface as manual input fields
- If not specified, tools use default values (5 seconds for all read operations)
- Invalid timeout values are caught and logged with a warning, defaulting to constants

### Default Timeout Values

- **Read Operations** (Search/Get/Get_All/History): 5 seconds (unified timeout, configurable)
- **Write Operations** (Add/Update/Delete): 15 seconds (configurable)
- `MAX_REQUEST_TIMEOUT`: 60 seconds

**Note**: Sync mode has no timeout protection (blocking calls). If timeout protection is needed, use `async_mode=true`

## Connection Stability & Resource Management

### TCP Connection Silent Timeout Prevention

**Problem**: In long-running processes, TCP connections to LLM services, embedding services, and vector databases (especially pgvector) can be silently closed by network infrastructure (firewalls, load balancers, NAT devices) due to inactivity. This causes connection failures and service interruptions.

**Solution**: The plugin implements a comprehensive connection keep-alive mechanism:

1. **Automatic Connection Keep-Alive**:
   - `ConnectionKeepAlive` class periodically sends lightweight heartbeat requests to all underlying services (LLM, embedding, vector store)
   - Default heartbeat interval: 120 seconds (configurable via `heartbeat_interval` credential, minimum: 30 seconds)
   - Heartbeat requests are non-blocking and run in a separate daemon thread
   - Heartbeat failures are logged but do not interrupt service (non-critical)

2. **PGVector TCP Keepalive Parameters**:
   - The plugin automatically adds TCP keepalive parameters to PostgreSQL connection strings if not present:
     - `keepalives=1`: Enable TCP keepalive
     - `keepalives_idle=30`: Start keepalive after 30 seconds of inactivity
     - `keepalives_interval=10`: Send keepalive probes every 10 seconds
     - `keepalives_count=3`: Maximum number of keepalive probes before considering connection dead
     - `connect_timeout=5`: Connection timeout in seconds
   - These parameters prevent TCP connections from being silently closed by network infrastructure
   - Applied to both `connection_string` and individual parameter configurations

**Configuration**: 
- Connection keep-alive is automatically enabled (no configuration required)
- To adjust heartbeat interval, set `heartbeat_interval` in plugin credentials (default: 120 seconds, minimum: 30 seconds)

### Connection Pool Memory Leak Prevention

**Problem**: In long-running processes, connection pools (especially pgvector ConnectionPool) can accumulate connections that are never properly closed, leading to memory leaks and connection pool exhaustion.

**Solution**: The plugin implements explicit resource cleanup:

1. **Automatic Resource Cleanup**:
   - `AsyncMem0Client.aclose()` method explicitly closes all critical resources (connection pools, database connections, graph store connections)
   - Automatic cleanup of old client instances when configuration changes
   - Resource cleanup runs asynchronously to avoid blocking operations

2. **Connection Pool Lifecycle Management**:
   - Connection pools are properly closed when client instances are replaced
   - Old connection pools are explicitly closed before creating new ones
   - Prevents connection pool exhaustion in high-concurrency scenarios

**Configuration**: 
- Resource cleanup is automatically handled (no manual intervention required)
- Connection pools are automatically managed throughout the plugin lifecycle

### Recommended PGVector Configuration

For production environments, we strongly recommend using one of the configuration methods described in the [Vector Store Configuration](#vector-store-configuration-local_vector_db_json_secret) section:

1. **Method 1 (Connection String + psycopg3 Pool)**: Recommended for production stability and pool lifecycle management
2. **Method 2 (Individual Parameters)**: Automatically adds TCP keepalive parameters

Both methods ensure:
- TCP connections remain alive during idle periods
- Connection pools are properly managed
- Memory leaks are prevented
- System stability in long-running processes

## Important Operational Notes

### Delete All Memories Operation

> **Note**: When using the `delete_all_memories` tool to delete memories in batch, Mem0 will automatically reset the vector index to optimize performance and reclaim space. You may see a log message like `WARNING: Resetting index mem0...` during this operation. This is a **normal and expected behavior** — the warning indicates that the vector store table is being dropped and recreated to ensure optimal query performance after bulk deletion. No action is needed from your side.

### PGVector Configuration

See the [Vector Store Configuration](#vector-store-configuration-local_vector_db_json_secret) section above for detailed configuration options. Key points:

- **Connection Pool**: Automatically configured with min=10, max=40 connections (configurable via performance parameters)
- **TCP Keepalive**: Automatically added to prevent connection silent timeouts
- **Parameter Priority**: `connection_pool` > `connection_string` > individual parameters
- **Automatic Processing**: The plugin automatically builds `connection_string` from individual parameters and sets connection pool settings

## Upgrade Guide

> 📖 **For complete upgrade instructions, see [README.md - Upgrade Guide](https://github.com/beersoccer/mem0_dify_plugin/blob/main/README.md#-upgrade-guide)**

### ⚠️ CRITICAL: Configuration Incompatibility

**🔴 IMPORTANT**: The plugin has undergone **breaking changes** in credentials configuration. You **MUST** delete old credentials before upgrading.

**Key Changes:**
- **Field Type & Names**: Changed from `*_json` (text-input) to `*_secret` (secret-input) fields
- **Removed Fields**: `pgvector_min_connections` and `pgvector_max_connections` credential fields removed (v0.1.9+)
  - **Migration**: Configure connection pool size in `local_vector_db_json_secret` JSON using `minconn` and `maxconn` (see [Vector Store Configuration](#vector-store-configuration-local_vector_db_json_secret))

**Required Steps:**
1. **Backup** your configuration values
2. **Delete** old credentials in Dify UI (`Settings` → `Plugins` → `mem0ai` → `Delete Credentials`)
3. **Upgrade** the plugin
4. **Reconfigure** using new `*_secret` fields and migrate pgvector connection pool settings to JSON config

**⚠️ If you skip deleting credentials**: Plugin will fail to start or show "Internal Server Error".

For detailed upgrade instructions and field mapping, see [README.md - Upgrade Guide](https://github.com/beersoccer/mem0_dify_plugin/blob/main/README.md#-upgrade-guide).

## Troubleshooting

### Installation Issues

**Problem**: Upload failed
- **Solution**: 
  - Ensure the plugin package is not corrupted
  - Try re-downloading or rebuilding the package
  - Check file size and format
  - Verify network connection

**Problem**: Plugin not appearing in Dify
- **Solution**: 
  - Check that the plugin was successfully installed
  - Try refreshing the page
  - Check Dify logs for installation errors
  - Try reinstalling the plugin

**Problem**: "Plugin already installed" error when running `python -m main`
- **Solution**: 
  - This is a Dify plugin management issue, not a code error
  - Uninstall the plugin from Dify UI (Settings → Plugins → Uninstall)
  - Or use CLI: `dify plugin uninstall mem0ai`
  - Then re-run `python -m main`

### Configuration Issues

**Problem**: Tools cannot be used
- **Solution**:
  1. Verify that operation mode (`async_mode`) is selected (default: `true`)
  2. Ensure all required fields are filled: `local_llm_json_secret`, `local_embedder_json_secret`, `local_vector_db_json_secret`
  3. **If upgrading from older versions**: Delete old credentials and reconfigure using the new `*_secret` fields (legacy `*_json` fields are no longer supported)
  4. Check that JSON structure is correct: `{ "provider": "...", "config": { ... } }`
  5. Validate JSON syntax (no trailing commas, proper quotes, matching braces)
  6. Validate all API keys and database connection information
  7. Check plugin logs in Dify for specific error messages (set `log_level` to DEBUG for detailed troubleshooting)

**Problem**: JSON parsing errors
- **Solution**:
  - Ensure JSON is valid (use an online JSON validator)
  - Remove trailing commas
  - Ensure all strings are properly quoted
  - Check for special characters that need escaping
  - Copy examples exactly and only replace placeholder values

**Problem**: Filter JSON errors
- **Solution**:
  - Ensure `filters` parameter is a valid JSON string
  - Use an online JSON validator to check format
  - Refer to examples in [CHANGELOG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CHANGELOG.md)

**Problem**: HTTP timeout
- **Solution**:
  - Check vector database (e.g., pgvector) or graph database (Neo4j) connection configuration
  - Verify credentials, address, and port are correct
  - Check network connectivity

### Performance Issues

**Problem**: Slow operations
- **Solution**:
  - Increase `max_concurrent_memory_operations` as needed
  - For pgvector: Set `maxconn` in vector store config JSON to match `max_concurrent_memory_operations`
  - Check database performance and connection pool settings
  - See [Performance Parameters](#step-3-configure-performance-parameters-optional-recommended-for-production) and [Vector Store Configuration](#vector-store-configuration-local_vector_db_json_secret) for configuration details

**Problem**: CPU usage at 99% or "Background task queue overloaded" warnings
- **Cause**: Write operations (add/update/delete) are accumulating faster than they can complete
- **Solution**:
  - Check logs for pending task counts
  - Reduce request frequency or increase `max_concurrent_memory_operations`
  - Consider using faster models (cloud APIs instead of self-hosted models)
  - Monitor for "rejecting new memory operation" messages indicating system overload

**Problem**: Warning logs about invalid concurrency configuration values
- **Cause**: Invalid or unset concurrency parameter values (cannot be converted to positive integers)
- **Solution**:
  - Check logs for specific warning messages indicating which parameter has an invalid value
  - Ensure concurrency parameters are positive integers (minimum: 1, default: 20)
  - Configure `max_concurrent_memory_operations` to control concurrency for all operations
  - See [Performance Parameters](#step-3-configure-performance-parameters-optional-recommended-for-production) for detailed configuration logic

**Problem**: Upgrade from v0.1.3 causes Internal Server Error
- **Solution**: See [Upgrade Guide](#upgrade-guide) for detailed instructions. In summary: Always upgrade to v0.1.7+ for seamless compatibility (no action required).

**Problem**: Configuration fields not appearing or configuration errors after upgrade
- **Solution**: 
  1. Delete old credentials in Dify UI (Settings → Plugins → mem0ai → Delete Credentials)
  2. Reconfigure using the new `*_secret` fields (e.g., `local_llm_json_secret`, `local_embedder_json_secret`)
  3. Legacy `*_json` fields are no longer shown in the UI and should not be used

## Additional Resources

- **Privacy Policy**: See [PRIVACY.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/PRIVACY.md) for details about data handling in self-hosted mode
- **Changelog**: See [CHANGELOG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CHANGELOG.md) for detailed version history
- **Main README**: See [README.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/README.md) for project overview and features
- **Mem0 Official Docs**: https://docs.mem0.ai
- **Dify Plugin Docs**: https://docs.dify.ai/docs/plugins

