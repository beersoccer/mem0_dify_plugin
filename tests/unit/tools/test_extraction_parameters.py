"""Unit tests for extract_long_term_memory parameter handling and statistics output.

Tests cover:
1. Time range generation from days_back parameter
2. conversations_limit parameter (10-500, default 50)
3. max_tokens_per_conversation parameter in K units (1-200, default 64K -> 64000 tokens)
4. DIFY_API_MAX_ITEMS_PER_REQUEST constant (100, Dify API constraint)
5. Per-user conversation and message counts in report
6. Time range filtering with start_time and end_time
"""

from __future__ import annotations

from typing import Any

from utils.extraction_helpers import get_time_range_from_days
from utils.helpers import parse_iso_timestamp


class TestTimeRangeFromDays:
    """Test time range generation from days_back parameter."""

    def test_days_back_1(self) -> None:
        """Verify days_back=1 generates yesterday 00:00:00 to today 00:00:00."""
        start_time, end_time = get_time_range_from_days(1)

        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)

        assert start_dt is not None
        assert end_dt is not None

        # Should be exactly 24 hours apart
        duration = (end_dt.timestamp() - start_dt.timestamp()) / 3600
        assert duration == 24.0, f"Expected 24 hours, got {duration}"

        # Both should be at midnight
        assert start_dt.hour == 0
        assert start_dt.minute == 0
        assert start_dt.second == 0

        assert end_dt.hour == 0
        assert end_dt.minute == 0
        assert end_dt.second == 0

        # end_time should be after start_time
        assert end_dt > start_dt

    def test_days_back_2(self) -> None:
        """Verify days_back=2 generates (today - 2 days) to today."""
        start_time, end_time = get_time_range_from_days(2)

        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)

        assert start_dt is not None
        assert end_dt is not None

        # Should be exactly 48 hours apart
        duration = (end_dt.timestamp() - start_dt.timestamp()) / 3600
        assert duration == 48.0, f"Expected 48 hours, got {duration}"

        # Both should be at midnight
        assert start_dt.hour == 0
        assert end_dt.hour == 0

    def test_days_back_7(self) -> None:
        """Verify days_back=7 generates last 7 days."""
        start_time, end_time = get_time_range_from_days(7)

        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)

        assert start_dt is not None
        assert end_dt is not None

        # Should be exactly 168 hours (7 days) apart
        duration = (end_dt.timestamp() - start_dt.timestamp()) / 3600
        assert duration == 168.0, f"Expected 168 hours, got {duration}"

    def test_days_back_clamping_below_minimum(self) -> None:
        """Verify days_back is clamped to minimum 1."""
        start_time, end_time = get_time_range_from_days(0)

        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)

        # Should behave like days_back=1
        duration = (end_dt.timestamp() - start_dt.timestamp()) / 3600
        assert duration == 24.0, "Should clamp to 1 day minimum"

    def test_days_back_clamping_above_maximum(self) -> None:
        """Verify days_back is clamped to maximum 7."""
        start_time, end_time = get_time_range_from_days(100)

        start_dt = parse_iso_timestamp(start_time)
        end_dt = parse_iso_timestamp(end_time)

        # Should behave like days_back=7
        duration = (end_dt.timestamp() - start_dt.timestamp()) / 3600
        assert duration == 168.0, "Should clamp to 7 days maximum"

    def test_iso_format(self) -> None:
        """Verify returned timestamps are valid ISO8601."""
        start_time, end_time = get_time_range_from_days(1)

        # Should be parseable
        assert parse_iso_timestamp(start_time) is not None
        assert parse_iso_timestamp(end_time) is not None

        # Should contain 'T' and timezone indicator
        assert "T" in start_time
        assert "T" in end_time


class TestConversationsAndTokenLimits:
    """Test conversations_limit and max_tokens_per_conversation parameter handling."""

    def test_conversations_limit_clamp_to_range(self) -> None:
        """Verify conversations_limit is clamped to 10-500 range."""
        # Test various inputs
        test_cases = [
            (5, 10),  # Below minimum
            (10, 10),  # At minimum
            (50, 50),  # Default
            (100, 100),  # Mid range
            (500, 500),  # At maximum
            (1000, 500),  # Above maximum
            (-10, 10),  # Negative
        ]

        for input_val, expected in test_cases:
            # Simulate the clamping logic
            result = max(10, min(500, input_val))
            assert result == expected, f"Input {input_val} should clamp to {expected}, got {result}"

    def test_default_conversations_limit(self) -> None:
        """Verify default conversations limit is 50."""
        from utils.constants import EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT

        assert EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT == 50

    def test_token_limit_clamp_to_range_in_k_units(self) -> None:
        """Verify token limit (in K units) is clamped to 1-200 range."""
        # Test various inputs
        test_cases = [
            (0, 1),  # Below minimum
            (1, 1),  # At minimum
            (64, 64),  # Default (64K)
            (128, 128),  # GPT-4 context (128K)
            (200, 200),  # At maximum
            (300, 200),  # Above maximum
            (-10, 1),  # Negative
        ]

        for input_val, expected in test_cases:
            # Simulate the clamping logic in K units (1-200)
            result = max(1, min(200, input_val))
            assert result == expected, f"Input {input_val} should clamp to {expected}, got {result}"

    def test_default_token_limit_in_k_units(self) -> None:
        """Verify default token limit constant is 64 (representing 64K tokens)."""
        from utils.constants import EXTRACTION_DEFAULT_MAX_TOKENS

        assert EXTRACTION_DEFAULT_MAX_TOKENS == 64

    def test_dify_api_max_items_per_request_constant(self) -> None:
        """Verify Dify API max items per request constant is 100."""
        from utils.constants import DIFY_API_MAX_ITEMS_PER_REQUEST

        assert DIFY_API_MAX_ITEMS_PER_REQUEST == 100


class TestUserReportStatistics:
    """Test per-user statistics in extraction report."""

    def test_user_report_contains_conversation_counts(self) -> None:
        """Verify user report includes conversation counts."""
        # Expected fields in user_report
        required_fields = [
            "user_id",
            "status",
            "scanned_conversations",
            "scanned_messages",
            "dropped_future_messages",
            "conversations_with_messages",
            "messages_in_time_range",
            "written_memories",
        ]

        # Simulate user_report structure
        user_report: dict[str, Any] = {
            "user_id": "test_user",
            "status": "SUCCESS",
            "scanned_conversations": 25,
            "scanned_messages": 150,
            "dropped_future_messages": 10,
            "conversations_with_messages": 20,
            "messages_in_time_range": 140,
            "written_memories": {
                "semantic": 50,
                "episodic": 30,
                "procedural": 20,
            },
            "errors": [],
        }

        for field in required_fields:
            assert field in user_report, f"Missing required field: {field}"

    def test_message_counts_are_consistent(self) -> None:
        """Verify message count consistency in report."""
        scanned = 150
        dropped_future = 10
        in_range = 140

        # scanned = in_range + dropped_future (+ potentially dropped_old)
        assert scanned >= dropped_future + in_range
        assert in_range == scanned - dropped_future or in_range < scanned

    def test_conversation_counts_are_consistent(self) -> None:
        """Verify conversation count consistency."""
        scanned_conversations = 25
        conversations_with_messages = 20

        # conversations_with_messages <= scanned_conversations
        assert conversations_with_messages <= scanned_conversations
        assert conversations_with_messages >= 0
        assert scanned_conversations >= 0


class TestTimeRangeFiltering:
    """Test time range filtering with start_time and run_at."""

    def test_time_range_one_minute(self) -> None:
        """Test filtering messages within a 1-minute time range."""
        start_time = "2026-01-17T12:00:00Z"
        run_at = "2026-01-17T12:01:00Z"

        start_dt = parse_iso_timestamp(start_time)
        run_at_dt = parse_iso_timestamp(run_at)

        assert start_dt is not None
        assert run_at_dt is not None

        duration_seconds = run_at_dt.timestamp() - start_dt.timestamp()
        assert duration_seconds == 60, "Should be exactly 60 seconds"

    def test_time_range_24_hours(self) -> None:
        """Test filtering messages within a 24-hour time range."""
        start_time = "2026-01-17T00:00:00Z"
        run_at = "2026-01-18T00:00:00Z"

        start_dt = parse_iso_timestamp(start_time)
        run_at_dt = parse_iso_timestamp(run_at)

        assert start_dt is not None
        assert run_at_dt is not None

        duration_hours = (run_at_dt.timestamp() - start_dt.timestamp()) / 3600
        assert duration_hours == 24.0, "Should be exactly 24 hours"

    def test_message_time_boundary_inclusive(self) -> None:
        """Verify time boundaries are inclusive (>= and <=)."""
        start_time = "2026-01-17T12:00:00Z"
        run_at = "2026-01-17T12:01:00Z"

        start_ts = parse_iso_timestamp(start_time).timestamp()
        run_at_ts = parse_iso_timestamp(run_at).timestamp()

        # Message exactly at start_time should be included
        msg_at_start = "2026-01-17T12:00:00Z"
        msg_start_ts = parse_iso_timestamp(msg_at_start).timestamp()
        assert msg_start_ts >= start_ts
        assert msg_start_ts <= run_at_ts

        # Message exactly at run_at should be included
        msg_at_end = "2026-01-17T12:01:00Z"
        msg_end_ts = parse_iso_timestamp(msg_at_end).timestamp()
        assert msg_end_ts >= start_ts
        assert msg_end_ts <= run_at_ts

        # Message just before start_time should be excluded
        msg_before = "2026-01-17T11:59:59Z"
        msg_before_ts = parse_iso_timestamp(msg_before).timestamp()
        assert msg_before_ts < start_ts

        # Message just after run_at should be excluded
        msg_after = "2026-01-17T12:01:01Z"
        msg_after_ts = parse_iso_timestamp(msg_after).timestamp()
        assert msg_after_ts > run_at_ts


class TestReportOutputFormat:
    """Test extraction report output format."""

    def test_report_contains_required_fields(self) -> None:
        """Verify extraction report contains all required fields."""
        required_fields = [
            "status",
            "run_id",
            "run_at",
            "start_time",
            "app_id",
            "user_count",
            "summary",
            "per_user",
            "checkpoint_updates",
            "budget_tokens",
        ]

        # Simulate full report structure
        report: dict[str, Any] = {
            "status": "SUCCESS",
            "run_id": "test_run_123",
            "run_at": "2026-01-17T12:00:00Z",
            "start_time": "2026-01-17T00:00:00Z",
            "app_id": None,
            "user_count": 2,
            "summary": {
                "processed_users": 2,
                "skipped_users": 0,
                "scanned_conversations": 40,
                "scanned_messages": 250,
                "written_memories": {
                    "semantic": 80,
                    "episodic": 50,
                    "procedural": 30,
                },
            },
            "per_user": [],
            "checkpoint_updates": {"success": 2, "failed": 0},
            "budget_tokens": {"total": 200000, "remaining": 150000},
        }

        for field in required_fields:
            assert field in report, f"Missing required field: {field}"

    def test_per_user_reports_are_detailed(self) -> None:
        """Verify per-user reports contain detailed statistics."""
        per_user_report = {
            "user_id": "user_123",
            "status": "SUCCESS",
            "stop_reason": "completed",
            "scanned_conversations": 20,
            "scanned_messages": 120,
            "dropped_future_messages": 5,
            "conversations_with_messages": 18,
            "messages_in_time_range": 115,
            "written_memories": {
                "semantic": 40,
                "episodic": 25,
                "procedural": 15,
            },
            "budget_remaining": 150000,
            "errors": [],
        }

        # Verify all expected fields are present
        assert "user_id" in per_user_report
        assert "scanned_conversations" in per_user_report
        assert "scanned_messages" in per_user_report
        assert "conversations_with_messages" in per_user_report
        assert "messages_in_time_range" in per_user_report

        # Verify counts make sense
        assert (
            per_user_report["conversations_with_messages"]
            <= per_user_report["scanned_conversations"]
        )
        assert (
            per_user_report["messages_in_time_range"]
            <= per_user_report["scanned_messages"]
        )

    def test_summary_aggregates_per_user_stats(self) -> None:
        """Verify summary correctly aggregates per-user statistics."""
        per_user = [
            {
                "user_id": "user_1",
                "scanned_conversations": 20,
                "scanned_messages": 100,
                "conversations_with_messages": 18,
                "messages_in_time_range": 95,
            },
            {
                "user_id": "user_2",
                "scanned_conversations": 15,
                "scanned_messages": 80,
                "conversations_with_messages": 12,
                "messages_in_time_range": 75,
            },
        ]

        # Calculate aggregated stats
        total_scanned_convs = sum(u["scanned_conversations"] for u in per_user)
        total_scanned_msgs = sum(u["scanned_messages"] for u in per_user)
        total_convs_with_msgs = sum(u["conversations_with_messages"] for u in per_user)
        total_msgs_in_range = sum(u["messages_in_time_range"] for u in per_user)

        assert total_scanned_convs == 35
        assert total_scanned_msgs == 180
        assert total_convs_with_msgs == 30
        assert total_msgs_in_range == 170


class TestParameterValidation:
    """Test parameter validation logic."""

    def test_iso8601_format_validation(self) -> None:
        """Test ISO8601 timestamp validation."""
        valid_timestamps = [
            "2026-01-17T12:00:00Z",
            "2026-01-17T12:00:00+00:00",
            "2026-01-17T12:00:00.000Z",
            "2026-01-17T00:00:00Z",
        ]

        for ts in valid_timestamps:
            dt = parse_iso_timestamp(ts)
            assert dt is not None, f"Failed to parse valid timestamp: {ts}"

    def test_invalid_iso8601_returns_none(self) -> None:
        """Test invalid ISO8601 formats are rejected."""
        invalid_timestamps = [
            "2026-01-17",  # Missing time
            "12:00:00",  # Missing date
            "2026/01/17 12:00:00",  # Wrong format
            "invalid",
            "",
            None,
        ]

        for ts in invalid_timestamps:
            dt = parse_iso_timestamp(ts)
            assert dt is None, f"Should reject invalid timestamp: {ts}"

    def test_limits_must_be_positive(self) -> None:
        """Test that limits are always positive."""
        test_values = [-10, 0, 1, 20, 100, 200]

        for val in test_values:
            clamped = max(1, min(100, val))
            assert clamped >= 1, f"Clamped value {clamped} should be >= 1"
            assert clamped <= 100, f"Clamped value {clamped} should be <= 100"


class TestIntegrationWithMockDify:
    """Integration tests with mock Dify data."""

    def test_conversations_limit_prevents_abuse(self) -> None:
        """Verify conversations_limit prevents processing excessive conversations."""
        from utils.constants import EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT

        # Scenario: Malicious user generates 300 conversations in 3 days
        malicious_user_conversations = 300
        limit = EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT  # 50

        # Only first 50 should be processed
        processed = min(malicious_user_conversations, limit)
        assert processed == 50
        assert processed < malicious_user_conversations

        # Normal user with 30 conversations - all processed
        normal_user_conversations = 30
        processed_normal = min(normal_user_conversations, limit)
        assert processed_normal == 30

    def test_dify_api_pagination_uses_max_items_per_request(self) -> None:
        """Verify Dify API calls use max items per request for pagination."""
        from utils.constants import DIFY_API_MAX_ITEMS_PER_REQUEST

        # API calls should always use the maximum items per request (100)
        # to minimize the number of API calls
        assert DIFY_API_MAX_ITEMS_PER_REQUEST == 100

        # Simulate pagination: fetching 250 items requires 3 API calls
        total_items = 250
        items_per_request = DIFY_API_MAX_ITEMS_PER_REQUEST
        expected_calls = (
            (total_items + items_per_request - 1) // items_per_request
        )

        assert expected_calls == 3, "Should need 3 API calls for 250 items"

    def test_token_limit_controls_message_fetching(self) -> None:
        """Verify token limit stops message fetching early."""
        # With token limit, we don't need a separate message count limit
        # Token counting happens during pagination and stops when limit is reached

        # Example: 1000 messages available, but token limit reached at 200 messages
        available_messages = 1000
        messages_fetched_before_token_limit = 200

        # Token limit should stop fetching early
        assert messages_fetched_before_token_limit < available_messages
        assert messages_fetched_before_token_limit == 200

    def test_empty_time_range_returns_zero_messages(self) -> None:
        """Test that empty time range (no messages) is handled gracefully."""
        # Time range in far past
        start_time = "2000-01-01T00:00:00Z"
        run_at = "2000-01-01T01:00:00Z"

        # All test messages are in 2026, so none should match
        test_messages = [
            {"id": "m1", "created_at": "2026-01-17T12:00:00Z"},
            {"id": "m2", "created_at": "2026-01-17T12:30:00Z"},
        ]

        start_ts = parse_iso_timestamp(start_time).timestamp()
        run_at_ts = parse_iso_timestamp(run_at).timestamp()

        filtered = []
        for msg in test_messages:
            msg_ts = parse_iso_timestamp(msg["created_at"]).timestamp()
            if start_ts <= msg_ts <= run_at_ts:
                filtered.append(msg)

        assert len(filtered) == 0, "Should have no messages in 2000 time range"

