# Plugin Submission Form

Last updated: 2026-04-22

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

This submission updates the Mem0 Dify plugin to **v0.3.0** (self-hosted mode). Key changes are summarized below; detailed release notes and historical context are in [CHANGELOG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CHANGELOG.md).

### Key Updates

- **Checkpoint Reliability** (PR #44): Fixed async-mode resume-cursor restoration (`resume_conversation_cursor`, `resume_run_at`, `resume_start_time` now correctly round-trip through `AsyncCheckpointManager.load()`); switched save order to add-first-then-delete to prevent accidental data loss on write failure
- **Distributed Lock Reliability** (PR #44): `acquire_lock()` now performs read-after-write verification using a new `_load_all_locks()` method; earliest `acquired_at` wins on contention, loser self-deletes; `forget_memories` gains `_clean_expired_locks()` for lock record hygiene
- **Provider Compatibility Gate**: 117 parametrized unit tests covering canonical provider name strings and critical config fields across all mainstream mem0 LLMs, Embedders, Vector DBs, and Rerankers; 28 of these cross-check the mem0 factory registry directly to fail early on version-upgrade provider drift; removed invalid `mistral` provider entry
- **Test Isolation Fix**: Async checkpoint tests refactored to sync `def` + `_run_async()` helper that spawns a dedicated thread and explicitly clears inherited running-loop state, eliminating pytest-asyncio AUTO mode cross-test contamination
- **Test Suite Growth**: Unit tests grew from ~380 to **471 passing** tests

All API keys and credentials are stored locally in the user's Dify instance configuration and are not shared with any third parties. The plugin only communicates with services configured by the user (their LLM, embedding, and database services).

### Privacy Policy

- [x] I confirm that I have prepared and included a privacy policy in my plugin package based on the Plugin Privacy Protection Guidelines

**Privacy Policy Location**: `PRIVACY.md` is included in the plugin package and clearly explains:
- Self-hosted mode operation and data storage
- Information processed by the plugin
- User's complete control over data
- No third-party data sharing
- User's responsibility for data security and compliance