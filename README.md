# Mem0 Dify Plugin v0.1.9

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Dify Plugin](https://img.shields.io/badge/Dify-Plugin-blue)](https://dify.ai)
[![Mem0 AI](https://img.shields.io/badge/Mem0-AI-green)](https://mem0.ai)

A comprehensive Dify plugin that integrates [Mem0 AI](https://mem0.ai)'s intelligent memory layer, providing **self-hosted mode** tools with a unified client for self-hosted setups.

---

## 🌟 Features

### Complete Memory Management (8 Tools)
- ✅ **Add Memory** - Intelligently add, update, or delete memories based on user interactions
- ✅ **Search Memory** - Search with advanced filters (AND/OR logic) and top_k limiting, returns timestamp field (most recent created_at/updated_at)
- ✅ **Get All Memories** - List memories with pagination
- ✅ **Get Memory** - Fetch specific memory details
- ✅ **Update Memory** - Modify existing memories
- ✅ **Delete Memory** - Remove individual memories
- ✅ **Delete All Memories** - Batch delete with filters
- ✅ **Get Memory History** - View change history

### Long-term Memory Consolidation (New)
- ✅ **Consolidate Long Term Memory** - Incrementally scan Dify conversation history for specified users and consolidate long-term memories into Mem0 (semantic/episodic/procedural)

### Advanced Capabilities
- 🖥️ **Self-Hosted Mode** - Run with Local Mem0 (JSON-based config)
- 🧱 **Simplified Local Config** - 5 JSON blocks: LLM, Embedder, Vector DB, Graph DB (optional), Reranker (optional)
- 🎯 **Entity Scoping** - user_id (required for add), agent_id, run_id
- 📊 **Metadata System** - Custom JSON metadata for rich context
- 🔍 **Filters** - JSON filters supported by Mem0 self-hosted mode
- 🌍 **Internationalized** - 中英双语 (Chinese/English)
- ⚙️ **Async Mode Switch** - `async_mode` is enabled by default; Write ops (Add/Update/Delete) are non-blocking in async mode, Read ops (Search/Get/History) always wait; in sync mode all operations block until completion.

### What's New (v0.1.9)
- **Connection Stability & Resource Management**: Resolved critical production issues
  - **TCP Connection Silent Timeout Prevention**: Implemented connection keep-alive mechanism
    - Automatic periodic heartbeat requests to LLM, embedding, and vector store services
    - Prevents TCP connections from being silently closed by network infrastructure
    - Configurable heartbeat interval (default: 120 seconds, minimum: 30 seconds)
  - **Connection Pool Memory Leak Prevention**: Implemented explicit resource cleanup
    - Automatic cleanup of connection pools when client configuration changes
    - Prevents memory leaks and connection pool exhaustion in long-running processes
    - Proper lifecycle management for all database connections
  - **PGVector Configuration Enhancement**: Improved connection pool management
    - Automatic addition of TCP keepalive parameters to connection strings
    - Two recommended configuration methods for production environments
    - See [CONFIG.md](CONFIG.md#connection-stability--resource-management) for details

### Previous Updates (v0.1.8)
- **Dynamic Log Level Configuration**: Added runtime log level control without redeployment
  - New `log_level` credential field (INFO/DEBUG/WARNING/ERROR) for online adjustment
  - Thread-safe log level updates apply to all existing loggers immediately
  - Default log level is INFO; can be changed to DEBUG for detailed troubleshooting
- **Timeout Optimization**: Unified and optimized operation timeouts for better performance
  - Read operations (Search/Get/Get_All/History): unified timeout reduced to 15 seconds (from 30s)
  - Write operations (Add/Update/Delete): timeout set to 30 seconds for persistence operations
  - Improved responsiveness while maintaining reliability
- **Request Tracing Enhancement**: Added `run_id` parameter to all tools for call chain tracking
  - Recommended to use Dify's `workflow_run_id` to link multiple memory operations in the same workflow
  - **Important**: `run_id` is only used for request tracing and logging; it is NOT used as a condition for memory layering or filtering
  - All tools now include request ID in logs for better traceability
- **Configuration Cleanup**: Removed deprecated configuration fields from UI
  - Legacy `*_json` fields (e.g., `local_llm_json`) are no longer shown in configuration UI
  - Only `*_secret` fields (e.g., `local_llm_json_secret`) are available for new installations
  - **Important**: If you encounter configuration issues after upgrade, please delete old credentials and reconfigure using the new `*_secret` fields

### Previous Updates (v0.1.7)
- **CPU Overload Protection**: Implemented comprehensive task queue monitoring and overload protection
  - Background task tracking prevents task accumulation causing CPU 99% utilization
  - Automatic rejection of new write operations when queue exceeds 5x concurrency limit
  - Enhanced logging with pending task counts for better observability
- **Seamless Upgrade Compatibility**: Resolved upgrade errors from v0.1.3 to v0.1.7. See [Upgrade Guide](#-upgrade-guide) for details.
- **Installation Time Optimization**: Removed `transformers` and `torch` dependencies to restore fast installation (~22 seconds). See [Upgrade Guide](#-upgrade-guide) for local reranker installation instructions.
- **Configuration Validation**: Added validation to catch common configuration errors
  - Detects when LLM providers are mistakenly used in vector database configuration
  - Provides clear error messages before Mem0 validation fails
- **Code Quality Improvements**:
  - Fixed recurring indentation errors in multiple tool files
  - Optimized code formatting and removed line length violations
  - Changed `_max_ops` from private to public attribute (`max_ops`)
  - Used `MAX_PENDING_TASKS_MULTIPLIER` constant instead of hardcoded values

### Previous Updates (v0.1.6)
- **Security Enhancement**: All sensitive configuration fields now use `secret-input` type to protect API keys and credentials in the Dify UI
  - All JSON configuration fields (`local_llm_json`, `local_embedder_json`, `local_vector_db_json`, `local_graph_db_json`, `local_reranker_json`) are now hidden in the UI
- **User-Configurable Performance Parameters**: Added optional configuration parameters for production environments
  - `max_concurrent_memory_operations` - Maximum concurrent memory operations (default: 40)
  - **Note**: `pgvector_min_connections` and `pgvector_max_connections` were added in v0.1.6 but removed in v0.1.9. Configure connection pool size in vector store JSON config using `minconn` and `maxconn` instead (see [CONFIG.md](CONFIG.md#vector-store-configuration-local_vector_db_json_secret))

### Previous Updates (v0.1.5)
- **Search Memory Timestamp Support**: Added timestamp field to search results, displaying the most recent timestamp (created_at or updated_at) in second precision format (`2025-11-03T20:06:27`)
- **Code Refactoring**: Created `utils/helpers.py` to centralize common utility functions
  - Abstracted `parse_timeout()` function for unified timeout parameter parsing across all read operations
  - Abstracted `format_recent_timestamp()` and `parse_iso_timestamp()` for timestamp handling
- **Code Quality Improvements**: 
  - Removed unused class imports (`LocalClient`, `AsyncLocalClient`) from tool files
  - Changed `AsyncLocalClient.ensure_bg_loop()` to instance method call `client.ensure_bg_loop()`
  - Fixed indentation errors in multiple tool files

### Previous Updates (v0.1.4)
- **Logging Investigation**: Documented logging output behavior and investigated potential improvements. Identified that logs may appear twice (JSON format from Dify handler + standard format from Python root logger) and that JSON format uses Unicode encoding for non-ASCII characters.

### Previous Updates (v0.1.3)
- **Unified Logging Configuration**: Implemented centralized logging using Dify's official plugin logger handler to ensure all logs are properly output to the Dify plugin container for better debugging and monitoring.
- **Database Connection Pool Optimization**: Added automatic connection pool settings for pgvector (min: 10, max: 20) to align with concurrent operation limits, ensuring sufficient database connections for high-concurrency scenarios.
- **PGVector Configuration Enhancement**: Optimized pgvector configuration handling according to Mem0 official documentation, properly supporting parameter priority (connection_pool > connection_string > individual parameters) and automatically building connection strings from discrete parameters.
- **Constant Naming Optimization**: Renamed `MAX_CONCURRENT_MEM_ADDS` to `MAX_CONCURRENT_MEMORY_OPERATIONS` (default: 10) to accurately reflect that it controls concurrency for all async memory operations, not just add operations.

### Previous Updates (v0.1.2)
- **Configurable Timeout Parameters**: All read operations (Search/Get/Get_All/History) now support user-configurable timeout values through the Dify plugin configuration interface. Timeout parameters are set as manual input fields (not exposed to LLM), allowing users to customize timeout behavior per tool based on their specific needs.
- **Optimized Default Timeouts**: Reduced default timeout values for better responsiveness - all read operations now default to 30 seconds (previously 60s for Search/Get_All), and `MAX_REQUEST_TIMEOUT` reduced to 60 seconds (from 120s).
- **Code Quality**: Added missing module and class docstrings, fixed formatting issues to comply with Python best practices.

### Previous Updates (v0.1.1)
- **Timeout & Service Degradation**: Added comprehensive timeout mechanisms for all async read operations (Search/Get/Get_All/History) with graceful service degradation. When operations timeout or encounter errors, the plugin logs the event and returns default/empty results to ensure Dify workflow continuity.
- **Robust Error Handling**: Enhanced exception handling across all tools to catch all error types (network errors, connection failures, etc.), ensuring workflows continue even when individual tools fail.
- **Resource Management**: Improved background task cancellation on timeout to prevent resource leaks and hanging tasks.
- **Production Stability**: Fixed production issues where tools would hang indefinitely, ensuring reliable operation in production environments.

### Previous Updates (v0.1.0)
- **Smart Memory Management**: `add_memory` tool description updated to reflect its ability to intelligently add, update, or delete memories based on context.
- **Robust Error Handling**: Enhanced `get_memory`, `update_memory`, and `delete_memory` to gracefully handle non-existent memories and race conditions with clear error messages instead of crashes.
- **Bug Fixes**: Fixed `get_all_memories` returning empty results by correctly parsing Mem0's dictionary response format.
- **Documentation**: Added important notes about `delete_all` index reset warnings and vector store connection details.

---

## 🚀 Quick Start

### Installation

> 📖 **For detailed installation steps, see [CONFIG.md - Installation](CONFIG.md#installation)**

1. **In Dify Dashboard**
   - Go to `Settings` → `Plugins`
   - Click `Install from GitHub` or upload the plugin package
   - Enter your repository URL or select the `.difypkg` file
   - Click `Install`

### Configuration

> 📖 **For detailed configuration steps and examples, see [CONFIG.md - Configuration Steps](CONFIG.md#configuration-steps)**

After installation, you need to configure:

1. **Operation Mode**: Choose between async (default, recommended for production) or sync mode (for testing)
2. **Required JSON Configs**: `local_llm_json_secret`, `local_embedder_json_secret`, `local_vector_db_json_secret`
3. **Optional Configs**: `local_graph_db_json_secret`, `local_reranker_json_secret`
4. **Performance Parameters** (optional): `max_concurrent_memory_operations`
   - **Note**: PGVector connection pool settings (`minconn`, `maxconn`) are configured in the vector store JSON config, not as separate credential fields
5. **Log Level** (optional): `log_level` (INFO/DEBUG/WARNING/ERROR, default: INFO) - can be changed online without redeployment

**Note**: All JSON configuration fields are displayed as password fields (hidden input) in the Dify UI to protect sensitive information. Legacy `*_json` fields are no longer shown in the UI.

### Start Using

Once configured, all 8 tools are available in your workflows!

---

## 📖 Usage Examples

> 📖 **For complete usage examples with all 8 tools, see [CONFIG.md - Usage Examples](CONFIG.md#usage-examples)**

### Quick Examples

**Add Memory:**
```json
{
  "user": "I love Italian food",
  "assistant": "Great! I'll remember that.",
  "user_id": "alex"
}
```

**Search Memories:**
```json
{
  "query": "What food does alex like?",
  "user_id": "alex",
  "top_k": 5
}
```

**Key Points:**
- `user_id` is **required** for `add_memory`, `search_memory`, and `get_all_memories`
- `filters` and `metadata` must be valid JSON strings when provided
- `top_k` defaults to 5 if not specified for `search_memory`
- `run_id` (optional): Recommended to use Dify's `workflow_run_id` for call chain tracking. **Note**: This parameter is only for tracing and is NOT used as a condition for memory layering or filtering

---

## 🛠️ Available Tools

| Tool | Description |
|------|-------------|
| `add_memory` | Add new memories (user_id required) |
| `search_memory` | Search with filters and top_k, returns timestamp field |
| `get_all_memories` | List all memories |
| `get_memory` | Get specific memory |
| `update_memory` | Update memory content |
| `delete_memory` | Delete single memory |
| `delete_all_memories` | Batch delete memories |
| `get_memory_history` | View change history |
| `consolidate_long_term_memory` | Incrementally consolidate long-term memories from Dify history |

### `consolidate_long_term_memory` Quick Example

```json
{
  "run_at": "2025-12-23T00:00:00Z",
  "user_ids": "[\"alex\",\"bob\"]",
  "app_id": "your_dify_app_id",
  "max_users_per_run": 100,
  "budget_tokens": 200000,
  "dify_base_url": "http://localhost:5001",
  "dify_api_key": "your-dify-api-key"
}
```

Notes:
- The tool writes three memory subtypes and sets `metadata.memory_subtype` to `semantic|episodic|procedural`.
- Checkpoints are stored in Mem0 as internal memories (`metadata.__internal=true`). If you later use `search_memory`, add a filter to exclude internal items.

---

## 📚 Documentation

- **[CONFIG.md](CONFIG.md)** - Complete installation and configuration guide
- **[CHANGELOG.md](CHANGELOG.md)** - Detailed changelog and version history
- **[PRIVACY.md](PRIVACY.md)** - Privacy policy and data handling
- **[Mem0 Official Docs](https://docs.mem0.ai)** - Full API documentation
- **[Dify Plugin Docs](https://docs.dify.ai/docs/plugins)** - Dify plugin development guide

---

## 🎯 Use Cases

### Personal Assistant
```python
# Remember user preferences
add_memory("I prefer morning meetings", user_id="john")
add_memory("I'm vegetarian", user_id="john")

# Query preferences
search("when does john prefer meetings?", user_id="john")
```

### Customer Support
```python
# Track interactions
add_memory("Customer reported login issue", user_id="customer_123")

# Retrieve context
search("previous issues", user_id="customer_123")
```

### Multi-Agent Systems
```python
# Agent-specific memories
add_memory("User likes Italian food", agent_id="food_agent")
add_memory("User prefers Rome", agent_id="travel_agent")

# Search across agents
search(
    "user preferences",
    filters='{"OR": [{"agent_id": "food_agent"}, {"agent_id": "travel_agent"}]}'
)
```

---

## ⚠️ Upgrade Guide

### ⚠️ CRITICAL: Credentials Configuration Incompatibility

**🔴 IMPORTANT**: The plugin has undergone **breaking changes** in credentials configuration that make old and new configurations **incompatible**. You **MUST** delete old credentials before upgrading to avoid configuration errors.

#### Configuration Field Changes

**Version History:**
- **v0.1.3 and earlier**: Used `text-input` type fields (e.g., `local_llm_json`, `local_embedder_json`, `local_vector_db_json`)
- **v0.1.6**: Changed to `secret-input` type fields (e.g., `local_llm_json_secret`, `local_embedder_json_secret`, `local_vector_db_json_secret`)
- **v0.1.6**: Added `pgvector_min_connections` and `pgvector_max_connections` as separate credential fields
- **v0.1.8+**: Removed legacy `*_json` fields completely, only `*_secret` fields are available
- **v0.1.9+**: Removed `pgvector_min_connections` and `pgvector_max_connections` credential fields (now configured in vector store JSON)

**Why This Causes Issues:**
- Dify framework **cannot automatically migrate** credentials from `text-input` to `secret-input` type
- Old credentials with `text-input` type will cause **Internal Server Error** or **configuration errors** when upgrading
- The field names changed (e.g., `local_llm_json` → `local_llm_json_secret`), making them incompatible
- Removed `pgvector_min_connections` and `pgvector_max_connections` fields will cause configuration errors if still present

#### Required Upgrade Steps

**⚠️ BEFORE UPGRADING, YOU MUST:**

1. **Backup Your Configuration** (Optional but Recommended)
   - Copy your current configuration values from Dify UI
   - Save them in a secure location (they contain sensitive API keys and passwords)

2. **Delete Old Credentials**
   - Go to Dify UI: `Settings` → `Plugins` → `mem0ai`
   - Click `Delete Credentials` or remove all existing credential values
   - **This step is mandatory** - old credentials will cause errors after upgrade

3. **Upgrade the Plugin**
   - Install the new plugin version (v0.1.6 or later)
   - Wait for installation to complete

4. **Reconfigure Credentials**
   - Go to `Settings` → `Plugins` → `mem0ai`
   - Fill in all required fields using the **new `*_secret` field names**:
     - `local_llm_json_secret` (was `local_llm_json`)
     - `local_embedder_json_secret` (was `local_embedder_json`)
     - `local_vector_db_json_secret` (was `local_vector_db_json`)
     - `local_graph_db_json_secret` (was `local_graph_db_json`, optional)
     - `local_reranker_json_secret` (was `local_reranker_json`, optional)
   - **Important**: If you previously used `pgvector_min_connections` and `pgvector_max_connections` credential fields, you must now configure them in the `local_vector_db_json_secret` JSON config:
     - Add `"minconn": 10` and `"maxconn": 40` to your pgvector config JSON (see [CONFIG.md](CONFIG.md#vector-store-configuration-local_vector_db_json_secret) for examples)
     - These fields are no longer available as separate credential fields
   - Use the same configuration values you backed up in step 1
   - Save the configuration

**⚠️ If You Skip Deleting Old Credentials:**
- Plugin may fail to start
- You may see "Internal Server Error" when accessing plugin settings
- Tools may not work correctly
- You will need to delete credentials and reconfigure anyway

### Upgrading to v0.1.8+

**⚠️ Important Configuration Changes:**
- **Deprecated Fields Removed**: Legacy `*_json` configuration fields (e.g., `local_llm_json`, `local_embedder_json`) are **completely removed** from the configuration UI
- **New Fields Required**: Only `*_secret` fields (e.g., `local_llm_json_secret`, `local_embedder_json_secret`) are available
- **Mandatory Action**: You **MUST** delete old credentials and reconfigure using `*_secret` fields

**New Features:**
- **Dynamic Log Level**: You can now change log level (INFO/DEBUG/WARNING/ERROR) in plugin credentials without redeployment
- **Request Tracing**: All tools now support `run_id` parameter for better call chain tracking (recommended to use Dify's `workflow_run_id`)
- **Timeout Optimization**: Read operation timeout reduced to 15 seconds for better responsiveness

### Upgrading from v0.1.3

**⚠️ Critical Issue**: If you upgrade from v0.1.3 directly to v0.1.6+, you will encounter an **Internal Server Error** because:
- v0.1.3 used `text-input` type for credential fields (e.g., `local_llm_json`)
- v0.1.6+ changed to `secret-input` type with different field names (e.g., `local_llm_json_secret`)
- Dify framework **cannot handle this type and name change** on existing credentials

**Required Steps:**

1. **✅ Delete Old Credentials First** (MANDATORY)
   - Go to Dify UI: `Settings` → `Plugins` → `mem0ai` → `Delete Credentials`
   - **Do this BEFORE upgrading** to avoid errors

2. **Upgrade the Plugin**
   - Install v0.1.6 or later version
   - Wait for installation to complete

3. **Reconfigure Using New Fields**
   - Go to `Settings` → `Plugins` → `mem0ai`
   - Configure using the new `*_secret` fields:
     - `local_llm_json_secret` (replaces `local_llm_json`)
     - `local_embedder_json_secret` (replaces `local_embedder_json`)
     - `local_vector_db_json_secret` (replaces `local_vector_db_json`)
     - `local_graph_db_json_secret` (replaces `local_graph_db_json`, optional)
     - `local_reranker_json_secret` (replaces `local_reranker_json`, optional)
   - Use the same configuration values as before (just different field names)

**Note**: v0.1.7 provides backward compatibility in code (can read old field names), but the UI only shows new fields. For cleanest upgrade, always delete old credentials and reconfigure.

### Installation Time Optimization

**v0.1.6 Installation Time Issue:**
- v0.1.6 included `transformers` and `torch` dependencies for local reranker support
- This **significantly increased installation time** from ~22 seconds to ~2 minutes 25 seconds

**v0.1.7 Solution:**
- **Removed `transformers` and `torch` from default dependencies** to restore fast installation (~22 seconds)
- **For Local Reranker Users Only**: If you need to use local reranker models (e.g., HuggingFace models), you must manually install these dependencies in the Dify plugin container after plugin installation:

```bash
# Access the Dify plugin container
docker exec -it <plugin-container-name> /bin/bash

# Install transformers and torch
pip install transformers torch
```

**Note**: 
- This only affects users who want to use **local reranker models**
- If you use **cloud-based rerankers** (e.g., Cohere API, OpenAI), no additional installation is needed
- Most users do not need local rerankers, so this change benefits the majority of users

---

## 📌 Important Notes

> 📖 **For detailed operational notes, runtime behavior, and troubleshooting, see [CONFIG.md](CONFIG.md)**

### Quick Reference

- **Delete All Memories**: Automatically resets vector index (normal behavior)
- **Async Mode** (default): Non-blocking writes, timeout-protected reads
- **Sync Mode**: All operations block until completion (no timeout protection)
- **Service Degradation**: Graceful error handling with default/empty results

---

## 🚀 Development

### Local Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/beersoccer/mem0_dify_plugin.git
   cd mem0_dify_plugin
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run locally**
   ```bash
   python -m main
   ```

### Testing

Run YAML validation:
```bash
for file in tools/*.yaml; do 
  python3 -c "import yaml; yaml.safe_load(open('$file'))" && echo "✅ $(basename $file)"
done
```

---

## 📊 Version History

| Version | Date | Changes |
|---------|------|---------|
| v0.1.9 | 2025-12-26 | Connection stability & resource management: TCP silent timeout prevention, connection pool memory leak prevention, PGVector configuration enhancement |
| v0.1.8 | 2025-12-25 | Dynamic log level configuration, timeout optimization, request tracing with run_id, configuration cleanup |
| v0.1.7 | 2025-12-16 | CPU overload protection, seamless upgrade compatibility, configuration validation, code quality improvements |
| v0.1.6 | 2025-12-08 | Security enhancement (secret-input for all configs), user-configurable performance parameters |
| v0.1.5 | 2025-11-28 | Search memory timestamp support, code refactoring with helpers module |
| v0.1.4 | 2025-11-23 | Logging investigation and documentation update |
| v0.1.3 | 2025-11-22 | Unified logging configuration, database connection pool optimization, pgvector config enhancement, constant naming optimization |
| v0.1.2 | 2025-11-21 | Configurable timeout parameters, optimized default timeouts (30s for all read ops), code quality improvements |
| v0.1.1 | 2025-11-20 | Timeout & service degradation for async operations, robust error handling, resource management improvements, production stability fixes |
| v0.1.0 | 2025-11-19 | Smart memory management, robust error handling for non-existent memories, race condition protection, bug fixes |
| v0.0.9 | 2025-11-17 | Unified return format, enhanced async operations (Update/Delete/Delete_All non-blocking), standardized fields, extended constants, complete documentation |
| v0.0.8 | 2025-11-11 | async_mode credential (default true), sync/async tool routing, provider validation aligned, docs updated |
| v0.0.7 | 2025-11-08 | Self-hosted mode refactor, centralized constants, background event loop with graceful shutdown, non-blocking add (queued), search via background loop, normalized outputs |
| v0.0.4 | 2025-10-29 | Dual-mode (SaaS/Local), unified client, simplified Local JSON config, search top_k, add requires user_id, HTTP→SDK refactor |
| v0.0.3 | 2025-10-06 | Added 6 new tools, v2 API support, metadata, multi-entity |
| v0.0.2 | 2025-02-24 | Basic add and retrieve functionality |
| v0.0.1 | Initial | First release |

See [CHANGELOG.md](CHANGELOG.md) for detailed changes.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 📞 Support

- **Issues**: [GitHub Issues](../../issues)
- **Documentation**: [Mem0 Docs](https://docs.mem0.ai)
- **Dify Docs**: [Plugin Development](https://docs.dify.ai/docs/plugins)

---

## ⭐ Show Your Support

If you find this plugin useful, please give it a ⭐ on GitHub!

---

## 🙏 Acknowledgments

- [Dify](https://dify.ai) - AI application development platform
- [Mem0 AI](https://mem0.ai) - Intelligent memory layer for AI
- [Dify Plugin SDK](https://docs.dify.ai/plugin-dev-en/0111-getting-started-dify-plugin) - Plugin development framework
- [Original Project](https://github.com/Feversun/dify-plugin-mem0) - Original dify-plugin-mem0 repository

This project is a **deeply modified and enhanced** version of the excellent [dify-plugin-mem0](https://github.com/Feversun/dify-plugin-mem0) project by **yevanchen**.

I sincerely appreciate the foundational work and outstanding contribution of the original author, yevanchen. The project provided a solid foundation for my localized, high-performance, and asynchronous plugin.

**Key Differences from the Original Project:**

The original project primarily supported Mem0 platform (SaaS mode) and synchronous request handling. This project has been fully refactored to include:
* **Self-Hosted Mode**: Supports configuring and running the user's own LLM, embedding models, vector databases (e.g., pgvector/Milvus), graph databases, and more.
* **Asynchronous Support**: Utilizes asynchronous request handling, significantly improving performance and concurrency.
