from __future__ import annotations


def test_parse_user_ids_variants() -> None:
    from utils.helpers import _parse_user_ids

    assert _parse_user_ids(["a", "b"]) == ["a", "b"]
    assert _parse_user_ids('["a","b"]') == ["a", "b"]
    assert _parse_user_ids("a,b") == ["a", "b"]


def test_run_id_stable() -> None:
    from utils.helpers import _build_run_id

    r1 = _build_run_id("2025-12-01T00:00:00Z", ["b", "a"], None)
    r2 = _build_run_id("2025-12-01T00:00:00Z", ["a", "b"], None)
    assert r1 == r2


def test_parse_user_ids_empty_inputs() -> None:
    from utils.helpers import _parse_user_ids

    assert _parse_user_ids(None) == []
    assert _parse_user_ids("") == []
    assert _parse_user_ids([]) == []
    assert _parse_user_ids("   ") == []


def test_parse_user_ids_with_whitespace() -> None:
    from utils.helpers import _parse_user_ids

    assert _parse_user_ids([" a ", " b "]) == ["a", "b"]
    assert _parse_user_ids(" a , b ") == ["a", "b"]


def test_run_id_different_for_different_inputs() -> None:
    from utils.helpers import _build_run_id

    r1 = _build_run_id("2025-12-01T00:00:00Z", ["a"], None)
    r2 = _build_run_id("2025-12-01T00:00:00Z", ["b"], None)
    r3 = _build_run_id("2025-12-02T00:00:00Z", ["a"], None)
    r4 = _build_run_id("2025-12-01T00:00:00Z", ["a"], "app1")

    assert r1 != r2
    assert r1 != r3
    assert r1 != r4


def test_dedup_keep_order() -> None:
    from utils.helpers import dedup_keep_order

    assert dedup_keep_order(["a", "b", "a", "c"]) == ["a", "b", "c"]
    assert dedup_keep_order(["x", "x", "x"]) == ["x"]
    assert dedup_keep_order([]) == []


def test_cmp_iso_timestamps() -> None:
    from utils.extraction_helpers import cmp_iso_timestamps

    assert cmp_iso_timestamps("2025-12-01T00:00:00Z", "2025-12-02T00:00:00Z") == -1
    assert cmp_iso_timestamps("2025-12-02T00:00:00Z", "2025-12-01T00:00:00Z") == 1
    assert cmp_iso_timestamps("2025-12-01T00:00:00Z", "2025-12-01T00:00:00Z") == 0
    assert cmp_iso_timestamps(None, "2025-12-01T00:00:00Z") == -1
    assert cmp_iso_timestamps("2025-12-01T00:00:00Z", None) == 1
    assert cmp_iso_timestamps(None, None) == 0

