"""Memory forgetting: quality scoring, access log updates, and forgetting logic.

Algorithm summary
-----------------
Each memory accumulates a "recall strength" over time based on how often and
how relevantly it has been recalled:

  quality       = rerank_score (if available) else score
                  (0-1 similarity from normalize_search_results)
  quality_ema   = α * quality + (1-α) * old_ema       [EWMA, only when quality >= q_min]
  recall_count  = min(recall_count + 1, n_max)        [only when quality >= q_min]
  recall_strength = recall_count * quality_ema

The Ebbinghaus-inspired stability grows with recall_strength:

  S (days) = s0 * g ** recall_strength

Retention at evaluation time is:

  age_days  = days since last_recalled_at (or created_at if never recalled)
  Retention = exp(-age_days / S)

A memory is forgotten when Retention < theta.

Algorithm parameters are fixed to tuned defaults in utils/constants.py (FORGET_*).
The only user-facing knob is memory_ttl_days: when set, any memory older than
that many days is force-deleted regardless of recall history.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime  # UTC used by _now_iso
from typing import Any

from .constants import (
    FORGET_ALPHA,
    FORGET_G,
    FORGET_N_MAX,
    FORGET_Q_MIN,
    FORGET_S0,
    FORGET_S0_BY_SUBTYPE,
    FORGET_THETA,
)
from .helpers import days_since

# ---------------------------------------------------------------------------
# Fixed algorithm parameters (not user-configurable)
# ---------------------------------------------------------------------------

_PARAMS: dict[str, Any] = {
    "q_min": FORGET_Q_MIN,
    "alpha": FORGET_ALPHA,
    "n_max": FORGET_N_MAX,
    "s0": FORGET_S0,
    "g": FORGET_G,
    "theta": FORGET_THETA,
}


def _s0_for_subtype(memory_subtype: str | None, params: dict[str, Any]) -> float:
    """Return the base stability (s0) for the given memory subtype.

    Looks up FORGET_S0_BY_SUBTYPE; falls back to params["s0"] (i.e. FORGET_S0)
    when the subtype is None or not recognised.
    """
    if memory_subtype:
        s0 = FORGET_S0_BY_SUBTYPE.get(memory_subtype)
        if s0 is not None:
            return s0
    return params["s0"]


def forget_params() -> dict[str, Any]:
    """Return the fixed forgetting algorithm parameters.

    These are tuned defaults from utils/constants.py and are not
    user-configurable. All callers should use this instead of building
    their own params dict.
    """
    return _PARAMS


# ---------------------------------------------------------------------------
# Quality score extraction
# ---------------------------------------------------------------------------

def get_quality_score(result: dict[str, Any]) -> float:
    """Extract a 0–1 quality score from a single search result.

    Priority:
    1. rerank_score — direct relevance signal from the reranker (0–1,
       higher = more relevant).  All mem0 rerankers produce this field and
       sort results in descending order, so no further transformation is
       needed.
    2. score — already normalised to 0–1 similarity by
       normalize_search_results() (which applies the correct conversion for
       each vector store backend based on score_mode).  Higher = more
       relevant for all backends.
    3. vector_distance fallback — for results that were not processed by
       normalize_search_results() (backward-compat only).

    The returned value is clamped to [0, 1].
    """
    rerank_score = result.get("rerank_score")
    if rerank_score is not None:
        return max(0.0, min(1.0, float(rerank_score)))

    # score is guaranteed to be 0-1 similarity by normalize_search_results.
    score = result.get("score")
    if score is not None:
        return max(0.0, min(1.0, float(score)))

    # Backward-compat: result was not processed by normalize_search_results.
    distance = result.get("vector_distance", 1.0)
    return max(0.0, 1.0 - float(distance))


# ---------------------------------------------------------------------------
# Access log entry management
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def update_entry(
    entry: dict[str, Any],
    quality: float,
    params: dict[str, Any],
) -> dict[str, Any] | None:
    """Update an access log entry with a new recall quality score.

    Returns the updated entry dict, or None if quality is below q_min
    (indicating the recall should not strengthen this memory).

    Args:
        entry: Existing entry dict (may be empty for a first-time recall).
        quality: Quality score for this recall (0–1).
        params: Forgetting parameters from forget_params().

    Returns:
        Updated entry dict, or None if quality < q_min.
    """
    q_min: float = params["q_min"]
    alpha: float = params["alpha"]
    n_max: int = params["n_max"]

    if quality < q_min:
        return None

    old_ema: float = entry.get("quality_ema", quality)
    new_ema: float = alpha * quality + (1.0 - alpha) * old_ema
    new_count: int = min(entry.get("recall_count", 0) + 1, n_max)

    return {
        "last_recalled_at": _now_iso(),
        "recall_count": new_count,
        "quality_ema": round(new_ema, 6),
    }


def build_updates(
    results: list[dict[str, Any]],
    log_dict: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Compute updated access log entries for a batch of search results.

    Args:
        results: Raw search results (each must have 'id').
        log_dict: Current access log dict keyed by mem_id.
        params: Forgetting parameters from forget_params().

    Returns:
        Dict of mem_id -> updated entry, containing only entries that were
        actually updated (quality >= q_min).
    """
    updates: dict[str, dict[str, Any]] = {}
    for r in results:
        mem_id = r.get("id")
        if not mem_id:
            continue
        quality = get_quality_score(r)
        existing = log_dict.get(str(mem_id), {})
        updated = update_entry(existing, quality, params)
        if updated is not None:
            updates[str(mem_id)] = updated
    return updates


# ---------------------------------------------------------------------------
# Forgetting decision
# ---------------------------------------------------------------------------

def should_forget(
    entry: dict[str, Any],
    memory_created_at: str | None,
    params: dict[str, Any],
    *,
    memory_ttl_days: int | None = None,
    memory_subtype: str | None = None,
) -> bool:
    """Decide whether a memory should be forgotten.

    Two independent conditions — either alone is sufficient to trigger deletion:

    1. **Forgetting curve**: Retention = exp(-age/S) < theta
       - age is measured from last_recalled_at (or created_at if never recalled)
       - S grows with recall_strength; rarely-recalled memories decay faster
       - S0 (base stability) is selected per memory_subtype when provided:
           episodic=14d, semantic=45d, procedural=90d, unknown→FORGET_S0(30d)

    2. **Hard TTL** (optional): age_since_created > memory_ttl_days
       - Measured from memory created_at regardless of recall history
       - Only applied when memory_ttl_days is set (not None and > 0)

    Args:
        entry: Access log entry for this memory (may be empty dict if never
               recalled — in that case decay is computed from created_at).
        memory_created_at: ISO-8601 creation timestamp of the memory itself.
        params: Forgetting parameters from forget_params().
        memory_ttl_days: Optional hard ceiling in days. When set, memories
                         older than this are force-deleted regardless of
                         recall history. None means disabled.
        memory_subtype: Optional subtype tag ("episodic", "semantic",
                        "procedural"). Selects the per-subtype base stability
                        S0. Falls back to params["s0"] when None or unknown.

    Returns:
        True if the memory should be deleted.
    """
    # Hard TTL check: age since creation regardless of recall history
    if memory_ttl_days and memory_ttl_days > 0:
        age_since_created = days_since(memory_created_at)
        if age_since_created > memory_ttl_days:
            return True

    # Ebbinghaus forgetting curve check
    s0: float = _s0_for_subtype(memory_subtype, params)
    g: float = params["g"]
    theta: float = params["theta"]
    n_max: int = params["n_max"]

    recall_count: int = min(entry.get("recall_count", 0), n_max)
    quality_ema: float = entry.get("quality_ema", 0.0)
    recall_strength: float = float(recall_count) * quality_ema

    stability: float = s0 * (g ** recall_strength)

    last_recalled = entry.get("last_recalled_at")
    age_days = days_since(last_recalled or memory_created_at)

    retention = math.exp(-age_days / stability)
    return retention < theta


def retention_info(
    entry: dict[str, Any],
    memory_created_at: str | None,
    params: dict[str, Any],
    *,
    memory_ttl_days: int | None = None,
    memory_subtype: str | None = None,
) -> dict[str, Any]:
    """Return human-readable retention details for debugging / dry-run output."""
    s0: float = _s0_for_subtype(memory_subtype, params)
    g: float = params["g"]
    theta: float = params["theta"]
    n_max: int = params["n_max"]

    recall_count: int = min(entry.get("recall_count", 0), n_max)
    quality_ema: float = entry.get("quality_ema", 0.0)
    recall_strength: float = float(recall_count) * quality_ema
    stability: float = s0 * (g ** recall_strength)

    last_recalled = entry.get("last_recalled_at")
    age_days = days_since(last_recalled or memory_created_at)
    retention = math.exp(-age_days / stability)

    age_since_created = days_since(memory_created_at)
    ttl_expired = bool(
        memory_ttl_days and memory_ttl_days > 0
        and age_since_created > memory_ttl_days
    )

    return {
        "recall_count": recall_count,
        "quality_ema": round(quality_ema, 4),
        "recall_strength": round(recall_strength, 4),
        "stability_days": round(stability, 2),
        "age_days": round(age_days, 2),
        "age_since_created_days": round(age_since_created, 2),
        "retention": round(retention, 4),
        "ttl_expired": ttl_expired,
        "forget": retention < theta or ttl_expired,
        "memory_subtype": memory_subtype,
        "s0_used": round(s0, 2),
    }
