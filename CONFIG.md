# Mem0 Dify Plugin - Configuration Guide

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

After installation, you should see the `mem0ai` plugin in your plugins list. The plugin provides 8 tools:
- `add_memory`, `search_memory`, `get_all_memories`, `get_memory`
- `update_memory`, `delete_memory`, `delete_all_memories`, `get_memory_history`

## Configuration Steps

### Step 1: Choose Operation Mode

First, select the operation mode in plugin credentials:

- **Async Mode** (`async_mode=true`, default)
  - Recommended for production environments
  - Supports high concurrency
  - Write operations (Add/Update/Delete/Delete_All): non-blocking, return ACCEPT status immediately
  - Read operations (Search/Get/Get_All/History): wait for results with timeout protection (default: 30s)

- **Sync Mode** (`async_mode=false`)
  - Recommended for testing environments
  - All operations block until completion
  - You can see the actual results of each memory operation immediately
  - **Note**: Sync mode has no timeout protection. If timeout protection is needed, use `async_mode=true`

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
- `max_concurrent_memory_operations` - Maximum concurrent memory operations (default: 40)
  - Applies to all operations including search/add/get/get_all/update/delete/delete_all/history
  - Must be a positive integer (>= 1)
  - Invalid values (<= 0 or cannot be converted to integer) will use default value 40 with warning logs

**Concurrency Configuration Logic:**
- **`max_concurrent_memory_operations` configured**: Uses the configured value directly
- **Not configured**: Uses default value (40)
- **Invalid values** (cannot be converted to positive integers): Uses default values and logs a warning
- **Unset or empty values**: Uses default values and logs a warning

**Notes:**
- If performance parameters are not configured, default values will be used
- PGVector connection pool settings (`min_connections`, `max_connections`) should be configured in the vector store JSON config (see Vector Store Configuration section below)
- Invalid or unset values trigger warning logs for better observability

## Configuration Examples

> **📚 Reference**: For detailed configuration options and supported providers, please refer to the [Mem0 Official Configuration Documentation](https://docs.mem0.ai/open-source/configuration).

### LLM Configuration (`local_llm_json_secret`)

**Azure OpenAI Example:**

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
      "azure_endpoint": "https://your-resource.openai.azure.com",
      "api_key": "your-azure-openai-api-key",
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
    "api_key": "your-openai-api-key"
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
      "azure_endpoint": "https://your-resource.openai.azure.com",
      "api_key": "your-azure-openai-api-key",
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
    "api_key": "your-openai-api-key"
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

> **📚 Important**: For production environments, we strongly recommend using one of the two recommended configuration methods below to prevent TCP connection silent timeouts and connection pool memory leaks. See [Connection Stability & Resource Management](#connection-stability--resource-management) section for details.

**Recommended Configuration Method 1: Using Individual Parameters with TCP Keepalive (Recommended for beginners)**

The plugin automatically adds TCP keepalive parameters to prevent connection silent timeouts:

```json
{
  "provider": "pgvector",
  "config": {
    "dbname": "mem0_vectors",
    "user": "postgres",
    "password": "your-password",
    "host": "localhost",
    "port": "5432",
    "sslmode": "disable",
    "minconn": 10,
    "maxconn": 40
  }
}
```

**Note**: 
- Replace `mem0_vectors`, `postgres`, `your-password`, `localhost`, `5432` with your actual database credentials
- The plugin will automatically build a `connection_string` from these parameters
- TCP keepalive parameters (`keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=3&connect_timeout=5`) are automatically added to the connection string
- Connection pool settings (`minconn`, `maxconn`) can be specified in the config
- If not specified, defaults to 10 (min) and 40 (max)

**Recommended Configuration Method 2: Using Connection String with TCP Keepalive (Recommended for production)**

If you already have a PostgreSQL connection string, you can use it directly with TCP keepalive parameters:

```json
{
  "provider": "pgvector",
  "config": {
    "connection_string": "postgresql://postgres:your-password@localhost:5432/mem0_vectors?sslmode=disable&keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=3&connect_timeout=5",
    "minconn": 10,
    "maxconn": 40
  }
}
```

**Note**: 
- Replace `postgres`, `your-password`, `localhost`, `5432`, `mem0_vectors` with your actual database credentials
- TCP keepalive parameters are included in the connection string to prevent silent timeouts
- If TCP keepalive parameters are not present in the connection string, the plugin will automatically add them
- The plugin automatically creates a psycopg3 ConnectionPool with best practice defaults
- Individual parameters (user, password, host, etc.) are ignored when `connection_string` is provided

**Option 3: Using Connection String with psycopg3 Connection Pool (Recommended for Production)**

The plugin automatically creates a psycopg3 ConnectionPool when `connection_string` is provided. You can configure pool parameters to optimize connection management and prevent connection pool exhaustion:

```json
{
  "provider": "pgvector",
  "config": {
    "connection_string": "postgresql://postgres:your-password@localhost:5432/mem0_vectors?sslmode=disable&keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=3&connect_timeout=5",
    "collection_name": "mem0",
    "embedding_model_dims": 1536,
    "min_connections": 10,
    "max_connections": 40,
    "pool_min_size": 10,
    "pool_max_size": 40,
    "pool_max_lifetime": 3600,
    "pool_max_idle": 600,
    "pool_timeout": 30,
    "pool_reconnect_timeout": 300,
    "pool_max_waiting": 0,
    "pool_open": true
  }
}
```

**Connection Pool Parameters (Optional, with best practice defaults):**
- `min_connections` (int, default: 10): Default minimum connections (used when `pool_min_size` not provided)
- `max_connections` (int, default: 40): Default maximum connections (used when `pool_max_size` not provided)
- `pool_min_size` (int, default: uses `min_connections` or 10): Minimum number of connections in the pool
- `pool_max_size` (int, default: uses `max_connections` or 40): Maximum number of connections in the pool
- `pool_max_lifetime` (float, default: 3600.0): Connection maximum lifetime in seconds (1 hour)
- `pool_max_idle` (float, default: 600.0): Connection maximum idle time in seconds (10 minutes)
- `pool_timeout` (float, default: 30.0): Timeout in seconds to get a connection from the pool
- `pool_reconnect_timeout` (float, default: 300.0): Reconnection timeout in seconds (5 minutes)
- `pool_max_waiting` (int, default: 0): Maximum number of requests waiting for a connection (0 = unlimited)
- `pool_open` (bool, default: true): Whether to open the pool immediately
- `pool_check` (callable/None, default: ConnectionPool.check_connection): Connection health check callback

**Note**: 
- The plugin automatically creates a psycopg3 ConnectionPool when `connection_string` is provided
- TCP keepalive parameters are automatically added to connection strings if not present (when using individual parameters)
- If `psycopg[pool]` is not installed, the plugin falls back to using `connection_string` only
- Connection pool parameters are only used when creating a psycopg3 ConnectionPool
- Parameter priority: `connection_pool` > `connection_string` > individual parameters

**Option 4: Using Pre-configured Connection Pool (Most Advanced)**

If you have a pre-configured psycopg3 ConnectionPool object, you can pass it directly. This requires custom Python code and is not recommended for Dify plugin usage.

**Important Notes:**
- If using individual parameters, `user` is required
- Connection pool defaults (`min_connections`, `max_connections`) should be specified in the vector store config JSON
- The plugin automatically sets `minconn` and `maxconn` based on `min_connections`/`max_connections` in config (or defaults: 10 and 40)
- **Production recommendation**: Set `max_connections` to match `max_concurrent_memory_operations` for optimal performance
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
    "password": "your-neo4j-password",
    "database": "neo4j"
  }
}
```

**For Neo4j Cloud (AuraDB):**

```json
{
  "provider": "neo4j",
  "config": {
    "url": "neo4j+s://your-instance-id.databases.neo4j.io",
    "username": "neo4j",
    "password": "your-neo4j-password"
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
    "api_key": "your-cohere-api-key",
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
   - **Expected Result**: Returns a list of memories with `id`, `memory`, `score`, `metadata`, and `timestamp` (if available)

4. **Verify Configuration**
   - If tools work correctly, your configuration is valid
   - If you encounter errors, check the [Troubleshooting](#troubleshooting) section

For detailed usage examples, see the [Usage Examples](#usage-examples) section below.

## Usage Examples

This section provides complete usage examples for all 8 tools. For a quick overview, see [README.md - Usage Examples](https://github.com/beersoccer/mem0_dify_plugin/blob/main/README.md#-usage-examples).

### Add Memory

In Dify workflow, add the `add_memory` tool and configure the following parameters:

![Add Memory Tool Configuration](images/add_memory_example.png)

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

![Search Memory Tool Configuration](images/search_memory_example.png)

**Required Parameters:**
- `query`: Search query (e.g., "What food does alex like?")
- `user_id`: User identifier (e.g., "alex")

**Optional Parameters:**
- `top_k`: Maximum number of results (default: 5)
- `filters`: JSON filter string for advanced filtering (e.g., `{"AND": [{"user_id": "alex"}, {"agent_id": "scheduler"}]}`)
- `agent_id`: Agent identifier for scoping
- `run_id`: Workflow run ID for tracing

**Search with Filters Example:**

![Search Memory with Filters](images/search_memory_filters_example.png)

Configure the `filters` parameter with a JSON string for advanced filtering:
- Example: `{"categories": {"contains": "diet"}}`

### Get All Memories

In Dify workflow, add the `get_all_memories` tool and configure the following parameters:

![Get All Memories Tool Configuration](images/get_all_memories_example.png)

**Required Parameters:**
- `user_id`: User identifier (e.g., "alex")

**Optional Parameters:**
- `agent_id`: Agent identifier for scoping
- `limit`: Maximum number of memories to return (default: 100)
- `filters`: Advanced metadata filters as JSON string
- `run_id`: Workflow run ID for tracing

### Get Memory

In Dify workflow, add the `get_memory` tool and configure the following parameters:

![Get Memory Tool Configuration](images/get_memory_example.png)

**Required Parameters:**
- `memory_id`: Memory ID (UUID format, e.g., "memory-uuid-here")

**Optional Parameters:**
- `run_id`: Workflow run ID for tracing

### Update Memory

In Dify workflow, add the `update_memory` tool and configure the following parameters:

![Update Memory Tool Configuration](images/update_memory_example.png)

**Required Parameters:**
- `memory_id`: Memory ID (UUID format, e.g., "memory-uuid-here")
- `text`: New memory content (e.g., "I love Italian and French food")

**Optional Parameters:**
- `run_id`: Workflow run ID for tracing

### Delete Memory

In Dify workflow, add the `delete_memory` tool and configure the following parameters:

![Delete Memory Tool Configuration](images/delete_memory_example.png)

**Required Parameters:**
- `memory_id`: Memory ID (UUID format, e.g., "memory-uuid-here")

**Optional Parameters:**
- `run_id`: Workflow run ID for tracing

### Delete All Memories

In Dify workflow, add the `delete_all_memories` tool and configure the following parameters:

![Delete All Memories Tool Configuration](images/delete_all_memories_example.png)

**Required Parameters:**
- `user_id`: User identifier (e.g., "alex")

**Optional Parameters:**
- `agent_id`: Agent identifier for filtering
- `run_id`: Workflow run ID for tracing (recommended to use Dify's `workflow_run_id`)

**Note**: This operation will automatically reset the vector index (normal behavior).

### Get Memory History

In Dify workflow, add the `get_memory_history` tool and configure the following parameters:

![Get Memory History Tool Configuration](images/get_memory_history_example.png)

**Required Parameters:**
- `memory_id`: Memory ID (UUID format, e.g., "memory-uuid-here")

**Optional Parameters:**
- `run_id`: Workflow run ID for tracing

**Important Notes:**
- `user_id` is **required** for `add_memory`, `search_memory`, and `get_all_memories`
- `filters` and `metadata` must be valid JSON strings when provided (the client will automatically parse them)
- `top_k` defaults to 5 if not specified for `search_memory`
- All tool parameters are case-sensitive
- **`run_id` Parameter** (optional): Recommended to use Dify's `workflow_run_id` to link multiple memory operations in the same workflow. **Important**: This parameter is only used for request tracing and logging; it is NOT used as a condition for memory layering or filtering
- **`agent_id` Parameter**: When using `agent_id` in Dify workflows, you should use the **Dify application's `app_id`** (not `workflow_id`). This is because `workflow_id` changes every time you publish a workflow, while `app_id` remains stable and allows you to scope memories consistently across workflow versions
- For runtime behavior details (async vs sync mode), see [Runtime Behavior](#runtime-behavior) section

## Runtime Behavior

### Async Mode (`async_mode=true`, default)

- **Write Operations** (Add/Update/Delete/Delete_All):
  - Non-blocking, return ACCEPT status immediately
  - Operations are performed in the background
  - Best for production environments with high traffic

- **Read Operations** (Search/Get/Get_All/History):
  - Wait for results and return actual data
  - **Timeout protection**: All async read operations have timeout mechanisms (default: 30s, configurable)
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
- If not specified, tools use default values (30 seconds for all read operations)
- Invalid timeout values are caught and logged with a warning, defaulting to constants

### Default Timeout Values

- **Read Operations** (Search/Get/Get_All/History): 15 seconds (unified timeout, configurable)
- **Write Operations** (Add/Update/Delete): 30 seconds (configurable)
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

For production environments, we strongly recommend using one of the two configuration methods described in the [Vector Store Configuration](#vector-store-configuration-local_vector_db_json_secret) section:

1. **Method 1 (Individual Parameters)**: Automatically adds TCP keepalive parameters
2. **Method 2 (Connection String)**: Includes TCP keepalive parameters in connection string

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
  - For pgvector: Set `max_connections` in vector store config JSON to match `max_concurrent_memory_operations`
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
  - Ensure concurrency parameters are positive integers (minimum: 1, default: 40)
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

