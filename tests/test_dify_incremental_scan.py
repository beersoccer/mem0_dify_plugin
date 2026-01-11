from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from utils.consolidation import ConversationCheckpoint, UserCheckpoint, scan_user_conversations_incremental


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


def test_incremental_stop_on_updated_at() -> None:
    dify = FakeDify()
    dify.conv_pages = [
        _Page(
            items=[
                {"id": "c_new", "updated_at": "2025-12-05T00:00:00Z"},
                {"id": "c_old", "updated_at": "2025-12-01T00:00:00Z"},
            ],
            next_cursor=None,
            has_more=False,
        ),
    ]
    dify.msg_pages["c_new"] = [
        _Page(items=[{"id": "m1", "created_at": "2025-12-04T00:00:00Z", "query": "hi"}], next_cursor=None, has_more=False),
    ]
    cp = UserCheckpoint(last_run_at="2025-12-02T00:00:00Z", conversations={})

    segs, stats, stop_reason = scan_user_conversations_incremental(
        dify,  # type: ignore[arg-type]
        user_id="u1",
        run_at="2025-12-10T00:00:00Z",
        user_checkpoint=cp,
        app_id=None,
    )
    assert "c_new" in segs
    assert stop_reason == "checkpoint_updated_at"
    assert stats.scanned_conversations >= 2


def test_drop_future_messages_and_stop_on_last_processed_message_id() -> None:
    dify = FakeDify()
    dify.conv_pages = [
        _Page(items=[{"id": "c1", "updated_at": "2025-12-05T00:00:00Z"}], next_cursor=None, has_more=False),
    ]
    dify.msg_pages["c1"] = [
        _Page(
            items=[
                {"id": "m_future", "created_at": "2025-12-11T00:00:00Z", "query": "future"},
                {"id": "m_new", "created_at": "2025-12-04T00:00:00Z", "query": "new"},
                {"id": "m_old", "created_at": "2025-12-01T00:00:00Z", "query": "old"},
            ],
            next_cursor=None,
            has_more=False,
        ),
    ]
    cp = UserCheckpoint(
        last_run_at="2025-11-01T00:00:00Z",
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


