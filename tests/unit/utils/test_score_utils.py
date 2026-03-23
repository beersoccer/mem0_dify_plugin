"""Tests for utils/score_utils.py.

Covers:
- _safe_parse: all edge cases (None, dict passthrough, JSON string, markdown-fenced,
  Python literal, empty, non-dict, unparseable)
- get_score_mode: every supported vector store backend, fallback behaviour,
  config field priority (secret > legacy), markdown-fenced credentials
"""
from __future__ import annotations

import json

import pytest

from utils.score_utils import _safe_parse, get_score_mode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _creds(provider: str, config: dict | None = None, *, secret: bool = True) -> dict:
    """Build a minimal credentials dict for the given vector-store provider."""
    block = {"provider": provider}
    if config:
        block["config"] = config
    raw = json.dumps(block)
    key = "local_vector_db_json_secret" if secret else "local_vector_db_json"
    return {key: raw}


# ===========================================================================
# _safe_parse
# ===========================================================================

class TestSafeParse:
    def test_none_returns_none(self):
        assert _safe_parse(None) is None

    def test_dict_passthrough(self):
        d = {"provider": "pgvector"}
        assert _safe_parse(d) is d

    def test_valid_json_string(self):
        assert _safe_parse('{"provider": "qdrant"}') == {"provider": "qdrant"}

    def test_markdown_fenced_json(self):
        raw = "```json\n{\"provider\": \"elasticsearch\"}\n```"
        assert _safe_parse(raw) == {"provider": "elasticsearch"}

    def test_markdown_fenced_no_lang(self):
        raw = "```\n{\"provider\": \"redis\"}\n```"
        assert _safe_parse(raw) == {"provider": "redis"}

    def test_python_literal_fallback(self):
        # ast.literal_eval handles single-quoted dicts
        raw = "{'provider': 'chroma', 'config': {}}"
        result = _safe_parse(raw)
        assert result == {"provider": "chroma", "config": {}}

    def test_empty_string_returns_none(self):
        assert _safe_parse("") is None

    def test_whitespace_only_returns_none(self):
        assert _safe_parse("   ") is None

    def test_non_dict_json_returns_none(self):
        assert _safe_parse("[1, 2, 3]") is None

    def test_unparseable_string_returns_none(self):
        assert _safe_parse("not json at all !!!") is None

    def test_nested_config_preserved(self):
        raw = json.dumps({"provider": "milvus", "config": {"metric_type": "COSINE"}})
        result = _safe_parse(raw)
        assert result == {"provider": "milvus", "config": {"metric_type": "COSINE"}}


# ===========================================================================
# get_score_mode – distance backends
# ===========================================================================

class TestGetScoreModeDistance:
    """Backends that return raw distances (lower = more similar)."""

    def test_pgvector(self):
        assert get_score_mode(_creds("pgvector")) == "distance"

    def test_pgvector_legacy_key(self):
        """local_vector_db_json fallback when secret key is absent."""
        creds = _creds("pgvector", secret=False)
        assert get_score_mode(creds) == "distance"

    def test_azure_mysql(self):
        assert get_score_mode(_creds("azure_mysql")) == "distance"

    def test_milvus_l2_default(self):
        """Milvus default metric_type is L2 → distance."""
        assert get_score_mode(_creds("milvus")) == "distance"

    def test_milvus_l2_explicit(self):
        assert get_score_mode(_creds("milvus", {"metric_type": "L2"})) == "distance"

    def test_milvus_l2_lowercase(self):
        """metric_type comparison is case-insensitive (uppercased internally)."""
        assert get_score_mode(_creds("milvus", {"metric_type": "l2"})) == "distance"

    def test_faiss_euclidean_default(self):
        """FAISS default distance_strategy is euclidean → distance."""
        assert get_score_mode(_creds("faiss")) == "distance"

    def test_faiss_euclidean_explicit(self):
        assert get_score_mode(_creds("faiss", {"distance_strategy": "euclidean"})) == "distance"

    def test_faiss_euclidean_uppercase(self):
        """distance_strategy comparison is case-insensitive (lowercased internally)."""
        assert get_score_mode(_creds("faiss", {"distance_strategy": "EUCLIDEAN"})) == "distance"


# ===========================================================================
# get_score_mode – similarity backends
# ===========================================================================

class TestGetScoreModeSimilarity:
    """Backends that return similarity/relevance scores (higher = better)."""

    # Milvus alternative metrics
    def test_milvus_cosine(self):
        assert get_score_mode(_creds("milvus", {"metric_type": "COSINE"})) == "similarity"

    def test_milvus_ip(self):
        assert get_score_mode(_creds("milvus", {"metric_type": "IP"})) == "similarity"

    def test_milvus_cosine_lowercase(self):
        assert get_score_mode(_creds("milvus", {"metric_type": "cosine"})) == "similarity"

    # FAISS alternative strategies
    def test_faiss_inner_product(self):
        assert (
            get_score_mode(_creds("faiss", {"distance_strategy": "inner_product"}))
            == "similarity"
        )

    def test_faiss_cosine(self):
        assert get_score_mode(_creds("faiss", {"distance_strategy": "cosine"})) == "similarity"

    # Search / cloud backends
    def test_elasticsearch(self):
        assert get_score_mode(_creds("elasticsearch")) == "similarity"

    def test_azure_ai_search(self):
        assert get_score_mode(_creds("azure_ai_search")) == "similarity"

    def test_qdrant(self):
        assert get_score_mode(_creds("qdrant")) == "similarity"

    def test_chroma(self):
        assert get_score_mode(_creds("chroma")) == "similarity"

    def test_pinecone(self):
        assert get_score_mode(_creds("pinecone")) == "similarity"

    def test_weaviate(self):
        assert get_score_mode(_creds("weaviate")) == "similarity"

    def test_mongodb(self):
        assert get_score_mode(_creds("mongodb")) == "similarity"

    def test_redis(self):
        assert get_score_mode(_creds("redis")) == "similarity"

    def test_opensearch(self):
        assert get_score_mode(_creds("opensearch")) == "similarity"

    def test_supabase(self):
        assert get_score_mode(_creds("supabase")) == "similarity"

    def test_unknown_provider_fallback_to_similarity(self):
        """Unknown provider defaults to similarity (safe catch-all)."""
        assert get_score_mode(_creds("some_future_db")) == "similarity"


# ===========================================================================
# get_score_mode – fallback / edge cases
# ===========================================================================

class TestGetScoreModeFallback:
    def test_empty_credentials(self):
        """No vector DB config → fallback to 'distance' for backward compat."""
        assert get_score_mode({}) == "distance"

    def test_unparseable_json(self):
        assert get_score_mode({"local_vector_db_json_secret": "not-json"}) == "distance"

    def test_missing_provider_key(self):
        """Parseable JSON but no 'provider' field → distance fallback."""
        raw = json.dumps({"config": {"metric_type": "COSINE"}})
        assert get_score_mode({"local_vector_db_json_secret": raw}) == "distance"

    def test_secret_key_takes_precedence_over_legacy(self):
        """local_vector_db_json_secret wins over local_vector_db_json."""
        secret_raw = json.dumps({"provider": "pgvector"})     # distance
        legacy_raw = json.dumps({"provider": "qdrant"})        # similarity
        creds = {
            "local_vector_db_json_secret": secret_raw,
            "local_vector_db_json": legacy_raw,
        }
        assert get_score_mode(creds) == "distance"

    def test_legacy_key_used_when_no_secret(self):
        legacy_raw = json.dumps({"provider": "qdrant"})
        creds = {"local_vector_db_json": legacy_raw}
        assert get_score_mode(creds) == "similarity"

    def test_markdown_fenced_credentials(self):
        raw = "```json\n{\"provider\": \"pgvector\"}\n```"
        assert get_score_mode({"local_vector_db_json_secret": raw}) == "distance"

    def test_provider_name_case_insensitive(self):
        """Provider names are lowercased before comparison."""
        assert get_score_mode(_creds("PgVector")) == "distance"
        assert get_score_mode(_creds("Qdrant")) == "similarity"
        assert get_score_mode(_creds("Milvus", {"metric_type": "L2"})) == "distance"

    def test_dict_passed_directly_as_credentials_value(self):
        """Credentials value may already be a parsed dict (not a JSON string)."""
        raw = {"provider": "qdrant", "config": {}}
        assert get_score_mode({"local_vector_db_json_secret": raw}) == "similarity"

    def test_config_override_empty_creds(self):
        """config_override mode passes empty {} credentials → distance fallback."""
        assert get_score_mode({}) == "distance"

    @pytest.mark.parametrize("provider", [
        "pgvector", "azure_mysql",
    ])
    def test_distance_providers_parametrized(self, provider):
        assert get_score_mode(_creds(provider)) == "distance"

    @pytest.mark.parametrize("provider", [
        "elasticsearch", "azure_ai_search", "qdrant",
        "chroma", "pinecone", "weaviate",
        "mongodb", "redis", "opensearch", "supabase",
    ])
    def test_similarity_providers_parametrized(self, provider):
        assert get_score_mode(_creds(provider)) == "similarity"
