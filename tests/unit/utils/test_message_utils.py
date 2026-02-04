from __future__ import annotations

from utils.message_utils import count_add_event_stats


def test_count_add_event_stats_empty() -> None:
    assert count_add_event_stats(None) == {}
    assert count_add_event_stats({}) == {}
    assert count_add_event_stats({"results": []}) == {}


def test_count_add_event_stats_counts() -> None:
    result = {
        "results": [
            {"event": "ADD"},
            {"event": "add"},
            {"event": "UPDATE"},
            {"event": "NONE"},
            {"event": "none"},
            {"event": ""},
            {"event": None},
        ]
    }
    assert count_add_event_stats(result) == {
        "ADD": 2,
        "UPDATE": 1,
        "NONE": 2,
        "UNKNOWN": 2,
    }

