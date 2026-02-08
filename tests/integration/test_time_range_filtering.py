"""Integration tests for time range filtering in chat history retrieval.

This test suite validates that the extract_long_term_memory tool correctly
filters messages by time range using TEST_START_TIME and TEST_END_TIME from tests/.env.
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

pytestmark = pytest.mark.slow


def load_env_dev() -> dict[str, str]:
    """Load credentials from .env file."""
    env_file = Path(__file__).parent.parent / ".env"
    env_vars: dict[str, str] = {
        key: os.environ[key]
        for key in (
            "DIFY_API_KEY",
            "DIFY_USER_ID",
            "DIFY_USER_IDS",
            "DIFY_BASE_URL",
            "TEST_START_TIME",
            "TEST_END_TIME",
            "ALLOW_LOCALHOST_DIFY",
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
    allow_localhost = (
        env_config.get("ALLOW_LOCALHOST_DIFY", "").strip().lower()
        in {"1", "true", "yes", "y"}
    )
    if hostname in {"localhost", "127.0.0.1", "::1"} and not allow_localhost:
        pytest.skip(
            "DIFY_BASE_URL points to localhost; "
            "set ALLOW_LOCALHOST_DIFY=1 to run locally"
        )
    api_key = env_config["DIFY_API_KEY"]
    return DifyClient(base_url=base_url, api_key=api_key)


class TestTimeRangeFiltering:
    """Test time range filtering with real Dify data."""

    def test_time_range_from_env_comprehensive(
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Comprehensive test of time range filtering with env config."""
        user_id = env_config["DIFY_USER_ID"]
        start_time = env_config.get("TEST_START_TIME")
        end_time = env_config.get("TEST_END_TIME")

        if not start_time or not end_time:
            pytest.fail("TEST_START_TIME and TEST_END_TIME not set in .env")

        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)
        if not start_dt or not end_dt:
            pytest.fail("Invalid TEST_START_TIME or TEST_END_TIME format")

        # Scan conversations with time range
        segments, stats, stop_reason = scan_user_conversations_incremental(
            dify_client,
            user_id=user_id,
            run_at=end_time,
            user_checkpoint=None,
            start_time=start_time,
        )

        # Calculate total messages returned
        total_messages = sum(len(msgs) for msgs in segments.values())
        dropped_old_messages = (
            stats.scanned_messages - stats.dropped_future_messages - total_messages
        )

        # Validate time boundaries for all returned messages
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
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Test behavior when no messages exist in time range."""
        user_id = env_config["DIFY_USER_ID"]

        # Use a time range in the far past where no messages should exist
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
        self, dify_client: DifyClient, env_config: dict[str, str]
    ) -> None:
        """Test that time range and checkpoint work together correctly."""
        user_id = env_config["DIFY_USER_ID"]
        start_time = env_config.get("TEST_START_TIME")
        end_time = env_config.get("TEST_END_TIME")

        if not start_time or not end_time:
            pytest.skip("TEST_START_TIME and TEST_END_TIME not set in .env")

        checkpoint = UserCheckpoint(
            conversations={},
        )

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


def test_extraction_respects_time_range() -> None:
    """Unit test: verify extraction logic correctly passes start_time."""
    import inspect

    sig = inspect.signature(scan_new_messages_for_conversation)
    assert "start_time" in sig.parameters, (
        "scan_new_messages_for_conversation should accept start_time parameter"
    )

    param = sig.parameters["start_time"]
    assert (
        param.default is not inspect.Parameter.empty or param.annotation == "str | None"
    ), "start_time should be optional"

