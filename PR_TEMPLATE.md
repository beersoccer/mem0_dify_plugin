# Plugin Submission Form

Last updated: 2026-02-08

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

This version update (v0.2.7) focuses on checkpoint windowing, resume accuracy, and consistent checkpoint updates to prevent duplicate or missed processing. The plugin integrates [Mem0 AI](https://mem0.ai)'s intelligent memory layer into Dify, providing comprehensive memory management capabilities for AI applications. The plugin operates exclusively in **self-hosted mode**, allowing users to configure and manage their own LLM, embedding models, vector databases, graph databases, and rerankers.

### What's New in v0.2.7:

- **Windowed checkpoint scanning**: Conversations are processed only within `[start_time, run_at]` to avoid missing updates
- **Resume cursor accuracy**: Resume cursors are only set when additional pages exist, preventing false caps
- **Consistent checkpoint updates**: Normalized message timestamps and unified checkpoint updates reduce reprocessing

### Previous Updates in v0.2.6:

- **Resume-safe extraction at conversation caps**: Checkpoints store resume cursors and defer task success to prevent silent skips on capped runs
- **Richer task status visibility**: `check_extraction_status` reports time range, duration, and processed vs scanned counters with local-time timestamps
- **Cleaner extraction writes**: Extraction writes pass `agent_id=app_id` and tag `memory_origin` for implicit memories

### Previous Updates in v0.2.5:

- **🧩 LLM Compatibility Shim (2026-02-04)**: Added `_parse_response` compatibility patch for structured LLM providers to reduce parsing errors; keepalive now uses provider-agnostic `generate_response()` without strict args for broader model compatibility
- **🧠 Sync Subtype Client Reuse**: Subtype clients accept config overrides to avoid manual Memory swapping; pool-sharing logic improves resource isolation while keeping prompts per subtype
- **🧪 Test & Tooling Stability**: `DifyClient` enforces `/v1` base URL format; integration tests normalize base URLs; cleanup script supports `DIFY_USER_IDS` and ensures client resources are closed

For full historical details, see [CHANGELOG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CHANGELOG.md).

All API keys and credentials are stored locally in the user's Dify instance configuration and are not shared with any third parties. The plugin only communicates with services configured by the user (their LLM, embedding, and database services).

### Privacy Policy

- [x] I confirm that I have prepared and included a privacy policy in my plugin package based on the Plugin Privacy Protection Guidelines

**Privacy Policy Location**: `PRIVACY.md` is included in the plugin package and clearly explains:
- Self-hosted mode operation and data storage
- Information processed by the plugin
- User's complete control over data
- No third-party data sharing
- User's responsibility for data security and compliance