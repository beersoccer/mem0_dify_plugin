"""Tests for retry utilities."""

from __future__ import annotations

import time

import pytest

from utils.retry import retry_operation, retry_with_exponential_backoff


class TestRetryWithExponentialBackoff:
    """Test retry_with_exponential_backoff decorator."""

    def test_success_on_first_try(self) -> None:
        """Test that function succeeds on first try without retry."""
        call_count = 0

        @retry_with_exponential_backoff(max_retries=3)
        def success_func() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        result = success_func()
        assert result == "success"
        assert call_count == 1

    def test_success_after_retries(self) -> None:
        """Test that function succeeds after failures."""
        call_count = 0

        @retry_with_exponential_backoff(max_retries=3, initial_delay=0.01)
        def flaky_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 3

    def test_failure_after_max_retries(self) -> None:
        """Test that function raises after max retries exhausted."""
        call_count = 0

        @retry_with_exponential_backoff(max_retries=2, initial_delay=0.01)
        def always_fail() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            always_fail()

        assert call_count == 3  # Initial + 2 retries

    def test_non_retriable_exception(self) -> None:
        """Test that non-retriable exceptions are not retried."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            initial_delay=0.01,
            retriable_exceptions=(ValueError,),
        )
        def raise_type_error() -> str:
            nonlocal call_count
            call_count += 1
            raise TypeError("Not retriable")

        with pytest.raises(TypeError, match="Not retriable"):
            raise_type_error()

        assert call_count == 1  # No retry

    def test_exponential_backoff(self) -> None:
        """Test that delays follow exponential backoff."""
        call_times: list[float] = []

        @retry_with_exponential_backoff(
            max_retries=3,
            initial_delay=0.1,
            exponential_base=2.0,
            jitter=False,  # Disable jitter for predictable testing
        )
        def fail_func() -> str:
            call_times.append(time.time())
            raise ValueError("Fail")

        with pytest.raises(ValueError):
            fail_func()

        # Check delays: 0.1s, 0.2s, 0.4s (approximate due to execution time)
        assert len(call_times) == 4  # Initial + 3 retries
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        delay3 = call_times[3] - call_times[2]

        # Allow ±50% tolerance for timing variations
        assert 0.05 < delay1 < 0.15  # ~0.1s
        assert 0.15 < delay2 < 0.30  # ~0.2s
        assert 0.30 < delay3 < 0.60  # ~0.4s


class TestRetryOperation:
    """Test retry_operation function."""

    def test_retry_operation_success(self) -> None:
        """Test retry_operation with successful operation."""
        call_count = 0

        def operation() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        result = retry_operation(operation, max_retries=3)
        assert result == "success"
        assert call_count == 1

    def test_retry_operation_with_args(self) -> None:
        """Test retry_operation with arguments."""
        call_count = 0

        def operation(a: int, b: int) -> int:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Fail once")
            return a + b

        result = retry_operation(operation, 10, 20, max_retries=3, initial_delay=0.01)
        assert result == 30
        assert call_count == 2

    def test_retry_operation_failure(self) -> None:
        """Test retry_operation exhausts retries."""
        call_count = 0

        def operation() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            retry_operation(operation, max_retries=2, initial_delay=0.01)

        assert call_count == 3  # Initial + 2 retries

