# Mem0 Dify Plugin - Changelog

## Version 0.1.9 (2025-12-26)

### 🔧 Connection Stability & Resource Management Optimization

This release focuses on resolving critical production issues related to TCP connection silent timeouts and connection pool memory leaks, significantly improving system stability and resource management in long-running processes.

#### Highlights
- **TCP Connection Silent Timeout Resolution**: Implemented comprehensive connection keep-alive mechanism
  - Added `ConnectionKeepAlive` class to periodically send heartbeat requests to LLM, embedding, and vector store services
  - Prevents TCP connections from being silently closed by network infrastructure (firewalls, load balancers, etc.)
  - Configurable heartbeat interval (default: 120 seconds, minimum: 30 seconds)
  - Automatic keep-alive for all underlying services (LLM, embedding, vector store)
- **Connection Pool Memory Leak Prevention**: Implemented explicit resource cleanup for async clients
  - Added `resource_cleanup.py` module with dedicated cleanup functions for vector store, graph store, and database connections
  - `AsyncMem0Client` now includes `aclose()` method for explicit resource cleanup
  - Automatic cleanup of old client instances when configuration changes
  - Prevents connection pool exhaustion and memory leaks in long-running processes
- **PGVector Connection Pool Configuration Enhancement**: Improved connection pool management with TCP keepalive support
  - Automatic addition of TCP keepalive parameters to connection strings if not present
  - Support for two recommended configuration methods (see [CONFIG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md#vector-store-configuration-local_vector_db_json_secret) for details)
  - Automatic creation of psycopg3 ConnectionPool with best practice defaults
  - Connection pool parameters properly configured to prevent connection exhaustion

#### 🔧 Technical Details
- **Connection Keep-Alive Implementation**:
  - `ConnectionKeepAlive` class in `utils/connection_keepalive.py`
  - Runs in a separate daemon thread to avoid blocking main operations
  - Sends lightweight heartbeat requests to LLM (`generate_response()`), embedding (`embed()`), and vector store (`list_cols()`)
  - Heartbeat failures are logged but do not interrupt service (non-critical)
  - Automatically started when `SyncMem0Client` or `AsyncMem0Client` is initialized
  - Configurable via `heartbeat_interval` credential (default: 120 seconds)
- **Resource Cleanup Implementation**:
  - `close_memory_resources()` function in `utils/resource_cleanup.py`
  - Explicitly closes vector store connection pools (`pool.close()` or `pool.closeall()`)
  - Closes graph store connections (Neo4j driver, etc.)
  - Closes database connections (SQLite, etc.)
  - Called automatically when `AsyncMem0Client.aclose()` is invoked
  - Called automatically when client configuration changes (old instance cleanup)
- **PGVector TCP Keepalive Parameters**:
  - Automatically added to connection strings: `keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=3&connect_timeout=5`
  - Applied to both `connection_string` and individual parameter configurations
  - Prevents TCP connections from being silently closed by network infrastructure
  - Parameters are only added if not already present in connection string
- **Connection Pool Management**:
  - Automatic creation of psycopg3 ConnectionPool when `connection_string` is provided
  - Falls back to psycopg2 ThreadedConnectionPool if psycopg3 is unavailable
  - Connection pool parameters properly extracted and configured
  - Pool lifecycle managed to prevent resource leaks

#### 📝 Files Changed
- **New Files**:
  - `utils/connection_keepalive.py` - Connection keep-alive manager for preventing TCP silent timeouts
  - `utils/resource_cleanup.py` - Resource cleanup utilities for preventing memory leaks
- **Modified Files**:
  - `utils/mem0_client.py` - Added ConnectionKeepAlive initialization, added `aclose()` method, added cleanup on config change
  - `utils/pgvector_config.py` - Enhanced to automatically add TCP keepalive parameters, improved connection pool creation
  - `utils/config_builder.py` - Updated to support heartbeat_interval configuration

#### ⚠️ Migration Notes
- **No Breaking Changes**: All changes are backward compatible
- **Removed Configuration Fields**: `pgvector_min_connections` and `pgvector_max_connections` credential fields removed
  - **Migration**: Configure connection pool size in `local_vector_db_json_secret` JSON using `minconn` and `maxconn` (see [CONFIG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md#vector-store-configuration-local_vector_db_json_secret))
  - If you have these fields in old credentials, delete credentials and reconfigure
- **Automatic Features**: Connection keep-alive and TCP keepalive parameters are automatically enabled
- **Configuration Optional**: `heartbeat_interval` can be configured in credentials (default: 120 seconds)
- **Resource Cleanup**: Explicit cleanup is handled automatically; no manual intervention required

#### 🐛 Bug Fixes
- Fixed TCP connection silent timeout issues causing connection failures in long-running processes
- Fixed connection pool memory leaks when client configuration changes
- Fixed connection pool exhaustion in high-concurrency scenarios

#### 🎯 Performance Recommendations
1. **Connection Keep-Alive**: Default heartbeat interval (120 seconds) is suitable for most environments. Adjust if needed based on network infrastructure timeout settings.
2. **PGVector Configuration**: Use recommended configuration methods (see [CONFIG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md#vector-store-configuration-local_vector_db_json_secret)) with TCP keepalive parameters for optimal connection stability.
3. **Resource Management**: Connection pools are automatically managed; no manual cleanup required. System will automatically clean up resources when configuration changes.

---

## Version 0.1.8 (2025-12-25)

### 🎯 Dynamic Logging & Performance Optimization

This release introduces dynamic log level configuration, optimizes operation timeouts, adds request tracing capabilities, and cleans up deprecated configuration fields.

#### Highlights
- **Dynamic Log Level Configuration**: Added runtime log level control without redeployment
  - New `log_level` credential field (INFO/DEBUG/WARNING/ERROR) for online adjustment
  - Thread-safe log level updates apply to all existing loggers immediately
  - Default log level is INFO; can be changed to DEBUG for detailed troubleshooting
  - Changes take effect immediately without requiring plugin redeployment
- **Timeout Optimization**: Unified and optimized operation timeouts for better performance
  - Read operations (Search/Get/Get_All/History): unified timeout reduced to 15 seconds (from 30s)
  - Write operations (Add/Update/Delete): timeout set to 30 seconds for persistence operations
  - Improved responsiveness while maintaining reliability
  - Unified timeout constants: `READ_OPERATION_TIMEOUT` (15s) and `WRITE_OPERATION_TIMEOUT` (30s)
- **Request Tracing Enhancement**: Added `run_id` parameter to all tools for call chain tracking
  - Recommended to use Dify's `workflow_run_id` to link multiple memory operations in the same workflow
  - **Important**: `run_id` is only used for request tracing and logging; it is NOT used as a condition for memory layering or filtering
  - All tools now include request ID in logs for better traceability
  - Request ID format: `[req:<run_id>]` prefix in log messages
- **Configuration Cleanup**: Removed deprecated configuration fields from UI
  - Legacy `*_json` fields (e.g., `local_llm_json`, `local_embedder_json`) are no longer shown in configuration UI
  - Only `*_secret` fields (e.g., `local_llm_json_secret`, `local_embedder_json_secret`) are available for new installations
  - **Important**: If you encounter configuration issues after upgrade, please delete old credentials and reconfigure using the new `*_secret` fields
- **Code Quality Improvements**:
  - Improved logging with request ID tracking across all operations
  - Better error messages with context information
  - Optimized timeout handling with unified constants
  - Enhanced log messages with operation context

#### 🔧 Technical Details
- **Log Level Management**:
  - Added `set_log_level()` function in `utils/logger.py` for thread-safe log level updates
  - Module-level log level cache with thread-safe locking
  - Updates apply to all existing loggers in `tools.*` and `utils.*` modules
  - Provider validation automatically sets log level from credentials
- **Timeout Constants**:
  - Replaced individual timeout constants (`SEARCH_OPERATION_TIMEOUT`, `GET_OPERATION_TIMEOUT`, etc.) with unified constants
  - `READ_OPERATION_TIMEOUT: int = 15` for all read operations
  - `WRITE_OPERATION_TIMEOUT: int = 30` for all write operations
  - All tools use `parse_timeout()` helper for consistent timeout handling
- **Request Tracing**:
  - All tools extract `run_id` from `tool_parameters` (defaults to "no-run-id" if not provided)
  - Request ID included in all log messages: `logger.info("[req:%s] ...", request_id, ...)`
  - `run_id` is NOT included in Mem0 API payloads (only used for tracing)
  - Helps track operations across workflow execution chains
- **Configuration Schema**:
  - Removed legacy `*_json` fields from `provider/mem0ai.yaml`
  - Only `*_secret` fields are shown in configuration UI
  - Backward compatibility: code still supports legacy fields via `_get_credential_value()` fallback, but UI no longer displays them

#### 📝 Files Changed
- **Modified Files**:
  - `manifest.yaml` - Updated version to 0.1.8, updated description
  - `provider/mem0ai.yaml` - Removed deprecated `*_json` fields, added `log_level` field
  - `provider/mem0ai.py` - Added log level initialization from credentials
  - `utils/logger.py` - Added `set_log_level()` function and thread-safe log level management
  - `utils/constants.py` - Unified timeout constants (READ_OPERATION_TIMEOUT, WRITE_OPERATION_TIMEOUT)
  - `tools/add_memory.py` - Added request ID tracking, improved logging
  - `tools/update_memory.py` - Added request ID tracking, improved logging
  - `tools/delete_memory.py` - Added request ID tracking, improved logging
  - `tools/delete_all_memories.py` - Added request ID tracking, improved logging
  - `tools/search_memory.py` - Added request ID tracking, improved logging
  - `tools/get_memory.py` - Added request ID tracking, improved logging
  - `tools/get_all_memories.py` - Added request ID tracking, improved logging
  - `tools/get_memory_history.py` - Added request ID tracking, improved logging
  - All tool YAML files - Added `run_id` parameter documentation

#### ⚠️ Migration Notes

**🔴 CRITICAL: Credentials Configuration Incompatibility**

**⚠️ BREAKING CHANGE**: This version introduces **incompatible changes** to credentials configuration. You **MUST** delete old credentials before upgrading.

**Configuration Field Changes:**
- **Removed**: Legacy `*_json` fields (e.g., `local_llm_json`, `local_embedder_json`) are **completely removed** from the configuration UI
- **Removed**: `pgvector_min_connections` and `pgvector_max_connections` credential fields (v0.1.9+)
- **Required**: Only `*_secret` fields (e.g., `local_llm_json_secret`, `local_embedder_json_secret`) are available
- **Migration**: PGVector connection pool settings must now be configured in `local_vector_db_json_secret` JSON using `minconn` and `maxconn` (see [CONFIG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md#vector-store-configuration-local_vector_db_json_secret))

**Required Upgrade Steps:**
1. **Backup your configuration** (copy all credential values)
2. **Delete old credentials** in Dify UI: `Settings` → `Plugins` → `mem0ai` → `Delete Credentials`
3. **Upgrade the plugin** to v0.1.8+
4. **Reconfigure** using the new `*_secret` fields
5. **Migrate PGVector settings**: If you used `pgvector_min_connections`/`pgvector_max_connections`, add `minconn` and `maxconn` to your pgvector JSON config

**⚠️ If you skip deleting old credentials:**
- Plugin may fail to start
- "Internal Server Error" when accessing plugin settings
- Tools may not work correctly

For detailed upgrade instructions, see [README.md - Upgrade Guide](https://github.com/beersoccer/mem0_dify_plugin/blob/main/README.md#-upgrade-guide).

**Other Changes:**
- **Timeout Changes**: Read operation timeout reduced from 30s to 15s
- **New Features**: `log_level` can be changed online; `run_id` parameter for request tracing

#### 🐛 Bug Fixes
- Fixed inconsistent timeout handling across different read operations
- Improved error messages with request context for better debugging

#### 🎯 Performance Recommendations
1. **Use Dynamic Log Level**: Set `log_level` to DEBUG for troubleshooting, then switch back to INFO for production
2. **Request Tracing**: Use Dify's `workflow_run_id` as `run_id` parameter to track operations across workflow chains
3. **Timeout Tuning**: If 15s timeout is too short for your environment, consider using sync mode or adjusting timeout values

---

## Version 0.1.7 (2025-12-16)

### 🚀 Performance Optimization & Upgrade Compatibility

This release focuses on resolving CPU overload issues, implementing backward-compatible credential upgrades, and improving overall system stability under high-load scenarios.

#### Highlights
- **CPU Overload Protection**: Implemented comprehensive task queue monitoring and overload protection
  - Added background task tracking mechanism to monitor pending operations
  - Implemented queue size check with rejection when exceeding 5x concurrency limit
  - Prevents task accumulation causing CPU 99% utilization
  - Logs pending task count for better observability
- **Backward-Compatible Credential Upgrade**: Resolved upgrade errors from v0.1.3 to v0.1.6+
  - Preserved legacy `text-input` fields for backward compatibility
  - Added new `*_secret` fields with `secret-input` type for enhanced security
  - Code automatically prefers new secret fields and falls back to legacy fields
  - Users can upgrade without deleting old credentials (no Internal Server Error)
  - **Important**: If upgrading from v0.1.3 directly to v0.1.6 (skipping v0.1.7), you must delete old credentials before upgrading
- **Installation Time Optimization**: Removed `transformers` and `torch` dependencies to restore fast installation
  - v0.1.6 installation time increased from ~22 seconds to ~2 minutes 25 seconds due to these dependencies
  - v0.1.7 restores fast installation (~22 seconds) by removing these dependencies
  - **For Local Reranker Users**: If you need local reranker models (e.g., HuggingFace), manually install `transformers` and `torch` in the Dify plugin container after installation
- **Configuration Validation**: Added validation to catch common configuration errors
  - Detects when LLM providers are mistakenly used in vector database configuration
  - Provides clear error messages before Mem0 validation fails
  - Improved help text in `mem0ai.yaml` with provider examples
- **Concurrency Configuration Optimization**: Improved concurrent operations configuration handling
  - Unified parsing logic with `_parse_concurrent_ops()` function for better code maintainability
  - Added warning logs when invalid or unset values are detected (cannot be converted to positive integers)
  - Unified concurrency control: `max_concurrent_memory_operations` applies to all operations including search
  - Validates all input values and uses default value (40) when invalid or unset
  - Enhanced observability with detailed warning messages for configuration issues
- **Code Quality Improvements**:
  - Fixed recurring indentation errors in multiple tool files
  - Optimized code formatting (removed line length violations)
  - Changed `_max_ops` from private to public attribute (`max_ops`)
  - Removed redundant task cleanup logic in `get_pending_tasks_count()`
  - Used `MAX_PENDING_TASKS_MULTIPLIER` constant instead of hardcoded value

#### 🔧 Technical Details
- **Task Tracking System**:
  - Added `AsyncLocalClient._bg_tasks` (ClassVar) to track all background tasks
  - Added `track_bg_task()` method with automatic cleanup via callbacks
  - Added `get_pending_tasks_count()` method for queue monitoring
  - Tasks are automatically removed when completed (no manual cleanup needed)
- **Overload Protection Logic**:
  - Check: `pending_count > max_ops * MAX_PENDING_TASKS_MULTIPLIER` (default: 5x)
  - Action: Reject new write operations (add/update/delete/delete_all) when queue is full
  - Log: Warning with operation type and relevant ID (user_id or memory_id)
  - Response: Return error message indicating system overload
- **Credential Schema Changes**:
  - New fields: `local_llm_json_secret`, `local_embedder_json_secret`, `local_vector_db_json_secret`, `local_graph_db_json_secret`, `local_reranker_json_secret`
  - Legacy fields: `local_llm_json`, `local_embedder_json`, `local_vector_db_json`, `local_graph_db_json`, `local_reranker_json` (marked as DEPRECATED)
  - Added `_get_credential_value()` helper in `utils/config_builder.py` for fallback logic
  - Field order reorganized: recommended fields first, deprecated fields last
- **Configuration Improvements**:
  - Fixed credential default values: changed numeric defaults to string format ("40", "10")
  - Added comprehensive help text for all credential fields
  - Added validation for vector store provider type
- **Concurrency Configuration Logic**:
  - `max_concurrent_memory_operations` configured: Uses configured value directly
  - Not configured: Uses default value (40)
  - Invalid/unset values: Uses defaults with warning logs
  - See [CONFIG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CONFIG.md#step-3-configure-performance-parameters-optional-recommended-for-production) for detailed documentation

#### 📝 Files Changed
- **Modified Files**:
  - `provider/mem0ai.yaml` - Reorganized credential fields, added backward-compatible schema, improved help text
  - `utils/config_builder.py` - Added `_get_credential_value()` for credential fallback logic, added vector store provider validation
  - `utils/mem0_client.py` - Added task tracking system, changed `_max_ops` to `max_ops`, removed redundant cleanup logic, optimized concurrency configuration parsing with unified validation and warning logs
  - `utils/constants.py` - Added `MAX_PENDING_TASKS_MULTIPLIER` constant
  - `tools/add_memory.py` - Added overload protection, task tracking, fixed indentation errors
  - `tools/update_memory.py` - Added overload protection, task tracking, fixed indentation errors
  - `tools/delete_memory.py` - Added overload protection, task tracking, fixed indentation errors
  - `tools/delete_all_memories.py` - Added overload protection, task tracking, fixed indentation errors
  - `tools/get_memory.py` - Fixed indentation errors
  - `tools/get_memory_history.py` - Fixed indentation errors
  - `.gitignore` - Added `logs/` directory and `*.log` files
  - `build_package.sh` - Updated version to 0.1.7

#### ⚠️ Migration Notes
- **Upgrading from v0.1.3**: See [README.md - Upgrade Guide](https://github.com/beersoccer/mem0_dify_plugin/blob/main/README.md#-upgrade-guide) for detailed upgrade instructions and installation time optimization details.
- **Credential Migration**: 
  - **Code-level backward compatibility**: Code can read both old `*_json` and new `*_secret` fields
  - **UI-level change**: New `*_secret` fields are shown in UI, old `*_json` fields are hidden
  - **Recommended**: For cleanest upgrade, delete old credentials and reconfigure using `*_secret` fields
  - **Note**: v0.1.8+ removes old fields completely, so you must delete and reconfigure before upgrading to v0.1.8+
- **Performance Impact**: Write operations may be rejected when system is overloaded (queue > 5x concurrency limit)
- **Monitoring**: Watch for "Background task queue overloaded" warnings in logs

#### 🐛 Bug Fixes
- Fixed credential default value type errors: numeric defaults changed to strings to comply with Dify's `text-input` type requirements
- Fixed recurring indentation errors in tool files that caused `IndentationError` during plugin installation
- Improved credential upgrade compatibility: Code can read both old and new field names, but UI only shows new fields

#### 🎯 Performance Recommendations
1. **Monitor Queue Length**: Check logs for pending task counts
2. **Adjust Configuration**: If overload warnings are frequent:
   - Increase `max_concurrent_memory_operations` (current: 40, recommend > 20 for production)
   - Use faster models (cloud API instead of self-hosted models)
   - Reduce request rate or use sync mode for testing
3. **CPU Optimization**: The task tracking and overload protection significantly reduce CPU usage by preventing unbounded task accumulation

---

## Version 0.1.6 (2025-12-08)

### 🔒 Security & Configuration Enhancements

This release focuses on security improvements for sensitive configuration data and adds user-configurable performance parameters for better production environment control.

#### Highlights
- **Security Enhancement**: All sensitive configuration fields now use `secret-input` type instead of `text-input`
  - `local_llm_json` - Now hidden in UI to protect API keys and sensitive credentials
  - `local_embedder_json` - Now hidden in UI to protect API keys
  - `local_vector_db_json` - Now hidden in UI to protect database credentials
  - `local_graph_db_json` - Now hidden in UI to protect graph database credentials
  - `local_reranker_json` - Now hidden in UI to protect reranker API keys
- **User-Configurable Performance Parameters**: Added three new optional configuration parameters
  - `max_concurrent_memory_operations` - Maximum concurrent async Mem0 operations per process (default: 40)
  - `pgvector_min_connections` - Minimum PGVector connection pool size (default: 10)
  - `pgvector_max_connections` - Maximum PGVector connection pool size (default: 40)
- **Production Recommendations**: Added guidance for production environments
  - `max_concurrent_memory_operations` should be greater than 20 for production
  - `pgvector_max_connections` should match `max_concurrent_memory_operations` for optimal performance

#### 🔧 Technical Details
- **Security Improvements**:
  - Changed all JSON configuration fields from `text-input` to `secret-input` type
  - Sensitive information (API keys, passwords, tokens) is now hidden in Dify UI
  - No functional changes, only UI display behavior
- **New Configuration Functions**:
  - Added `get_int_credential()` function in `utils/config_builder.py` for safe integer parsing
  - Handles string-to-integer conversion with validation and fallback to defaults
  - Validates positive integer values and logs warnings for invalid inputs
- **PGVector Connection Pool Configuration**:
  - Modified `_normalize_pgvector_config()` to accept user-configurable min/max connections
  - User-provided values override default constants when specified
  - Maintains backward compatibility with existing configurations
- **Async Client Concurrency Control**:
  - `AsyncLocalClient` now reads `max_concurrent_memory_operations` from credentials
  - Semaphore size dynamically adjusts based on user configuration
  - Falls back to `MAX_CONCURRENT_MEMORY_OPERATIONS` constant if not configured

#### 📝 Files Changed
- **Modified Files**:
  - `provider/mem0ai.yaml` - Changed all JSON config fields to `secret-input`, added three new performance parameters
  - `utils/config_builder.py` - Added `get_int_credential()` function, modified `_normalize_pgvector_config()` to accept user config
  - `utils/mem0_client.py` - Modified `AsyncLocalClient.__init__()` to use user-configured concurrency limit

#### ⚠️ Migration Notes

**🔴 CRITICAL: Credentials Configuration Incompatibility**

**⚠️ BREAKING CHANGE**: This version introduces **incompatible changes** to credentials configuration. You **MUST** delete old credentials before upgrading.

**Configuration Field Changes:**
- **Field Type Changed**: Changed from `text-input` to `secret-input` type
- **Field Names Changed**: Changed from `*_json` to `*_secret` (e.g., `local_llm_json` → `local_llm_json_secret`)
- **Incompatible**: Dify framework **cannot automatically migrate** between different field types
- **Result**: Old credentials will cause **Internal Server Error** after upgrade

**Required Upgrade Steps:**
1. **Backup your configuration** (copy all credential values)
2. **Delete old credentials** in Dify UI: `Settings` → `Plugins` → `mem0ai` → `Delete Credentials`
3. **Upgrade the plugin** to v0.1.6+
4. **Reconfigure** using the new `*_secret` fields with the same values you backed up

**⚠️ If you skip deleting old credentials:**
- Plugin will fail to start
- "Internal Server Error" when accessing plugin settings
- Tools will not work
- You must delete and reconfigure anyway

**Other Changes:**
- **UI Changes**: Sensitive configuration fields will now appear as password fields (hidden input) in Dify UI
- **New Optional Parameters**: The three new performance parameters are optional and use sensible defaults if not configured
- **Production Recommendations**: Users are encouraged to configure these parameters based on their workload and infrastructure

#### 🐛 Bug Fixes
- Fixed Dify plugin framework compatibility issue: changed `type: number` to `type: text-input` for numeric configuration fields (Dify framework doesn't support `number` type in credentials)

---

## Version 0.1.5 (2025-11-28)

### 🎯 Search Memory Timestamp Support & Code Refactoring

This release adds timestamp support to search results and refactors common utility functions into a centralized helpers module for better code maintainability.

#### Highlights
- **Search Memory Timestamp Support**: Added `timestamp` field to search results
  - Displays the most recent timestamp from `created_at` or `updated_at` fields
  - Format: `2025-11-03T20:06:27` (second precision, no milliseconds or timezone)
  - Only included in results when at least one timestamp is available
  - Logic: If both `created_at` and `updated_at` exist, returns the more recent one; if only one exists, returns that one; if both are empty, `timestamp` field is not included
- **Code Refactoring**: Created `utils/helpers.py` to centralize common utility functions
  - Abstracted `parse_timeout()` function for unified timeout parameter parsing
  - Abstracted `format_recent_timestamp()` and `parse_iso_timestamp()` for timestamp handling
  - Renamed `utils/timestamp.py` to `utils/helpers.py` for better naming (supports future utility functions)
- **Code Quality Improvements**:
  - Removed unused class imports (`LocalClient`, `AsyncLocalClient`) from all tool files
  - Changed `AsyncLocalClient.ensure_bg_loop()` to instance method call `client.ensure_bg_loop()`
  - Updated comments to remove direct references to `AsyncLocalClient.shutdown()`
  - Fixed indentation errors in multiple tool files (`add_memory.py`, `update_memory.py`, `delete_memory.py`, `delete_all_memories.py`)

#### 🔧 Technical Details
- **Timestamp Formatting**:
  - `format_recent_timestamp()` compares `created_at` and `updated_at` timestamps
  - Returns the most recent timestamp in `YYYY-MM-DDTHH:MM:SS` format
  - Handles ISO8601 timestamp parsing with timezone support
  - Converts timestamps to local timezone before formatting
- **Helper Functions**:
  - `parse_timeout()`: Unified timeout parsing with default value fallback and logging
  - `parse_iso_timestamp()`: Robust ISO8601 timestamp parsing with timezone handling
  - `format_recent_timestamp()`: Timestamp comparison and formatting logic
- **Import Optimization**:
  - Tool files now only import factory functions (`get_local_client`, `get_async_local_client`)
  - Removed direct class imports that were not used
  - Cleaner import statements and better code organization

#### 📝 Files Changed
- **New Files**:
  - `utils/helpers.py` - Common utility functions module
- **Modified Files**:
  - `tools/search_memory.py` - Added timestamp formatting, uses `parse_timeout()` and `format_recent_timestamp()`
  - `tools/get_all_memories.py` - Uses `parse_timeout()`
  - `tools/get_memory.py` - Uses `parse_timeout()`
  - `tools/get_memory_history.py` - Uses `parse_timeout()`
  - `tools/add_memory.py` - Fixed indentation errors
  - `tools/update_memory.py` - Fixed indentation errors
  - `tools/delete_memory.py` - Fixed indentation errors
  - `tools/delete_all_memories.py` - Fixed indentation errors
- **Removed Files**:
  - `utils/timestamp.py` - Renamed to `utils/helpers.py`

#### ⚠️ Migration Notes
- No breaking changes in API or behavior
- Search results now include `timestamp` field when available (backward compatible)
- All existing functionality remains unchanged
- Code refactoring is internal only, no user-facing changes

#### 🐛 Bug Fixes
- Fixed indentation errors in `add_memory.py`, `update_memory.py`, `delete_memory.py`, and `delete_all_memories.py` that caused syntax errors

---

## Version 0.1.4 (2025-11-23)

### 🔍 Logging Investigation & Documentation Update

This release documents logging-related investigations and discussions, with no code changes.

#### Highlights
- **Logging Issue Investigation**: Identified and documented logging output behavior
  - Discovered that logs may appear twice in command line output (JSON format from Dify plugin handler and standard format from Python root logger)
  - Identified Unicode encoding in JSON format logs (Chinese characters displayed as `\uXXXX` format)
  - Investigated potential solutions including disabling logger propagation and custom formatters
- **Documentation Updates**: Updated all markdown files to reflect current version and maintain consistency

#### 🔧 Technical Details
- **Logging Behavior Analysis**:
  - Dify's `plugin_logger_handler` outputs logs in JSON format: `{"event": "log", "data": {"level": "INFO", "message": "...", "timestamp": ...}}`
  - Python's root logger may also output logs in standard format: `INFO:tools.update_memory:...`
  - This can result in duplicate log output when logger propagation is enabled
  - JSON format uses `ensure_ascii=True` by default, causing Unicode characters to be encoded as `\uXXXX`
- **Investigation Notes**:
  - Considered setting `logger.propagate = False` to prevent duplicate logs
  - Considered custom formatter with standard format and timestamp
  - Current implementation uses Dify's official plugin logger handler as-is

#### ⚠️ Known Issues
- Logs may appear twice in command line output (JSON format + standard format)
- JSON format logs display Chinese characters as Unicode escape sequences (`\uXXXX`)
- These are framework-level behaviors from Dify's plugin logger handler

#### 📝 Notes
- No code changes in this release
- Documentation updated to maintain consistency across all markdown files
- Version number incremented to 0.1.4

---

## Version 0.1.3 (2025-11-22)

### 🎯 Logging, Configuration & Database Connection Pool Optimization

This release focuses on improving logging infrastructure, optimizing configuration handling, and enhancing database connection pool management for better production stability.

#### Highlights
- **Unified Logging Configuration**: Implemented centralized logging using Dify's official plugin logger handler (`plugin_logger_handler`) to ensure all logs are properly output to the Dify plugin container
  - Created `utils/logger.py` module with `get_logger()` function for consistent logger initialization
  - All Python modules now use the unified logger configuration
  - Logs are correctly routed to Dify's logging system for better debugging and monitoring
- **Constant Naming Optimization**: Renamed `MAX_CONCURRENT_MEM_ADDS` to `MAX_CONCURRENT_MEMORY_OPERATIONS` to accurately reflect its purpose
  - The constant controls concurrency for all async memory operations (search, add, get, get_all, update, delete, delete_all, history), not just add operations
  - Updated default value from 5 to 40 to support higher concurrency
- **Database Connection Pool Configuration**: Added automatic connection pool settings for pgvector
  - New constants: `PGVECTOR_MIN_CONNECTIONS` (10) and `PGVECTOR_MAX_CONNECTIONS` (40)
  - Connection pool settings are automatically applied when initializing pgvector if not explicitly provided
  - Pool size aligns with `MAX_CONCURRENT_MEMORY_OPERATIONS` to ensure sufficient database connections
- **PGVector Configuration Optimization**: Enhanced pgvector configuration handling according to Mem0 official documentation
  - Properly handles parameter priority: `connection_pool` (highest) > `connection_string` > individual parameters
  - Automatically builds `connection_string` from discrete parameters (dbname, user, password, host, port, sslmode)
  - Cleans up redundant connection parameters based on priority
  - Preserves all valid pgvector config keys (collection_name, embedding_model_dims, diskann, hnsw, etc.)

#### 🔧 Technical Details
- **Logging Infrastructure**:
  - Created `utils/logger.py` with `get_logger(name: str)` function
  - Uses `dify_plugin.config.logger_format.plugin_logger_handler` for proper log routing
  - All tool files, utility modules, and main.py updated to use unified logger
  - Prevents duplicate log handlers with `if not logger.handlers` check
- **Constants Updates**:
  - Renamed `MAX_CONCURRENT_MEM_ADDS` → `MAX_CONCURRENT_MEMORY_OPERATIONS` (default: 40)
  - Added `PGVECTOR_MIN_CONNECTIONS: int = 10`
  - Added `PGVECTOR_MAX_CONNECTIONS: int = 40`
- **PGVector Configuration**:
  - Updated `_normalize_pgvector_config()` to handle three connection methods with proper priority
  - Automatically sets `minconn` and `maxconn` if not provided in user configuration
  - Supports both `connection_string` and discrete parameter forms
  - Validates and preserves all official pgvector config keys

#### ⚠️ Migration Notes
- No breaking changes in API or behavior
- Constant name change: `MAX_CONCURRENT_MEM_ADDS` → `MAX_CONCURRENT_MEMORY_OPERATIONS` (internal only, no user impact)
- Connection pool settings are automatically applied to pgvector configurations
- If custom connection pool settings are needed, they can be explicitly set in pgvector config

#### 🐛 Bug Fixes
- Fixed logging output routing to ensure logs appear in Dify plugin container
- Fixed constant naming to accurately reflect its purpose
- Improved pgvector configuration handling to match Mem0 official documentation

---

## Version 0.1.2 (2025-11-21)

### 🎯 Configurable Timeout & Code Quality Improvements

This release introduces configurable timeout parameters for all read operations and optimizes default timeout values for better performance and reliability.

#### Highlights
- **Configurable Timeout Parameters**: All read operations (Search/Get/Get_All/History) now support user-configurable timeout values through the Dify plugin configuration interface
  - Timeout parameters are set as `form: form` (manual input), not exposed to LLM for inference
  - If not specified, tools use default values from `constants.py`
  - Allows users to customize timeout behavior per tool based on their specific needs
- **Optimized Default Timeouts**: Reduced default timeout values for better responsiveness:
  - `MAX_REQUEST_TIMEOUT`: 120 seconds → **60 seconds**
  - `SEARCH_OPERATION_TIMEOUT`: 60 seconds → **30 seconds**
  - `GET_ALL_OPERATION_TIMEOUT`: 60 seconds → **30 seconds**
  - `GET_OPERATION_TIMEOUT`: 30 seconds → **30 seconds** (unchanged)
  - `HISTORY_OPERATION_TIMEOUT`: 30 seconds → **30 seconds** (unchanged)
- **Code Quality**: Added missing module and class docstrings, fixed formatting issues to comply with Python best practices

#### 🔧 Technical Details
- **Timeout Configuration**:
  - Added `timeout` parameter to `search_memory.yaml`, `get_all_memories.yaml`, `get_memory.yaml`, `get_memory_history.yaml`
  - Parameters are optional and use `form: form` (manual configuration, not LLM inference)
  - Tools read timeout from `tool_parameters.get("timeout")` and fall back to constants if not provided
  - Invalid timeout values are caught and logged with a warning, defaulting to constants
- **Default Timeout Values**:
  - All read operations now default to 30 seconds (previously 60s for Search/Get_All)
  - `MAX_REQUEST_TIMEOUT` reduced to 60 seconds for faster failure detection
- **Code Quality**:
  - Added module docstrings to all tool files
  - Added class docstrings to all tool classes
  - Fixed formatting issues (blank lines after class docstrings)

#### ⚠️ Migration Notes
- No breaking changes in API or behavior
- Default timeout values have changed (60s → 30s for Search/Get_All operations)
- Users can now configure custom timeout values per tool in the Dify plugin configuration interface
- If custom timeout values are needed, they should be set in the tool configuration

#### 🐛 Bug Fixes
- Fixed missing module and class docstrings in tool files
- Fixed formatting issues (missing blank lines after class docstrings)

---

## Version 0.1.1 (2025-11-20)

### 🎯 Production Stability & Timeout Protection

This release addresses critical production issues where tools would hang indefinitely, implementing comprehensive timeout mechanisms and service degradation strategies to ensure reliable operation in production environments.

#### Highlights
- **Timeout Protection**: Added timeout mechanisms for all async read operations (Search/Get/Get_All/History) to prevent indefinite hanging
  - Search Memory: 60 seconds timeout
  - Get All Memories: 60 seconds timeout
  - Get Memory: 30 seconds timeout
  - Get Memory History: 30 seconds timeout
- **Service Degradation**: When operations timeout or encounter errors, the plugin gracefully degrades by:
  - Logging the event with full exception details
  - Cancelling background tasks to prevent resource leaks
  - Returning default/empty results (empty list `[]` for Search/Get_All/History, `None` for Get)
  - Ensuring Dify workflow continues execution without interruption
- **Robust Error Handling**: Enhanced exception handling to catch all error types (network errors, connection failures, SSL errors, etc.), not just specific exceptions
- **Resource Management**: Improved background task cancellation on timeout using `future.cancel()` to prevent hanging tasks and resource leaks

#### 🔧 Technical Details
- **Timeout Implementation**:
  - Added timeout constants in `utils/constants.py`: `SEARCH_OPERATION_TIMEOUT`, `GET_OPERATION_TIMEOUT`, `GET_ALL_OPERATION_TIMEOUT`, `HISTORY_OPERATION_TIMEOUT`
  - Applied timeouts to `future.result(timeout=...)` calls in all async read operations
  - Used `concurrent.futures.TimeoutError` (aliased as `FuturesTimeoutError`) for correct exception handling
  - **Note**: Sync mode has no timeout protection (blocking calls). If timeout protection is needed, use `async_mode=true`
- **Service Degradation**:
  - All tools now initialize result variables with default values before `try` blocks
  - Timeout handlers call `future.cancel()` to prevent background tasks from hanging
  - Exception handlers catch all `Exception` types, not just specific ones
  - Tools return empty/default results on any error to ensure workflow continuity
- **Unified Exception Handling**:
  - Removed redundant outer `except FuturesTimeoutError` blocks (sync mode doesn't throw this exception)
  - Unified exception handling pattern: async mode handles timeout and general exceptions, sync mode handles general exceptions only
  - Both modes implement service degradation (return default/empty results) to ensure workflow continuity
- **Code Quality**:
  - Ensured `ensure_bg_loop()` guarantees a long-lived, reusable event loop
  - Added comprehensive documentation for timeout and service degradation mechanisms
  - Improved error logging with `logger.exception` for detailed stack traces
  - Simplified code structure by removing duplicate exception handling blocks

#### ⚠️ Migration Notes
- No breaking changes in API or behavior
- Tools now have timeout protection, which may cause operations to return empty results if they exceed timeout limits
- Workflows should handle empty results gracefully (which they already should)
- Production environments will benefit from improved stability and reliability

#### 🐛 Bug Fixes
- Fixed production issue where `Search memory` tool would hang indefinitely without proper termination
- Fixed issue where tools would fail without proper error handling, causing workflow interruptions
- Fixed resource leaks from hanging background tasks after timeouts

---

## Version 0.1.0 (2025-11-19)

### 🎯 Smart Memory Management & Robustness

This release transforms the `add_memory` tool into a smart memory manager and significantly improves the plugin's stability by handling edge cases and race conditions.

#### Highlights
- **Smart Memory Management**: The `add_memory` tool description has been updated to reflect its true capability. It leverages Mem0's intelligence to automatically decide whether to add, update, or delete memories based on user interaction context.
- **Robust Error Handling**: Operations on non-existent memories (Get/Update/Delete) now return clear, friendly error messages instead of crashing with internal Python exceptions.
- **Race Condition Protection**: Implemented a multi-layer defense mechanism for `update` and `delete` operations to handle concurrent modifications safely.

#### 🔧 Technical Details
- **Tool Updates**:
  - `add_memory`: Updated YAML description to emphasize intelligent memory management (Add/Update/Delete).
  - `get_all_memories`: Fixed a bug where results were empty due to incorrect parsing of Mem0's dictionary response format.
  - `get_memory`: Added checks for `None` results to prevent `AttributeError`.
  - `update_memory` / `delete_memory`: Added pre-checks and internal `try-except` blocks to catch `AttributeError` caused by Mem0's internal race conditions when operating on deleted memories.
- **Documentation**:
  - Added "Important Notes" section in README/GUIDE about `delete_all` triggering "Resetting index" warnings (normal behavior).
  - Clarified vector store connection settings for Debug vs Production modes.

#### ⚠️ Migration Notes
- No breaking changes in API.
- `add_memory` tool description is updated, but the tool name and label remain "Add Memory".

---

## Version 0.0.9 (2025-11-17)

### 🎯 Unified Return Format & Enhanced Async Operations

This release focuses on standardizing tool outputs and extending non-blocking async behavior to all write operations.

#### Highlights
- **Unified JSON Return Structure**:
  - All tools now return consistent format: `{"status": "SUCCESS/ERROR", "messages": {...}, "results": {...}}`
  - `status`: Operation status (SUCCESS or ERROR)
  - `messages`: Context information (query params, filters, IDs, etc.)
  - `results`: Actual data (memories, history, operation results)
  
- **Enhanced Async Operations**:
  - Write operations (Add/Update/Delete/Delete_All) are now non-blocking in async mode
  - Return ACCEPT messages immediately: `UPDATE_ACCEPT_RESULT`, `DELETE_ACCEPT_RESULT`, `DELETE_ALL_ACCEPT_RESULT`
  - Read operations (Search/Get/Get_All/History) always wait for results
  
- **Standardized Return Fields**:
  - Search/Get/Get_All: `id`, `memory`, `metadata`, `created_at`, `updated_at`
  - History: `memory_id`, `old_memory`, `new_memory`, `event`, `created_at`, `updated_at`, `is_deleted`
  - Removed redundant fields: `hash`, `user_id`, `agent_id`, `run_id` from individual memory objects
  
- **Extended Constants** (`utils/constants.py`):
  - Added `UPDATE_ACCEPT_RESULT`: `{"message": "Memory update has been accepted"}`
  - Added `DELETE_ACCEPT_RESULT`: `{"message": "Memory deletion has been accepted"}`
  - Added `DELETE_ALL_ACCEPT_RESULT`: `{"message": "Batch memory deletion has been accepted"}`
  
- **Complete Documentation**:
  - All methods in `LocalClient` and `AsyncLocalClient` now have comprehensive docstrings
  - Consistent parameter descriptions and return value documentation
  - Clear async vs sync behavior documentation

#### Technical Details
- **Async Mode Behavior**:
  - When `async_mode=true` (default):
    - Add/Update/Delete/Delete_All: Submit to background loop without waiting, return ACCEPT status
    - Search/Get/Get_All/History: Wait for results via `asyncio.run_coroutine_threadsafe().result()`
  - When `async_mode=false`:
    - All operations use `LocalClient` and block until completion
    
- **Error Handling**:
  - All error responses include `"results": []` for consistency
  - Exception types unified: `(ValueError, RuntimeError, TypeError)`

#### Migration Notes
- Tool outputs now use `status` instead of `event` for top-level status indicator
- If your workflow parses tool outputs, update to use the new field names
- Async write operations now return ACCEPT messages instead of actual results

---

## Version 0.0.8 (2025-11-11)

- Add async_mode provider credential (default true) with clear runtime behavior
- Tools route to LocalClient/AsyncLocalClient based on async_mode for all operations
- Provider validation aligns with async_mode
- Docs updated (README/INSTALL/GUIDE/manifest) to reflect async vs sync behavior

## Version 0.0.7 (2025-11-08)

### 🚀 Self-hosted mode, async client, graceful shutdown

This release focuses on stability, self-hosted mode operation, and developer ergonomics.

#### Highlights
- Centralized constants in `utils/constants.py`:
  - `MAX_CONCURRENT_MEMORY_OPERATIONS` (default: 5, renamed from MAX_CONCURRENT_MEM_ADDS)
  - `SEARCH_DEFAULT_TOP_K` (default: 5)
  - `MAX_REQUEST_TIMEOUT` (default: 120)
  - Shared response shapes: `ADD_SKIP_RESULT`, `ADD_ACCEPT_RESULT`
  - `CUSTOM_PROMPT` for memory distillation (optional)
- Background event loop:
  - Single process-wide loop created once and reused
  - Tools dispatch async operations via `asyncio.run_coroutine_threadsafe(...)`
- Graceful shutdown:
  - `AsyncLocalClient.shutdown()` drains pending tasks briefly and stops the loop
  - Registered via `atexit` and SIGTERM/SIGINT in `main.py`
- Non-blocking add:
  - `AddMem0Tool` enqueues add and returns immediately with `{"status": "queued", ...}`
  - Skips empty/blank messages with `{"status": "skipped", "reason": "no messages", ...}`
- Search improvements:
  - Executes on the background loop
  - Returns normalized JSON and a detailed text message for downstream nodes

#### Removals/Cleanups
- SaaS mode and API version parameters removed
- Deprecated `run_async_task` and background task tracking removed
- Input validation for empty messages centralized in tool layer

---

## Version 0.0.3 (2025-10-05)

### 🎉 Major Update: Full Mem0 API v2 Support

This version brings complete support for Mem0's latest API features, including v2 advanced filtering and full CRUD operations.

---

## ✨ New Features

### 📦 6 New Tools Added

1. **Get All Memories** (`get_all_memories`)
   - Retrieve all memories for a user, agent, app, or run
   - Supports pagination with limit parameter
   - Multi-entity filtering support

2. **Get Memory** (`get_memory`)
   - Fetch a specific memory by its ID
   - Returns complete memory details including metadata

3. **Update Memory** (`update_memory`)
   - Update existing memory content
   - Preserves memory metadata and entity associations

4. **Delete Memory** (`delete_memory`)
   - Delete a specific memory by ID
   - Safe deletion with confirmation

5. **Delete All Memories** (`delete_all_memories`)
   - Batch delete memories by entity filters
   - Requires at least one entity ID for safety

6. **Get Memory History** (`get_memory_history`)
   - View complete change history of a memory
   - Shows previous and new values for each change

---

## 🔄 Enhanced Existing Tools

### **Add Memory** (Enhanced)
**New Parameters:**
- `agent_id` - Associate memory with an agent
- `app_id` - Associate memory with an application
- `run_id` - Associate memory with a specific run
- `metadata` - Custom metadata as JSON string
- `output_format` - Choose between v1.0, v1.1, or v2 output formats

**Breaking Changes:**
- `user_id` is now optional (at least one entity ID should be provided)

### **Search Memory** (Enhanced)
**New Parameters:**
- `agent_id` - Filter by agent ID
- `run_id` - Filter by run ID
- `filters` - Advanced AND/OR logic filters (JSON string)
- `top_k` - Maximum number of results

**Advanced Filters Example:**
```json
{
  "AND": [
    {"user_id": "alex"},
    {
      "OR": [
        {"agent_id": "travel_agent"},
        {"agent_id": "food_agent"}
      ]
    }
  ]
}
```

---

## 🌟 Key Improvements

### Multi-Entity Support
All tools now support multiple entity types:
- `user_id` - User-specific memories (required for add_memory)
- `agent_id` - Agent-specific memories
- `run_id` - Run-specific memories

### Metadata Support
- Add custom metadata when creating memories
- Retrieve and filter by metadata
- Supports any JSON-serializable data

### Output Format
- Choose output format (v1.0/v1.1/v2) via `output_format` parameter
- Different formats provide varying levels of detail
- Default is v1.1

### Enhanced Error Handling
- Better error messages for invalid JSON
- Clear validation for required parameters
- HTTP status code specific error handling

---

## 📋 Complete Tool List

### Memory Management (8 Tools)
1. ✅ Add Memory - Create new memories
2. ✅ Search Memory - Search memories with advanced filters
3. ✅ Get All Memories - List all memories
4. ✅ Get Memory - Get single memory details
5. ✅ Update Memory - Modify existing memories
6. ✅ Delete Memory - Remove single memory
7. ✅ Delete All Memories - Batch delete memories
8. ✅ Get Memory History - View memory change history

---

## 🔧 Technical Details

### Self-Hosted Mode Implementation
- This plugin runs in **self-hosted mode** using Mem0 SDK
- All operations use local Mem0 client (not HTTP API)
- Requires local configuration for LLM, Embedder, and Vector DB

### Dependencies
- `mem0` - Mem0 SDK for self-hosted mode
- `dify_plugin` - Dify plugin framework
- Python 3.12

### Configuration Updates
- Updated `provider/mem0.yaml` with all 8 tools
- Updated `manifest.yaml` to version 0.0.3
- Enhanced tool descriptions with self-hosted mode features

---

## 🌍 Internationalization

All new features include complete translations:
- 🇺🇸 English (en_US)
- 🇨🇳 Simplified Chinese (zh_Hans)
- 🇧🇷 Portuguese (pt_BR)
- 🇯🇵 Japanese (ja_JP)

---

## 🚀 Migration Guide

### From v0.0.2 to v0.0.3

**Breaking Changes:**
1. `user_id` in `add_memory` is required
   - **Action**: Always provide `user_id` when adding memories

2. `user_id` in `search_memory` is required
   - **Action**: Always provide `user_id` when searching memories

**Recommended Updates:**
1. Start using `metadata` for richer context
2. Migrate to v2 API for advanced filtering
3. Use entity IDs to organize memories by context

**Backward Compatibility:**
- All v0.0.2 workflows continue to work
- No code changes required for existing implementations
- New parameters are optional

---

## 📚 Usage Examples

### Example 1: Add Memory with Metadata
```json
{
  "user": "I love Italian food",
  "assistant": "Great! I'll remember that.",
  "user_id": "alex",
  "agent_id": "food_assistant",
  "metadata": "{\"category\": \"food_preferences\", \"cuisine\": \"italian\"}"
}
```

### Example 2: Advanced Search with v2 Filters
```json
{
  "query": "What are my food preferences?",
  "version": "v2",
  "filters": "{\"AND\": [{\"user_id\": \"alex\"}, {\"agent_id\": \"food_assistant\"}]}"
}
```

### Example 3: Get All Memories for an Agent
```json
{
  "agent_id": "travel_assistant",
  "limit": 50
}
```

---

## 🐛 Bug Fixes
- Fixed JSON parsing errors with better error messages
- Improved HTTP status code handling
- Enhanced validation for required parameters

---

## 📝 Notes

- Plugin runs in self-hosted mode (no SaaS/API mode)
- All operations use Mem0 SDK (not HTTP API)
- JSON responses include both structured data and human-readable text
- Supports all Mem0 self-hosted mode features

---

## 🙏 Credits

- Based on [Mem0 AI](https://mem0.ai) SDK and documentation
- Compatible with Dify Plugin Framework

---

## 📞 Support

For issues or questions:
- Check the official [Mem0 Documentation](https://docs.mem0.ai)
- Review the tool YAML files for parameter details
- Test with Dify Plugin Debugger

---

**Full Changelog**: v0.0.2 → v0.0.3
