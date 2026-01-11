"""Common utility functions for Dify plugin tools."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logging import Logger


def parse_timeout(
    value: object,
    default: int,
    logger: Logger | None = None,
    context: str = "operation",
) -> int:
    """Parse timeout value from tool parameters.

    Args:
        value: The timeout value from parameters (may be None, str, int, float).
        default: Default timeout value if parsing fails or value is None (int).
        logger: Optional logger for warning messages.
        context: Context string for log messages (e.g., "search", "get").

    Returns:
        Parsed timeout as int (seconds), or the default value.

    """
    if value is None:
        return default

    try:
        # Convert to float first to support decimal input, then round to int
        int_value = round(float(value))
        # Ensure positive integer (> 0)
        if int_value <= 0:
            if logger:
                logger.warning(
                    "Invalid timeout value for %s: %s (must be > 0), using default: %s",
                    context,
                    value,
                    default,
                )
            return default
        # Return valid positive integer
        return max(1, int_value)
    except (TypeError, ValueError):
        if logger:
            logger.warning(
                "Invalid timeout value for %s: %s, using default: %s",
                context,
                value,
                default,
            )
        return default


def parse_iso_timestamp(value: object) -> datetime | None:
    """Parse ISO8601 timestamp string into timezone-aware datetime.

    Supports formats like:
    - "2025-11-03T20:06:27.669359-08:00"
    - "2025-11-03T20:06:27Z"
    - "2025-11-03T20:06:27"

    Args:
        value: The timestamp string to parse.

    Returns:
        A timezone-aware datetime object, or None if parsing fails.

    """
    if not isinstance(value, str) or not value:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    # Convert 'Z' suffix to '+00:00' for fromisoformat compatibility
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    # Ensure timezone-aware (assume UTC if naive)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_recent_timestamp(created_at: object, updated_at: object) -> str:
    """Return the most recent timestamp (created/updated) in second precision.

    Compares created_at and updated_at, returning whichever is more recent.
    If both are empty/invalid, returns an empty string.

    Args:
        created_at: The creation timestamp (ISO8601 string).
        updated_at: The update timestamp (ISO8601 string).

    Returns:
        Formatted timestamp string like "2025-11-03T20:06:27", or empty string.

    """
    candidates = []
    for raw in (created_at, updated_at):
        parsed = parse_iso_timestamp(raw)
        if parsed is not None:
            candidates.append(parsed)

    if not candidates:
        return ""

    latest = max(candidates, key=lambda dt: dt.timestamp())
    return latest.astimezone().strftime("%Y-%m-%dT%H:%M:%S")


def parse_positive_int(
    value: object,
    default: int,
    min_value: int = 1,
    logger: Logger | None = None,
    config_name: str = "config",
) -> int:
    """Parse a positive integer config value with validation and warning logging.

    Args:
        value: Raw config value (may be None, empty string, or any type).
        default: Default value to use if value is invalid.
        min_value: Minimum allowed value (inclusive). Defaults to 1.
        logger: Optional logger for warning messages.
        config_name: Name of the config for logging purposes.

    Returns:
        int: Valid integer value >= min_value.

    """
    if value in (None, ""):
        if logger:
            logger.warning(
                "%s not set or empty, using default value: %d",
                config_name,
                default,
            )
        return max(min_value, default)

    try:
        int_value = int(value)
    except (TypeError, ValueError):
        if logger:
            logger.warning(
                "%s=%s cannot be converted to an integer, using default value: %d",
                config_name,
                value,
                default,
            )
        return max(min_value, default)
    else:
        if int_value < min_value:
            if logger:
                logger.warning(
                    "%s=%s is less than minimum value %d, using default value: %d",
                    config_name,
                    value,
                    min_value,
                    default,
                )
            return max(min_value, default)
        return int_value


def strip_code_fences(text: str) -> str:
    """Strip markdown code fences (```json ... ```) from text.

    This is useful for parsing JSON or code blocks that users may paste
    with markdown formatting.

    Args:
        text: Text that may contain code fences.

    Returns:
        Text with code fences removed.

    """
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    # Drop first fence line and possible trailing fence
    if lines:
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def log_thread_info(
    logger: Logger,
    request_id: str,
    action: str,
    start_time: float | None = None,
) -> None:
    """Log thread information for debugging concurrent calls.

    This function is used to verify whether Dify Plugin SDK supports multi-threaded
    concurrent tool invocations. By recording thread ID and thread name, we can
    determine whether multiple concurrent requests are executed simultaneously using
    different threads, or sequentially using the same thread.

    Args:
        logger: Logger instance for outputting logs.
        request_id: Request ID for tracking.
        action: Action description, such as "STARTED" or "COMPLETED".
        start_time: Optional start timestamp. If provided, calculates and logs duration.

    """
    thread_id = threading.current_thread().ident
    thread_name = threading.current_thread().name
    timestamp = time.time()

    if start_time is not None:
        duration = timestamp - start_time
        logger.debug(
            "[req:%s] [THREAD] %s - thread_id=%s, thread_name=%s, duration=%.6f",
            request_id,
            action,
            thread_id,
            thread_name,
            duration,
        )
    else:
        logger.debug(
            "[req:%s] [THREAD] %s - thread_id=%s, thread_name=%s, timestamp=%.6f",
            request_id,
            action,
            thread_id,
            thread_name,
            timestamp,
        )
