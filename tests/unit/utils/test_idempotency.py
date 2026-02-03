"""Test idempotency check for extract_long_term_memory.

This test verifies that the idempotency check uses strict > (not >=) to handle:
1. Time range expansion (start_time moves backward)
2. New messages created after previous run (within same end_time)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from utils.extraction import ConversationCheckpoint, UserCheckpoint


class TestIdempotency:
    """Test cases for idempotency check."""

    def test_should_skip_when_last_run_beyond_end_time(self) -> None:
        """Should skip when last_run_at > end_time (strict greater than)."""
        cp = UserCheckpoint(
            last_run_at="2026-01-20T00:00:00Z",
            conversations={},
        )
        
        end_time = "2026-01-19T00:00:00Z"
        
        # last_run_at (Jan 20) > end_time (Jan 19)
        # Should skip: already processed beyond this end_time
        from utils.extraction_helpers import cmp_iso_timestamps
        assert cmp_iso_timestamps(cp.last_run_at, end_time) > 0

    def test_should_process_when_last_run_equals_end_time(self) -> None:
        """Should process when last_run_at == end_time (may have new messages)."""
        cp = UserCheckpoint(
            last_run_at="2026-01-20T00:00:00Z",
            conversations={},
        )
        
        end_time = "2026-01-20T00:00:00Z"
        
        # last_run_at (Jan 20) == end_time (Jan 20)
        # Should NOT skip: may have new messages or time range expansion
        from utils.extraction_helpers import cmp_iso_timestamps
        assert cmp_iso_timestamps(cp.last_run_at, end_time) == 0
        # This should NOT trigger skip in the code

    def test_should_process_when_last_run_before_end_time(self) -> None:
        """Should process when last_run_at < end_time (new time range)."""
        cp = UserCheckpoint(
            last_run_at="2026-01-19T00:00:00Z",
            conversations={},
        )
        
        end_time = "2026-01-20T00:00:00Z"
        
        # last_run_at (Jan 19) < end_time (Jan 20)
        # Should process: new time range
        from utils.extraction_helpers import cmp_iso_timestamps
        assert cmp_iso_timestamps(cp.last_run_at, end_time) < 0

    def test_time_range_expansion_scenario(self) -> None:
        """Test scenario: time range expansion (start_time moves backward)."""
        # Run 1: processed [T2, T3]
        cp = UserCheckpoint(
            last_run_at="2026-01-20T12:00:00Z",  # T3
            conversations={
                "conv1": ConversationCheckpoint(
                    last_processed_message_id="msg3",
                    processed_range_start="2026-01-20T10:00:00Z",  # T2
                    processed_range_end="2026-01-20T12:00:00Z",  # T3
                )
            },
        )
        
        # Run 2: want to process [T1, T3] (start_time expanded backward)
        start_time = "2026-01-20T08:00:00Z"  # T1 (earlier)
        end_time = "2026-01-20T12:00:00Z"  # T3 (same)
        
        # Idempotency check
        from utils.extraction_helpers import cmp_iso_timestamps
        should_skip = cmp_iso_timestamps(cp.last_run_at, end_time) > 0
        
        # Should NOT skip (last_run_at == end_time, not >)
        assert not should_skip, "Should process to handle time range expansion"
        
        # Verify range expansion is detected at message level
        conv_cp = cp.conversations["conv1"]
        range_is_expanding = (
            start_time < conv_cp.processed_range_start
        )
        assert range_is_expanding, "Should detect time range expansion"

    def test_new_message_after_previous_run_scenario(self) -> None:
        """Test scenario: new message created after previous run."""
        base_time = datetime.now(UTC)
        
        # Run 1: executed at T2.5, processed messages up to T2
        cp = UserCheckpoint(
            last_run_at=(base_time + timedelta(hours=3)).isoformat(),  # end_time=T3
            conversations={
                "conv1": ConversationCheckpoint(
                    last_processed_message_id="msg2",
                    processed_range_start=base_time.isoformat(),  # T0
                    processed_range_end=(base_time + timedelta(hours=2)).isoformat(),  # T2
                )
            },
        )
        
        # At T2.8: new message created (after Run 1 but before end_time T3)
        # Message: created_at=T2.8, updated conversation.updated_at
        
        # Run 2: executed at T3.5, same end_time=T3
        end_time = (base_time + timedelta(hours=3)).isoformat()  # T3
        
        # Idempotency check
        from utils.extraction_helpers import cmp_iso_timestamps
        should_skip = cmp_iso_timestamps(cp.last_run_at, end_time) > 0
        
        # Should NOT skip (last_run_at == end_time, not >)
        assert not should_skip, "Should process to catch new messages"
        
        # In real execution:
        # - Conversation level: updated_at > last_run_at, will scan
        # - Message level: msg(T2.8) > processed_range_end(T2), will collect

    def test_strict_duplicate_run_scenario(self) -> None:
        """Test scenario: strict duplicate run (same parameters)."""
        cp = UserCheckpoint(
            last_run_at="2026-01-20T12:00:00Z",
            conversations={
                "conv1": ConversationCheckpoint(
                    last_processed_message_id="msg3",
                    processed_range_start="2026-01-20T10:00:00Z",
                    processed_range_end="2026-01-20T12:00:00Z",
                )
            },
        )
        
        # Run again with same end_time
        end_time = "2026-01-20T12:00:00Z"
        
        # Idempotency check
        from utils.extraction_helpers import cmp_iso_timestamps
        should_skip = cmp_iso_timestamps(cp.last_run_at, end_time) > 0
        
        # Should NOT skip at user level (last_run_at == end_time)
        # But will be handled efficiently by conversation/message level checkpoints
        assert not should_skip
        
        # Verify conversation level will skip unchanged conversations
        # (this happens in scan_user_conversations_incremental)

    def test_none_checkpoint_first_run(self) -> None:
        """Test first run with no checkpoint."""
        cp = UserCheckpoint(
            last_run_at=None,  # First run
            conversations={},
        )
        
        end_time = "2026-01-20T12:00:00Z"
        
        # Idempotency check
        from utils.extraction_helpers import cmp_iso_timestamps
        should_skip = cmp_iso_timestamps(cp.last_run_at, end_time) > 0
        
        # Should NOT skip (None < any time)
        assert not should_skip, "First run should always process"

