# Plugin Submission Form

Last updated: 2026-03-23

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

This submission updates the Mem0 Dify plugin (self-hosted mode). Key changes are summarized below; detailed release notes and historical context are in [CHANGELOG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CHANGELOG.md).

### Key Updates

- **Score Semantics Unification**: Added automatic score mode inference (`distance` / `similarity`) and unified search outputs to stable 0-1 similarity across vector backends
- **Memory Lifecycle Maintenance**: Added access-log-driven forgetting plus new `forget_memories` maintenance workflow with `dry_run` preview support
- **Retention Controls & Isolation Fix**: Added `memory_ttl_days` / `checkpoint_ttl_days` and fixed checkpoint app-scope isolation with `agent_id=app_id`

All API keys and credentials are stored locally in the user's Dify instance configuration and are not shared with any third parties. The plugin only communicates with services configured by the user (their LLM, embedding, and database services).

### Privacy Policy

- [x] I confirm that I have prepared and included a privacy policy in my plugin package based on the Plugin Privacy Protection Guidelines

**Privacy Policy Location**: `PRIVACY.md` is included in the plugin package and clearly explains:
- Self-hosted mode operation and data storage
- Information processed by the plugin
- User's complete control over data
- No third-party data sharing
- User's responsibility for data security and compliance