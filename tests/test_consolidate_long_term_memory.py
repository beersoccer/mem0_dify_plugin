from __future__ import annotations


def test_parse_user_ids_variants() -> None:
    from tools.consolidate_long_term_memory import _parse_user_ids

    assert _parse_user_ids(["a", "b"]) == ["a", "b"]
    assert _parse_user_ids('["a","b"]') == ["a", "b"]
    assert _parse_user_ids("a,b") == ["a", "b"]


def test_run_id_stable() -> None:
    from tools.consolidate_long_term_memory import _build_run_id

    r1 = _build_run_id("2025-12-01T00:00:00Z", ["b", "a"], None)
    r2 = _build_run_id("2025-12-01T00:00:00Z", ["a", "b"], None)
    assert r1 == r2
