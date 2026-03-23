"""Tests for utils/memory_forgetting.py.

Covers every public function:
- get_quality_score    : priority chain (rerank_score → score → vector_distance) + clamping
- update_entry         : quality < q_min guard, EWMA update, recall_count cap
- build_updates        : batch processing, missing id, selective update
- should_forget        : hard TTL, Ebbinghaus forgetting curve (forget / keep),
                         per-subtype S0 (episodic/semantic/procedural/unknown)
- retention_info       : output structure and key formulas, s0_used field
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from utils.constants import FORGET_S0_BY_SUBTYPE
from utils.memory_forgetting import (
    build_updates,
    forget_params,
    get_quality_score,
    retention_info,
    should_forget,
    update_entry,
)

# ---------------------------------------------------------------------------
# Shared constants (mirrors utils/constants.py defaults)
# ---------------------------------------------------------------------------
PARAMS = forget_params()
Q_MIN: float = PARAMS["q_min"]   # 0.50
ALPHA: float = PARAMS["alpha"]   # 0.30
N_MAX: int   = PARAMS["n_max"]   # 6
S0: float    = PARAMS["s0"]      # 30.0
G: float     = PARAMS["g"]       # 1.8
THETA: float = PARAMS["theta"]   # 0.05


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(days_ago: float = 0.0) -> str:
    """Return an ISO-8601 UTC timestamp *days_ago* days in the past."""
    dt = datetime.now(UTC) - timedelta(days=days_ago)
    return dt.isoformat()


def _retention(recall_count: int, quality_ema: float, age_days: float) -> float:
    recall_strength = recall_count * quality_ema
    stability = S0 * (G ** recall_strength)
    return math.exp(-age_days / stability)


# ===========================================================================
# get_quality_score
# ===========================================================================

class TestGetQualityScore:
    def test_rerank_score_priority(self):
        """rerank_score wins even when score and vector_distance are also present."""
        r = {"rerank_score": 0.9, "score": 0.3, "vector_distance": 0.7}
        assert get_quality_score(r) == pytest.approx(0.9)

    def test_rerank_score_clamped_above_one(self):
        assert get_quality_score({"rerank_score": 1.5}) == pytest.approx(1.0)

    def test_rerank_score_clamped_below_zero(self):
        assert get_quality_score({"rerank_score": -0.3}) == pytest.approx(0.0)

    def test_score_fallback_when_no_rerank(self):
        r = {"score": 0.75, "vector_distance": 0.25}
        assert get_quality_score(r) == pytest.approx(0.75)

    def test_score_clamped_above_one(self):
        assert get_quality_score({"score": 2.0}) == pytest.approx(1.0)

    def test_score_clamped_below_zero(self):
        assert get_quality_score({"score": -0.1}) == pytest.approx(0.0)

    def test_vector_distance_fallback(self):
        """Backward-compat: no rerank_score or score → derive from vector_distance."""
        r = {"vector_distance": 0.3}
        assert get_quality_score(r) == pytest.approx(0.7)

    def test_vector_distance_zero_gives_one(self):
        assert get_quality_score({"vector_distance": 0.0}) == pytest.approx(1.0)

    def test_vector_distance_one_gives_zero(self):
        assert get_quality_score({"vector_distance": 1.0}) == pytest.approx(0.0)

    def test_empty_result_defaults_to_zero(self):
        """No fields present → vector_distance defaults to 1.0 → quality = 0."""
        assert get_quality_score({}) == pytest.approx(0.0)

    def test_rerank_score_none_falls_through_to_score(self):
        """Explicit None rerank_score must not block fallback chain."""
        r = {"rerank_score": None, "score": 0.6}
        assert get_quality_score(r) == pytest.approx(0.6)

    def test_score_none_falls_through_to_distance(self):
        r = {"rerank_score": None, "score": None, "vector_distance": 0.4}
        assert get_quality_score(r) == pytest.approx(0.6)

    @pytest.mark.parametrize("rerank,expected", [
        (0.0, 0.0), (0.5, 0.5), (1.0, 1.0),
    ])
    def test_rerank_boundary_values(self, rerank, expected):
        assert get_quality_score({"rerank_score": rerank}) == pytest.approx(expected)


# ===========================================================================
# update_entry
# ===========================================================================

class TestUpdateEntry:
    def test_quality_below_q_min_returns_none(self):
        entry: dict[str, Any] = {}
        assert update_entry(entry, Q_MIN - 0.01, PARAMS) is None

    def test_quality_exactly_at_q_min_is_accepted(self):
        """quality == q_min must NOT return None (boundary inclusive)."""
        result = update_entry({}, Q_MIN, PARAMS)
        assert result is not None

    def test_first_recall_creates_entry(self):
        result = update_entry({}, 0.8, PARAMS)
        assert result is not None
        assert "last_recalled_at" in result
        assert result["recall_count"] == 1
        # First recall: old_ema = quality → new_ema = alpha*q + (1-alpha)*q = q
        assert result["quality_ema"] == pytest.approx(0.8, abs=1e-6)

    def test_ewma_update(self):
        old_ema = 0.6
        quality = 0.9
        entry = {"recall_count": 2, "quality_ema": old_ema}
        result = update_entry(entry, quality, PARAMS)
        expected_ema = ALPHA * quality + (1.0 - ALPHA) * old_ema
        assert result["quality_ema"] == pytest.approx(expected_ema, abs=1e-6)

    def test_recall_count_incremented(self):
        entry = {"recall_count": 3, "quality_ema": 0.7}
        result = update_entry(entry, 0.75, PARAMS)
        assert result["recall_count"] == 4

    def test_recall_count_capped_at_n_max(self):
        entry = {"recall_count": N_MAX, "quality_ema": 0.8}
        result = update_entry(entry, 0.9, PARAMS)
        assert result["recall_count"] == N_MAX

    def test_recall_count_just_below_n_max(self):
        entry = {"recall_count": N_MAX - 1, "quality_ema": 0.8}
        result = update_entry(entry, 0.8, PARAMS)
        assert result["recall_count"] == N_MAX

    def test_last_recalled_at_is_set(self):
        result = update_entry({}, 0.8, PARAMS)
        ts = result["last_recalled_at"]
        # Should be a recent ISO-8601 string
        dt = datetime.fromisoformat(ts)
        delta = abs((datetime.now(UTC) - dt).total_seconds())
        assert delta < 5  # within 5 seconds

    def test_returns_only_relevant_keys(self):
        result = update_entry({}, 0.8, PARAMS)
        assert set(result.keys()) == {"last_recalled_at", "recall_count", "quality_ema"}

    def test_quality_ema_rounded_to_six_decimals(self):
        entry = {"recall_count": 1, "quality_ema": 1 / 3}
        result = update_entry(entry, 0.7, PARAMS)
        # Must not exceed 6 decimal places
        s = str(result["quality_ema"])
        if "." in s:
            assert len(s.split(".")[1]) <= 6


# ===========================================================================
# build_updates
# ===========================================================================

class TestBuildUpdates:
    def _result(self, mem_id: str, score: float) -> dict:
        return {"id": mem_id, "score": score, "rerank_score": None, "vector_distance": 1 - score}

    def test_updates_returned_only_for_high_quality(self):
        results = [
            self._result("good", 0.9),  # quality >= q_min
            self._result("bad", 0.1),   # quality < q_min → skip
        ]
        updates = build_updates(results, {}, PARAMS)
        assert "good" in updates
        assert "bad" not in updates

    def test_skips_results_without_id(self):
        results = [{"score": 0.9, "memory": "no id"}]
        updates = build_updates(results, {}, PARAMS)
        assert updates == {}

    def test_existing_entry_is_used(self):
        existing = {"recall_count": 3, "quality_ema": 0.7, "last_recalled_at": _iso(1)}
        results = [self._result("m1", 0.8)]
        updates = build_updates(results, {"m1": existing}, PARAMS)
        assert updates["m1"]["recall_count"] == 4

    def test_new_memory_gets_count_one(self):
        results = [self._result("new", 0.9)]
        updates = build_updates(results, {}, PARAMS)
        assert updates["new"]["recall_count"] == 1

    def test_multiple_results_batch(self):
        results = [
            self._result("a", 0.9),
            self._result("b", 0.8),
            self._result("c", 0.2),  # below q_min
        ]
        updates = build_updates(results, {}, PARAMS)
        assert set(updates.keys()) == {"a", "b"}

    def test_string_cast_of_mem_id(self):
        """mem_id may come as an integer-like string; dict key must be str."""
        results = [{"id": 42, "score": 0.9, "rerank_score": None}]
        updates = build_updates(results, {}, PARAMS)
        assert "42" in updates


# ===========================================================================
# should_forget
# ===========================================================================

class TestShouldForget:
    # --- Hard TTL ---

    def test_ttl_triggers_deletion_when_exceeded(self):
        entry: dict[str, Any] = {}
        created = _iso(days_ago=100)
        assert should_forget(entry, created, PARAMS, memory_ttl_days=90) is True

    def test_ttl_does_not_trigger_when_not_exceeded(self):
        entry: dict[str, Any] = {}
        created = _iso(days_ago=30)
        # Only TTL check; ensure retention doesn't trigger (fresh memory)
        result = should_forget(entry, created, PARAMS, memory_ttl_days=60)
        # Retention for brand-new memory: exp(-30/30) ≈ 0.37 > theta=0.05
        assert result is False

    def test_ttl_none_disables_ttl_check(self):
        """memory_ttl_days=None → no TTL; fresh memory must not be forgotten."""
        entry: dict[str, Any] = {}
        created = _iso(days_ago=1)
        assert should_forget(entry, created, PARAMS, memory_ttl_days=None) is False

    def test_ttl_zero_disables_ttl_check(self):
        """memory_ttl_days=0 is treated as disabled; only the forgetting curve decides.
        Use a freshly-created memory so retention is high and the curve keeps it."""
        entry: dict[str, Any] = {}
        created = _iso(days_ago=0)   # brand new memory → retention ≈ 1 > theta
        assert should_forget(entry, created, PARAMS, memory_ttl_days=0) is False

    # --- Ebbinghaus forgetting curve ---

    def test_fresh_memory_with_no_recalls_is_kept(self):
        """Memory created today → retention ≈ 1 → should not be forgotten."""
        entry: dict[str, Any] = {}
        created = _iso(days_ago=0)
        assert should_forget(entry, created, PARAMS) is False

    def test_very_old_memory_with_no_recalls_is_forgotten(self):
        """Memory 10 years old with 0 recalls → retention ≈ 0 → forget."""
        entry: dict[str, Any] = {}
        created = _iso(days_ago=3650)
        assert should_forget(entry, created, PARAMS) is True

    def test_well_recalled_memory_survives_longer(self):
        """A memory recalled 6× with high quality should have high stability."""
        entry = {"recall_count": N_MAX, "quality_ema": 0.9, "last_recalled_at": _iso(5)}
        created = _iso(days_ago=30)
        # recall_strength = 6 * 0.9 = 5.4 → S = 30 * 1.8^5.4 ≈ very large
        assert should_forget(entry, created, PARAMS) is False

    def test_poorly_recalled_memory_decays_faster(self):
        """Memory never recalled and old enough should decay below theta."""
        entry: dict[str, Any] = {}
        created = _iso(days_ago=200)
        # recall_strength = 0 → S = s0 = 30; retention = exp(-200/30) ≈ 0.0013 < 0.05
        assert should_forget(entry, created, PARAMS) is True

    def test_boundary_retention_just_above_theta_kept(self):
        """Manually construct a case where retention is just above theta."""
        # Target: retention = theta + epsilon
        # retention = exp(-age/S) → age = -S * ln(retention)
        recall_strength = 0.0
        stability = S0 * (G ** recall_strength)  # 30
        target_retention = THETA + 0.01          # 0.06
        age_needed = -stability * math.log(target_retention)  # ≈ 28.4 days
        entry: dict[str, Any] = {}
        created = _iso(days_ago=age_needed - 0.1)  # slightly younger
        assert should_forget(entry, created, PARAMS) is False

    def test_boundary_retention_just_below_theta_forgotten(self):
        recall_strength = 0.0
        stability = S0 * (G ** recall_strength)
        target_retention = THETA - 0.01
        if target_retention <= 0:
            target_retention = 0.001
        age_needed = -stability * math.log(target_retention)
        entry: dict[str, Any] = {}
        created = _iso(days_ago=age_needed + 0.5)
        assert should_forget(entry, created, PARAMS) is True

    def test_last_recalled_at_used_over_created_at(self):
        """Forgetting age measured from last_recalled_at, not created_at."""
        # Old created_at but very recent last_recalled_at → should keep
        entry = {
            "recall_count": 1,
            "quality_ema": 0.8,
            "last_recalled_at": _iso(days_ago=0),  # recalled today
        }
        created = _iso(days_ago=365)
        assert should_forget(entry, created, PARAMS) is False

    def test_ttl_and_curve_independent_ttl_wins(self):
        """Hard TTL fires even when forgetting curve says keep."""
        entry = {"recall_count": N_MAX, "quality_ema": 0.95, "last_recalled_at": _iso(1)}
        created = _iso(days_ago=91)
        # Curve says keep (strong recall), but TTL=90 says forget
        assert should_forget(entry, created, PARAMS, memory_ttl_days=90) is True


# ===========================================================================
# retention_info
# ===========================================================================

class TestRetentionInfo:
    REQUIRED_KEYS = {
        "recall_count", "quality_ema", "recall_strength",
        "stability_days", "age_days", "age_since_created_days",
        "retention", "ttl_expired", "forget",
    }

    def test_output_keys_complete(self):
        info = retention_info({}, _iso(10), PARAMS)
        assert self.REQUIRED_KEYS.issubset(set(info.keys()))

    def test_forget_consistent_with_should_forget(self):
        """retention_info['forget'] must agree with should_forget()."""
        entry: dict[str, Any] = {}
        for days_ago in (1, 30, 200, 3650):
            created = _iso(days_ago)
            info = retention_info(entry, created, PARAMS)
            expected = should_forget(entry, created, PARAMS)
            assert info["forget"] == expected, (
                f"days_ago={days_ago}: retention_info says {info['forget']}, "
                f"should_forget says {expected}"
            )

    def test_retention_between_zero_and_one(self):
        for days_ago in (0, 10, 100):
            info = retention_info({}, _iso(days_ago), PARAMS)
            assert 0.0 <= info["retention"] <= 1.0

    def test_ttl_expired_flag_true_when_exceeded(self):
        created = _iso(days_ago=100)
        info = retention_info({}, created, PARAMS, memory_ttl_days=50)
        assert info["ttl_expired"] is True
        assert info["forget"] is True

    def test_ttl_expired_flag_false_when_not_exceeded(self):
        created = _iso(days_ago=10)
        info = retention_info({}, created, PARAMS, memory_ttl_days=30)
        assert info["ttl_expired"] is False

    def test_well_recalled_has_large_stability(self):
        entry = {"recall_count": 6, "quality_ema": 0.9}
        info = retention_info(entry, _iso(30), PARAMS)
        # stability_days should be much larger than s0=30
        assert info["stability_days"] > S0 * 10

    def test_zero_recalls_stability_equals_s0(self):
        info = retention_info({}, _iso(0), PARAMS)
        assert info["stability_days"] == pytest.approx(S0, abs=0.01)

    def test_age_days_approximately_correct(self):
        target_days = 7.0
        info = retention_info({}, _iso(target_days), PARAMS)
        assert info["age_days"] == pytest.approx(target_days, abs=0.01)


# ===========================================================================
# Per-subtype S0 — should_forget
# ===========================================================================

class TestSubtypeS0ShouldForget:
    """Verify that per-subtype base stability (S0) is applied correctly."""

    # ---- Fallback behaviour for unknown / absent subtype -------------------

    def test_none_subtype_uses_default_s0(self):
        """memory_subtype=None must fall back to FORGET_S0 (30 days)."""
        # At 200 days with no recalls: exp(-200/30) ≈ 0.001 < theta → forget
        entry: dict[str, Any] = {}
        created = _iso(days_ago=200)
        assert should_forget(entry, created, PARAMS, memory_subtype=None) is True

    def test_unknown_subtype_uses_default_s0(self):
        """Unrecognised subtype string must fall back to FORGET_S0."""
        entry: dict[str, Any] = {}
        created = _iso(days_ago=200)
        assert should_forget(entry, created, PARAMS, memory_subtype="custom") is True

    # ---- Each recognised subtype uses its own S0 ---------------------------

    @pytest.mark.parametrize("subtype,s0", [
        ("episodic",   FORGET_S0_BY_SUBTYPE["episodic"]),
        ("semantic",   FORGET_S0_BY_SUBTYPE["semantic"]),
        ("procedural", FORGET_S0_BY_SUBTYPE["procedural"]),
    ])
    def test_survival_boundary_exact(self, subtype: str, s0: float):
        """A never-recalled memory at exactly the survival boundary for each
        subtype: age = s0 × ln(1/theta) (the point where retention == theta).
        One day under → keep; one day over → forget.
        """
        survival_days = s0 * math.log(1 / THETA)  # ≈ 3 × s0

        entry: dict[str, Any] = {}
        created_keep   = _iso(days_ago=survival_days - 1)
        created_forget = _iso(days_ago=survival_days + 1)

        assert should_forget(entry, created_keep,   PARAMS, memory_subtype=subtype) is False, (
            f"{subtype}: memory at {survival_days - 1:.1f} days should be kept"
        )
        assert should_forget(entry, created_forget, PARAMS, memory_subtype=subtype) is True, (
            f"{subtype}: memory at {survival_days + 1:.1f} days should be forgotten"
        )

    # ---- Cross-subtype comparison at a fixed age ---------------------------

    def test_episodic_forgotten_while_semantic_kept_at_100_days(self):
        """At 100 days without recall:
        - episodic  S0=14  → S=14, retention=exp(-100/14)≈0.0008 < theta → forget
        - semantic  S0=45  → S=45, retention=exp(-100/45)≈0.109  > theta → keep
        """
        entry: dict[str, Any] = {}
        created = _iso(days_ago=100)
        assert should_forget(entry, created, PARAMS, memory_subtype="episodic") is True
        assert should_forget(entry, created, PARAMS, memory_subtype="semantic") is False

    def test_semantic_forgotten_while_procedural_kept_at_200_days(self):
        """At 200 days without recall:
        - semantic   S0=45  → S=45, retention=exp(-200/45)≈0.012 < theta → forget
        - procedural S0=90  → S=90, retention=exp(-200/90)≈0.108 > theta → keep
        """
        entry: dict[str, Any] = {}
        created = _iso(days_ago=200)
        assert should_forget(entry, created, PARAMS, memory_subtype="semantic")   is True
        assert should_forget(entry, created, PARAMS, memory_subtype="procedural") is False

    # ---- Subtype does not affect hard-TTL logic ----------------------------

    def test_hard_ttl_still_overrides_subtype(self):
        """A procedural memory (high S0) older than TTL must still be force-deleted."""
        entry: dict[str, Any] = {}
        created = _iso(days_ago=100)
        # Without TTL the procedural memory would survive (S0=90, exp(-100/90)≈0.33)
        assert should_forget(entry, created, PARAMS, memory_subtype="procedural") is False
        # With TTL=90 it must be deleted regardless of subtype
        assert should_forget(
            entry, created, PARAMS, memory_ttl_days=90, memory_subtype="procedural"
        ) is True

    # ---- Recalled memories also benefit from higher S0 --------------------

    def test_recalled_procedural_outlasts_recalled_episodic(self):
        """After one recall, procedural memory should outlast episodic
        by the same proportional factor (S0_procedural / S0_episodic = 90/14).
        """
        created = _iso(days_ago=30)

        # At 600 days since last recalled (well past episodic survival window):
        # episodic:   S = 14 * 1.8^0.8 ≈ 23.0 → exp(-600/23) ≈ 0 → forget
        # procedural: S = 90 * 1.8^0.8 ≈ 147.6 → exp(-600/147.6) ≈ 0.017 < theta → forget
        # But at 400 days since recall:
        # episodic:   exp(-400/23)  ≈ 0    → forget
        # procedural: exp(-400/147.6) ≈ 0.066 > theta → keep
        long_lived_entry = {
            "recall_count": 1,
            "quality_ema": 0.8,
            "last_recalled_at": _iso(400),
        }
        assert (
            should_forget(
                long_lived_entry, created, PARAMS, memory_subtype="episodic"
            )
            is True
        )
        assert (
            should_forget(
                long_lived_entry, created, PARAMS, memory_subtype="procedural"
            )
            is False
        )


# ===========================================================================
# Per-subtype S0 — retention_info
# ===========================================================================

class TestSubtypeS0RetentionInfo:
    """Verify that retention_info correctly reflects per-subtype S0."""

    @pytest.mark.parametrize("subtype,expected_s0", [
        ("episodic",   FORGET_S0_BY_SUBTYPE["episodic"]),
        ("semantic",   FORGET_S0_BY_SUBTYPE["semantic"]),
        ("procedural", FORGET_S0_BY_SUBTYPE["procedural"]),
        (None,         S0),       # fallback to default FORGET_S0
        ("unknown",    S0),       # unrecognised → fallback
    ])
    def test_s0_used_field(self, subtype, expected_s0):
        """retention_info must report the actual S0 used for each subtype."""
        info = retention_info({}, _iso(0), PARAMS, memory_subtype=subtype)
        assert info["s0_used"] == pytest.approx(expected_s0, abs=0.01)

    @pytest.mark.parametrize("subtype,expected_s0", [
        ("episodic",   FORGET_S0_BY_SUBTYPE["episodic"]),
        ("semantic",   FORGET_S0_BY_SUBTYPE["semantic"]),
        ("procedural", FORGET_S0_BY_SUBTYPE["procedural"]),
    ])
    def test_stability_days_uses_subtype_s0(self, subtype, expected_s0):
        """stability_days for a never-recalled memory must equal the subtype S0."""
        info = retention_info({}, _iso(0), PARAMS, memory_subtype=subtype)
        # recall_strength = 0 → stability = s0 × g^0 = s0
        assert info["stability_days"] == pytest.approx(expected_s0, abs=0.01)

    def test_memory_subtype_field_in_output(self):
        """retention_info must echo back the memory_subtype passed in."""
        info = retention_info({}, _iso(0), PARAMS, memory_subtype="semantic")
        assert info["memory_subtype"] == "semantic"

    def test_memory_subtype_none_in_output(self):
        info = retention_info({}, _iso(0), PARAMS, memory_subtype=None)
        assert info["memory_subtype"] is None

    def test_forget_field_consistent_with_should_forget_per_subtype(self):
        """retention_info['forget'] must agree with should_forget() for every subtype."""
        entry: dict[str, Any] = {}
        for subtype in ("episodic", "semantic", "procedural", None):
            for days_ago in (1, 50, 150, 300):
                created = _iso(days_ago)
                info = retention_info(entry, created, PARAMS, memory_subtype=subtype)
                expected = should_forget(entry, created, PARAMS, memory_subtype=subtype)
                assert info["forget"] == expected, (
                    f"subtype={subtype!r}, days_ago={days_ago}: "
                    f"retention_info says {info['forget']}, "
                    f"should_forget says {expected}"
                )
