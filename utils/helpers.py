"""Common utility functions for Dify plugin tools."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime
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
    """Parse timestamp into timezone-aware datetime.

    Supports formats like:
    - "2025-11-03T20:06:27.669359-08:00" (ISO8601 string)
    - "2025-11-03T20:06:27Z" (ISO8601 string with Z suffix)
    - "2025-11-03T20:06:27" (ISO8601 string without timezone)
    - 1768622401 (Unix timestamp as int)
    - 1768622401.123 (Unix timestamp as float)

    Args:
        value: The timestamp to parse (string, int, or float).

    Returns:
        A timezone-aware datetime object, or None if parsing fails.

    """
    if value is None:
        return None

    local_tz = datetime.now().astimezone().tzinfo

    # Handle Unix timestamps (int or float)
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(value, tz=local_tz)
        except (OSError, OverflowError, ValueError):
            return None

    if not isinstance(value, str) or not value:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    # Require time component (ISO8601 should have 'T' separator)
    # Reject date-only formats like "2026-01-17"
    if "T" not in normalized and not normalized.endswith("Z"):
        # Check if it's a date-only format (YYYY-MM-DD)
        if len(normalized) == 10 and normalized.count("-") == 2:
            return None

    # Convert 'Z' suffix to '+00:00' for fromisoformat compatibility
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    # Ensure timezone-aware (assume local timezone if naive)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz)
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


def compute_duration_seconds(
    started_at: object, updated_at: object | None
) -> int | None:
    """Compute duration in seconds from two timestamps.

    Args:
        started_at: Start timestamp (ISO8601 string or Unix timestamp).
        updated_at: End timestamp (ISO8601 string or Unix timestamp).

    Returns:
        Duration in seconds (>=0) or None if start is invalid.
    """
    start_dt = parse_iso_timestamp(started_at)
    if start_dt is None:
        return None
    end_dt = parse_iso_timestamp(updated_at) or datetime.now().astimezone()
    return max(0, int((end_dt - start_dt).total_seconds()))


def format_duration_mmss(total_seconds: int | None) -> str | None:
    """Format duration in mm:ss or hh:mm:ss."""
    if total_seconds is None:
        return None
    total_seconds = max(0, int(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def format_task_time_range(
    started_at: object, updated_at: object | None
) -> tuple[str | None, str | None]:
    """Format task start/end timestamps for display (local TZ, second precision)."""
    start_dt = parse_iso_timestamp(started_at)
    if start_dt is None:
        return None, None
    end_dt = parse_iso_timestamp(updated_at)
    start_display = start_dt.astimezone().isoformat(timespec="seconds")
    end_display = (
        end_dt.astimezone().isoformat(timespec="seconds") if end_dt else None
    )
    return start_display, end_display


def resolve_task_time_range(
    range_start: object, range_end: object | None, final_report: object
) -> tuple[object | None, object | None]:
    """Resolve conversation time range from status fields or final report."""
    if range_start:
        return range_start, range_end
    if isinstance(final_report, dict):
        return final_report.get("start_time"), final_report.get("end_time")
    return None, None


def strip_tz_offset(timestamp: str | None) -> str | None:
    """Strip timezone offset suffix from ISO8601 string for display."""
    if not timestamp:
        return timestamp
    if timestamp.endswith("Z"):
        return timestamp[:-1]
    plus_index = timestamp.rfind("+")
    minus_index = timestamp.rfind("-")
    index = max(plus_index, minus_index)
    if index > 10:
        return timestamp[:index]
    return timestamp


def trim_midnight_timestamp(timestamp: str | None) -> str | None:
    """Trim trailing 'T00:00:00' from ISO8601 timestamp for display."""
    if not timestamp:
        return timestamp
    if timestamp.endswith("T00:00:00"):
        return timestamp.replace("T00:00:00", "")
    return timestamp


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


def _parse_user_ids(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple):
        ids: list[str] = []
        for x in value:
            if x is None:
                continue
            s = str(x).strip()
            if s:
                ids.append(s)
        return ids
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        return [s.strip() for s in text.split(",") if s.strip()]
    return [str(value).strip()] if str(value).strip() else []


def dedup_keep_order(items: list[str]) -> list[str]:
    """Remove duplicates from a list while preserving order.
    
    Args:
        items: List of strings (may contain duplicates)
        
    Returns:
        List with duplicates removed, preserving first occurrence order
    """
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _build_run_id(run_at: str, user_ids: list[str], app_id: str | None) -> str:
    base = {
        "run_at": run_at,
        "user_ids": sorted(set(user_ids)),
        "app_id": app_id or "",
    }
    raw = json.dumps(base, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
