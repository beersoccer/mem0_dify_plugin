"""Integration tests for Dify chat history retrieval using real Dify API.

This test suite validates the extract_long_term_memory tool against a real
Dify instance. All runtime data (user IDs, conversation IDs, time windows)
comes from the session-scoped ``integration_seed`` fixture — no manual
``DIFY_USER_ID`` configuration is required in ``.env.local``.

Static connection config (``DIFY_BASE_URL``, ``DIFY_CHATFLOW_API_KEY``) is the only
thing read from ``.env.local``.

Pure-logic tests (segmentation, message normalisation, checkpoint, budget
control) have been moved to tests/unit/.
"""

from __future__ import annotations

import pytest

from tests.helpers.dify_seed import SeedManifest
from utils.dify_client import DifyAPIError, DifyClient
from utils.extraction import (
    UserCheckpoint,
    scan_new_messages_for_conversation,
    scan_user_conversations_incremental,
)
from utils.helpers import parse_iso_timestamp

pytestmark = pytest.mark.dify_api


@pytest.fixture
def dify_client(dify_client_session: DifyClient) -> DifyClient:
    """Re-expose the session DifyClient for function-scoped use."""
    return dify_client_session


class TestDifyClientConnectivity:
    """Test basic Dify API connectivity and response structure.

    Data comes entirely from ``integration_seed`` — no pre-existing Dify data
    is required and no ``DIFY_USER_ID`` env var is needed.
    """

    def test_list_conversations_returns_valid_page(
        self, dify_client: DifyClient, integration_seed: SeedManifest
    ) -> None:
        """Verify conversations API returns valid page structure."""
        user_id = integration_seed.primary_user_id
        page = dify_client.list_conversations(user_id=user_id, limit=5)

        assert isinstance(page.items, list)
        assert len(page.items) > 0, "seed 应至少生成一个会话"
        assert isinstance(page.has_more, bool)
        assert page.next_cursor is None or isinstance(page.next_cursor, str)

        conv = page.items[0]
        assert isinstance(conv, dict)
        assert "id" in conv
        assert "updated_at" in conv or "created_at" in conv

    def test_list_conversations_pagination(
        self, dify_client: DifyClient, integration_seed: SeedManifest
    ) -> None:
        """Verify pagination works when a user has more than 2 conversations.

        ``integration_seed`` is configured with ``extra_per_user=2``, so the
        primary user will always have ≥ 3 conversations.
        """
        user_id = integration_seed.primary_user_id
        primary_convs = integration_seed.primary_conversations
        assert len(primary_convs) >= 3, (
            f"primary user {user_id!r} has only {len(primary_convs)} seeded "
            "conversations; need ≥ 3 for pagination test"
        )

        page1 = dify_client.list_conversations(user_id=user_id, limit=2)
        assert page1.items, "第一页应有结果"
        assert page1.has_more, "3 个会话用 limit=2 查询，has_more 应为 True"

        page2 = dify_client.list_conversations(
            user_id=user_id, limit=2, last_id=page1.next_cursor
        )
        assert isinstance(page2.items, list)
        assert page1.items[0]["id"] != page2.items[0]["id"], "两页首条记录应不同"

    def test_list_messages_returns_valid_page(
        self, dify_client: DifyClient, integration_seed: SeedManifest
    ) -> None:
        """Verify messages API returns valid page structure using a seeded conversation."""
        primary = integration_seed.primary_conversations[0]
        msg_page = dify_client.list_messages(
            user_id=primary.user_id,
            conversation_id=primary.conversation_id,
            limit=10,
        )

        assert isinstance(msg_page.items, list)
        assert len(msg_page.items) > 0, "seed 应至少写入一条消息"
        assert isinstance(msg_page.has_more, bool)

        msg = msg_page.items[0]
        assert isinstance(msg, dict)
        assert "id" in msg
        assert "created_at" in msg

    def test_invalid_api_key_raises_error(
        self, integration_env_config: dict[str, str], integration_seed: SeedManifest
    ) -> None:
        """Verify invalid API key raises DifyAPIError."""
        from tests.helpers.dify_env import normalize_base_url

        base_url = normalize_base_url(integration_env_config.get("DIFY_BASE_URL"))
        bad_client = DifyClient(base_url=base_url, api_key="invalid-key-12345")

        with pytest.raises(DifyAPIError):
            bad_client.list_conversations(user_id=integration_seed.primary_user_id)


class TestIncrementalScanRealData:
    """Test incremental scan logic against seeded Dify data."""

    def test_scan_new_messages_respects_run_at_cutoff(
        self, dify_client: DifyClient, integration_seed: SeedManifest
    ) -> None:
        """Messages created after run_at should be dropped.

        We use ``started_at - 120s`` as ``run_at``, which predates all seeded
        messages, so the returned list must be empty.
        """
        primary = integration_seed.primary_conversations[0]
        run_at = integration_seed.started_at_with_buffer(-120)

        messages, stats = scan_new_messages_for_conversation(
            dify_client,
            user_id=primary.user_id,
            conversation_id=primary.conversation_id,
            run_at=run_at,
            last_processed_message_id=None,
        )

        assert isinstance(messages, list)
        assert messages == [], (
            f"run_at={run_at} predates seed; all messages should be filtered out"
        )
        assert stats.dropped_future_messages >= 0

    def test_scan_with_time_range_from_seed(
        self, dify_client: DifyClient, integration_seed: SeedManifest
    ) -> None:
        """Messages scanned within the seed time window must all fall inside it."""
        user_id = integration_seed.primary_user_id
        start_time = integration_seed.started_at_with_buffer(-60)
        end_time = integration_seed.finished_at_with_buffer(60)

        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)
        assert start_dt and end_dt

        segments, stats, _ = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=end_time,
            user_checkpoint=None,
            start_time=start_time,
        )

        for segs in segments.values():
            for msg in segs:
                created_at = parse_iso_timestamp(msg.get("created_at"))
                if created_at:
                    assert created_at.timestamp() >= start_dt.timestamp(), (
                        f"Message {msg.get('id')} is before start_time {start_time}"
                    )
                    assert created_at.timestamp() <= end_dt.timestamp(), (
                        f"Message {msg.get('id')} is after end_time {end_time}"
                    )

        assert isinstance(segments, dict)
        assert stats.scanned_conversations >= 0

    def test_scan_conversations_incremental_with_checkpoint(
        self, dify_client: DifyClient, integration_seed: SeedManifest
    ) -> None:
        """Verify incremental scan works with an existing (empty) checkpoint."""
        user_id = integration_seed.primary_user_id

        segments, stats, stop_reason = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at="2100-01-01T00:00:00Z",
            user_checkpoint=UserCheckpoint(),
        )

        assert stop_reason in {"no_more_conversations", "completed", "max_conversations_reached"}
        assert stats.scanned_conversations >= 0

    def test_scan_with_no_checkpoint_processes_all(
        self, dify_client: DifyClient, integration_seed: SeedManifest
    ) -> None:
        """Verify scan without checkpoint processes all seeded conversations."""
        user_id = integration_seed.primary_user_id
        expected_count = len(integration_seed.primary_conversations)

        segments, stats, stop_reason = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at="2100-01-01T00:00:00Z",
            user_checkpoint=None,
        )

        assert isinstance(segments, dict)
        assert stats.scanned_conversations >= expected_count, (
            f"expected ≥ {expected_count} conversations to be scanned, "
            f"got {stats.scanned_conversations}"
        )
        assert stop_reason in {"no_more_conversations", "completed", "max_conversations_reached"}

    def test_seeded_conversations_visible_to_incremental_scan(
        self, dify_client: DifyClient, integration_seed: SeedManifest
    ) -> None:
        """Each seeded conversation must appear in the incremental scan result."""
        start_time = integration_seed.started_at_with_buffer(-60)
        end_time = integration_seed.finished_at_with_buffer(60)

        for seeded in integration_seed.conversations:
            conversations_data, stats, _ = scan_user_conversations_incremental(
                dify_client,
                user_id=seeded.user_id,
                run_at=end_time,
                user_checkpoint=None,
                start_time=start_time,
                app_id=None,
                max_conversations=50,
            )
            assert stats.scanned_conversations >= 1, (
                f"user {seeded.user_id!r}: expected ≥ 1 scanned conversation"
            )
            assert stats.scanned_messages >= 1, (
                f"user {seeded.user_id!r}: expected ≥ 1 scanned message"
            )
            assert seeded.conversation_id in conversations_data, (
                f"seeded conversation {seeded.conversation_id!r} not found in scan result "
                f"for user {seeded.user_id!r}"
            )
            assert len(conversations_data[seeded.conversation_id]) >= 1, (
                f"seeded conversation {seeded.conversation_id!r} has no messages in scan result"
            )
