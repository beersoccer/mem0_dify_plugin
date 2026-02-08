from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from utils.extraction import (
    ConversationCheckpoint,
    UserCheckpoint,
    scan_user_conversations_incremental,
)


@dataclass(frozen=True)
class _Page:
    items: list[dict[str, Any]]
    next_cursor: str | None
    has_more: bool


class FakeDify:
    def __init__(self) -> None:
        self.conv_pages: list[_Page] = []
        self.msg_pages: dict[str, list[_Page]] = {}
        self._msg_page_index: dict[str, int] = {}

    def list_conversations(self, **kwargs: Any) -> _Page:
        # Pop first page each time
        if not self.conv_pages:
            return _Page([], None, False)
        return self.conv_pages.pop(0)

    def list_messages(self, *, conversation_id: str, **kwargs: Any) -> _Page:
        idx = self._msg_page_index.get(conversation_id, 0)
        pages = self.msg_pages.get(conversation_id, [])
        if idx >= len(pages):
            return _Page([], None, False)
        self._msg_page_index[conversation_id] = idx + 1
        return pages[idx]


def test_window_filters_by_updated_at() -> None:
    """Test that scanning only processes conversations within the time window."""
    dify = FakeDify()
    # Descending order: newer conversations first
    dify.conv_pages = [
        _Page(
            items=[
                # New conversation, should be processed
                {"id": "c_new", "updated_at": "2025-12-05T00:00:00Z"},
                # Old conversation, should be skipped by window filter
                {"id": "c_old", "updated_at": "2025-12-01T00:00:00Z"},
            ],
            next_cursor=None,
            has_more=False,
        ),
    ]
    dify.msg_pages["c_new"] = [
        _Page(
            items=[{"id": "m1", "created_at": "2025-12-04T00:00:00Z", "query": "hi"}],
            next_cursor=None,
            has_more=False,
        ),
    ]
    segs, stats, stop_reason = scan_user_conversations_incremental(
        dify,  # type: ignore[arg-type]
        user_id="u1",
        run_at="2025-12-06T00:00:00Z",
        user_checkpoint=UserCheckpoint(conversations={}),
        app_id=None,
        start_time="2025-12-04T00:00:00Z",
    )
    # c_new processed, c_old skipped by window filter
    assert "c_new" in segs
    assert "c_old" not in segs
    assert stop_reason == "completed"
    assert stats.scanned_conversations == 2


def test_max_conversations_sets_resume_cursor() -> None:
    dify = FakeDify()
    dify.conv_pages = [
        _Page(
            items=[
                {"id": "c3", "updated_at": "2025-12-05T00:00:00Z"},
                {"id": "c2", "updated_at": "2025-12-04T00:00:00Z"},
                {"id": "c1", "updated_at": "2025-12-03T00:00:00Z"},
            ],
            next_cursor="c1",
            has_more=True,
        ),
    ]
    cp = UserCheckpoint(conversations={})

    _, stats, stop_reason = scan_user_conversations_incremental(
        dify,  # type: ignore[arg-type]
        user_id="u1",
        run_at="2025-12-10T00:00:00Z",
        user_checkpoint=cp,
        app_id=None,
        max_conversations=2,
    )

    assert stop_reason == "max_conversations_reached"
    assert stats.resume_conversation_cursor == "c2"


def test_max_conversations_no_more_returns_completed() -> None:
    dify = FakeDify()
    dify.conv_pages = [
        _Page(
            items=[
                {"id": "c3", "updated_at": "2025-12-05T00:00:00Z"},
                {"id": "c2", "updated_at": "2025-12-04T00:00:00Z"},
                {"id": "c1", "updated_at": "2025-12-03T00:00:00Z"},
            ],
            next_cursor=None,
            has_more=False,
        ),
    ]
    cp = UserCheckpoint(conversations={})

    _, stats, stop_reason = scan_user_conversations_incremental(
        dify,  # type: ignore[arg-type]
        user_id="u1",
        run_at="2025-12-10T00:00:00Z",
        user_checkpoint=cp,
        app_id=None,
        max_conversations=2,
    )

    assert stop_reason == "completed"
    assert stats.resume_conversation_cursor is None


def test_scan_with_checkpoint_uses_window() -> None:
    dify = FakeDify()
    dify.conv_pages = [
        _Page(
            items=[{"id": "c_old", "updated_at": "2025-12-01T00:00:00Z"}],
            next_cursor=None,
            has_more=False,
        ),
    ]
    dify.msg_pages["c_old"] = [
        _Page(
            items=[{"id": "m1", "created_at": "2025-12-01T00:00:00Z", "query": "hi"}],
            next_cursor=None,
            has_more=False,
        ),
    ]
    segs, _, stop_reason = scan_user_conversations_incremental(
        dify,  # type: ignore[arg-type]
        user_id="u1",
        run_at="2025-12-02T00:00:00Z",
        user_checkpoint=UserCheckpoint(
            conversations={},
        ),
        app_id=None,
        start_time="2025-11-30T00:00:00Z",
    )

    assert "c_old" in segs
    assert stop_reason == "completed"


def test_drop_future_messages_and_stop_on_last_processed_message_id() -> None:
    dify = FakeDify()
    dify.conv_pages = [
        _Page(
            items=[{"id": "c1", "updated_at": "2025-12-05T00:00:00Z"}],
            next_cursor=None,
            has_more=False,
        ),
    ]
    dify.msg_pages["c1"] = [
        _Page(
            items=[
                {
                    "id": "m_future",
                    "created_at": "2025-12-11T00:00:00Z",
                    "query": "future",
                },
                {"id": "m_new", "created_at": "2025-12-04T00:00:00Z", "query": "new"},
                {"id": "m_old", "created_at": "2025-12-01T00:00:00Z", "query": "old"},
            ],
            next_cursor=None,
            has_more=False,
        ),
    ]
    cp = UserCheckpoint(
        conversations={"c1": ConversationCheckpoint(last_processed_message_id="m_old")},
    )

    segs, stats, _ = scan_user_conversations_incremental(
        dify,  # type: ignore[arg-type]
        user_id="u1",
        run_at="2025-12-10T00:00:00Z",
        user_checkpoint=cp,
        app_id=None,
    )
    assert "c1" in segs
    # m_future dropped
    assert stats.dropped_future_messages == 1


def test_empty_conversations_returns_no_segments() -> None:
    dify = FakeDify()
    dify.conv_pages = [
        _Page(items=[], next_cursor=None, has_more=False),
    ]

    segs, stats, stop_reason = scan_user_conversations_incremental(
        dify,  # type: ignore[arg-type]
        user_id="u1",
        run_at="2025-12-10T00:00:00Z",
        user_checkpoint=None,
        app_id=None,
    )

    assert segs == {}
    assert stop_reason == "no_more_conversations"
    assert stats.scanned_conversations == 0


def test_app_id_filtering() -> None:
    dify = FakeDify()
    dify.conv_pages = [
        _Page(
            items=[
                {"id": "c1", "updated_at": "2025-12-05T00:00:00Z", "app_id": "app1"},
                {"id": "c2", "updated_at": "2025-12-04T00:00:00Z", "app_id": "app2"},
                {"id": "c3", "updated_at": "2025-12-03T00:00:00Z", "app_id": "app1"},
            ],
            next_cursor=None,
            has_more=False,
        ),
    ]
    dify.msg_pages["c1"] = [
        _Page(
            items=[{"id": "m1", "created_at": "2025-12-04T00:00:00Z", "query": "q1"}],
            next_cursor=None,
            has_more=False,
        ),
    ]
    dify.msg_pages["c3"] = [
        _Page(
            items=[{"id": "m3", "created_at": "2025-12-02T00:00:00Z", "query": "q3"}],
            next_cursor=None,
            has_more=False,
        ),
    ]

    segs, stats, _ = scan_user_conversations_incremental(
        dify,  # type: ignore[arg-type]
        user_id="u1",
        run_at="2025-12-10T00:00:00Z",
        user_checkpoint=None,
        app_id="app1",
    )

    assert "c1" in segs
    assert "c2" not in segs
    assert "c3" in segs
    assert stats.scanned_conversations == 3


def test_messages_sorted_chronologically() -> None:
    from utils.extraction import scan_new_messages_for_conversation

    dify = FakeDify()
    dify.msg_pages["c1"] = [
        _Page(
            items=[
                {"id": "m3", "created_at": "2025-12-03T00:00:00Z", "query": "third"},
                {"id": "m1", "created_at": "2025-12-01T00:00:00Z", "query": "first"},
                {"id": "m2", "created_at": "2025-12-02T00:00:00Z", "query": "second"},
            ],
            next_cursor=None,
            has_more=False,
        ),
    ]

    messages, _ = scan_new_messages_for_conversation(
        dify,  # type: ignore[arg-type]
        user_id="u1",
        conversation_id="c1",
        run_at="2025-12-10T00:00:00Z",
        last_processed_message_id=None,
    )

    assert len(messages) == 3
    assert messages[0]["id"] == "m1"
    assert messages[1]["id"] == "m2"
    assert messages[2]["id"] == "m3"


def test_pagination_with_multiple_pages() -> None:
    from utils.extraction import scan_new_messages_for_conversation

    dify = FakeDify()
    dify.msg_pages["c1"] = [
        _Page(
            items=[
                {"id": "m3", "created_at": "2025-12-03T00:00:00Z", "query": "msg3"},
                {"id": "m2", "created_at": "2025-12-02T00:00:00Z", "query": "msg2"},
            ],
            next_cursor="cursor1",
            has_more=True,
        ),
        _Page(
            items=[
                {"id": "m1", "created_at": "2025-12-01T00:00:00Z", "query": "msg1"},
            ],
            next_cursor=None,
            has_more=False,
        ),
    ]

    messages, stats = scan_new_messages_for_conversation(
        dify,  # type: ignore[arg-type]
        user_id="u1",
        conversation_id="c1",
        run_at="2025-12-10T00:00:00Z",
        last_processed_message_id=None,
    )

    assert len(messages) == 3
    assert stats.scanned_messages == 3
    assert messages[0]["id"] == "m1"
    assert messages[2]["id"] == "m3"


def test_no_checkpoint_processes_all_messages() -> None:
    from utils.extraction import scan_new_messages_for_conversation

    dify = FakeDify()
    dify.msg_pages["c1"] = [
        _Page(
            items=[
                {"id": "m1", "created_at": "2025-12-01T00:00:00Z", "query": "msg1"},
                {"id": "m2", "created_at": "2025-12-02T00:00:00Z", "query": "msg2"},
            ],
            next_cursor=None,
            has_more=False,
        ),
    ]

    messages, stats = scan_new_messages_for_conversation(
        dify,  # type: ignore[arg-type]
        user_id="u1",
        conversation_id="c1",
        run_at="2025-12-10T00:00:00Z",
        last_processed_message_id=None,
    )

    assert len(messages) == 2
    assert stats.scanned_messages == 2


def test_start_time_filters_old_messages() -> None:
    """Verify messages before start_time are filtered out."""
    from utils.extraction import scan_new_messages_for_conversation

    dify = FakeDify()
    dify.msg_pages["c1"] = [
        _Page(
            items=[
                {"id": "m_new", "created_at": "2025-12-05T00:00:00Z", "query": "new"},
                {"id": "m_in_range", "created_at": "2025-12-03T00:00:00Z", "query": "in_range"},
                {"id": "m_old", "created_at": "2025-12-01T00:00:00Z", "query": "old"},
            ],
            next_cursor=None,
            has_more=False,
        ),
    ]

    messages, stats = scan_new_messages_for_conversation(
        dify,  # type: ignore[arg-type]
        user_id="u1",
        conversation_id="c1",
        run_at="2025-12-10T00:00:00Z",
        last_processed_message_id=None,
        start_time="2025-12-02T00:00:00Z",
    )

    assert len(messages) == 2
    assert messages[0]["id"] == "m_in_range"
    assert messages[1]["id"] == "m_new"
    assert stats.scanned_messages == 3


def test_time_range_filters_both_bounds() -> None:
    """Verify both start_time and run_at filter messages correctly."""
    from utils.extraction import scan_new_messages_for_conversation

    dify = FakeDify()
    dify.msg_pages["c1"] = [
        _Page(
            items=[
                {"id": "m_future", "created_at": "2025-12-15T00:00:00Z", "query": "future"},
                {"id": "m_in_range", "created_at": "2025-12-05T00:00:00Z", "query": "in_range"},
                {"id": "m_old", "created_at": "2025-12-01T00:00:00Z", "query": "old"},
            ],
            next_cursor=None,
            has_more=False,
        ),
    ]

    messages, stats = scan_new_messages_for_conversation(
        dify,  # type: ignore[arg-type]
        user_id="u1",
        conversation_id="c1",
        run_at="2025-12-10T00:00:00Z",
        last_processed_message_id=None,
        start_time="2025-12-03T00:00:00Z",
    )

    assert len(messages) == 1
    assert messages[0]["id"] == "m_in_range"
    assert stats.scanned_messages == 3
    assert stats.dropped_future_messages == 1


def test_scan_user_conversations_with_start_time() -> None:
    """Verify scan_user_conversations_incremental passes start_time correctly."""
    dify = FakeDify()
    dify.conv_pages = [
        _Page(
            items=[{"id": "c1", "updated_at": "2025-12-05T00:00:00Z"}],
            next_cursor=None,
            has_more=False,
        ),
    ]
    dify.msg_pages["c1"] = [
        _Page(
            items=[
                {"id": "m_new", "created_at": "2025-12-05T00:00:00Z", "query": "new"},
                {"id": "m_old", "created_at": "2025-12-01T00:00:00Z", "query": "old"},
            ],
            next_cursor=None,
            has_more=False,
        ),
    ]

    segs, stats, _ = scan_user_conversations_incremental(
        dify,  # type: ignore[arg-type]
        user_id="u1",
        run_at="2025-12-10T00:00:00Z",
        user_checkpoint=None,
        start_time="2025-12-03T00:00:00Z",
    )

    assert "c1" in segs
    # segs now returns list of messages directly (no MessageSegment wrapper)
    all_msgs = segs["c1"]
    assert len(all_msgs) == 1
    assert all_msgs[0]["id"] == "m_new"
