"""Core incremental scan utilities for Dify -> Mem0 memory extraction.

This module implements the "equivalent incremental" scan strategy described in SPEC.md:
- conversations: reverse scan (newest first), stop when conversation.updated_at <= last_run_at
- messages: reverse pagination, stop when reaching last_processed_message_id
- drop messages created_at > run_at
- reorder collected new messages to chronological order for downstream extraction
- return all messages per conversation as a simple list (no segmentation)
- token-based truncation is handled in extract_long_term_memory.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from .constants import (
    EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT,
    EXTRACTION_DEFAULT_ENCODING,
    DIFY_API_MAX_ITEMS_PER_REQUEST,
)
from .dify_client import DifyClient
from .helpers import parse_iso_timestamp

if TYPE_CHECKING:
    pass


ScanStopReason = Literal[
    "checkpoint_updated_at",
    "no_more_conversations",
    "conversation_failed",
    "completed",
]


@dataclass
class ConversationCheckpoint:
    last_processed_message_id: str | None = None
    # Time range tracking to prevent data loss on range expansion
    processed_range_start: str | None = None  # Earliest processed message time
    # Latest processed message time (replaces last_processed_message_created_at)
    processed_range_end: str | None = None


@dataclass
class UserCheckpoint:
    last_run_at: str | None = None
    conversations: dict[str, ConversationCheckpoint] | None = None

    def get_conv(self, conversation_id: str) -> ConversationCheckpoint:
        if self.conversations is None:
            self.conversations = {}
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = ConversationCheckpoint()
        return self.conversations[conversation_id]
    
    def mark_task_success(self, run_at: str) -> None:
        """Mark task as successfully completed."""
        self.last_run_at = run_at


@dataclass
class ScanStats:
    scanned_conversations: int = 0
    scanned_messages: int = 0
    dropped_future_messages: int = 0
    conversations_with_new_messages: int = 0


@dataclass
class MessageSegment:
    segment_id: str
    messages: list[dict[str, Any]]


def estimate_tokens(text: str) -> int:
    # Very rough heuristic: ~4 chars/token for English-ish text. Works OK for budgeting.
    if not text:
        return 0
    return max(1, len(text) // 4)


def _get_id(obj: dict[str, Any]) -> str:
    return str(
        obj.get("id") or obj.get("message_id") or obj.get("conversation_id") or ""
    ).strip()


def _coerce_dt_iso(raw: object) -> tuple[float | None, str | None]:
    dt = parse_iso_timestamp(raw)
    if dt is None:
        return None, None
    return dt.timestamp(), dt.isoformat()


def _sort_messages_chronological(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    def _key(m: dict[str, Any]) -> tuple[float, str]:
        ts, _ = _coerce_dt_iso(m.get("created_at"))
        return (ts or 0.0, _get_id(m))

    return sorted(messages, key=_key)


def scan_new_messages_for_conversation(
    dify: DifyClient,
    *,
    user_id: str,
    conversation_id: str,
    run_at: str,
    last_processed_message_id: str | None,
    processed_range_start: str | None = None,
    processed_range_end: str | None = None,
    start_time: str | None = None,
    max_pages: int = 200,
    max_tokens: int | None = None,
    encoding_name: str = EXTRACTION_DEFAULT_ENCODING,
) -> tuple[list[dict[str, Any]], ScanStats]:
    """Fetch new messages for one conversation according to checkpoint + run_at.
    
    This function uses reverse pagination (newest first) and stops when:
    1. Checkpoint reached (last_processed_message_id or processed_range_end)
    2. Time boundary reached (start_time)
    3. Token limit reached (max_tokens, if specified)
    
    When max_tokens is specified, token counting is performed during pagination.
    Once the accumulated tokens exceed max_tokens, pagination stops immediately,
    avoiding unnecessary network transfer and memory usage.

    Args:
        start_time: Optional lower bound (ISO8601).
            Messages with created_at < start_time are dropped.
        run_at: Upper bound (ISO8601).
            Messages with created_at > run_at are dropped.
        processed_range_start: Start of previously processed time range
            to detect expansion.
        processed_range_end: End of previously processed time range
            (latest processed message time).
        max_tokens: Optional maximum tokens limit. If specified, stops fetching
            when accumulated tokens exceed this limit. This avoids fetching
            unnecessary historical messages.
        encoding_name: Tiktoken encoding name for token counting.
            Defaults to EXTRACTION_DEFAULT_ENCODING (cl100k_base).
    """
    stats = ScanStats()
    run_at_dt = parse_iso_timestamp(run_at)
    if run_at_dt is None:
        raise ValueError("run_at must be ISO8601")
    run_at_ts = run_at_dt.timestamp()

    start_time_ts: float | None = None
    if start_time:
        start_time_dt = parse_iso_timestamp(start_time)
        if start_time_dt is None:
            raise ValueError("start_time must be ISO8601")
        start_time_ts = start_time_dt.timestamp()
    
    # Check if time range is expanding (going back in time)
    range_is_expanding = False
    if start_time_ts is not None and processed_range_start:
        processed_start_dt = parse_iso_timestamp(processed_range_start)
        if processed_start_dt and start_time_ts < processed_start_dt.timestamp():
            range_is_expanding = True
    
    # Parse last processed message timestamp for time-based stopping
    last_processed_ts: float | None = None
    if processed_range_end:
        last_proc_dt = parse_iso_timestamp(processed_range_end)
        if last_proc_dt:
            last_processed_ts = last_proc_dt.timestamp()

    collected: list[dict[str, Any]] = []
    first_id: str | None = None
    pages = 0
    
    # Token counting for early termination (if max_tokens specified)
    accumulated_tokens = 0
    encoding = None
    if max_tokens is not None:
        try:
            import tiktoken
            encoding = tiktoken.get_encoding(encoding_name)
        except Exception:
            # If tiktoken fails, disable token-based early termination
            max_tokens = None

    while pages < max_pages:
        # Use Dify API max items per request for optimal pagination
        page = dify.list_messages(
            user_id=user_id,
            conversation_id=conversation_id,
            first_id=first_id,
            limit=DIFY_API_MAX_ITEMS_PER_REQUEST,
        )
        pages += 1
        if not page.items:
            break
        for msg in page.items:
            stats.scanned_messages += 1
            msg_id = _get_id(msg)
            created_ts, _ = _coerce_dt_iso(msg.get("created_at"))
            
            # 1. Checkpoint stop check: timestamp-based (most reliable)
            # If message created_at <= last processed message time, it's already processed
            if (last_processed_ts is not None and 
                created_ts is not None and 
                created_ts <= last_processed_ts and 
                not range_is_expanding):
                # This message and older ones are already processed, stop scanning
                return _sort_messages_chronological(collected), stats
            
            # 2. Checkpoint stop check: ID matching (fallback mechanism)
            # If we encounter the last processed message ID, stop scanning
            if (last_processed_message_id and 
                msg_id == last_processed_message_id and 
                not range_is_expanding):
                # Stop at checkpoint (exclude this message)
                return _sort_messages_chronological(collected), stats

            # 3. Time range filter: drop messages after run_at (future messages)
            if created_ts is not None and created_ts > run_at_ts:
                stats.dropped_future_messages += 1
                continue
            
            # 4. Time range filter: strictly respect start_time (user's sampling intent)
            # Even if it's a new message after checkpoint, skip if before start_time
            # This supports user's "sampling" use case
            if start_time_ts is not None and created_ts is not None and created_ts < start_time_ts:
                # Message earlier than start_time, skip regardless of checkpoint status
                continue
            
            # 5. Token limit check (if enabled)
            # Count tokens for this message before adding
            if max_tokens is not None and encoding is not None:
                msg_tokens = 0
                for field in ("query", "answer", "content", "text"):
                    value = msg.get(field)
                    if isinstance(value, str) and value.strip():
                        msg_tokens += len(encoding.encode(value.strip()))
                
                # Check if adding this message would exceed token limit
                if accumulated_tokens + msg_tokens > max_tokens and collected:
                    # Already have some messages, stop here to avoid exceeding limit
                    # Return what we have collected so far (will be sorted chronologically)
                    return _sort_messages_chronological(collected), stats
                
                accumulated_tokens += msg_tokens
            
            # 6. Collect messages that meet all criteria
            collected.append(msg)

        # Reverse pagination: move cursor to oldest message in this page
        first_id = page.next_cursor
        if not page.has_more or not first_id:
            break

    return _sort_messages_chronological(collected), stats


def segment_messages(
    messages: list[dict[str, Any]],
    *,
    max_messages: int = 30,
    max_tokens: int = 1500,
) -> list[MessageSegment]:
    """Segment messages to keep extraction prompts bounded."""
    segments: list[MessageSegment] = []
    cur: list[dict[str, Any]] = []
    cur_tokens = 0

    def _flush() -> None:
        nonlocal cur, cur_tokens
        if not cur:
            return
        first_id = _get_id(cur[0]) or "start"
        last_id = _get_id(cur[-1]) or "end"
        segments.append(
            MessageSegment(segment_id=f"{first_id}_{last_id}", messages=cur)
        )
        cur = []
        cur_tokens = 0

    for m in messages:
        # count approximate tokens from a best-effort text field
        content = str(
            m.get("content")
            or m.get("query")
            or m.get("answer")
            or m.get("text")
            or "",
        )
        t = estimate_tokens(content)
        if cur and (len(cur) >= max_messages or (cur_tokens + t) > max_tokens):
            _flush()
        cur.append(m)
        cur_tokens += t
    _flush()
    return segments


def scan_user_conversations_incremental(
    dify: DifyClient,
    *,
    user_id: str,
    run_at: str,
    user_checkpoint: UserCheckpoint | None,
    app_id: str | None = None,
    start_time: str | None = None,
    max_conversations: int = EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT,
    max_tokens_per_conversation: int | None = None,
    encoding_name: str = EXTRACTION_DEFAULT_ENCODING,
) -> tuple[dict[str, list[dict[str, Any]]], ScanStats, ScanStopReason]:
    """Scan conversations in reverse chronological order (newest first).
    
    Conversations are scanned in descending updated_at order (newest to oldest).
    Stops when:
    1. A conversation with updated_at <= last_run_at is found (checkpoint)
    2. max_conversations limit is reached (business limit to prevent abuse)
    3. No more conversations available
    
    All messages in each conversation are collected and returned as a simple list.
    If max_tokens_per_conversation is specified, message fetching stops early when
    the token limit is reached, avoiding unnecessary network transfer.

    Args:
        start_time: Optional lower bound (ISO8601).
            Messages with created_at < start_time are dropped.
        run_at: Upper bound (ISO8601).
            Messages with created_at > run_at are dropped.
        max_conversations: Maximum total conversations to process per user.
            Defaults to EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT (50).
            This prevents malicious users from consuming excessive processing time.
        max_tokens_per_conversation: Optional token limit per conversation.
            If specified, stops fetching messages when limit is reached.
            This optimizes network usage by not fetching unnecessary history.
        encoding_name: Tiktoken encoding name for token counting.
            Defaults to EXTRACTION_DEFAULT_ENCODING (cl100k_base).
            
    Returns:
        Tuple of (conversations_data, stats, stop_reason) where:
        - conversations_data: dict mapping conversation_id to list of message dicts
        - stats: ScanStats with counts of scanned/dropped messages
        - stop_reason: reason why scanning stopped
    """
    stats = ScanStats()

    run_at_dt = parse_iso_timestamp(run_at)
    if run_at_dt is None:
        raise ValueError("run_at must be ISO8601")

    last_run_at_dt = (
        parse_iso_timestamp(user_checkpoint.last_run_at) if user_checkpoint else None
    )

    results: dict[str, list[dict[str, Any]]] = {}
    last_id: str | None = None
    conversations_processed = 0

    while conversations_processed < max_conversations:
        # Optimize pagination: only request what we need
        # If we need fewer conversations than the API max, request only what we need
        # This reduces unnecessary data transfer when max_conversations is small
        remaining = max_conversations - conversations_processed
        request_limit = min(DIFY_API_MAX_ITEMS_PER_REQUEST, remaining)
        
        page = dify.list_conversations(
            user_id=user_id,
            last_id=last_id,
            limit=request_limit,
            sort_by="-updated_at",  # Descending order: prioritize newer conversations
        )
        if not page.items:
            return results, stats, "no_more_conversations"

        for conv in page.items:
            # Check if we've reached the conversation limit
            if conversations_processed >= max_conversations:
                return results, stats, "max_conversations_reached"
            
            conversations_processed += 1
            stats.scanned_conversations += 1
            conv_id = _get_id(conv) or str(conv.get("id") or "").strip()
            if not conv_id:
                continue

            if app_id:
                conv_app = str(conv.get("app_id") or conv.get("app") or "").strip()
                if conv_app and conv_app != app_id:
                    continue

            updated_at_dt = parse_iso_timestamp(conv.get("updated_at"))
            # Descending scan: stop when conversation updated_at <= last_run_at
            # (already processed, no updates)
            if (
                last_run_at_dt
                and updated_at_dt
                and updated_at_dt.timestamp() <= last_run_at_dt.timestamp()
            ):
                return results, stats, "checkpoint_updated_at"

            last_processed_message_id = None
            processed_range_start = None
            processed_range_end = None
            if user_checkpoint:
                conv_cp = user_checkpoint.get_conv(conv_id)
                last_processed_message_id = conv_cp.last_processed_message_id
                processed_range_start = conv_cp.processed_range_start
                processed_range_end = conv_cp.processed_range_end

            new_messages, msg_stats = scan_new_messages_for_conversation(
                dify,
                user_id=user_id,
                conversation_id=conv_id,
                run_at=run_at,
                last_processed_message_id=last_processed_message_id,
                processed_range_start=processed_range_start,
                processed_range_end=processed_range_end,
                start_time=start_time,
                max_tokens=max_tokens_per_conversation,
                encoding_name=encoding_name,
            )
            stats.scanned_messages += msg_stats.scanned_messages
            stats.dropped_future_messages += msg_stats.dropped_future_messages

            if new_messages:
                stats.conversations_with_new_messages += 1
                # Return all messages as a simple list (no segmentation)
                # Token-based truncation is handled by the caller
                results[conv_id] = new_messages

        last_id = page.next_cursor
        if not page.has_more or not last_id:
            return results, stats, "completed"
    
    # If we exit the loop normally (conversations_processed >= max_conversations)
    # without hitting any return statement, return with completed status
    return results, stats, "completed"

