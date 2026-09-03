from __future__ import annotations

import pytest


def test_pgvector_defaults_to_hnsw_when_index_not_specified() -> None:
    """If neither hnsw nor diskann is specified, plugin should default to hnsw.

    This is a safety net to match Mem0's defaults and to avoid accidental "no index"
    setups when users only provide connection settings.
    """
    from utils.pgvector_config import normalize_pgvector_config

    cfg = {
        # Avoid creating a real network-backed pool in unit tests
        "connection_pool": object(),
        "collection_name": "mem0",
        "embedding_model_dims": 1536,
        # NOTE: intentionally omit `hnsw` and `diskann`
    }

    normalized = normalize_pgvector_config(cfg)
    assert normalized["hnsw"] is True
    assert normalized["diskann"] is False


def test_pgvector_high_dimensions_default_to_exact_search() -> None:
    """4096-dimensional vectors must not create an unsupported HNSW index."""
    from utils.pgvector_config import normalize_pgvector_config

    cfg = {
        "connection_pool": object(),
        "collection_name": "mem0_local_test",
        "embedding_model_dims": 4096,
    }

    normalized = normalize_pgvector_config(cfg)

    assert normalized["hnsw"] is False
    assert normalized["diskann"] is False


def test_pgvector_rejects_explicit_high_dimension_hnsw() -> None:
    """An explicit unsupported HNSW request should fail with an actionable error."""
    from utils.pgvector_config import normalize_pgvector_config

    cfg = {
        "connection_pool": object(),
        "collection_name": "mem0_local_test",
        "embedding_model_dims": 4096,
        "hnsw": True,
        "diskann": False,
    }

    with pytest.raises(ValueError, match="at most 2000 dimensions"):
        normalize_pgvector_config(cfg)
