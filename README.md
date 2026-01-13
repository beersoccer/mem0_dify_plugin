# Mem0 Dify Plugin v0.1.9

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Dify Plugin](https://img.shields.io/badge/Dify-Plugin-blue)](https://dify.ai)
[![Mem0 AI](https://img.shields.io/badge/Mem0-AI-green)](https://mem0.ai)

A comprehensive Dify plugin that integrates [Mem0 AI](https://mem0.ai)'s intelligent memory layer, providing **self-hosted mode** tools with a unified client for self-hosted setups. [View on GitHub](https://github.com/beersoccer/mem0_dify_plugin)

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
    - See [CONFIG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md#connection-stability--resource-management) for details

> 📖 **For previous version updates, see [CHANGELOG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CHANGELOG.md)**

---

## 🚀 Quick Start

### Installation

> 📖 **For detailed installation steps, see [CONFIG.md - Installation](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md#installation)**

1. **In Dify Dashboard**
   - Go to `Settings` → `Plugins`
   - Click `Install from GitHub` or upload the plugin package
   - Enter your repository URL or select the `.difypkg` file
   - Click `Install`

### Configuration

> 📖 **For detailed configuration steps and examples, see [CONFIG.md - Configuration Steps](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md#configuration-steps)**

After installation, you need to configure:

1. **Operation Mode**: Choose between async (default, recommended for production) or sync mode (for testing)
2. **Required JSON Configs**: `local_llm_json_secret`, `local_embedder_json_secret`, `local_vector_db_json_secret`
3. **Optional Configs**: `local_graph_db_json_secret`, `local_reranker_json_secret`
4. **Performance Parameters** (optional): `max_concurrent_memory_operations`
   - **Note**: PGVector connection pool settings (`minconn`, `maxconn`) are configured in the vector store JSON config, not as separate credential fields
5. **Connection Keep-Alive** (optional): `heartbeat_interval` (default: 120 seconds, minimum: 30 seconds) - configurable heartbeat interval for connection keep-alive mechanism
6. **Log Level** (optional): `log_level` (INFO/DEBUG/WARNING/ERROR, default: INFO) - can be changed online without redeployment

**Note**: All JSON configuration fields are displayed as password fields (hidden input) in the Dify UI to protect sensitive information. Legacy `*_json` fields are no longer shown in the UI.

### Start Using

Once configured, all 8 tools are available in your workflows!

---

## 📖 Quick Examples

> 📖 **For complete usage examples with all 8 tools, see [CONFIG.md - Usage Examples](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md#usage-examples)**

### Add Memory

In Dify workflow, add the `add_memory` tool and configure the following parameters:

![Add Memory Tool Configuration](images/add_memory_example.png)

**Required Parameters:**
- `user`: User message (e.g., "I love Italian food")
- `user_id`: User identifier (e.g., "alex")

**Optional Parameters:**
- `assistant`: Assistant response (e.g., "Great! I'll remember that.")
- `agent_id`: Agent identifier for scoping
- `run_id`: Workflow run ID for tracing (recommended to use Dify's `workflow_run_id`)
- `metadata`: Custom JSON metadata string

### Search Memories

In Dify workflow, add the `search_memory` tool and configure the following parameters:

![Search Memory Tool Configuration](images/search_memory_example.png)

**Required Parameters:**
- `query`: Search query (e.g., "What food does alex like?")
- `user_id`: User identifier (e.g., "alex")

**Optional Parameters:**
- `top_k`: Maximum number of results (default: 5)
- `filters`: JSON filter string for advanced filtering
- `agent_id`: Agent identifier for scoping
- `run_id`: Workflow run ID for tracing

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

---

## 📚 Documentation

- **[CONFIG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md)** - Complete installation and configuration guide
- **[CHANGELOG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CHANGELOG.md)** - Detailed changelog and version history
- **[PRIVACY.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/PRIVACY.md)** - Privacy policy and data handling
- **[Mem0 Official Docs](https://docs.mem0.ai)** - Full API documentation
- **[Dify Plugin Docs](https://docs.dify.ai/docs/plugins)** - Dify plugin development guide

---

## ⚠️ Upgrade Guide

### ⚠️ CRITICAL: Credentials Configuration Incompatibility

**🔴 IMPORTANT**: The plugin has undergone **breaking changes** in credentials configuration that make old and new configurations **incompatible**. You **MUST** delete old credentials before upgrading to avoid configuration errors.

#### Configuration Field Changes

**Version History:**
- **v0.1.9+**: Removed `pgvector_min_connections` and `pgvector_max_connections` credential fields (now configured in vector store JSON)
- **v0.1.8+**: Removed legacy `*_json` fields completely, only `*_secret` fields are available
- **v0.1.6**: Changed to `secret-input` type fields (e.g., `local_llm_json_secret`, `local_embedder_json_secret`, `local_vector_db_json_secret`)
- **v0.1.6**: Added `pgvector_min_connections` and `pgvector_max_connections` as separate credential fields
- **v0.1.3 and earlier**: Used `text-input` type fields (e.g., `local_llm_json`, `local_embedder_json`, `local_vector_db_json`)

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
     - Add `"minconn": 10` and `"maxconn": 40` to your pgvector config JSON (see [CONFIG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md#vector-store-configuration-local_vector_db_json_secret) for examples)
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

> 📖 **For detailed operational notes, runtime behavior, and troubleshooting, see [CONFIG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md)**

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
| v0.1.9 | 2025-01-11 | Connection stability & resource management: TCP silent timeout prevention, connection pool memory leak prevention, PGVector configuration enhancement |
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

See [CHANGELOG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CHANGELOG.md) for detailed changes.

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

- **Issues**: [GitHub Issues](https://github.com/beersoccer/mem0_dify_plugin/issues)
- **Documentation**: [Mem0 Docs](https://docs.mem0.ai)
- **Dify Docs**: [Plugin Development](https://docs.dify.ai/docs/plugins)

---

## ⭐ Show Your Support

If you find this plugin useful, please give it a ⭐ on [GitHub](https://github.com/beersoccer/mem0_dify_plugin)!

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
