"""Helper functions for memory operation tools.

These functions provide common functionality that can be used by tools
without requiring class inheritance, avoiding class loader issues.
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import TYPE_CHECKING, Any, Callable

from utils.logger import get_logger
from utils.mem0_client import (
    QueueOverloadError,
    get_async_client,
    get_sync_client,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from dify_plugin.entities.tool import ToolInvokeMessage

logger = get_logger(__name__)


def init_request_context(
    tool_parameters: dict[str, Any],
) -> tuple[str, float]:
    """Initialize request context (request_id and start_time).

    Args:
        tool_parameters: Tool parameters dictionary

    Returns:
        Tuple of (request_id, start_time).
    """
    request_id = tool_parameters.get("run_id") or "no-run-id"
    start_time = time.time()
    return (request_id, start_time)


def validate_user_id(
    tool_parameters: dict[str, Any],
) -> str | None:
    """Validate user_id parameter and return it or None if invalid."""
    return tool_parameters.get("user_id")


def validate_memory_id(
    tool_parameters: dict[str, Any],
) -> str | None:
    """Validate memory_id parameter and return it or None if invalid."""
    return tool_parameters.get("memory_id")


def yield_error(
    tool_instance: Any,
    request_id: str,
    error_message: str,
    operation_name: str,
    default_results: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> Generator[ToolInvokeMessage, None, None]:
    """Yield error messages in standard format.

    Args:
        tool_instance: Tool instance (for accessing create_json_message, etc.)
        request_id: Request ID for tracing
        error_message: Error message to display
        operation_name: Name of the operation (e.g., "search memory", "add memory")
        default_results: Default results to return (empty dict or list)

    Returns:
        Generator of tool invoke messages.
    """
    if default_results is None:
        default_results = {}
    logger.error("[req:%s] %s failed: %s", request_id, operation_name, error_message)
    yield tool_instance.create_json_message(
        {"status": "ERROR", "messages": error_message, "results": default_results},
    )
    yield tool_instance.create_text_message(f"Failed to {operation_name}: {error_message}")


def execute_async_read_operation(  # noqa: PLR0913
    tool_instance: Any,
    operation: Callable,
    operation_args: tuple[Any, ...],
    operation_kwargs: dict[str, Any],
    timeout: float,
    request_id: str,
    mode_str: str,
    start_time: float,
    operation_name: str,
) -> tuple[Any, str | None]:
    """Execute async read operation with error handling.

    Args:
        tool_instance: Tool instance (for accessing runtime.credentials)
        operation: Async operation function to execute
        operation_args: Positional arguments for the operation
        operation_kwargs: Keyword arguments for the operation (including timeout_s)
        timeout: Operation timeout
        request_id: Request ID for tracing
        mode_str: Mode string ("async" or "sync")
        start_time: Operation start time
        operation_name: Name of the operation for logging

    Returns:
        Tuple of (result, error_type). result is None on error, error_type is None on success.
    """
    client = get_async_client(tool_instance.runtime.credentials)
    loop = client.ensure_bg_loop()
    future = asyncio.run_coroutine_threadsafe(
        operation(*operation_args, **operation_kwargs),
        loop,
    )
    client.track_bg_task(
        future,
        f"{operation_name}(req_id={request_id})",
    )

    result: Any = None
    error_type: str | None = None
    try:
        failsafe_timeout = timeout + 1.0
        result = future.result(timeout=failsafe_timeout)
    except asyncio.TimeoutError:
        error_type = "TIMEOUT"
        result = None
    except FuturesTimeoutError:
        future.cancel()
        elapsed = time.time() - start_time
        logger.warning(
            "[req:%s] %s operation failsafe timeout after %s seconds "
            "(mode: %s, duration: %.2fs)",
            request_id,
            operation_name,
            failsafe_timeout,
            mode_str,
            elapsed,
        )
        error_type = "TIMEOUT"
        result = None
    except QueueOverloadError:
        error_type = "OVERLOAD"
        result = None
    except Exception as e:
        elapsed = time.time() - start_time
        logger.exception(
            "[req:%s] %s operation failed with error: %s "
            "(mode: %s, duration: %.2fs)",
            request_id,
            operation_name,
            type(e).__name__,
            mode_str,
            elapsed,
        )
        error_type = "ERROR"
        result = None

    return (result, error_type)


def execute_sync_read_operation(  # noqa: PLR0913
    tool_instance: Any,
    operation: Callable[..., object | None],
    operation_args: tuple[Any, ...],
    operation_kwargs: dict[str, Any],
    request_id: str,
    mode_str: str,
    start_time: float,
    operation_name: str,
) -> object | None:
    """Execute sync read operation with error handling.

    Args:
        tool_instance: Tool instance (for accessing runtime.credentials)
        operation: Sync operation function to execute
        operation_args: Positional arguments for the operation
        operation_kwargs: Keyword arguments for the operation
        request_id: Request ID for tracing
        mode_str: Mode string ("async" or "sync")
        start_time: Operation start time
        operation_name: Name of the operation for logging

    Returns:
        Operation result, or None/empty list on error.
    """
    get_sync_client(tool_instance.runtime.credentials)  # Ensure client is initialized
    try:
        return operation(*operation_args, **operation_kwargs)
    except Exception as e:
        elapsed = time.time() - start_time
        logger.exception(
            "[req:%s] %s operation failed with error: %s "
            "(mode: %s, duration: %.2fs)",
            request_id,
            operation_name,
            type(e).__name__,
            mode_str,
            elapsed,
        )
        # Return appropriate default based on operation type
        # For list operations, return empty list; for dict operations, return None
        return None


def build_status_and_message(
    error_type: str | None,
    success_message: str,
) -> tuple[str, str]:
    """Build status and message from error type and success message.

    Args:
        error_type: Error type string or None
        success_message: Success message to use when no error

    Returns:
        Tuple of (status, messages).
    """
    if error_type:
        if error_type == "TIMEOUT":
            return ("TIMEOUT", "Operation timed out, returning empty results")
        if error_type == "OVERLOAD":
            return ("OVERLOAD", "System overloaded, returning empty results")
        return ("ERROR", "Operation failed, returning empty results")
    return ("SUCCESS", success_message)

