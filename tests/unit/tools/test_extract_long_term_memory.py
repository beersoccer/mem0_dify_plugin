from __future__ import annotations

import pytest


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
    from tools.extract_long_term_memory import _dedup_keep_order

    assert _dedup_keep_order(["a", "b", "a", "c"]) == ["a", "b", "c"]
    assert _dedup_keep_order(["x", "x", "x"]) == ["x"]
    assert _dedup_keep_order([]) == []


def test_cmp_iso_timestamps() -> None:
    from tools.extract_long_term_memory import _cmp_iso

    assert _cmp_iso("2025-12-01T00:00:00Z", "2025-12-02T00:00:00Z") == -1
    assert _cmp_iso("2025-12-02T00:00:00Z", "2025-12-01T00:00:00Z") == 1
    assert _cmp_iso("2025-12-01T00:00:00Z", "2025-12-01T00:00:00Z") == 0
    assert _cmp_iso(None, "2025-12-01T00:00:00Z") == -1
    assert _cmp_iso("2025-12-01T00:00:00Z", None) == 1
    assert _cmp_iso(None, None) == 0


class TestDifyMessageNormalization:
    """Test Dify message to Mem0 message normalization."""

    def test_query_answer_pairs(self) -> None:
        from utils.message_utils import dify_msg_to_mem0_messages

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
        from utils.message_utils import dify_msg_to_mem0_messages

        dify_msgs = [
            {"id": "m1", "role": "user", "content": "Hello"},
            {"id": "m2", "role": "assistant", "content": "Hi there"},
        ]

        result = dify_msg_to_mem0_messages(dify_msgs)

        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "Hello"}
        assert result[1] == {"role": "assistant", "content": "Hi there"}

    def test_empty_content_skipped(self) -> None:
        from utils.message_utils import dify_msg_to_mem0_messages

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
        from utils.message_utils import dify_msg_to_mem0_messages

        dify_msgs = [
            {"id": "m1", "query": "  ", "answer": "  "},
            {"id": "m2", "query": "Valid", "answer": "Response"},
        ]

        result = dify_msg_to_mem0_messages(dify_msgs)

        assert len(result) == 2

    def test_unknown_role_treated_as_user(self) -> None:
        from utils.message_utils import dify_msg_to_mem0_messages

        dify_msgs = [
            {"id": "m1", "role": "system", "content": "System message"},
            {"id": "m2", "role": "unknown", "content": "Unknown role"},
        ]

        result = dify_msg_to_mem0_messages(dify_msgs)

        assert all(msg["role"] == "user" for msg in result)

    def test_mixed_formats(self) -> None:
        from utils.message_utils import dify_msg_to_mem0_messages

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
        from utils.message_utils import count_add_results

        result = {
            "results": [
                {"id": "m1", "event": "ADD"},
                {"id": "m2", "event": "UPDATE"},
                {"id": "m3", "event": "NONE"},
            ]
        }

        assert count_add_results(result) == 2

    def test_count_none_events_excluded(self) -> None:
        from utils.message_utils import count_add_results

        result = {"results": [{"id": "m1", "event": "NONE"}]}

        assert count_add_results(result) == 0

    def test_count_empty_results(self) -> None:
        from utils.message_utils import count_add_results

        assert count_add_results({}) == 0
        assert count_add_results({"results": []}) == 0
        assert count_add_results(None) == 0
        assert count_add_results({"results": None}) == 0

    def test_count_case_insensitive_events(self) -> None:
        from utils.message_utils import count_add_results

        result = {
            "results": [
                {"id": "m1", "event": "add"},
                {"id": "m2", "event": "UPDATE"},
                {"id": "m3", "event": "none"},
            ]
        }

        assert count_add_results(result) == 2

