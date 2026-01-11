from __future__ import annotations

from datetime import datetime, timezone

from logs.log_analyzer import analyze_events, parse_plugin_log_line


def test_timeout_then_completed_found0_is_degraded() -> None:
    ts = datetime(2025, 12, 22, 2, 51, 26, tzinfo=timezone.utc)
    timeout_line = (
        "2025/12/22 02:51:26 stdio.go:182: [INFO]plugin beersoccer/mem0ai:0.1.7: "
        "Search operation timed out after 5.0 seconds (async, query: 我是谁..., user_id: u1)"
    )
    completed_line = (
        "2025/12/22 02:51:26 stdio.go:182: [INFO]plugin beersoccer/mem0ai:0.1.7: "
        "Search completed (async, query: 我是谁..., user_id: u1, found 0 results, results: [])"
    )
    ev1 = parse_plugin_log_line(ts, timeout_line)
    ev2 = parse_plugin_log_line(ts, completed_line)
    assert ev1 is not None
    assert ev2 is not None

    res = analyze_events([ev1, ev2])
    assert res.search_completed == 1
    assert res.search_timeout == 1
    assert res.degraded_completed_from_timeout == 1
    assert res.degraded_completed_from_failed == 0


def test_failed_then_completed_found0_is_degraded() -> None:
    ts = datetime(2025, 12, 22, 3, 0, 0, tzinfo=timezone.utc)
    failed_line = (
        "2025/12/22 03:00:00 stdio.go:182: [INFO]plugin beersoccer/mem0ai:0.1.7: "
        "Search operation failed with error: ConnectionError (async, query: q..., user_id: u2)"
    )
    completed_line = (
        "2025/12/22 03:00:00 stdio.go:182: [INFO]plugin beersoccer/mem0ai:0.1.7: "
        "Search completed (async, query: q..., user_id: u2, found 0 results, results: [])"
    )
    ev1 = parse_plugin_log_line(ts, failed_line)
    ev2 = parse_plugin_log_line(ts, completed_line)
    assert ev1 is not None
    assert ev2 is not None

    res = analyze_events([ev1, ev2])
    assert res.search_completed == 1
    assert res.search_failed == 1
    assert res.degraded_completed_from_failed == 1


def test_completed_found0_without_error_is_not_degraded() -> None:
    ts = datetime(2025, 12, 22, 4, 0, 0, tzinfo=timezone.utc)
    completed_line = (
        "2025/12/22 04:00:00 stdio.go:182: [INFO]plugin beersoccer/mem0ai:0.1.7: "
        "Search completed (async, query: q..., user_id: u3, found 0 results, results: [])"
    )
    ev = parse_plugin_log_line(ts, completed_line)
    assert ev is not None

    res = analyze_events([ev])
    assert res.search_completed == 1
    assert res.search_completed_found_eq0 == 1
    assert res.search_timeout == 0
    assert res.search_failed == 0
    assert res.degraded_completed_from_timeout == 0
    assert res.degraded_completed_from_failed == 0


