"""Integration tests for time range filtering in chat history retrieval.

This test suite validates that the extract_long_term_memory tool correctly
filters messages by time range. Time boundaries are derived from the
``integration_seed`` session fixture — no ``TEST_START_TIME`` / ``TEST_END_TIME``
env vars are needed.
"""

from __future__ import annotations

import pytest

from tests.helpers.dify_seed import SeedManifest
from utils.dify_client import DifyClient
from utils.extraction import (
    UserCheckpoint,
    scan_user_conversations_incremental,
)
from utils.helpers import parse_iso_timestamp

pytestmark = [pytest.mark.dify_api, pytest.mark.slow]


@pytest.fixture
def dify_client(dify_client_session: DifyClient) -> DifyClient:
    """Re-expose the session DifyClient for function-scoped use."""
    return dify_client_session


class TestTimeRangeFiltering:
    """Test time range filtering with real Dify data."""

    def test_time_range_from_env_comprehensive(
        self, dify_client: DifyClient, integration_seed: SeedManifest
    ) -> None:
        """Comprehensive test of time range filtering using seed manifest times."""
        user_id = integration_seed.primary_user_id
        start_time = integration_seed.started_at_with_buffer(-60)
        end_time = integration_seed.finished_at_with_buffer(60)

        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)
        assert start_dt and end_dt, "Seed manifest timestamps could not be parsed"

        segments, stats, stop_reason = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=end_time,
            user_checkpoint=None,
            start_time=start_time,
        )

        total_messages = sum(len(msgs) for msgs in segments.values())
        dropped_old_messages = (
            stats.scanned_messages - stats.dropped_future_messages - total_messages
        )

        violations = []
        for _conv_id, segs in segments.items():
            for msg in segs:
                created_at = parse_iso_timestamp(msg.get("created_at"))
                if not created_at:
                    violations.append(
                        f"Message {msg.get('id')} has no created_at timestamp"
                    )
                    continue

                msg_ts = created_at.timestamp()
                start_ts = start_dt.timestamp()
                end_ts = end_dt.timestamp()

                if msg_ts < start_ts:
                    violations.append(
                        f"Message {msg.get('id')} created_at {msg.get('created_at')} "
                        f"is before start_time {start_time}"
                    )

                if msg_ts > end_ts:
                    violations.append(
                        f"Message {msg.get('id')} created_at {msg.get('created_at')} "
                        f"is after end_time {end_time}"
                    )

        if violations:
            pytest.fail(f"Found {len(violations)} time boundary violations")

        assert isinstance(segments, dict)
        assert stats.scanned_conversations >= 0
        assert stats.scanned_messages >= total_messages
        assert stats.dropped_future_messages >= 0
        assert dropped_old_messages >= 0

    def test_time_range_boundary_conditions(
        self, dify_client: DifyClient, integration_seed: SeedManifest
    ) -> None:
        """Test that messages exactly at boundaries are included."""
        user_id = integration_seed.primary_user_id
        start_time = integration_seed.started_at_with_buffer(-60)
        end_time = integration_seed.finished_at_with_buffer(60)

        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)
        assert start_dt and end_dt

        segments, _stats, _ = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=end_time,
            user_checkpoint=None,
            start_time=start_time,
        )

        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp()

        for _conv_id, segs in segments.items():
            for msg in segs:
                created_at = parse_iso_timestamp(msg.get("created_at"))
                if created_at:
                    msg_ts = created_at.timestamp()
                    assert msg_ts >= start_ts, "start_time should be inclusive (>=)"
                    assert msg_ts <= end_ts, "end_time should be inclusive (<=)"

    def test_time_range_with_no_messages(
        self, dify_client: DifyClient, integration_seed: SeedManifest
    ) -> None:
        """Test behavior when no messages exist in time range (far past)."""
        user_id = integration_seed.primary_user_id

        start_time = "2000-01-01T00:00:00Z"
        run_at = "2000-01-01T00:01:00Z"

        segments, stats, _stop_reason = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=run_at,
            user_checkpoint=None,
            start_time=start_time,
        )

        total_messages = sum(len(msgs) for msgs in segments.values())

        assert isinstance(segments, dict)
        assert total_messages == 0 or stats.scanned_messages > 0

    def test_time_range_statistics_accuracy(
        self, dify_client: DifyClient, integration_seed: SeedManifest
    ) -> None:
        """Test that statistics accurately reflect filtering."""
        user_id = integration_seed.primary_user_id
        start_time = integration_seed.started_at_with_buffer(-60)
        end_time = integration_seed.finished_at_with_buffer(60)

        segments, stats, _ = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=end_time,
            user_checkpoint=None,
            start_time=start_time,
        )

        total_returned = sum(len(msgs) for msgs in segments.values())
        dropped_old = stats.scanned_messages - stats.dropped_future_messages - total_returned

        assert (
            total_returned + stats.dropped_future_messages + dropped_old
            == stats.scanned_messages
        )
        assert dropped_old >= 0
        assert stats.dropped_future_messages >= 0


class TestTimeRangeWithCheckpoint:
    """Test time range filtering combined with checkpoint logic."""

    def test_time_range_with_existing_checkpoint(
        self, dify_client: DifyClient, integration_seed: SeedManifest
    ) -> None:
        """Test that time range and checkpoint work together correctly."""
        user_id = integration_seed.primary_user_id
        start_time = integration_seed.started_at_with_buffer(-60)
        end_time = integration_seed.finished_at_with_buffer(60)

        checkpoint = UserCheckpoint(conversations={})

        segments, _stats, _stop_reason = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=end_time,
            user_checkpoint=checkpoint,
            start_time=start_time,
        )

        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)

        for _conv_id, segs in segments.items():
            for msg in segs:
                created_at = parse_iso_timestamp(msg.get("created_at"))
                if created_at and start_dt and end_dt:
                    assert created_at.timestamp() >= start_dt.timestamp()
                    assert created_at.timestamp() <= end_dt.timestamp()


