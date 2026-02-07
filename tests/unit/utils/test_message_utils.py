from __future__ import annotations

from utils.message_utils import (
    count_add_event_stats,
    count_add_results,
    dify_msg_to_mem0_messages,
)


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


class TestDifyMessageNormalization:
    """Test Dify message to Mem0 message normalization."""

    def test_query_answer_pairs(self) -> None:
        dify_msgs = [
            {"id": "m1", "query": "What is AI?", "answer": "AI is artificial intelligence"},
            {"id": "m2", "query": "Tell me more", "answer": "Sure, AI includes..."},
        ]

        result = dify_msg_to_mem0_messages(dify_msgs)

        assert len(result) == 4
        assert result[0] == {"role": "user", "content": "What is AI?"}
        assert result[1] == {"role": "assistant", "content": "AI is artificial intelligence"}
        assert result[2] == {"role": "user", "content": "Tell me more"}
        assert result[3] == {"role": "assistant", "content": "Sure, AI includes..."}

    def test_role_content_format(self) -> None:
        dify_msgs = [
            {"id": "m1", "role": "user", "content": "Hello"},
            {"id": "m2", "role": "assistant", "content": "Hi there"},
        ]

        result = dify_msg_to_mem0_messages(dify_msgs)

        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "Hello"}
        assert result[1] == {"role": "assistant", "content": "Hi there"}

    def test_empty_content_skipped(self) -> None:
        dify_msgs = [
            {"id": "m1", "query": "", "answer": ""},
            {"id": "m2", "role": "user", "content": ""},
            {"id": "m3", "query": "Valid", "answer": "Response"},
        ]

        result = dify_msg_to_mem0_messages(dify_msgs)

        assert len(result) == 2
        assert result[0]["content"] == "Valid"
        assert result[1]["content"] == "Response"

    def test_whitespace_only_content_skipped(self) -> None:
        dify_msgs = [
            {"id": "m1", "query": "  ", "answer": "  "},
            {"id": "m2", "query": "Valid", "answer": "Response"},
        ]

        result = dify_msg_to_mem0_messages(dify_msgs)

        assert len(result) == 2

    def test_unknown_role_treated_as_user(self) -> None:
        dify_msgs = [
            {"id": "m1", "role": "system", "content": "System message"},
            {"id": "m2", "role": "unknown", "content": "Unknown role"},
        ]

        result = dify_msg_to_mem0_messages(dify_msgs)

        assert all(msg["role"] == "user" for msg in result)

    def test_mixed_formats(self) -> None:
        dify_msgs = [
            {"id": "m1", "query": "Question 1", "answer": "Answer 1"},
            {"id": "m2", "role": "user", "content": "Question 2"},
            {"id": "m3", "role": "assistant", "content": "Answer 2"},
        ]

        result = dify_msg_to_mem0_messages(dify_msgs)

        assert len(result) == 4
        assert result[0]["content"] == "Question 1"
        assert result[1]["content"] == "Answer 1"
        assert result[2]["content"] == "Question 2"
        assert result[3]["content"] == "Answer 2"


class TestMemoryAddResultCounting:
    """Test counting of Mem0 add operation results."""

    def test_count_add_update_events(self) -> None:
        result = {
            "results": [
                {"id": "m1", "event": "ADD"},
                {"id": "m2", "event": "UPDATE"},
                {"id": "m3", "event": "NONE"},
            ]
        }

        assert count_add_results(result) == 2

    def test_count_none_events_excluded(self) -> None:
        result = {"results": [{"id": "m1", "event": "NONE"}]}

        assert count_add_results(result) == 0

    def test_count_empty_results(self) -> None:
        assert count_add_results({}) == 0
        assert count_add_results({"results": []}) == 0
        assert count_add_results(None) == 0
        assert count_add_results({"results": None}) == 0

    def test_count_case_insensitive_events(self) -> None:
        result = {
            "results": [
                {"id": "m1", "event": "add"},
                {"id": "m2", "event": "UPDATE"},
                {"id": "m3", "event": "none"},
            ]
        }

        assert count_add_results(result) == 2

