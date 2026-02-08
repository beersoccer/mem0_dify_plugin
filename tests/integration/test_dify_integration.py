"""Integration tests for Dify chat history retrieval using real Dify API.

This test suite validates the extract_long_term_memory tool against a real
Dify instance using credentials from tests/.env. It verifies:
- Real API connectivity and pagination
- Message retrieval and filtering
- Checkpoint persistence and idempotency
- Budget control and priority degradation
- Error handling for API failures

Prerequisites:
- Dify instance running (docker compose)
- tests/.env file with valid credentials
- At least one user with chat history in Dify
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from utils.checkpoint import SyncCheckpointManager
from utils.dify_client import DifyAPIError, DifyClient
from utils.extraction import (
    UserCheckpoint,
    scan_new_messages_for_conversation,
    scan_user_conversations_incremental,
    segment_messages,
)
from utils.helpers import parse_iso_timestamp


def load_env_dev() -> dict[str, str]:
    """Load credentials from .env file."""
    # .env 文件应该在 tests/.env，而不是 tests/integration/.env
    env_file = Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        pytest.skip("No .env file found in tests/ directory")

    env_vars: dict[str, str] = {}
    with env_file.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            env_vars[key.strip()] = value.strip().strip('"')

    # DIFY_USER_ID can be extracted from DIFY_USER_IDS if not explicitly set
    if "DIFY_USER_ID" not in env_vars and "DIFY_USER_IDS" in env_vars:
        test_user_ids = env_vars["DIFY_USER_IDS"]
        first_user = test_user_ids.split(",")[0].strip()
        if first_user:
            env_vars["DIFY_USER_ID"] = first_user
    
    required = ["DIFY_API_KEY", "DIFY_USER_ID"]
    missing = [k for k in required if k not in env_vars]
    if missing:
        pytest.skip(f"Missing required env vars in .env: {missing}")

    return env_vars


def normalize_base_url(raw_base_url: str | None) -> str:
    """Ensure base_url has scheme and ends with /v1."""
    base_url = (raw_base_url or "").strip()
    if not base_url:
        return ""
    if not base_url.startswith("http"):
        base_url = f"http://{base_url}"
    base_url = base_url.rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return base_url


@pytest.fixture
def env_config() -> dict[str, str]:
    """Fixture providing .env configuration."""
    return load_env_dev()


@pytest.fixture
def dify_client(env_config: dict[str, str]) -> DifyClient:
    """Fixture providing configured DifyClient."""
    base_url = normalize_base_url(env_config.get("DIFY_BASE_URL", "http://localhost/v1"))
    api_key = env_config["DIFY_API_KEY"]
    return DifyClient(base_url=base_url, api_key=api_key)


class TestDifyClientConnectivity:
    """Test basic Dify API connectivity and pagination."""

    def test_list_conversations_returns_valid_page(
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Verify conversations API returns valid page structure."""
        user_id = env_config["DIFY_USER_ID"]
        page = dify_client.list_conversations(user_id=user_id, limit=5)

        assert isinstance(page.items, list)
        assert isinstance(page.has_more, bool)
        assert page.next_cursor is None or isinstance(page.next_cursor, str)

        if page.items:
            conv = page.items[0]
            assert isinstance(conv, dict)
            assert "id" in conv
            assert "updated_at" in conv or "created_at" in conv

    def test_list_conversations_pagination(
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Verify conversations pagination works correctly."""
        user_id = env_config["DIFY_USER_ID"]

        page1 = dify_client.list_conversations(user_id=user_id, limit=2)
        if not page1.items or not page1.has_more:
            pytest.skip("Not enough conversations for pagination test")

        page2 = dify_client.list_conversations(
            user_id=user_id, limit=2, last_id=page1.next_cursor
        )

        assert isinstance(page2.items, list)
        if page1.items and page2.items:
            assert page1.items[0]["id"] != page2.items[0]["id"]

    def test_list_messages_returns_valid_page(
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Verify messages API returns valid page structure."""
        user_id = env_config["DIFY_USER_ID"]

        conv_page = dify_client.list_conversations(user_id=user_id, limit=1)
        if not conv_page.items:
            pytest.skip("No conversations found for user")

        conv_id = conv_page.items[0]["id"]
        msg_page = dify_client.list_messages(
            user_id=user_id, conversation_id=conv_id, limit=10
        )

        assert isinstance(msg_page.items, list)
        assert isinstance(msg_page.has_more, bool)

        if msg_page.items:
            msg = msg_page.items[0]
            assert isinstance(msg, dict)
            assert "id" in msg
            assert "created_at" in msg

    def test_invalid_api_key_raises_error(self, env_config: dict[str, str]) -> None:
        """Verify invalid API key raises DifyAPIError."""
        base_url = normalize_base_url(env_config.get("DIFY_BASE_URL", "http://localhost/v1"))

        bad_client = DifyClient(base_url=base_url, api_key="invalid-key-12345")
        user_id = env_config["DIFY_USER_ID"]

        with pytest.raises(DifyAPIError):
            bad_client.list_conversations(user_id=user_id)


class TestIncrementalScanRealData:
    """Test incremental scan logic with real Dify data."""

    def test_scan_new_messages_respects_run_at_cutoff(
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Verify messages created after run_at are dropped."""
        user_id = env_config["DIFY_USER_ID"]

        conv_page = dify_client.list_conversations(user_id=user_id, limit=1)
        if not conv_page.items:
            pytest.skip("No conversations found")

        conv_id = conv_page.items[0]["id"]

        run_at = "2020-01-01T00:00:00Z"
        messages, stats = scan_new_messages_for_conversation(
            dify_client,
            user_id=user_id,
            conversation_id=conv_id,
            run_at=run_at,
            last_processed_message_id=None,
        )

        assert isinstance(messages, list)
        assert stats.dropped_future_messages >= 0

        for msg in messages:
            created_at = parse_iso_timestamp(msg.get("created_at"))
            run_at_dt = parse_iso_timestamp(run_at)
            if created_at and run_at_dt:
                assert created_at.timestamp() <= run_at_dt.timestamp()

    def test_scan_with_time_range_from_env(
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Test scanning messages within a specific time range from .env.
        
        This test uses TEST_START_TIME and TEST_END_TIME from .env to filter
        messages to a specific time window. Useful for testing with known test data.
        """
        user_id = env_config["DIFY_USER_ID"]
        start_time = env_config.get("TEST_START_TIME")
        end_time = env_config.get("TEST_END_TIME")

        if not start_time or not end_time:
            pytest.skip("TEST_START_TIME and TEST_END_TIME not set in .env")

        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)
        if not start_dt or not end_dt:
            pytest.skip("Invalid TEST_START_TIME or TEST_END_TIME format")

        print(f"\n  Testing time range: {start_time} to {end_time}")
        print(f"  Duration: {(end_dt.timestamp() - start_dt.timestamp()):.0f} seconds")

        segments, stats, stop_reason = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=end_time,
            user_checkpoint=None,
            start_time=start_time,
        )

        print(f"  Stop reason: {stop_reason}")
        print(f"  Scanned conversations: {stats.scanned_conversations}")
        print(f"  Scanned messages: {stats.scanned_messages}")
        print(f"  Dropped future messages: {stats.dropped_future_messages}")
        print(f"  Conversations with messages in range: {stats.conversations_with_new_messages}")

        total_messages = sum(
            len(msgs) for msgs in segments.values()
        )
        print(f"  Total messages in time range: {total_messages}")

        for segs in segments.values():
            for msg in segs:
                    created_at = parse_iso_timestamp(msg.get("created_at"))
                    if created_at:
                        assert created_at.timestamp() >= start_dt.timestamp(), (
                            f"Message {msg.get('id')} created_at {msg.get('created_at')} "
                            f"is before start_time {start_time}"
                        )
                        assert created_at.timestamp() <= end_dt.timestamp(), (
                            f"Message {msg.get('id')} created_at {msg.get('created_at')} "
                            f"is after end_time {end_time}"
                        )

        assert isinstance(segments, dict)
        assert stats.scanned_conversations >= 0

    def test_scan_conversations_incremental_with_checkpoint(
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Verify scan works with an existing checkpoint."""
        user_id = env_config["DIFY_USER_ID"]

        checkpoint = UserCheckpoint()
        run_at = "2100-01-01T00:00:00Z"

        segments, stats, stop_reason = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=run_at,
            user_checkpoint=checkpoint,
        )

        assert stop_reason in {
            "no_more_conversations",
            "completed",
            "max_conversations_reached",
        }
        assert stats.scanned_conversations >= 0

    def test_scan_with_no_checkpoint_processes_all(
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Verify scan without checkpoint processes all conversations."""
        user_id = env_config["DIFY_USER_ID"]
        run_at = "2100-01-01T00:00:00Z"

        segments, stats, stop_reason = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=run_at,
            user_checkpoint=None,
        )

        assert isinstance(segments, dict)
        assert stats.scanned_conversations >= 0
        assert stop_reason in {
            "no_more_conversations",
            "completed",
            "max_conversations_reached",
        }


class TestMessageSegmentation:
    """Test message segmentation logic."""

    def test_segment_messages_respects_max_messages(self) -> None:
        """Verify segmentation splits by message count."""
        messages = [{"id": f"m{i}", "content": "test"} for i in range(50)]

        segments = segment_messages(messages, max_messages=10, max_tokens=10000)

        assert len(segments) >= 5
        for seg in segments:
            assert len(seg.messages) <= 10  # seg is a MessageSegment object

    def test_segment_messages_respects_max_tokens(self) -> None:
        """Verify segmentation splits by token estimate."""
        messages = [
            {"id": f"m{i}", "content": "x" * 1000} for i in range(10)
        ]  # ~250 tokens each

        segments = segment_messages(messages, max_messages=100, max_tokens=500)

        assert len(segments) >= 5
        for seg in segments:
            # seg is a MessageSegment object
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


class TestCheckpointPersistence:
    """Test checkpoint persistence with fake memory client."""

    class FakeMemory:
        """Minimal fake memory client for testing."""

        def __init__(self) -> None:
            self._store: list[dict[str, Any]] = []
            self.get_all_calls: list[dict[str, Any]] = []

        def get_all(self, **kwargs: Any) -> dict[str, Any]:
            self.get_all_calls.append(kwargs)
            filters = kwargs.get("filters", {})
            results = []
            for item in self._store:
                if self._match_filters(item.get("metadata", {}), filters):
                    results.append(item)
            return {"results": results}

        def _match_filters(self, metadata: dict[str, Any], filters: Any) -> bool:
            if not filters:
                return True
            if not isinstance(filters, dict):
                return True
            if "AND" in filters:
                parts = filters.get("AND", [])
                return all(self._match_filters(metadata, f) for f in parts)
            for key, value in filters.items():
                if isinstance(value, dict) and "eq" in value:
                    if metadata.get(key) != value["eq"]:
                        return False
                elif metadata.get(key) != value:
                    return False
            return True

        def add(self, text: str, **kwargs: Any) -> dict[str, Any]:
            new_id = f"mem_{len(self._store) + 1}"
            self._store.append(
                {"id": new_id, "memory": text, "metadata": kwargs.get("metadata", {})}
            )
            return {"results": [{"id": new_id, "event": "ADD"}]}

        def update(self, memory_id: str, text: str) -> dict[str, Any]:
            for item in self._store:
                if item["id"] == memory_id:
                    item["memory"] = text
                    return {"message": "updated"}
            return {"message": "not found"}

        def delete(self, memory_id: str) -> dict[str, Any]:
            self._store = [x for x in self._store if x["id"] != memory_id]
            return {"message": "deleted"}

    def test_checkpoint_roundtrip(self) -> None:
        """Verify checkpoint can be saved and loaded."""
        mem = self.FakeMemory()
        mgr = SyncCheckpointManager(mem)

        checkpoint = UserCheckpoint(
            conversations={}
        )

        ok, cp_id = mgr.save(
            checkpoint_id=None, user_id="u1", app_id=None, checkpoint=checkpoint
        )

        assert ok is True
        assert cp_id is not None

        loaded_id, loaded_cp = mgr.load(user_id="u1", app_id=None)

        assert loaded_id == cp_id
        assert loaded_cp is not None
        assert loaded_cp.conversations == {}

    def test_checkpoint_update_same_id(self) -> None:
        """Verify updating checkpoint reuses same ID."""
        mem = self.FakeMemory()
        mgr = SyncCheckpointManager(mem)

        cp1 = UserCheckpoint()
        ok1, id1 = mgr.save(
            checkpoint_id=None, user_id="u1", app_id=None, checkpoint=cp1
        )

        cp2 = UserCheckpoint()
        ok2, id2 = mgr.save(
            checkpoint_id=id1, user_id="u1", app_id=None, checkpoint=cp2
        )

        assert ok2 is True
        assert id2 == id1

        _, loaded = mgr.load(user_id="u1", app_id=None)
        assert loaded is not None
        assert loaded.conversations == {}


class TestDifyMessageNormalization:
    """Test Dify message format normalization."""

    def test_dify_msg_to_mem0_messages_query_answer_pairs(self) -> None:
        """Verify query/answer pairs are normalized correctly."""
        from utils.message_utils import dify_msg_to_mem0_messages

        dify_messages = [
            {"id": "m1", "query": "What is AI?", "answer": "AI is..."},
            {"id": "m2", "query": "Tell me more", "answer": "Sure..."},
        ]

        mem0_msgs = dify_msg_to_mem0_messages(dify_messages)

        assert len(mem0_msgs) == 4
        assert mem0_msgs[0] == {"role": "user", "content": "What is AI?"}
        assert mem0_msgs[1] == {"role": "assistant", "content": "AI is..."}
        assert mem0_msgs[2] == {"role": "user", "content": "Tell me more"}
        assert mem0_msgs[3] == {"role": "assistant", "content": "Sure..."}

    def test_dify_msg_to_mem0_messages_role_content_format(self) -> None:
        """Verify role/content format is normalized correctly."""
        from utils.message_utils import dify_msg_to_mem0_messages

        dify_messages = [
            {"id": "m1", "role": "user", "content": "Hello"},
            {"id": "m2", "role": "assistant", "content": "Hi there"},
        ]

        mem0_msgs = dify_msg_to_mem0_messages(dify_messages)

        assert len(mem0_msgs) == 2
        assert mem0_msgs[0] == {"role": "user", "content": "Hello"}
        assert mem0_msgs[1] == {"role": "assistant", "content": "Hi there"}

    def test_dify_msg_to_mem0_messages_empty_content_skipped(self) -> None:
        """Verify empty content messages are skipped."""
        from utils.message_utils import dify_msg_to_mem0_messages

        dify_messages = [
            {"id": "m1", "query": "", "answer": ""},
            {"id": "m2", "role": "user", "content": ""},
            {"id": "m3", "query": "Valid", "answer": "Response"},
        ]

        mem0_msgs = dify_msg_to_mem0_messages(dify_messages)

        assert len(mem0_msgs) == 2
        assert mem0_msgs[0]["content"] == "Valid"
        assert mem0_msgs[1]["content"] == "Response"


class TestBudgetControl:
    """Test budget control and priority degradation."""

    def test_count_add_results(self) -> None:
        """Verify memory add result counting."""
        from utils.message_utils import count_add_results

        result = {
            "results": [
                {"id": "m1", "event": "ADD"},
                {"id": "m2", "event": "UPDATE"},
                {"id": "m3", "event": "NONE"},
            ]
        }

        count = count_add_results(result)
        assert count == 2

    def test_count_add_results_empty(self) -> None:
        """Verify empty result returns zero."""
        from utils.message_utils import count_add_results

        assert count_add_results({}) == 0
        assert count_add_results({"results": []}) == 0
        assert count_add_results(None) == 0


class TestEndToEndExtraction:
    """End-to-end integration tests requiring full Dify + Mem0 setup.

    These tests require full Dify + Mem0 setup.
    """

    def test_extract_with_real_dify_and_mem0(
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Full end-to-end test with real Dify and Mem0 (requires setup)."""
