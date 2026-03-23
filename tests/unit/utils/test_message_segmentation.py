from __future__ import annotations

from utils.extraction import segment_messages


class TestMessageSegmentation:
    """Test segment_messages pure-logic splitting by count and token budget."""

    def test_segment_messages_respects_max_messages(self) -> None:
        """Verify segmentation splits by message count."""
        messages = [{"id": f"m{i}", "content": "test"} for i in range(50)]

        segments = segment_messages(messages, max_messages=10, max_tokens=10000)

        assert len(segments) >= 5
        for seg in segments:
            assert len(seg.messages) <= 10

    def test_segment_messages_respects_max_tokens(self) -> None:
        """Verify segmentation splits by token estimate."""
        messages = [{"id": f"m{i}", "content": "x" * 1000} for i in range(10)]

        segments = segment_messages(messages, max_messages=100, max_tokens=500)

        assert len(segments) >= 5
        for seg in segments:
            total_chars = sum(len(m.get("content", "")) for m in seg.messages)
            assert total_chars // 4 <= 600

    def test_segment_empty_messages_returns_empty(self) -> None:
        """Verify empty message list returns empty segments."""
        segments = segment_messages([])
        assert segments == []

    def test_segment_single_message_returns_single_segment(self) -> None:
        """Verify single message returns single segment."""
        messages = [{"id": "m1", "content": "test"}]
        segments = segment_messages(messages)

        assert len(segments) == 1
        assert len(segments[0].messages) == 1
        assert segments[0].segment_id == "m1_m1"
