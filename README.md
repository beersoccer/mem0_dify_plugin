# Mem0 Dify Plugin v0.3.0

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Dify Plugin](https://img.shields.io/badge/Dify-Plugin-blue)](https://dify.ai)
[![Mem0 AI](https://img.shields.io/badge/Mem0-AI-green)](https://mem0.ai)

Last updated: 2026-04-22

A comprehensive Dify plugin that integrates [Mem0 AI](https://mem0.ai)'s intelligent memory layer, providing **self-hosted mode** tools with a unified client for self-hosted setups. [View on GitHub](https://github.com/beersoccer/mem0_dify_plugin)

---

## 🌟 Features

### Complete Memory Management (12 Tools)
- ✅ **Add Memory** - Intelligently add, update, or delete memories based on user interactions
- ✅ **Search Memory** - Search with advanced filters (AND/OR logic) and top_k limiting, returns timestamp field (most recent created_at/updated_at)
- ✅ **Get All Memories** - List memories with pagination
- ✅ **Get Memory** - Fetch specific memory details
- ✅ **Update Memory** - Modify existing memories
- ✅ **Delete Memory** - Remove individual memories
- ✅ **Delete All Memories** - Batch delete with filters
- ✅ **Get Memory History** - View change history
- ✅ **Extract Long-Term Memory** - Automatically extract semantic/episodic/procedural memories from Dify conversation history
- ✅ **Check Extraction Status** - Check the status and progress of async extraction tasks
- ✅ **Get User Checkpoint** - Inspect extraction checkpoint state for a user/app
- ✅ **Forget Memories** - Periodically forget low-retention memories and clean up stale extraction checkpoints

### Advanced Capabilities
- 🖥️ **Self-Hosted Mode** - Run with Local Mem0 (JSON-based config)
- 🧱 **Simplified Local Config** - 5 JSON blocks: LLM, Embedder, Vector DB, Graph DB (optional), Reranker (optional)
- 🎯 **Entity Scoping** - user_id (required for add), agent_id, run_id
- 📊 **Metadata System** - Custom JSON metadata for rich context
- 🔍 **Filters** - JSON filters supported by Mem0 self-hosted mode
- 📈 **Score Normalization** - Automatically adapts to distance/similarity backends and returns unified 0-1 similarity
- 🧠 **Memory Lifecycle** - Access-log-driven forgetting curve with optional hard TTL for controlled memory retention
- 🌍 **Internationalized** - Chinese/English
- ⚙️ **Async Mode Switch** - `async_mode` is enabled by default; Write ops (Add/Update/Delete) are non-blocking in async mode, Read ops (Search/Get/History) always wait; in sync mode all operations block until completion.

### What's New (v0.3.0) - Checkpoint & Lock Reliability ✅
- **Checkpoint and distributed lock reliability** (PR #44):
  - Improved checkpoint write/read sequencing to eliminate rare race conditions under concurrent extraction tasks
  - Strengthened distributed lock acquisition and release paths for more predictable behavior under load
- **Async checkpoint test isolation**:
  - Isolated async checkpoint tests from pytest-asyncio event loop pollution for more deterministic CI
- **Provider compatibility gate & registry validation**:
  - Added validation tests for LLMs, embedders, vector DBs, and rerankers to catch unsupported provider configurations early
  - Removed the invalid `mistral` provider entry that caused silent failures during credential validation

### Previous Updates (v0.2.12) - Dynamic Extract Params & Cohere SDK ✅
- **Dynamic extraction tool inputs**:
  - Changed all `extract_long_term_memory` parameters to `form: llm` so Dify can bind system variables and upstream values more consistently
- **Built-in Cohere reranker dependency**:
  - Added the `cohere>=6.1.0` runtime dependency and clarified SDK expectations for cloud rerankers in the docs

### Previous Updates (v0.2.11) - AsyncMemory Compatibility & Release Docs ✅
- **AsyncMemory initialization compatibility**:
  - Added a compatibility shim around `AsyncMemory.from_config(...)` so async mode now works whether mem0 exposes it as a coroutine-returning API or a regular classmethod
  - Preserved the existing async credential validation flow in the provider, avoiding behavioral changes outside the initialization fix
- **Supported mem0 version range**:
  - Documented and aligned the supported `mem0ai` dependency range to `>=1.0.2,<=1.0.11`
  - Kept the current lockfile on `1.0.2` while allowing explicit future validation within the supported range
- **Regression coverage & release docs**:
  - Added unit coverage for both async/sync `from_config` semantics and async provider credential validation
  - Refreshed top-level docs, testing notes, privacy metadata, and submission template for this release

These changes fix the async-mode startup regression against newer mem0 releases while keeping installation and release documentation aligned.

### Previous Updates (v0.2.10) - Score Adaptation & Memory Evolution ✅
- **Cross-backend score semantics**:
  - Added automatic score mode inference (`distance` vs `similarity`) by vector provider/metric and normalized search outputs to stable 0-1 similarity
  - `search_memory` results now consistently expose `score` (similarity), `vector_distance`, and `rerank_score`
- **Access-log-driven forgetting**:
  - Search now updates per-user/per-app access logs from raw recall results (sync and async paths)
  - Forgetting uses EWMA quality + Ebbinghaus-style retention curve, with subtype-aware base stability
- **Operational cleanup controls**:
  - Added new `forget_memories` tool with `dry_run` preview support
  - Added credentials: `memory_ttl_days` (optional hard memory TTL) and `checkpoint_ttl_days` (checkpoint cleanup TTL, default 90)

These changes improve cross-backend retrieval consistency and establish a controllable memory lifecycle for long-term operation.

### Previous Updates (v0.2.9) - Extraction Worker Pool Optimization ✅
- **Sliding-window concurrency**:
  - Extraction uses `asyncio.as_completed` with a true Semaphore sliding window; a slow user no longer blocks the next one from starting (straggler problem eliminated)
- **Precise time budget enforcement**:
  - Time budget is checked after acquiring the Semaphore slot, preventing new work from starting past the deadline at user granularity
- **Cleaner error handling**:
  - User-level exceptions are captured inside each coroutine and returned as ERROR results; progress updates flush every N completions

These changes **improve extraction throughput and resource utilization** for large user batches; the global concurrency ceiling across multiple concurrent extraction tasks remains unchanged.

For full historical details, see [CHANGELOG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CHANGELOG.md).

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

**Recommended configuration choices (brief)**:
- **LLM**: Prefer `azure_openai_structured` for stricter schema handling and more reliable structured parsing
- **Vector DB**: Prefer `pgvector` with `connection_string` + psycopg3 pool for stability (TCP keepalive + pool lifecycle)
- **Details**: See [CONFIG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md#configuration-examples) for full examples and placeholders

**Note**: All JSON configuration fields are displayed as password fields (hidden input) in the Dify UI to protect sensitive information. Legacy `*_json` fields are no longer shown in the UI.

### Long-Term Memory Extraction Modes (Extract Tool)

- **Async mode (`async_mode=true`)**: Recommended for production and batch jobs; returns `task_id` and runs in background.
- **Sync mode (`async_mode=false`)**: Recommended for testing or small runs; sequential and blocking.

Details (including batch processing behavior) are in `CONFIG.md` under **Extract Long-Term Memory**.

### Start Using

Once configured, all 12 tools are available in your workflows!

---

## 📖 Quick Examples

> 📖 **For complete usage examples with all 12 tools, see [CONFIG.md - Usage Examples](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md#usage-examples)**

### Add Memory

In Dify workflow, add the `add_memory` tool and configure the following parameters:

![Add Memory Tool Configuration](images/add_memory.png)

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

![Search Memory Tool Configuration](images/search_memory.png)

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
| `extract_long_term_memory` | Extract semantic/episodic/procedural memories from Dify conversation history |
| `check_extraction_status` | Check the status and progress of async extraction tasks |
| `get_user_checkpoint` | Inspect extraction checkpoint state for a user/app |
| `forget_memories` | Forget stale memories and clean old checkpoints (supports dry_run) |

Note: `extract_long_term_memory` uses `conversations_limit` as the per-user total conversation cap within the configured `days_back` time range.

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
     - Add `"minconn": 10` and `"maxconn": 20` to your pgvector config JSON (or set `maxconn` to match your `max_concurrent_memory_operations`, default: 20). See [CONFIG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md#vector-store-configuration-local_vector_db_json_secret) for examples.
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
- **Timeout Optimization**: Read operation timeout is tuned for responsiveness (current default: 5s, configurable per tool)

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
- For **Cohere reranker**, install the Cohere SDK dependency (`cohere>=6.1.0`) in the plugin runtime environment
- Other cloud rerankers may also require their own provider SDKs depending on the selected backend
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
| v0.3.0 | 2026-04-22 | Checkpoint and distributed lock reliability improvements, async checkpoint test isolation, provider compatibility gate and registry validation |
| v0.2.12 | 2026-04-16 | Dynamic `extract_long_term_memory` parameter binding via `form: llm`, bundled Cohere SDK dependency, and reranker documentation refresh |
| v0.2.11 | 2026-04-14 | AsyncMemory.from_config compatibility across mem0 variants, supported mem0 version range alignment, and release/test documentation refresh |
| v0.2.10 | 2026-03-23 | Score semantics unification, memory evolution lifecycle, and new forget_memories maintenance controls |
| v0.2.9 | 2026-03-04 | Extraction worker-pool sliding-window optimization with tighter time-budget and progress flushing behavior |
| v0.2.8 | 2026-02-12 | Stability under load: pre-enqueue overload guard, conservative defaults, pgvector pool/DSN hardening |
| v0.2.7 | 2026-02-08 | Checkpoint windowing, resume cursor accuracy, normalized message timestamps |
| v0.2.6 | 2026-02-07 | Extraction resume safeguards, richer status metrics, local-time task timestamps |
| v0.2.5 | 2026-02-04 | Documentation refresh: recommended config choices and placeholder-safe examples |
| v0.2.4 | 2026-02-03 | Resource isolation optimization: Connection pool sharing for long-term memory tool (67% reduction in database connections) |
| v0.2.3 | 2026-01-31 | Documentation updates: Comprehensive documentation synchronization, merged design documents, improved consistency |
| v0.2.2 | 2026-01-30 | Performance optimizations: Smart memory classification (33% LLM call reduction), token-aware processing with tiktoken, code quality improvements |
| v0.2.1 | 2026-01-29 | Critical bug fix: Data loss prevention when time range expands backward, enhanced checkpoint with time range awareness |
| v0.2.0 | 2026-01-22 | New tool: Long-term memory consolidation, automatic retry mechanism, distributed lock, enhanced checkpoint, atomic save |
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
