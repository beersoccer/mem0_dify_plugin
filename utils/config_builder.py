"""Build Mem0 local configuration from provider credentials.

This module parses simplified JSON blocks for self-hosted mode:
- local_llm_json_secret (required)
- local_embedder_json_secret (required)
- local_vector_db_json_secret (required)
- local_reranker_json_secret (optional)
- local_graph_db_json_secret (optional)

Each is expected to be a JSON object with at least {"provider": ..., "config": {...}}.

Note: Legacy fields (local_llm_json, etc.) are still supported for backward compatibility
but are deprecated and removed from the configuration UI.
"""

from __future__ import annotations

import ast
import hashlib
import json
import threading
from typing import Any

from .helpers import strip_code_fences
from .logger import get_logger
from .pgvector_config import normalize_pgvector_config

logger = get_logger(__name__)


def _raise_config_error(msg: str) -> None:
    """Raise a ValueError for configuration errors with logging.

    Args:
        msg: Error message to log and raise.

    """
    logger.error(msg)
    raise ValueError(msg)


def _parse_json_text(text: str, field_name: str) -> dict[str, Any]:
    """Parse JSON text with fallback to Python literal evaluation.

    Args:
        text: JSON text to parse.
        field_name: Field name for error messages.

    Returns:
        Parsed dictionary.

    Raises:
        ValueError: If parsing fails or result is not a dict.

    """
    # First try strict JSON
    try:
        data = json.loads(text)
        # Verify that json.loads returned a dict (it could return list, str, etc.)
        if not isinstance(data, dict):
            msg = f"{field_name} must be a JSON object"
            _raise_config_error(msg)
    except (json.JSONDecodeError, TypeError):
        # Fallback: accept Python-literal style dicts (single quotes, etc.)
        try:
            candidate = ast.literal_eval(text)
            if not isinstance(candidate, dict):
                msg = f"{field_name} must be a JSON object"
                _raise_config_error(msg)
            data = candidate
        except Exception:
            msg = f"{field_name} is not valid JSON"
            logger.exception("Failed to parse %s", field_name)
            _raise_config_error(msg)
    return data


def _validate_parsed_data(data: dict[str, Any], field_name: str) -> None:
    """Validate that parsed data has required structure.

    Args:
        data: Parsed data dictionary.
        field_name: Field name for error messages.

    Raises:
        ValueError: If validation fails.

    """
    if not isinstance(data, dict):
        msg = f"{field_name} must be a JSON object"
        _raise_config_error(msg)
    provider = data.get("provider")
    cfg = data.get("config")
    if not provider or not isinstance(cfg, dict):
        msg = f"{field_name} must include 'provider' and 'config' object"
        _raise_config_error(msg)


def _parse_json_block(raw: str | dict[str, Any] | None, field_name: str) -> dict[str, Any] | None:
    """Parse a JSON block from string or dict.

    Args:
        raw: Raw input (string, dict, or None).
        field_name: Field name for error messages.

    Returns:
        Parsed dictionary or None if input is None/empty.

    Raises:
        ValueError: If parsing or validation fails.

    """
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
        text = strip_code_fences(text)
        data = _parse_json_text(text, field_name)
    _validate_parsed_data(data, field_name)
    provider = data.get("provider")
    logger.debug("Successfully parsed %s with provider: %s", field_name, provider)
    return data


def _get_credential_value(
    credentials: dict[str, Any],
    primary_key: str,
    fallback_key: str,
) -> str | dict[str, Any] | None:
    """Read credential value with backward-compatible fallback.

    Prefer `primary_key` (new fields) and fall back to `fallback_key` (legacy fields).
    """
    primary = credentials.get(primary_key)
    if primary is not None and primary != "":
        return primary
    return credentials.get(fallback_key)


# Cache for built configurations to avoid redundant logging
_built_config_cache: dict[str, dict[str, Any]] = {}
_build_config_lock = threading.Lock()


def _get_cache_key(credentials: dict[str, Any]) -> str | None:
    """Generate a cache key from credentials.

    Args:
        credentials: Provider credentials dictionary.

    Returns:
        Cache key string or None if serialization fails.

    """
    try:
        cred_str = json.dumps(credentials, sort_keys=True)
        return hashlib.md5(cred_str.encode()).hexdigest()  # noqa: S324
    except Exception:  # noqa: BLE001
        # If serialization fails, don't cache
        return None


def _parse_required_configs(
    credentials: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Parse and validate required configuration blocks.

    Args:
        credentials: Provider credentials dictionary.

    Returns:
        Tuple of (llm, embedder, vector_store) configurations.

    Raises:
        ValueError: If any required configuration is missing.

    """
    llm = _parse_json_block(
        _get_credential_value(credentials, "local_llm_json_secret", "local_llm_json"),
        "local_llm_json",
    )
    embedder = _parse_json_block(
        _get_credential_value(credentials, "local_embedder_json_secret", "local_embedder_json"),
        "local_embedder_json",
    )
    vector_store = _parse_json_block(
        _get_credential_value(
            credentials,
            "local_vector_db_json_secret",
            "local_vector_db_json",
        ),
        "local_vector_db_json",
    )

    if llm is None:
        msg = "LLM configuration (local_llm_json_secret) is required in self-hosted mode"
        _raise_config_error(msg)
    if embedder is None:
        msg = (
            "Embedder configuration (local_embedder_json_secret) "
            "is required in self-hosted mode"
        )
        _raise_config_error(msg)
    if vector_store is None:
        msg = (
            "Vector Database configuration (local_vector_db_json_secret) "
            "is required in self-hosted mode"
        )
        _raise_config_error(msg)

    return llm, embedder, vector_store


def _normalize_vector_store(vector_store: dict[str, Any]) -> None:
    """Normalize vector store configuration, especially for pgvector.

    Note: Only pgvector requires special processing (connection pool optimization).
    All other vector store providers (qdrant, chroma, pinecone, mongodb, milvus,
    weaviate, faiss, redis, elasticsearch, opensearch, azure_ai_search, etc.)
    are fully supported and their configs are passed through as-is to mem0.
    Connection pool settings (minconn, maxconn) should be specified
    in the vector_store config JSON, same level as connection_string.

    Args:
        vector_store: Vector store configuration dictionary (modified in-place).

    """
    if (
        vector_store.get("provider") == "pgvector"
        and isinstance(vector_store.get("config"), dict)
    ):
        logger.debug("Normalizing pgvector configuration")
        vector_store["config"] = normalize_pgvector_config(
            vector_store["config"],
        )  # type: ignore[index]
    else:
        provider = vector_store.get("provider") if vector_store else "unknown"
        logger.debug(
            "Vector store provider '%s' - config passed through without modification",
            provider,
        )


def _build_config_dict(
    llm: dict[str, Any],
    embedder: dict[str, Any],
    vector_store: dict[str, Any],
    credentials: dict[str, Any],
) -> dict[str, Any]:
    """Build the final configuration dictionary.

    Args:
        llm: LLM configuration.
        embedder: Embedder configuration.
        vector_store: Vector store configuration.
        credentials: Provider credentials dictionary.

    Returns:
        Complete configuration dictionary.

    """
    reranker = _parse_json_block(
        _get_credential_value(credentials, "local_reranker_json_secret", "local_reranker_json"),
        "local_reranker_json",
    )
    graph_store = _parse_json_block(
        _get_credential_value(credentials, "local_graph_db_json_secret", "local_graph_db_json"),
        "local_graph_db_json",
    )

    config: dict[str, Any] = {
        "llm": llm,
        "embedder": embedder,
        "vector_store": vector_store,
    }
    if reranker:
        config["reranker"] = reranker
        logger.debug("Reranker configuration included")
    if graph_store:
        config["graph_store"] = graph_store
        logger.debug("Graph store configuration included")

    return config


def build_local_mem0_config(credentials: dict[str, Any]) -> dict[str, Any]:
    """Construct mem0 local config dict from simplified JSON credential blocks.

    Required: local_llm_json_secret, local_embedder_json_secret, local_vector_db_json_secret
    Optional: local_reranker_json_secret, local_graph_db_json_secret

    Vector Store Support:
    - All mem0-supported vector stores are compatible (qdrant, chroma, pinecone, pgvector,
      mongodb, milvus, weaviate, faiss, redis, elasticsearch, opensearch, azure_ai_search, etc.)
    - Only pgvector receives special processing (connection pool optimization)
    - Other vector store configs are passed through as-is to mem0

    Note: Legacy fields (local_llm_json, etc.) are still supported for backward compatibility
    but are deprecated and removed from the configuration UI.
    """
    cache_key = _get_cache_key(credentials)

    # Check cache first
    if cache_key and cache_key in _built_config_cache:
        return _built_config_cache[cache_key]

    # Build new config
    with _build_config_lock:
        # Double-check after acquiring lock
        if cache_key and cache_key in _built_config_cache:
            return _built_config_cache[cache_key]

        logger.debug("Building Mem0 local configuration from credentials")

        llm, embedder, vector_store = _parse_required_configs(credentials)
        _normalize_vector_store(vector_store)
        config = _build_config_dict(llm, embedder, vector_store, credentials)

        logger.debug("Mem0 local configuration built successfully")

        # Cache the config if we have a valid cache key
        if cache_key:
            _built_config_cache[cache_key] = config

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
