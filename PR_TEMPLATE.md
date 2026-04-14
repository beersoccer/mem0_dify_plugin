# Plugin Submission Form

Last updated: 2026-04-14

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

This submission updates the Mem0 Dify plugin to **v0.2.11** (self-hosted mode). Key changes are summarized below; detailed release notes and historical context are in [CHANGELOG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CHANGELOG.md).

### Key Updates

- **AsyncMemory Compatibility Fix**: Added a compatibility layer for old/new `AsyncMemory.from_config()` semantics so `async_mode=true` no longer fails on newer mem0 releases
- **Supported Mem0 Version Range**: Aligned dependency declarations and documentation to support `mem0ai>=1.0.2,<=1.0.11`
- **Regression Tests & Release Docs**: Added targeted compatibility/validation tests and refreshed configuration, changelog, privacy, and submission documents for this release

All API keys and credentials are stored locally in the user's Dify instance configuration and are not shared with any third parties. The plugin only communicates with services configured by the user (their LLM, embedding, and database services).

### Privacy Policy

- [x] I confirm that I have prepared and included a privacy policy in my plugin package based on the Plugin Privacy Protection Guidelines

**Privacy Policy Location**: `PRIVACY.md` is included in the plugin package and clearly explains:
- Self-hosted mode operation and data storage
- Information processed by the plugin
- User's complete control over data
- No third-party data sharing
- User's responsibility for data security and compliance