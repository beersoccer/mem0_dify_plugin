"""Build Mem0 local configuration from provider credentials.

This module parses simplified JSON blocks for local mode:
- local_llm_json
- local_embedder_json
- local_reranker_json (optional)
- local_vector_db_json
- local_graph_db_json (optional)

Each is expected to be a JSON object with at least {"provider": ..., "config": {...}}.
"""

from __future__ import annotations

import ast
import json
from typing import Any
from urllib.parse import quote_plus


class ConfigError(ValueError):
    pass


def _parse_json_block(raw: str | dict[str, Any] | None, field_name: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    # Accept already-parsed dicts from upstream runtimes
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw).strip()
        if text == "":
            return None
        # Strip code fences if user pasted with ```json ... ```
        if text.startswith("```"):
            lines = text.splitlines()
            # Drop first fence line and possible trailing fence
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # First try strict JSON
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            # Fallback: accept Python-literal style dicts (single quotes, etc.)
            try:
                candidate = ast.literal_eval(text)
                if not isinstance(candidate, dict):
                    msg = f"{field_name} must be a JSON object"
                    raise ConfigError(msg)
                data = candidate
            except Exception as e:
                msg = f"{field_name} is not valid JSON: {e}"
                raise ConfigError(msg) from e
    if not isinstance(data, dict):
        msg = f"{field_name} must be a JSON object"
        raise ConfigError(msg)
    provider = data.get("provider")
    cfg = data.get("config")
    if not provider or not isinstance(cfg, dict):
        msg = f"{field_name} must include 'provider' and 'config' object"
        raise ConfigError(msg)
    return data


def _normalize_pgvector_config(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize pgvector config to use a single connection_string if needed.

    Supports two forms:
    - Direct: {"connection_string": "postgresql://user:pass@host:port/dbname?sslmode=..."}
    - Discrete: {"dbname": ..., "user": ..., "password": ..., "host": ..., "port": ..., "sslmode": ...}
    """
    # If a usable connection string is already provided, keep it
    if "connection_string" in config and isinstance(config["connection_string"], str):
        return config

    dbname = config.get("dbname") or config.get("database") or ""
    user = config.get("user") or ""
    password = config.get("password") or ""
    host = config.get("host") or "localhost"
    port = str(config.get("port") or "5432")
    sslmode = config.get("sslmode")  # e.g., "disable" | "require"

    if not dbname or not user:
        # If insufficient fields, return as-is; Mem0 may handle other forms.
        return config

    user_enc = quote_plus(str(user))
    pwd_enc = quote_plus(str(password))
    # psycopg2 accepts postgresql:// URI; do NOT include '+psycopg2'
    dsn = f"postgresql://{user_enc}:{pwd_enc}@{host}:{port}/{dbname}"
    if sslmode:
        dsn = f"{dsn}?sslmode={quote_plus(str(sslmode))}"

    normalized: dict[str, Any] = {"connection_string": dsn}
    # Preserve optional tuning keys if present
    for key in ("collection_name", "embedding_model_dims", "metric"):
        if key in config and config[key] is not None:
            normalized[key] = config[key]
    return normalized


def build_local_mem0_config(credentials: dict[str, Any]) -> dict[str, Any]:
    """Construct mem0 local config dict from simplified JSON credential blocks.

    Required: local_llm_json, local_embedder_json, local_vector_db_json
    Optional: local_reranker_json, local_graph_db_json
    """
    llm = _parse_json_block(credentials.get("local_llm_json"), "local_llm_json")
    embedder = _parse_json_block(credentials.get("local_embedder_json"), "local_embedder_json")
    vector_store = _parse_json_block(credentials.get("local_vector_db_json"), "local_vector_db_json")

    if llm is None:
        msg = "LLM configuration (local_llm_json) is required in Local mode"
        raise ConfigError(msg)
    if embedder is None:
        msg = "Embedder configuration (local_embedder_json) is required in Local mode"
        raise ConfigError(msg)
    if vector_store is None:
        msg = "Vector Database configuration (local_vector_db_json) is required in Local mode"
        raise ConfigError(msg)

    # Normalize pgvector config shape if necessary
    if (vector_store.get("provider") == "pgvector" and isinstance(vector_store.get("config"), dict)):
        vector_store["config"] = _normalize_pgvector_config(vector_store["config"])  # type: ignore[index]

    reranker = _parse_json_block(credentials.get("local_reranker_json"), "local_reranker_json")
    graph_store = _parse_json_block(credentials.get("local_graph_db_json"), "local_graph_db_json")

    config: dict[str, Any] = {
        "llm": llm,
        "embedder": embedder,
        "vector_store": vector_store,
    }
    if reranker:
        config["reranker"] = reranker
    if graph_store:
        config["graph_store"] = graph_store

    return config


def is_async_mode(credentials: dict[str, Any]) -> bool:
    """Read async_mode from credentials and coerce to boolean.

    Defaults to True (异步模式). Accepts common truthy/falsey string values.
    """
    value = credentials.get("async_mode")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "y", "on"}:
            return True
        if text in {"false", "0", "no", "n", "off"}:
            return False
    # Default: async enabled
    return True
