from __future__ import annotations


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


