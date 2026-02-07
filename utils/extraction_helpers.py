"""Helper functions for long-term memory extraction operations.

This module provides utility functions for token counting, message truncation,
time range calculation, and timestamp comparison used in extraction tasks.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from .constants import EXTRACTION_DEFAULT_ENCODING
from .helpers import parse_iso_timestamp
from .logger import get_logger

logger = get_logger(__name__)


def count_message_tokens(
    messages: list[dict[str, Any]],
    encoding_name: str = EXTRACTION_DEFAULT_ENCODING,
) -> int:
    """Count total tokens for a list of Dify messages using tiktoken.
    
    Args:
        messages: List of Dify message dicts
        encoding_name: Tiktoken encoding name (default: cl100k_base for GPT-4/3.5)
        
    Returns:
        Accurate token count
    """
    # Lazy import tiktoken to avoid gevent monkey-patching issues
    try:
        import tiktoken
        encoding = tiktoken.get_encoding(encoding_name)
    except Exception as e:
        logger.warning(
            f"Failed to load tiktoken encoding '{encoding_name}': {e}. "
            f"Using fallback estimation."
        )
        # Fallback to character-based estimation (4 chars per token)
        total = 0
        for m in messages:
            content = str(
                m.get("content") or m.get("query") or m.get("answer") or m.get("text") or ""
            )
            total += max(1, len(content) // 4)
        return total
    
    total = 0
    for m in messages:
        # Extract all text content from message
        content_parts = []
        for field in ("query", "answer", "content", "text"):
            value = m.get(field)
            if isinstance(value, str) and value.strip():
                content_parts.append(value.strip())
        
        if content_parts:
            combined = "\n".join(content_parts)
            total += len(encoding.encode(combined))
    
    return total


def truncate_to_recent_messages(
    messages: list[dict[str, Any]],
    max_tokens: int,
    encoding_name: str = EXTRACTION_DEFAULT_ENCODING,
) -> list[dict[str, Any]]:
    """Truncate messages to fit within token limit, keeping the most recent ones.
    
    This function processes messages in reverse chronological order (newest first),
    accumulating tokens until the limit is reached. This ensures the most recent
    and relevant conversation context is preserved.
    
    Args:
        messages: List of Dify message dicts (chronological order)
        max_tokens: Maximum token limit
        encoding_name: Tiktoken encoding name
        
    Returns:
        Truncated message list (chronological order) that fits within token limit
    """
    if not messages:
        return []
    
    # Quick check: if total is under limit, return all
    total_tokens = count_message_tokens(messages, encoding_name)
    if total_tokens <= max_tokens:
        return messages
    
    # Lazy import tiktoken to avoid gevent monkey-patching issues
    try:
        import tiktoken
        encoding = tiktoken.get_encoding(encoding_name)
    except Exception as e:
        logger.warning(
            f"Failed to load tiktoken encoding '{encoding_name}': {e}. "
            f"Using fallback truncation."
        )
        # Fallback: estimate 4 chars per token
        accumulated_chars = 0
        max_chars = max_tokens * 4
        result = []
        for m in reversed(messages):
            content = str(
                m.get("content") or m.get("query") or m.get("answer") or m.get("text") or ""
            )
            msg_chars = len(content)
            if accumulated_chars + msg_chars > max_chars:
                break
            result.insert(0, m)
            accumulated_chars += msg_chars
        return result if result else messages[-1:]  # At least return the last message
    
    # Process messages in reverse chronological order (newest first)
    accumulated_tokens = 0
    result: list[dict[str, Any]] = []
    
    for m in reversed(messages):
        # Count tokens for this message
        content_parts = []
        for field in ("query", "answer", "content", "text"):
            value = m.get(field)
            if isinstance(value, str) and value.strip():
                content_parts.append(value.strip())
        
        msg_tokens = 0
        if content_parts:
            combined = "\n".join(content_parts)
            msg_tokens = len(encoding.encode(combined))
        
        # Check if adding this message would exceed limit
        if accumulated_tokens + msg_tokens > max_tokens and result:
            # Already have some messages, stop here
            break
        
        # Add message to result (will be reversed later)
        result.insert(0, m)
        accumulated_tokens += msg_tokens
    
    # Ensure we return at least the most recent message
    if not result and messages:
        result = [messages[-1]]
    
    # Log truncation details only if debug level is enabled
    if logger.isEnabledFor(logging.DEBUG):
        total_tokens = count_message_tokens(messages, encoding_name)
        accumulated_tokens = count_message_tokens(result, encoding_name)
        logger.debug(
            "Truncated conversation from %d messages (%d tokens) to %d messages (%d tokens)",
            len(messages),
            total_tokens,
            len(result),
            accumulated_tokens,
        )
    
    return result


def get_time_range_from_days(days_back: int) -> tuple[str, str]:
    """Calculate time range based on days_back parameter.
    
    Args:
        days_back: Number of days to look back (1-7).
                   For example, days_back=2 means yesterday and the day before.
    
    Returns:
        tuple[str, str]: (start_time, end_time) in ISO8601 format
                        start_time: (today - days_back) 00:00:00 (local time)
                        end_time: today 00:00:00 (local time)
    
    Example:
        If today is Jan 25, 2026:
        - days_back=1: [Jan 24 00:00:00, Jan 25 00:00:00)
        - days_back=2: [Jan 23 00:00:00, Jan 25 00:00:00)
        - days_back=3: [Jan 22 00:00:00, Jan 25 00:00:00)
    """
    # Clamp days_back to 1-7
    days_back = max(1, min(7, days_back))
    
    now = datetime.now().astimezone()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # start_time: (today - days_back) at 00:00:00
    start_time = today_start - timedelta(days=days_back)
    
    # end_time: today at 00:00:00
    end_time = today_start
    
    return start_time.isoformat(), end_time.isoformat()


def cmp_iso_timestamps(a: str | None, b: str | None) -> int:
    """Compare two ISO timestamps; returns -1/0/1 where None is smallest.
    
    Args:
        a: First ISO timestamp string or None
        b: Second ISO timestamp string or None
        
    Returns:
        -1 if a < b, 0 if a == b, 1 if a > b
        None is treated as the smallest value
    """
    da = parse_iso_timestamp(a)
    db = parse_iso_timestamp(b)
    if da is None and db is None:
        return 0
    if da is None:
        return -1
    if db is None:
        return 1
    ta = da.timestamp()
    tb = db.timestamp()
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0

