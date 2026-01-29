"""Test time range expansion to prevent data loss."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest

from utils.extraction import (
    ConversationCheckpoint,
    UserCheckpoint,
    scan_new_messages_for_conversation,
)

if TYPE_CHECKING:
    pass


class FakeDifyClient:
    """Fake Dify client for testing."""

    def __init__(self, messages: list[dict[str, Any]]) -> None:
        """Initialize with predefined messages (newest first for reverse pagination)."""
        self.messages = messages

    def list_messages(
        self, *, user_id: str, conversation_id: str, first_id: str | None, limit: int
    ) -> Any:
        """Mock list_messages with reverse pagination."""
        if first_id is None:
            # First page: return newest messages
            items = self.messages[:limit]
        else:
            # Find the message with first_id and return older messages
            try:
                idx = next(
                    i for i, m in enumerate(self.messages) if m["id"] == first_id
                )
                items = self.messages[idx + 1 : idx + 1 + limit]
            except StopIteration:
                items = []

        next_cursor = items[-1]["id"] if items else None
        has_more = bool(items) and len(self.messages) > self.messages.index(items[-1]) + 1

        # Return a mock page object
        class Page:
            pass

        page = Page()
        page.items = items
        page.next_cursor = next_cursor
        page.has_more = has_more
        return page


class TestTimeRangeExpansion:
    """Test that time range expansion doesn't cause data loss."""

    def test_range_expansion_prevents_data_loss(self) -> None:
        """Test that expanding time range backward doesn't skip messages."""
        base_time = datetime.now(UTC)

        # Create messages at different times (newest first for reverse pagination)
        messages = [
            {
                "id": "msg5",
                "created_at": (base_time + timedelta(hours=4)).isoformat(),
                "content": "message 5",
            },
            {
                "id": "msg4",
                "created_at": (base_time + timedelta(hours=3)).isoformat(),
                "content": "message 4",
            },
            {
                "id": "msg3",
                "created_at": (base_time + timedelta(hours=2)).isoformat(),
                "content": "message 3",
            },
            {
                "id": "msg2",
                "created_at": (base_time + timedelta(hours=1)).isoformat(),
                "content": "message 2",
            },
            {
                "id": "msg1",
                "created_at": base_time.isoformat(),
                "content": "message 1",
            },
        ]

        client = FakeDifyClient(messages)

        # First run: process messages 2-4 (T+1h to T+3h)
        start_time1 = (base_time + timedelta(hours=1)).isoformat()
        end_time1 = (base_time + timedelta(hours=3)).isoformat()

        result1, stats1 = scan_new_messages_for_conversation(
            client,
            user_id="user1",
            conversation_id="conv1",
            run_at=end_time1,
            last_processed_message_id=None,
            start_time=start_time1,
        )

        # Should get msg2, msg3, msg4
        assert len(result1) == 3
        assert result1[0]["id"] == "msg2"
        assert result1[2]["id"] == "msg4"

        # Simulate checkpoint after first run
        checkpoint = ConversationCheckpoint(
            last_processed_message_id="msg2",
            processed_range_start=start_time1,
            processed_range_end=(base_time + timedelta(hours=3)).isoformat(),
        )

        # Second run: expand range backward to include msg1 (T+0h to T+4h)
        start_time2 = base_time.isoformat()
        end_time2 = (base_time + timedelta(hours=4)).isoformat()

        result2, stats2 = scan_new_messages_for_conversation(
            client,
            user_id="user1",
            conversation_id="conv1",
            run_at=end_time2,
            last_processed_message_id=checkpoint.last_processed_message_id,
            processed_range_start=checkpoint.processed_range_start,
            processed_range_end=checkpoint.processed_range_end,
            start_time=start_time2,
        )

        # Should get msg1 and msg5 (msg2-4 already processed)
        # With range expansion detection, it should continue scanning past msg2
        assert len(result2) >= 1  # At least msg1 should be found
        msg_ids = [m["id"] for m in result2]
        assert "msg1" in msg_ids  # ✅ msg1 should NOT be skipped!
        assert "msg5" in msg_ids  # msg5 is new

    def test_no_range_expansion_stops_at_checkpoint(self) -> None:
        """Test that without range expansion, checkpoint stops scanning normally."""
        base_time = datetime.now(UTC)

        messages = [
            {
                "id": "msg3",
                "created_at": (base_time + timedelta(hours=2)).isoformat(),
                "content": "message 3",
            },
            {
                "id": "msg2",
                "created_at": (base_time + timedelta(hours=1)).isoformat(),
                "content": "message 2",
            },
            {
                "id": "msg1",
                "created_at": base_time.isoformat(),
                "content": "message 1",
            },
        ]

        client = FakeDifyClient(messages)

        # First run: process msg1-2
        start_time1 = base_time.isoformat()
        end_time1 = (base_time + timedelta(hours=1)).isoformat()

        result1, _ = scan_new_messages_for_conversation(
            client,
            user_id="user1",
            conversation_id="conv1",
            run_at=end_time1,
            last_processed_message_id=None,
            start_time=start_time1,
        )

        assert len(result1) == 2
        assert result1[0]["id"] == "msg1"

        # Checkpoint after first run
        checkpoint = ConversationCheckpoint(
            last_processed_message_id="msg1",
            processed_range_start=start_time1,
            processed_range_end=(base_time + timedelta(hours=1)).isoformat(),
        )

        # Second run: extend range forward (no backward expansion)
        start_time2 = base_time.isoformat()  # Same start
        end_time2 = (base_time + timedelta(hours=2)).isoformat()  # Extended forward

        result2, _ = scan_new_messages_for_conversation(
            client,
            user_id="user1",
            conversation_id="conv1",
            run_at=end_time2,
            last_processed_message_id=checkpoint.last_processed_message_id,
            processed_range_start=checkpoint.processed_range_start,
            processed_range_end=checkpoint.processed_range_end,
            start_time=start_time2,
        )

        # Should only get msg3 (checkpoint stops at msg1)
        assert len(result2) == 1
        assert result2[0]["id"] == "msg3"

    def test_checkpoint_backward_compatibility(self) -> None:
        """Test that old checkpoints without range fields still work."""
        base_time = datetime.now(UTC)

        messages = [
            {
                "id": "msg2",
                "created_at": (base_time + timedelta(hours=1)).isoformat(),
                "content": "message 2",
            },
            {
                "id": "msg1",
                "created_at": base_time.isoformat(),
                "content": "message 1",
            },
        ]

        client = FakeDifyClient(messages)

        # Old checkpoint without range fields (None)
        checkpoint = ConversationCheckpoint(
            last_processed_message_id="msg1",
            processed_range_start=None,  # Old checkpoint
            processed_range_end=None,  # Old checkpoint
        )

        # New run should work with old checkpoint
        start_time = base_time.isoformat()
        end_time = (base_time + timedelta(hours=1)).isoformat()

        result, _ = scan_new_messages_for_conversation(
            client,
            user_id="user1",
            conversation_id="conv1",
            run_at=end_time,
            last_processed_message_id=checkpoint.last_processed_message_id,
            processed_range_start=checkpoint.processed_range_start,
            processed_range_end=checkpoint.processed_range_end,
            start_time=start_time,
        )

        # Should get msg2 (stops at msg1 checkpoint)
        assert len(result) == 1
        assert result[0]["id"] == "msg2"

