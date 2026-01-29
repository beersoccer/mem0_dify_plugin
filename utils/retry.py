"""Retry utilities with exponential backoff for robust API calls.

This module provides retry decorators and helpers to handle transient failures
in network calls and external service interactions.
"""

from __future__ import annotations

import random
import time
from functools import wraps
from typing import TYPE_CHECKING, TypeVar

from .logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)

T = TypeVar("T")


def retry_with_exponential_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retriable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry decorator with exponential backoff and jitter.

    Parameters:
    - max_retries: Maximum number of retries (excluding initial call)
    - initial_delay: Initial delay in seconds
    - max_delay: Maximum delay in seconds
    - exponential_base: Exponential base for backoff
    - jitter: Whether to add random jitter (avoids thundering herd)
    - retriable_exceptions: Tuple of exception types to retry

    Retry delay calculation:
    delay = min(initial_delay * (exponential_base ** retry_count), max_delay)
    if jitter: delay *= random.uniform(0.5, 1.5)

    Example:
        @retry_with_exponential_backoff(max_retries=3, initial_delay=1.0)
        def call_api():
            return requests.get("https://api.example.com")
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: object, **kwargs: object) -> T:
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retriable_exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        # Last retry failed, raise exception
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
                        raise

                    # Calculate delay time
                    delay = min(
                        initial_delay * (exponential_base**attempt), max_delay
                    )

                    if jitter:
                        delay *= random.uniform(0.5, 1.5)

                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    time.sleep(delay)
                except Exception as e:
                    # Non-retriable exception, raise immediately
                    logger.error(f"Non-retriable exception in {func.__name__}: {e}")
                    raise

            # Should never reach here
            if last_exception:
                raise last_exception
            msg = "Unexpected retry loop exit"
            raise RuntimeError(msg)

        return wrapper

    return decorator


def retry_operation(
    operation: Callable[..., T],
    *args: object,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    **kwargs: object,
) -> T:
    """Execute an operation with retries (non-decorator version).

    Suitable for scenarios where retry logic needs to be decided at runtime.

    Example:
        result = retry_operation(
            mem0_client.add,
            messages=messages,
            user_id=user_id,
            max_retries=3,
        )
    """

    @retry_with_exponential_backoff(
        max_retries=max_retries,
        initial_delay=initial_delay,
        retriable_exceptions=(Exception,),
    )
    def wrapped() -> T:
        return operation(*args, **kwargs)

    return wrapped()

