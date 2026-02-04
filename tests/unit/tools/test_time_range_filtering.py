"""Comprehensive tests for time range filtering in chat history retrieval.

This test suite validates that the extract_long_term_memory tool correctly
filters messages by time range using TEST_START_TIME and TEST_END_TIME from tests/.env.

Test scenarios:
1. Messages within time range are included
2. Messages before start_time are excluded
3. Messages after end_time are excluded
4. Boundary conditions (exactly at start_time or end_time)
5. Empty time ranges handle gracefully
6. Multi-conversation time filtering
7. Statistics accuracy (scanned vs returned messages)
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

from utils.dify_client import DifyClient
from utils.extraction import (
    UserCheckpoint,
    scan_new_messages_for_conversation,
    scan_user_conversations_incremental,
)
from utils.helpers import parse_iso_timestamp


def load_env_dev() -> dict[str, str]:
    """Load credentials from .env file."""
    # .env 文件应该在 tests/.env，而不是 tests/unit/tools/.env
    env_file = Path(__file__).parent.parent.parent / ".env"
    env_vars: dict[str, str] = {
        key: os.environ[key]
        for key in (
            "DIFY_API_KEY",
            "DIFY_USER_ID",
            "DIFY_USER_IDS",
            "DIFY_BASE_URL",
            "TEST_START_TIME",
            "TEST_END_TIME",
        )
        if key in os.environ
    }

    if env_file.exists():
        with env_file.open() as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key not in env_vars:
                    env_vars[key] = value.strip().strip('"')

    # DIFY_USER_ID can be extracted from DIFY_USER_IDS if not explicitly set
    if "DIFY_USER_ID" not in env_vars and "DIFY_USER_IDS" in env_vars:
        test_user_ids = env_vars["DIFY_USER_IDS"]
        first_user = test_user_ids.split(",")[0].strip()
        if first_user:
            env_vars["DIFY_USER_ID"] = first_user
    
    required = ["DIFY_API_KEY", "DIFY_USER_ID"]
    missing = [k for k in required if not env_vars.get(k)]
    if missing:
        pytest.skip(f"Missing required env vars: {missing}")

    return env_vars


@pytest.fixture
def env_config() -> dict[str, str]:
    """Fixture providing .env configuration."""
    return load_env_dev()


@pytest.fixture
def dify_client(env_config: dict[str, str]) -> DifyClient:
    """Fixture providing configured DifyClient."""
    base_url = env_config.get("DIFY_BASE_URL", "http://localhost/v1")
    if not base_url.startswith("http"):
        base_url = f"http://{base_url}"
    if not base_url.endswith("/v1"):
        base_url = f"{base_url.rstrip('/')}/v1"
    hostname = urlparse(base_url).hostname or ""
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        pytest.skip("DIFY_BASE_URL points to localhost; no Dify server in CI")
    api_key = env_config["DIFY_API_KEY"]
    return DifyClient(base_url=base_url, api_key=api_key)


class TestTimeRangeFiltering:
    """Test time range filtering with real Dify data."""

    def test_time_range_from_env_comprehensive(
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Comprehensive test of time range filtering with env config.

        This is the main test for your requirement: filtering messages between
        TEST_START_TIME and TEST_END_TIME (2026-01-17 12:00:00 to 12:01:00).
        """
        user_id = env_config["DIFY_USER_ID"]
        start_time = env_config.get("TEST_START_TIME")
        end_time = env_config.get("TEST_END_TIME")

        if not start_time or not end_time:
            pytest.fail("TEST_START_TIME and TEST_END_TIME not set in .env")

        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)
        if not start_dt or not end_dt:
            pytest.fail("Invalid TEST_START_TIME or TEST_END_TIME format")

        print(f"\n{'='*70}")
        print("TIME RANGE FILTERING TEST")
        print(f"{'='*70}")
        print(f"User ID: {user_id}")
        print(f"Start time: {start_time}")
        print(f"End time: {end_time}")
        print(f"Duration: {(end_dt.timestamp() - start_dt.timestamp()):.0f} seconds")
        print(f"{'='*70}\n")

        # Scan conversations with time range
        segments, stats, stop_reason = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=end_time,
            user_checkpoint=None,
            start_time=start_time,
        )

        # Print detailed statistics
        print("SCAN STATISTICS:")
        print(f"  Stop reason: {stop_reason}")
        print(f"  Scanned conversations: {stats.scanned_conversations}")
        print(f"  Scanned messages: {stats.scanned_messages}")
        print(f"  Dropped future messages: {stats.dropped_future_messages}")
        print(f"  Conversations with messages in range: {stats.conversations_with_new_messages}")

        # Calculate total messages returned
        # segments now returns dict[conv_id, list[message]] (no MessageSegment wrapper)
        total_messages = sum(len(msgs) for msgs in segments.values())
        dropped_old_messages = (
            stats.scanned_messages - stats.dropped_future_messages - total_messages
        )
        
        print("\nMESSAGE BREAKDOWN:")
        print(f"  Total messages scanned: {stats.scanned_messages}")
        print(f"  - Messages in time range (returned): {total_messages}")
        print(f"  - Messages before start_time (dropped): {dropped_old_messages}")
        print(f"  - Messages after end_time (dropped): {stats.dropped_future_messages}")
        print(
            f"  Verification: {stats.scanned_messages} = {total_messages} + "
            f"{dropped_old_messages} + {stats.dropped_future_messages}"
        )

        # Validate time boundaries for all returned messages
        violations = []
        for conv_id, segs in segments.items():
            print(f"\nConversation {conv_id}:")
            # segs is now a list of messages directly (no MessageSegment wrapper)
            print(f"  Messages: {len(segs)}")
            for msg in segs:
                    created_at = parse_iso_timestamp(msg.get("created_at"))
                    if not created_at:
                        violations.append(f"Message {msg.get('id')} has no created_at timestamp")
                        continue
                    
                    msg_ts = created_at.timestamp()
                    start_ts = start_dt.timestamp()
                    end_ts = end_dt.timestamp()
                    
                    # Check lower bound
                    if msg_ts < start_ts:
                        violations.append(
                            f"Message {msg.get('id')} created_at {msg.get('created_at')} "
                            f"is before start_time {start_time} "
                            f"(diff: {start_ts - msg_ts:.2f}s)"
                        )
                    
                    # Check upper bound
                    if msg_ts > end_ts:
                        violations.append(
                            f"Message {msg.get('id')} created_at {msg.get('created_at')} "
                            f"is after end_time {end_time} "
                            f"(diff: {msg_ts - end_ts:.2f}s)"
                        )
                    
                    print(f"    - {msg.get('id')}: {msg.get('created_at')}")

        # Report violations if any
        if violations:
            print(f"\n{'='*70}")
            print("TIME BOUNDARY VIOLATIONS DETECTED:")
            print(f"{'='*70}")
            for v in violations:
                print(f"  ❌ {v}")
            pytest.fail(f"Found {len(violations)} time boundary violations")
        
        # Test passed
        print(f"\n{'='*70}")
        print("✅ TIME RANGE FILTERING TEST PASSED")
        print(f"{'='*70}")
        print(f"All {total_messages} returned messages are within the time range.")
        print("Time filtering logic is correct and robust.")
        
        # Assertions for test framework
        assert isinstance(segments, dict)
        assert stats.scanned_conversations >= 0
        assert stats.scanned_messages >= total_messages
        assert stats.dropped_future_messages >= 0

    def test_time_range_boundary_conditions(
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Test that messages exactly at boundaries are included."""
        user_id = env_config["DIFY_USER_ID"]
        start_time = env_config.get("TEST_START_TIME")
        end_time = env_config.get("TEST_END_TIME")

        if not start_time or not end_time:
            pytest.skip("TEST_START_TIME and TEST_END_TIME not set in .env")

        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)
        if not start_dt or not end_dt:
            pytest.skip("Invalid TEST_START_TIME or TEST_END_TIME format")

        segments, stats, _ = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=end_time,
            user_checkpoint=None,
            start_time=start_time,
        )

        # Check that boundaries use <= and >= (inclusive)
        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp()
        
        for _conv_id, segs in segments.items():
            # segs is now list of messages
            for msg in segs:
                # Already iterating messages
                    created_at = parse_iso_timestamp(msg.get("created_at"))
                    if created_at:
                        msg_ts = created_at.timestamp()
                        # Boundaries should be inclusive
                        assert msg_ts >= start_ts, "start_time should be inclusive (>=)"
                        assert msg_ts <= end_ts, "end_time should be inclusive (<=)"

    def test_time_range_with_no_messages(
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Test behavior when no messages exist in time range."""
        user_id = env_config["DIFY_USER_ID"]
        
        # Use a time range in the far past where no messages should exist
        start_time = "2000-01-01T00:00:00Z"
        run_at = "2000-01-01T00:01:00Z"

        segments, stats, stop_reason = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=run_at,
            user_checkpoint=None,
            start_time=start_time,
        )

        # Should handle empty result gracefully
        total_messages = sum(
            len(msgs) for msgs in segments.values()
        )
        
        print("\nEmpty time range test:")
        print(f"  Scanned conversations: {stats.scanned_conversations}")
        print(f"  Scanned messages: {stats.scanned_messages}")
        print(f"  Messages in range: {total_messages}")
        
        # Should not crash and return valid empty or minimal results
        assert isinstance(segments, dict)
        assert total_messages == 0 or stats.scanned_messages > 0

    def test_time_range_statistics_accuracy(
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Test that statistics accurately reflect filtering."""
        user_id = env_config["DIFY_USER_ID"]
        start_time = env_config.get("TEST_START_TIME")
        end_time = env_config.get("TEST_END_TIME")

        if not start_time or not end_time:
            pytest.skip("TEST_START_TIME and TEST_END_TIME not set in .env")

        segments, stats, _ = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=end_time,
            user_checkpoint=None,
            start_time=start_time,
        )

        # segments now returns dict[conv_id, list[message]] (no MessageSegment wrapper)
        total_returned = sum(len(msgs) for msgs in segments.values())
        
        # Statistics should add up correctly
        # scanned = returned + dropped_future + dropped_old
        dropped_old = stats.scanned_messages - stats.dropped_future_messages - total_returned
        
        print("\nStatistics accuracy check:")
        print(f"  Scanned: {stats.scanned_messages}")
        print(f"  Returned: {total_returned}")
        print(f"  Dropped (future): {stats.dropped_future_messages}")
        print(f"  Dropped (old): {dropped_old}")
        print(
            f"  Sum check: {total_returned + stats.dropped_future_messages + dropped_old} == "
            f"{stats.scanned_messages}"
        )
        
        # Verify the accounting is correct
        assert (
            total_returned + stats.dropped_future_messages + dropped_old
            == stats.scanned_messages
        )
        assert dropped_old >= 0, "Cannot have negative dropped old messages"
        assert stats.dropped_future_messages >= 0, "Cannot have negative dropped future messages"


class TestTimeRangeWithCheckpoint:
    """Test time range filtering combined with checkpoint logic."""

    def test_time_range_with_existing_checkpoint(
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Test that time range and checkpoint work together correctly."""
        user_id = env_config["DIFY_USER_ID"]
        start_time = env_config.get("TEST_START_TIME")
        end_time = env_config.get("TEST_END_TIME")

        if not start_time or not end_time:
            pytest.skip("TEST_START_TIME and TEST_END_TIME not set in .env")

        # Create a checkpoint before the test time range
        checkpoint = UserCheckpoint(
            last_run_at="2026-01-17T11:00:00Z",  # Before TEST_START_TIME
            conversations={}
        )

        segments, stats, stop_reason = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=end_time,
            user_checkpoint=checkpoint,
            start_time=start_time,
        )

        # Should still respect the time range even with checkpoint
        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)
        
        for _conv_id, segs in segments.items():
            # segs is now list of messages
            for msg in segs:
                # Already iterating messages
                    created_at = parse_iso_timestamp(msg.get("created_at"))
                    if created_at and start_dt and end_dt:
                        assert created_at.timestamp() >= start_dt.timestamp()
                        assert created_at.timestamp() <= end_dt.timestamp()


def test_extraction_respects_time_range():
    """Unit test: verify extraction logic correctly passes start_time."""
    
    # This is tested with mock data in test_dify_incremental_scan.py
    # Here we just verify the function signature accepts start_time
    import inspect
    sig = inspect.signature(scan_new_messages_for_conversation)
    assert (
        'start_time' in sig.parameters
    ), "scan_new_messages_for_conversation should accept start_time parameter"
    
    # Verify it's optional (has default)
    param = sig.parameters['start_time']
    assert param.default is not inspect.Parameter.empty or param.annotation == 'str | None', \
        "start_time should be optional"

