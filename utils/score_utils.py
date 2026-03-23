"""Score mode determination for vector store backends.

Returns 'distance' or 'similarity' based on the configured vector store
provider and metric type, so that normalize_search_results can convert
raw scores uniformly to 0-1 similarity values.

Distance-type backends (raw score is a distance, lower = more similar):
  - pgvector        : cosine distance via <=> operator, range [0, 2]
  - azure_mysql     : same as pgvector
  - milvus (L2)     : Euclidean distance; default metric_type in mem0 config
  - faiss (euclidean): L2 distance; default distance_strategy in mem0

Similarity-type backends (raw score is relevance/similarity, higher = better):
  - elasticsearch   : _score (cosine similarity or BM25)
  - azure_ai_search : @search.score
  - qdrant          : all metrics; Qdrant normalises internally to higher=better
  - milvus (COSINE / IP) : cosine similarity or inner product
  - faiss (inner_product / cosine)
  - chroma, pinecone, weaviate, mongodb, redis, opensearch, supabase, etc.
"""

from __future__ import annotations

import ast
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Providers where the raw score is a *distance* (lower = more similar).
_DISTANCE_PROVIDERS = frozenset({"pgvector", "azure_mysql"})


def _safe_parse(raw: Any) -> dict[str, Any] | None:
    """Lightly parse a credentials JSON block without raising.

    Returns the parsed dict, or None on any failure.
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        result = ast.literal_eval(text)
        return result if isinstance(result, dict) else None
    except Exception:  # noqa: BLE001
        return None


def get_score_mode(credentials: dict[str, Any]) -> str:
    """Return 'distance' or 'similarity' for the configured vector store.

    Reads ``local_vector_db_json_secret`` (preferred) or the legacy
    ``local_vector_db_json`` field from *credentials*, then inspects the
    ``provider`` and relevant metric/distance config fields.

    Returns 'distance' for backends where the raw search score is a
    distance value (lower = more similar).  Returns 'similarity' for all
    other backends where the raw score already represents relevance
    (higher = better).

    Falls back to 'distance' when the config cannot be parsed, preserving
    backward-compatible behaviour for pgvector-only deployments.

    Args:
        credentials: Provider credentials dict from Dify runtime.

    Returns:
        'distance' or 'similarity'.
    """
    raw = credentials.get("local_vector_db_json_secret") or credentials.get(
        "local_vector_db_json"
    )
    data = _safe_parse(raw)
    if not isinstance(data, dict):
        logger.debug(
            "score_utils: could not parse vector store config, defaulting to 'distance'"
        )
        return "distance"

    provider = str(data.get("provider") or "").lower().strip()
    config: dict[str, Any] = data.get("config") or {}

    if not provider:
        logger.debug(
            "score_utils: vector store provider not found, defaulting to 'distance'"
        )
        return "distance"

    # pgvector and azure_mysql always use cosine distance (<=>)
    if provider in _DISTANCE_PROVIDERS:
        logger.debug("score_utils: provider=%s → distance", provider)
        return "distance"

    # Milvus: L2 metric is distance, COSINE / IP are similarity
    if provider == "milvus":
        metric = str(config.get("metric_type", "L2")).upper().strip()
        mode = "distance" if metric == "L2" else "similarity"
        logger.debug("score_utils: provider=milvus metric_type=%s → %s", metric, mode)
        return mode

    # FAISS: euclidean (IndexFlatL2) is distance; inner_product/cosine are similarity
    if provider == "faiss":
        strategy = str(config.get("distance_strategy", "euclidean")).lower().strip()
        mode = "distance" if strategy == "euclidean" else "similarity"
        logger.debug(
            "score_utils: provider=faiss distance_strategy=%s → %s", strategy, mode
        )
        return mode

    # All remaining providers (qdrant, elasticsearch, azure_ai_search, chroma,
    # pinecone, weaviate, mongodb, redis, opensearch, supabase, databricks, etc.)
    # return higher-is-better relevance/similarity scores.
    logger.debug("score_utils: provider=%s → similarity", provider)
    return "similarity"
