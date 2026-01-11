# Plugin Submission Form

## 1. Metadata

<!--
Please provide the following metadata of your plugin to make it easier for the reviewer to check the changes.

  - Plugin Author : The author of the plugin which is defined in your manifest.yaml

  - Plugin Name   : The name of the plugin which is defined in your manifest.yaml

  - Repository URL: The URL of the repository where the source code of your plugin is hosted

-->

- **Plugin Author**: beersoccer

- **Plugin Name**: mem0ai

- **Repository URL**: https://github.com/beersoccer/mem0_dify_plugin

## 2. Submission Type

- [ ] New plugin submission

- [x] Version update for existing plugin

## 3. Description

<!-- Please briefly describe the purpose of the new plugin or the updates made to the existing plugin -->

This version update (v0.1.9) brings connection stability improvements, resource management optimization, and resolves critical production issues related to TCP connection silent timeouts and connection pool memory leaks. The plugin integrates [Mem0 AI](https://mem0.ai)'s intelligent memory layer into Dify, providing comprehensive memory management capabilities for AI applications. The plugin operates exclusively in **self-hosted mode**, allowing users to configure and manage their own LLM, embedding models, vector databases, graph databases, and rerankers.

### What's New in v0.1.9:

- **🔧 Connection Stability & Resource Management**: Resolved critical production issues
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
    - Connection pool settings now configured in vector store JSON config (not as separate credential fields)

### Previous Updates (v0.1.8):

- **🎯 Dynamic Log Level Configuration**: Added runtime log level control without redeployment
  - New `log_level` credential field (INFO/DEBUG/WARNING/ERROR) for online adjustment
  - Thread-safe log level updates apply to all existing loggers immediately
  - Default log level is INFO; can be changed to DEBUG for detailed troubleshooting
  - Changes take effect immediately without requiring plugin redeployment

- **⚡ Timeout Optimization**: Unified and optimized operation timeouts for better performance
  - Read operations (Search/Get/Get_All/History): unified timeout reduced to 15 seconds (from 30s)
  - Write operations (Add/Update/Delete): timeout set to 30 seconds for persistence operations
  - Improved responsiveness while maintaining reliability

- **🔍 Request Tracing Enhancement**: Added `run_id` parameter to all tools for call chain tracking
  - Recommended to use Dify's `workflow_run_id` to link multiple memory operations in the same workflow
  - **Important**: `run_id` is only used for request tracing and logging; it is NOT used as a condition for memory layering or filtering
  - All tools now include request ID in logs for better traceability

- **🧹 Configuration Cleanup**: Removed deprecated configuration fields from UI
  - Legacy `*_json` fields (e.g., `local_llm_json`, `local_embedder_json`) are no longer shown in configuration UI
  - Only `*_secret` fields (e.g., `local_llm_json_secret`, `local_embedder_json_secret`) are available for new installations
  - **Important**: If you encounter configuration issues after upgrade, please delete old credentials and reconfigure using the new `*_secret` fields

### Previous Updates (v0.1.7):

- **🚀 CPU Overload Protection**: Implemented comprehensive task queue monitoring and overload protection
  - Background task tracking prevents task accumulation causing CPU 99% utilization
  - Automatic rejection of new write operations when queue exceeds 5x concurrency limit
  - Enhanced logging with pending task counts for better observability
  - Prevents system overload under high-load scenarios

- **🔄 Seamless Upgrade Compatibility**: Resolved upgrade errors from v0.1.3 to v0.1.7
  - Preserved legacy `text-input` fields for backward compatibility
  - Added new `*_secret` fields with `secret-input` type for enhanced security
  - Users can upgrade without deleting old credentials (no Internal Server Error)
  - Code automatically prefers new secret fields and falls back to legacy fields

- **✅ Configuration Validation**: Added validation to catch common configuration errors
  - Detects when LLM providers are mistakenly used in vector database configuration
  - Provides clear error messages before Mem0 validation fails
  - Improved help text in `mem0ai.yaml` with provider examples

- **🔧 Code Quality Improvements**:
  - Fixed recurring indentation errors in multiple tool files
  - Optimized code formatting and removed line length violations
  - Changed `_max_ops` from private to public attribute (`max_ops`)
  - Used `MAX_PENDING_TASKS_MULTIPLIER` constant instead of hardcoded values

### ⚠️ Important Upgrade Notes:

**🔴 CRITICAL: Configuration Incompatibility**

**⚠️ BREAKING CHANGES**: The plugin has undergone **incompatible changes** in credentials configuration. You **MUST** delete old credentials before upgrading.

**Configuration Field Changes:**
- **Field Type & Names**: Changed from `*_json` (text-input) to `*_secret` (secret-input) fields
- **Removed Fields**: `pgvector_min_connections` and `pgvector_max_connections` credential fields removed (v0.1.9+)
  - **Migration**: Configure connection pool size in `local_vector_db_json_secret` JSON using `minconn` and `maxconn`
- **Removed Fields**: Legacy `*_json` fields completely removed from UI (v0.1.8+)

**Required Upgrade Steps:**
1. **Backup** your configuration values
2. **Delete** old credentials in Dify UI (`Settings` → `Plugins` → `mem0ai` → `Delete Credentials`)
3. **Upgrade** the plugin
4. **Reconfigure** using new `*_secret` fields and migrate pgvector connection pool settings to JSON config

**⚠️ If you skip deleting credentials**: Plugin will fail to start or show "Internal Server Error".

**Upgrading from v0.1.3:**

**Problem**: If you upgrade from v0.1.3 directly to v0.1.6, you will encounter an **Internal Server Error** because:
- v0.1.3 used `text-input` type for credential fields
- v0.1.6 changed to `secret-input` type for the same fields
- Dify framework cannot handle this type change on existing credentials

**Solution:**
- **✅ Recommended: Upgrade to v0.1.7+ (Seamless)**
  - v0.1.7+ supports backward-compatible credential upgrades
  - Your old `text-input` credentials will continue to work automatically
  - **No action required** - just upgrade the plugin to v0.1.7+
  - Optionally migrate to new encrypted fields (`*_secret`) for enhanced security later
  - This is the **recommended approach** for all users

**Summary**: Always upgrade to v0.1.7+ for seamless compatibility. Avoid upgrading directly to v0.1.6 from v0.1.3.

**Installation Time Optimization:**

**v0.1.6 Installation Time Issue:**
- v0.1.6 included `transformers` and `torch` dependencies for local reranker support
- This **significantly increased installation time** from ~22 seconds to ~2 minutes 25 seconds

**v0.1.7+ Solution:**
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

### Previous Updates (v0.1.6):

- **🔒 Security Enhancement**: All sensitive configuration fields now use `secret-input` type to protect API keys and credentials in the Dify UI
  - All JSON configuration fields (`local_llm_json`, `local_embedder_json`, `local_vector_db_json`, `local_graph_db_json`, `local_reranker_json`) are now hidden in the UI
  - Sensitive information (API keys, passwords, tokens) is protected from accidental exposure

- **⚙️ User-Configurable Performance Parameters**: Added optional configuration parameters for production environments
  - `max_concurrent_memory_operations` - Maximum concurrent memory operations (default: 40)
  - **Note**: `pgvector_min_connections` and `pgvector_max_connections` were added in v0.1.6 but removed in v0.1.9. Configure connection pool size in vector store JSON config using `minconn` and `maxconn` instead
  - **Concurrency Configuration Logic**: Validates all inputs with warning logs

- **🐛 Bug Fixes**: Fixed Dify plugin framework compatibility issue (changed `type: number` to `type: text-input` for numeric configuration fields)

### Previous Updates (v0.1.5):

- **📅 Search Memory Timestamp Support**: Added timestamp field to search results, displaying the most recent timestamp (created_at or updated_at) in second precision format (`2025-11-03T20:06:27`)
- **🔧 Code Refactoring**: Created `utils/helpers.py` to centralize common utility functions for better code maintainability
- **✨ Code Quality Improvements**: Removed unused imports, fixed indentation errors, improved code organization

### Key Features:

- **8 Complete Memory Management Tools**:
  - Add Memory - Intelligently add, update, or delete memories based on user interactions
  - Search Memory - Search with advanced filters (AND/OR logic) and top_k limiting, returns timestamp field
  - Get All Memories - List memories with pagination
  - Get Memory - Fetch specific memory details
  - Update Memory - Modify existing memories
  - Delete Memory - Remove individual memories
  - Delete All Memories - Batch delete with filters
  - Get Memory History - View change history

- **Flexible Operation Modes**:
  - **Async Mode** (default): Recommended for production, supports high concurrency with non-blocking write operations
  - **Sync Mode**: Recommended for testing, all operations block until completion for immediate result visibility

- **Self-Hosted Mode Architecture**:
  - All data stored in user's own infrastructure (vector database, graph database)
  - No data sent to external servers
  - Complete user control over data storage and processing

- **Production-Ready Features**:
  - Comprehensive timeout protection and service degradation
  - Robust error handling ensuring workflow continuity
  - Database connection pool optimization for high concurrency (configured in vector store JSON)
  - Connection keep-alive mechanism to prevent TCP silent timeouts
  - Automatic resource cleanup to prevent memory leaks
  - Unified logging configuration for better debugging

### Configuration:

Users configure the plugin by:
1. Choosing operation mode (async/sync)
2. Providing JSON configurations for:
   - LLM provider (required)
   - Embedding model (required)
   - Vector database (required, e.g., pgvector)
   - Graph database (optional, e.g., Neo4j)
   - Reranker (optional)
3. (Optional) Configuring performance parameters for production environments

**Note**: All JSON configuration fields are displayed as password fields (hidden input) in the Dify UI to protect sensitive information.

For detailed configuration options, users are directed to the [Mem0 Official Configuration Documentation](https://docs.mem0.ai/open-source/configuration).

## 4. Checklist

- [x] I have read and followed the Publish to Dify Marketplace guidelines

- [x] I have read and comply with the Plugin Developer Agreement

- [x] I confirm my plugin works properly on both Dify Community Edition and Cloud Version

- [x] I confirm my plugin has been thoroughly tested for completeness and functionality

- [x] My plugin brings new value to Dify

## 5. Documentation Checklist

Please confirm that your plugin README includes all necessary information:

- [x] Step-by-step setup instructions

- [x] Detailed usage instructions

- [x] All required APIs and credentials are clearly listed

- [x] Connection requirements and configuration details

- [x] Link to the repository for the plugin source code

**Documentation Details:**

- **README.md**: Project overview, quick start guide, feature highlights, and brief usage examples with references to detailed documentation
- **CONFIG.md**: Complete installation and configuration guide with detailed examples for all providers, troubleshooting, and operational notes
- **PRIVACY.md**: Complete privacy policy explaining self-hosted mode operation and data handling
- **CHANGELOG.md**: Detailed version history and changes for all versions

**Documentation Improvements in v0.1.9:**
- Added comprehensive connection stability and resource management documentation
- Documented TCP connection silent timeout prevention mechanism
- Documented connection pool memory leak prevention
- Added PGVector connection pool configuration migration guide (removed credential fields)
- Enhanced upgrade guide with critical configuration incompatibility warnings
- Streamlined documentation to eliminate duplicate content through cross-references

**Documentation Improvements in v0.1.8:**
- Added dynamic log level configuration documentation
- Updated timeout values and operation behavior documentation
- Added `run_id` parameter usage guide and important notes
- Updated configuration cleanup instructions for deprecated fields
- Enhanced troubleshooting section with configuration migration guidance

**Documentation Improvements in v0.1.7:**
- Added troubleshooting section for CPU overload and upgrade compatibility issues
- Updated configuration guide with backward-compatible upgrade instructions
- Enhanced performance recommendations based on task queue monitoring

**Documentation Improvements in v0.1.6:**
- Eliminated duplicate content across markdown files
- Established clear cross-references between documents
- Added comprehensive configuration examples for all supported providers
- Updated all examples to use placeholder values (no sensitive information)
- Enhanced troubleshooting section with production-specific guidance

All configuration examples follow the format specified in Mem0 official documentation, and users are directed to the official docs for advanced configuration options.

## 6. Privacy Protection Information

Based on Dify Plugin Privacy Protection [Guidelines](https://docs.dify.ai/plugins/publish-plugins/publish-to-dify-marketplace/plugin-privacy-protection-guidelines):

### Data Collection

**No user personal data is collected by this plugin.**

This plugin operates exclusively in **self-hosted mode**, which means:

- **All data is stored in the user's own infrastructure** - Users configure and manage their own vector database and graph database
- **No data is sent to external servers** - All processing happens locally using user-configured services (LLM, embedding models, databases)
- **Complete user control** - Users have full control over where and how their data is stored

The plugin only processes:
- Conversation history (chat messages) - stored in user's own vector database
- User IDs, Agent IDs, Run IDs - used for data partitioning and scoping within user's own database
- Message metadata (timestamps, roles) - stored in user's own database

**No personal identification information (PII) is required or collected beyond user-provided identifiers (user_id, agent_id, run_id).**

**Security Enhancements in v0.1.9:**
- Connection keep-alive mechanism ensures reliable service connectivity
- Automatic resource cleanup prevents memory leaks and connection pool exhaustion
- Enhanced connection stability reduces service interruptions

**Security Enhancements in v0.1.8:**
- Configuration cleanup removes deprecated fields from UI to prevent confusion
- Enhanced request tracing with `run_id` for better auditability
- Improved logging with context information for security monitoring

**Security Enhancements in v0.1.7:**
- Backward-compatible credential upgrade ensures seamless migration from v0.1.3
- New encrypted fields (`*_secret`) provide enhanced security while maintaining compatibility
- Configuration validation prevents common errors (e.g., using LLM providers in vector database fields)

**Security Enhancements in v0.1.6:**
- All sensitive configuration fields (API keys, passwords, tokens) are now hidden in the Dify UI using `secret-input` type
- Configuration fields appear as password fields (hidden input) to prevent accidental exposure
- No functional changes to data handling - only UI display behavior improved for security

All API keys and credentials are stored locally in the user's Dify instance configuration and are not shared with any third parties. The plugin only communicates with services configured by the user (their LLM, embedding, and database services).

### Privacy Policy

- [x] I confirm that I have prepared and included a privacy policy in my plugin package based on the Plugin Privacy Protection Guidelines

**Privacy Policy Location**: `PRIVACY.md` is included in the plugin package and clearly explains:
- Self-hosted mode operation and data storage
- Information processed by the plugin
- User's complete control over data
- No third-party data sharing
- User's responsibility for data security and compliance

