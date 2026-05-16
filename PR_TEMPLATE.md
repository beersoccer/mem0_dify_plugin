# Plugin Submission Form

Last updated: 2026-05-16

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

This submission updates the Mem0 Dify plugin to **v0.3.1** (self-hosted mode). Key changes are summarized below; detailed release notes and historical context are in [CHANGELOG.md](https://github.com/beersoccer/mem0_dify_plugin/blob/main/CHANGELOG.md).

### Key Updates

- **Windows Debugging Fix** (PR #47, credit: sususweet): Fixed psycopg3 connection errors on Windows caused by gevent's selector conflicting with `ProactorEventLoop`; added `asyncio.WindowsSelectorEventLoopPolicy()` on `win32` at startup; made psycopg dependency platform-conditional (psycopg3 on Linux/macOS, psycopg2 on Windows)
- **Write Timeout Increase** (PR #47): Raised `WRITE_OPERATION_TIMEOUT` from 15 s to 45 s; write operations involve an extra LLM inference step that can exceed 15 s on slower providers, previously causing silent background write failures in async mode
- **Ollama Dependency Fix** (PR #46, credit: sususweet): Added missing `ollama` package to `pyproject.toml` so the API-key validation screen no longer hangs when Ollama is selected as the LLM provider

All API keys and credentials are stored locally in the user's Dify instance configuration and are not shared with any third parties. The plugin only communicates with services configured by the user (their LLM, embedding, and database services).

### Privacy Policy

- [x] I confirm that I have prepared and included a privacy policy in my plugin package based on the Plugin Privacy Protection Guidelines

**Privacy Policy Location**: `PRIVACY.md` is included in the plugin package and clearly explains:
- Self-hosted mode operation and data storage
- Information processed by the plugin
- User's complete control over data
- No third-party data sharing
- User's responsibility for data security and compliance