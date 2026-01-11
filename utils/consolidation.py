"""Core incremental scan utilities for Dify -> Mem0 memory consolidation.

This module implements the "equivalent incremental" scan strategy described in SPEC.md:
- conversations: reverse scan, stop when conversation.updated_at <= user_checkpoint.last_run_at
- messages: reverse pagination, stop when reaching last_processed_message_id
- drop messages created_at > run_at
- reorder collected new messages to chronological order for downstream extraction
- segment messages to avoid overlong prompts
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .dify_client import DifyClient
from .helpers import parse_iso_timestamp


ScanStopReason = Literal[
    "checkpoint_updated_at",
    "no_more_conversations",
    "conversation_failed",
    "completed",
]


@dataclass
class ConversationCheckpoint:
    last_processed_message_id: str | None = None
    last_processed_message_created_at: str | None = None
    last_seen_updated_at: str | None = None


@dataclass
class UserCheckpoint:
    last_run_at: str | None = None
    conversations: dict[str, ConversationCheckpoint] | None = None
    version: str = "v1"

    def get_conv(self, conversation_id: str) -> ConversationCheckpoint:
        if self.conversations is None:
            self.conversations = {}
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = ConversationCheckpoint()
        return self.conversations[conversation_id]


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
    return str(obj.get("id") or obj.get("message_id") or obj.get("conversation_id") or "").strip()


def _coerce_dt_iso(raw: object) -> tuple[float | None, str | None]:
    dt = parse_iso_timestamp(raw)
    if dt is None:
        return None, None
    return dt.timestamp(), dt.isoformat()


def _sort_messages_chronological(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    messages_page_limit: int = 100,
    max_pages: int = 200,
) -> tuple[list[dict[str, Any]], ScanStats]:
    """Fetch new messages for one conversation according to checkpoint + run_at."""
    stats = ScanStats()
    run_at_dt = parse_iso_timestamp(run_at)
    if run_at_dt is None:
        raise ValueError("run_at must be ISO8601")
    run_at_ts = run_at_dt.timestamp()

    collected: list[dict[str, Any]] = []
    first_id: str | None = None
    pages = 0

    while pages < max_pages:
        page = dify.list_messages(
            user_id=user_id,
            conversation_id=conversation_id,
            first_id=first_id,
            limit=messages_page_limit,
        )
        pages += 1
        if not page.items:
            break
        for msg in page.items:
            stats.scanned_messages += 1
            msg_id = _get_id(msg)
            if last_processed_message_id and msg_id == last_processed_message_id:
                # Stop at checkpoint (do not include this message)
                return _sort_messages_chronological(collected), stats

            created_ts, _ = _coerce_dt_iso(msg.get("created_at"))
            if created_ts is not None and created_ts > run_at_ts:
                stats.dropped_future_messages += 1
                continue
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
        segments.append(MessageSegment(segment_id=f"{first_id}_{last_id}", messages=cur))
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
    conversations_page_limit: int = 20,
    messages_page_limit: int = 100,
) -> tuple[dict[str, list[MessageSegment]], ScanStats, ScanStopReason]:
    """Scan conversations in reverse updated_at order and return new message segments per conversation."""
    stats = ScanStats()

    run_at_dt = parse_iso_timestamp(run_at)
    if run_at_dt is None:
        raise ValueError("run_at must be ISO8601")

    last_run_at_dt = parse_iso_timestamp(user_checkpoint.last_run_at) if user_checkpoint else None

    results: dict[str, list[MessageSegment]] = {}
    last_id: str | None = None

    while True:
        page = dify.list_conversations(
            user_id=user_id,
            last_id=last_id,
            limit=conversations_page_limit,
            sort_by="-updated_at",
        )
        if not page.items:
            return results, stats, "no_more_conversations"

        for conv in page.items:
            stats.scanned_conversations += 1
            conv_id = _get_id(conv) or str(conv.get("id") or "").strip()
            if not conv_id:
                continue

            if app_id:
                conv_app = str(conv.get("app_id") or conv.get("app") or "").strip()
                if conv_app and conv_app != app_id:
                    continue

            updated_at_dt = parse_iso_timestamp(conv.get("updated_at"))
            if last_run_at_dt and updated_at_dt and updated_at_dt.timestamp() <= last_run_at_dt.timestamp():
                return results, stats, "checkpoint_updated_at"

            last_processed_message_id = None
            if user_checkpoint:
                last_processed_message_id = user_checkpoint.get_conv(conv_id).last_processed_message_id

            new_messages, msg_stats = scan_new_messages_for_conversation(
                dify,
                user_id=user_id,
                conversation_id=conv_id,
                run_at=run_at,
                last_processed_message_id=last_processed_message_id,
                messages_page_limit=messages_page_limit,
            )
            stats.scanned_messages += msg_stats.scanned_messages
            stats.dropped_future_messages += msg_stats.dropped_future_messages

            if new_messages:
                stats.conversations_with_new_messages += 1
                results[conv_id] = segment_messages(new_messages)

        last_id = page.next_cursor
        if not page.has_more or not last_id:
            return results, stats, "completed"


