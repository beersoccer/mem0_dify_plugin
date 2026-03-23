"""Tests for normalize_search_results in utils/mem0_client.py.

Covers:
- distance mode: raw score is a distance → score = 1 - raw, vector_distance = raw
- similarity mode: raw score is relevance → score = clamped raw, vector_distance = 1 - score
- rerank_score priority over score_mode
- edge cases: empty / None input, dict wrapper, non-dict items, field aliases,
  negative scores, scores > 1, score = 0 / 1 boundaries
"""
from __future__ import annotations

import pytest

from utils.mem0_client import normalize_search_results

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _raw(score: float, **extra) -> dict:
    """Build a minimal raw Mem0 result dict."""
    return {"id": "m1", "memory": "hello", "score": score, **extra}


def _assert_invariants(result: dict):
    """score and vector_distance must be complementary and within [0, 1]."""
    assert 0.0 <= result["score"] <= 1.0
    assert 0.0 <= result["vector_distance"] <= 1.0
    assert abs(result["score"] + result["vector_distance"] - 1.0) < 1e-9, (
        f"score={result['score']} + vector_distance={result['vector_distance']} != 1.0"
    )


# ===========================================================================
# Empty / malformed input
# ===========================================================================

class TestEmptyInput:
    def test_none_returns_empty(self):
        assert normalize_search_results(None) == []

    def test_empty_list_returns_empty(self):
        assert normalize_search_results([]) == []

    def test_empty_dict_returns_empty(self):
        assert normalize_search_results({}) == []

    def test_dict_with_empty_results_key(self):
        assert normalize_search_results({"results": []}) == []

    def test_non_dict_items_are_skipped(self):
        results = [{"id": "m1", "memory": "ok", "score": 0.2}, "not a dict", 42]
        out = normalize_search_results(results, score_mode="distance")
        assert len(out) == 1
        assert out[0]["id"] == "m1"


# ===========================================================================
# Input formats
# ===========================================================================

class TestInputFormats:
    def test_list_input(self):
        items = [_raw(0.3)]
        out = normalize_search_results(items, score_mode="distance")
        assert len(out) == 1

    def test_dict_wrapper_with_results_key(self):
        payload = {"results": [_raw(0.3)]}
        out = normalize_search_results(payload, score_mode="distance")
        assert len(out) == 1

    def test_multiple_results_preserved(self):
        items = [_raw(0.1), _raw(0.5), _raw(0.9)]
        out = normalize_search_results(items, score_mode="distance")
        assert len(out) == 3


# ===========================================================================
# distance mode
# ===========================================================================

class TestDistanceMode:
    """Backend returns a distance value; lower is more similar."""

    def test_basic_conversion(self):
        out = normalize_search_results([_raw(0.3)], score_mode="distance")
        r = out[0]
        assert r["vector_distance"] == pytest.approx(0.3)
        assert r["score"] == pytest.approx(0.7)

    def test_perfect_match(self):
        """Distance 0 → similarity 1."""
        out = normalize_search_results([_raw(0.0)], score_mode="distance")
        assert out[0]["score"] == pytest.approx(1.0)
        assert out[0]["vector_distance"] == pytest.approx(0.0)

    def test_worst_match(self):
        """Distance 1 → similarity 0."""
        out = normalize_search_results([_raw(1.0)], score_mode="distance")
        assert out[0]["score"] == pytest.approx(0.0)
        assert out[0]["vector_distance"] == pytest.approx(1.0)

    def test_distance_greater_than_one_clamps_score(self):
        """pgvector cosine distance is in [0, 2]; score must not go negative."""
        out = normalize_search_results([_raw(1.5)], score_mode="distance")
        assert out[0]["score"] == pytest.approx(0.0)

    def test_negative_distance_score_exceeds_one(self):
        """In distance mode score = max(0, 1 - raw_score), so a physically-invalid
        negative raw distance produces score > 1. Document the actual behavior;
        real backends (pgvector, Milvus-L2) always return distances >= 0."""
        out = normalize_search_results([_raw(-0.1)], score_mode="distance")
        # score = max(0.0, 1.0 - (-0.1)) = 1.1, not clamped from above
        assert out[0]["score"] == pytest.approx(1.1)

    def test_midpoint(self):
        out = normalize_search_results([_raw(0.5)], score_mode="distance")
        _assert_invariants(out[0])
        assert out[0]["score"] == pytest.approx(0.5)

    def test_default_score_mode_is_distance(self):
        """Default score_mode must be 'distance' for backward compatibility."""
        out_default = normalize_search_results([_raw(0.3)])
        out_explicit = normalize_search_results([_raw(0.3)], score_mode="distance")
        assert out_default[0]["score"] == out_explicit[0]["score"]

    @pytest.mark.parametrize("raw,expected_score", [
        (0.0, 1.0),
        (0.2, 0.8),
        (0.5, 0.5),
        (0.8, 0.2),
        (1.0, 0.0),
    ])
    def test_distance_parametrized(self, raw, expected_score):
        out = normalize_search_results([_raw(raw)], score_mode="distance")
        assert out[0]["score"] == pytest.approx(expected_score, abs=1e-9)
        _assert_invariants(out[0])


# ===========================================================================
# similarity mode
# ===========================================================================

class TestSimilarityMode:
    """Backend returns a relevance/similarity score; higher is better."""

    def test_basic_conversion(self):
        out = normalize_search_results([_raw(0.8)], score_mode="similarity")
        r = out[0]
        assert r["score"] == pytest.approx(0.8)
        assert r["vector_distance"] == pytest.approx(0.2)

    def test_perfect_match(self):
        """Similarity 1 → distance 0."""
        out = normalize_search_results([_raw(1.0)], score_mode="similarity")
        assert out[0]["score"] == pytest.approx(1.0)
        assert out[0]["vector_distance"] == pytest.approx(0.0)

    def test_zero_score(self):
        out = normalize_search_results([_raw(0.0)], score_mode="similarity")
        assert out[0]["score"] == pytest.approx(0.0)
        assert out[0]["vector_distance"] == pytest.approx(1.0)

    def test_score_above_one_clamped(self):
        """Some backends (e.g. ES BM25) can exceed 1; must be clamped."""
        out = normalize_search_results([_raw(3.5)], score_mode="similarity")
        assert out[0]["score"] == pytest.approx(1.0)
        assert out[0]["vector_distance"] == pytest.approx(0.0)

    def test_negative_score_clamped(self):
        out = normalize_search_results([_raw(-0.5)], score_mode="similarity")
        assert out[0]["score"] == pytest.approx(0.0)
        assert out[0]["vector_distance"] == pytest.approx(1.0)

    def test_synthetic_distance_complement(self):
        """vector_distance must always be 1 - score in similarity mode."""
        for raw in (0.1, 0.4, 0.6, 0.9):
            out = normalize_search_results([_raw(raw)], score_mode="similarity")
            _assert_invariants(out[0])

    @pytest.mark.parametrize("raw,expected_score", [
        (0.0, 0.0),
        (0.3, 0.3),
        (0.7, 0.7),
        (1.0, 1.0),
    ])
    def test_similarity_parametrized(self, raw, expected_score):
        out = normalize_search_results([_raw(raw)], score_mode="similarity")
        assert out[0]["score"] == pytest.approx(expected_score, abs=1e-9)
        _assert_invariants(out[0])


# ===========================================================================
# rerank_score priority
# ===========================================================================

class TestRerankPriority:
    """rerank_score must override score_mode regardless of its value."""

    def test_rerank_overrides_distance_mode(self):
        item = _raw(0.9, rerank_score=0.4)  # distance 0.9 would give score=0.1
        out = normalize_search_results([item], score_mode="distance")
        assert out[0]["score"] == pytest.approx(0.4)
        assert out[0]["vector_distance"] == pytest.approx(0.6)

    def test_rerank_overrides_similarity_mode(self):
        item = _raw(0.1, rerank_score=0.95)  # similarity 0.1 would give score=0.1
        out = normalize_search_results([item], score_mode="similarity")
        assert out[0]["score"] == pytest.approx(0.95)

    def test_rerank_score_clamped_above_one(self):
        item = _raw(0.5, rerank_score=1.5)
        out = normalize_search_results([item], score_mode="distance")
        assert out[0]["score"] == pytest.approx(1.0)
        assert out[0]["vector_distance"] == pytest.approx(0.0)

    def test_rerank_score_clamped_below_zero(self):
        item = _raw(0.5, rerank_score=-0.2)
        out = normalize_search_results([item], score_mode="similarity")
        assert out[0]["score"] == pytest.approx(0.0)
        assert out[0]["vector_distance"] == pytest.approx(1.0)

    def test_rerank_score_preserved_in_output(self):
        item = _raw(0.5, rerank_score=0.75)
        out = normalize_search_results([item], score_mode="distance")
        assert out[0]["rerank_score"] == pytest.approx(0.75)

    def test_no_rerank_score_is_none_in_output(self):
        out = normalize_search_results([_raw(0.5)], score_mode="similarity")
        assert out[0]["rerank_score"] is None

    def test_invariants_with_rerank(self):
        item = _raw(0.3, rerank_score=0.6)
        out = normalize_search_results([item], score_mode="distance")
        _assert_invariants(out[0])


# ===========================================================================
# Field mapping
# ===========================================================================

class TestFieldMapping:
    def test_id_from_memory_id_alias(self):
        r = {"memory_id": "abc", "memory": "text", "score": 0.5}
        out = normalize_search_results([r], score_mode="similarity")
        assert out[0]["id"] == "abc"

    def test_memory_from_text_alias(self):
        r = {"id": "x", "text": "some text", "score": 0.5}
        out = normalize_search_results([r], score_mode="similarity")
        assert out[0]["memory"] == "some text"

    def test_score_from_similarity_alias(self):
        """Older Mem0 versions may emit 'similarity' instead of 'score'."""
        r = {"id": "y", "memory": "hi", "similarity": 0.7}
        out = normalize_search_results([r], score_mode="similarity")
        assert out[0]["score"] == pytest.approx(0.7)

    def test_created_at_from_timestamp_alias(self):
        r = {"id": "z", "memory": "hi", "score": 0.5, "timestamp": "2024-01-01T00:00:00Z"}
        out = normalize_search_results([r], score_mode="similarity")
        assert out[0]["created_at"] == "2024-01-01T00:00:00Z"

    def test_metadata_defaults_to_empty_dict(self):
        out = normalize_search_results([_raw(0.5)], score_mode="similarity")
        assert out[0]["metadata"] == {}

    def test_metadata_preserved(self):
        r = _raw(0.5, metadata={"user": "alice"})
        out = normalize_search_results([r], score_mode="similarity")
        assert out[0]["metadata"] == {"user": "alice"}

    def test_output_keys_complete(self):
        out = normalize_search_results([_raw(0.5)], score_mode="similarity")
        assert set(out[0].keys()) == {"id", "memory", "score", "vector_distance",
                                       "rerank_score", "metadata", "created_at"}


# ===========================================================================
# Real-world backend score distributions
# ===========================================================================

class TestRealWorldScores:
    """Sanity-check that typical score ranges from each backend produce
    meaningful similarity values after normalization."""

    @pytest.mark.parametrize("raw_distance,expected_similarity", [
        (0.05, 0.95),  # very close match in pgvector
        (0.40, 0.60),  # moderate match
        (0.85, 0.15),  # weak match
    ])
    def test_pgvector_cosine_distance(self, raw_distance, expected_similarity):
        out = normalize_search_results([_raw(raw_distance)], score_mode="distance")
        assert out[0]["score"] == pytest.approx(expected_similarity, abs=1e-9)

    @pytest.mark.parametrize("raw_similarity", [0.92, 0.75, 0.60])
    def test_qdrant_similarity_score(self, raw_similarity):
        out = normalize_search_results([_raw(raw_similarity)], score_mode="similarity")
        assert out[0]["score"] == pytest.approx(raw_similarity, abs=1e-9)

    def test_elasticsearch_high_bm25_score_clamped(self):
        """ES BM25 can return scores well above 1; must be clamped to 1."""
        out = normalize_search_results([_raw(15.3)], score_mode="similarity")
        assert out[0]["score"] == pytest.approx(1.0)

    @pytest.mark.parametrize("raw", [0.88, 0.72, 0.55])
    def test_azure_ai_search_scores(self, raw):
        """Azure AI Search @search.score is already in [0, 1]."""
        out = normalize_search_results([_raw(raw)], score_mode="similarity")
        assert out[0]["score"] == pytest.approx(raw, abs=1e-9)
