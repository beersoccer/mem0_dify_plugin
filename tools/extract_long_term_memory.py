"""Dify tool: extract long-term memories from Dify conversation history into Mem0.

This tool is implemented as an async task pattern:
- Tool immediately returns ACCEPTED status with task_id
- Actual extraction runs in background event loop (reusing existing infrastructure)
- Task status can be queried via check_extraction_status tool
- Supports concurrent processing of up to 5 users for faster batch processing

Optimization (2026-01-24):
- Intelligently classifies each conversation to determine the most relevant memory type
- Extracts only the classified type (semantic/episodic/procedural) instead of all three
- Reduces LLM calls from 3 per conversation to 2 (1 classification + 1 extraction)
- Based on the assumption that conversations typically focus on a single topic/memory type

Optimization (2026-01-25):
- Per-conversation processing with configurable token limits
  (default: EXTRACTION_DEFAULT_MAX_TOKENS = 64K)
- Uses tiktoken (EXTRACTION_DEFAULT_ENCODING = cl100k_base) for accurate token counting
- Token limiting applied during API pagination to optimize network transfer
- When token limit reached, pagination stops early and only recent messages are fetched
- No segmentation needed - preserves complete conversation context
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from dify_plugin import Tool

from utils.background_loop import BackgroundEventLoop
from utils.checkpoint import load_checkpoint, save_checkpoint_atomic
from utils.config_builder import build_local_mem0_config
from utils.constants import (
    EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT,
    EXTRACTION_DEFAULT_ENCODING,
    EXTRACTION_DEFAULT_MAX_TOKENS,
    EXTRACTION_DIFY_TIMEOUT,
    EXTRACTION_LOCK_TTL,
    EXTRACTION_MAX_CONCURRENT_USERS,
    EXTRACTION_TIME_BUDGET,
)
from utils.dify_client import DifyAPIError, DifyClient
from utils.distributed_lock import LockManager
from utils.extraction import UserCheckpoint, scan_user_conversations_incremental
from utils.helpers import _parse_user_ids, parse_iso_timestamp
from utils.logger import get_logger
from utils.mem0_client import Memory
from utils.mem0_extraction import (
    build_memory_metadata,
    build_subtype_memories,
    classify_conversation_memory_type,
    mem0_add_segment,
)
from utils.message_utils import (
    count_add_results,
    dify_msg_to_mem0_messages,
)
from utils.task_status import (
    ExtractionTaskStatus,
    mark_task_completed,
    mark_task_failed,
    save_task_status,
    update_task_progress,
)
from utils.task_tracker import TaskTracker

if TYPE_CHECKING:
    from collections.abc import Generator

    from dify_plugin.entities.tool import ToolInvokeMessage

logger = get_logger(__name__)


def _dedup_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _get_time_range_from_days(days_back: int) -> tuple[str, str]:
    """Calculate time range based on days_back parameter.
    
    Args:
        days_back: Number of days to look back (1-7).
                   For example, days_back=2 means yesterday and the day before.
    
    Returns:
        tuple[str, str]: (start_time, end_time) in ISO8601 format
                         start_time: (today - days_back) 00:00:00
                         end_time: today 00:00:00
    
    Example:
        If today is Jan 25, 2026:
        - days_back=1: [Jan 24 00:00:00, Jan 25 00:00:00) (yesterday)
        - days_back=2: [Jan 23 00:00:00, Jan 25 00:00:00) (yesterday + day before)
        - days_back=3: [Jan 22 00:00:00, Jan 25 00:00:00) (last 3 days)
    """
    # Clamp days_back to 1-7
    days_back = max(1, min(7, days_back))
    
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # start_time: (today - days_back) at 00:00:00
    start_time = today_start - timedelta(days=days_back)
    
    # end_time: today at 00:00:00
    end_time = today_start
    
    return start_time.isoformat(), end_time.isoformat()


def _cmp_iso(a: str | None, b: str | None) -> int:
    """Compare two ISO timestamps; returns -1/0/1 where None is smallest."""
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


# Message conversion functions moved to utils/message_utils.py for better testability


def _count_message_tokens(
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


def _truncate_to_recent_messages(
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
    total_tokens = _count_message_tokens(messages, encoding_name)
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
    
    logger.debug(
        "Truncated conversation from %d messages (%d tokens) to %d messages (%d tokens)",
        len(messages),
        total_tokens,
        len(result),
        accumulated_tokens,
    )
    
    return result


def _process_single_user(
    base_mem: Memory,
    subtype_mems: dict[str, Any],
    user_id: str,
    app_id: str,
    run_id: str,
    start_time: str,
    end_time: str,
    dify: DifyClient,
    lock_manager: LockManager,
    max_conversations: int,
    max_tokens_per_conversation: int,
) -> dict[str, Any]:
    """Process a single user's conversations.
    
    This is the core processing logic for one user, designed to be called
    concurrently for multiple users.
    
    Each conversation is processed as a whole (no segmentation). If a conversation
    exceeds the token limit, only the most recent messages within the limit are
    processed to preserve the most relevant context.
    
    Args:
        base_mem: Memory instance for checkpoints
        subtype_mems: Dictionary of subtype-specific Memory instances
        user_id: User ID to process
        app_id: Application ID
        run_id: Run identifier for lock management
        start_time: ISO8601 start time
        end_time: ISO8601 end time
        dify: Dify API client
        lock_manager: Lock manager instance
        max_conversations: Maximum conversations to process (prevents abuse)
        max_tokens_per_conversation: Maximum tokens per conversation for processing
        
    Returns:
        User processing report dict
    """
    user_report: dict[str, Any] = {
        "user_id": user_id,
        "status": "SUCCESS",
        "skipped": False,
        "errors": [],
        "scanned_conversations": 0,
        "scanned_messages": 0,
        "written_memories": {"semantic": 0, "episodic": 0, "procedural": 0},
    }

    # 1. Try to acquire lock
    lock_acquired, existing_lock = lock_manager.acquire_lock(
        user_id=user_id,
        app_id=app_id,
        holder_id=run_id,
        ttl_seconds=EXTRACTION_LOCK_TTL,
    )

    if not lock_acquired:
        user_report["status"] = "SKIPPED"
        user_report["skipped"] = True
        user_report["reason"] = "lock_held"
        user_report["lock_holder"] = (
            existing_lock.holder_id if existing_lock else "unknown"
        )
        lock_holder = existing_lock.holder_id if existing_lock else "unknown"
        logger.warning(
            "[run:%s] Skip user %s: lock held by %s",
            run_id,
            user_id,
            lock_holder,
        )
        return user_report

    try:
        # Load checkpoint
        cp_id, cp = load_checkpoint(base_mem, user_id=user_id, app_id=app_id)
        if cp is None:
            cp = UserCheckpoint()

        # Idempotency check
        if _cmp_iso(cp.last_run_at, end_time) > 0:
            logger.info(
                "[run:%s] Skip user %s: already processed beyond %s (last_run_at: %s)",
                run_id,
                user_id,
                end_time,
                cp.last_run_at,
            )
            user_report["status"] = "SKIPPED"
            user_report["skipped"] = True
            user_report["reason"] = "already_processed"
            user_report["last_run_at"] = cp.last_run_at
            return user_report

        if _cmp_iso(cp.last_run_at, end_time) == 0:
            logger.info(
                "[run:%s] Reprocess user %s with same end_time %s: "
                "checking for new messages or time range expansion",
                run_id,
                user_id,
                end_time,
            )

        # Process user
        try:
            conversations_data, stats, stop_reason = scan_user_conversations_incremental(
                dify,
                user_id=user_id,
                run_at=end_time,
                user_checkpoint=cp,
                app_id=None,
                start_time=start_time,
                max_conversations=max_conversations,
                max_tokens_per_conversation=max_tokens_per_conversation,
            )
        except DifyAPIError as e:
            logger.warning(
                "[run:%s] Dify API error while processing user %s: %s",
                run_id,
                user_id,
                e,
            )
            user_report["status"] = "ERROR"
            user_report["errors"].append(
                {"type": "dify_api_error", "message": str(e)}
            )
            return user_report
        except Exception as e:
            logger.error(
                "[run:%s] Unexpected error while processing user %s: %s",
                run_id,
                user_id,
                e,
            )
            user_report["status"] = "ERROR"
            user_report["errors"].append(
                {"type": type(e).__name__, "message": str(e)}
            )
            return user_report

        # Calculate stats
        conversations_with_messages = len(conversations_data)
        total_messages_in_range = sum(
            len(messages) for messages in conversations_data.values()
        )

        user_report["stop_reason"] = stop_reason
        user_report["scanned_conversations"] = stats.scanned_conversations
        user_report["scanned_messages"] = stats.scanned_messages
        user_report["dropped_future_messages"] = stats.dropped_future_messages
        user_report["conversations_with_messages"] = conversations_with_messages
        user_report["messages_in_time_range"] = total_messages_in_range

        # Process each conversation's messages
        # Note: Token limiting is now handled in scan_user_conversations_incremental()
        # to avoid fetching unnecessary messages from Dify API
        for conv_id, conversation_messages in conversations_data.items():
            conv_cp = cp.get_conv(conv_id)

            last_processed_id: str | None = None
            last_processed_created_at: str | None = None

            if not conversation_messages:
                continue

            # Log message count (token limiting already applied during fetch)
            total_tokens = _count_message_tokens(conversation_messages)
            msg_count = len(conversation_messages)
            logger.debug(
                "[run:%s] Processing conversation %s: %d messages, %d tokens",
                run_id,
                conv_id,
                msg_count,
                total_tokens,
            )

            # Convert to mem0 message format
            mem0_msgs = dify_msg_to_mem0_messages(conversation_messages)
            if not mem0_msgs:
                continue

            # Build message ID range for metadata (start_id~end_id)
            first_id = (
                conversation_messages[0].get("id", "start")
                if conversation_messages
                else "start"
            )
            last_id = (
                conversation_messages[-1].get("id", "end")
                if conversation_messages
                else "end"
            )
            message_id_range = f"{first_id}~{last_id}"

            # STEP 1: Classify conversation and evaluate extraction value (combined)
            # Use the first subtype's memory instance for classification (they share LLM config)
            classified_type, should_extract = classify_conversation_memory_type(
                mem=subtype_mems["semantic"].memory,
                messages=mem0_msgs,
                context={
                    "user_id": user_id,
                    "conversation_id": conv_id,
                    "message_id_range": message_id_range,
                },
            )
            
            # Skip if no significant content, classification failed, or not worth extracting
            if classified_type is None or not should_extract:
                skip_reason = (
                    "no significant memorable content" if classified_type is None
                    else "LLM determined content not worth extracting"
                )
                logger.debug(
                    "[run:%s] Skip conversation %s: %s",
                    run_id,
                    conv_id,
                    skip_reason,
                )
                # Still update checkpoint to avoid reprocessing
                last_msg = conversation_messages[-1] if conversation_messages else None
                if isinstance(last_msg, dict):
                    last_processed_id = str(last_msg.get("id", "")).strip() or None
                    ca = last_msg.get("created_at")
                    if isinstance(ca, str) and ca.strip():
                        last_processed_created_at = ca.strip()
                # Update checkpoint even if skipped
                if last_processed_id:
                    conv_cp.last_processed_message_id = last_processed_id
                    if conv_cp.processed_range_start is None or (
                        start_time and start_time < conv_cp.processed_range_start
                    ):
                        conv_cp.processed_range_start = start_time
                    if conv_cp.processed_range_end is None or (
                        last_processed_created_at
                        and last_processed_created_at > conv_cp.processed_range_end
                    ):
                        conv_cp.processed_range_end = last_processed_created_at
                continue

            logger.debug(
                "[run:%s] Conversation %s classified as %s memory and approved for extraction",
                run_id,
                conv_id,
                classified_type,
            )

            # STEP 2: Extract memory using only the classified type
            md = build_memory_metadata(
                subtype=classified_type,
                app_id=app_id,
                conversation_id=conv_id,
                segment_id=message_id_range,
                run_at=end_time,
                message_id_range=message_id_range,
            )
            
            try:
                res = mem0_add_segment(
                    mem=subtype_mems[classified_type].memory,
                    messages=mem0_msgs,
                    user_id=user_id,
                    metadata=md,
                )
                c = count_add_results(res)
                user_report["written_memories"][classified_type] += c
                logger.debug(
                    "[run:%s] Successfully wrote %d %s memories for conversation %s",
                    run_id,
                    c,
                    classified_type,
                    conv_id,
                )
            except Exception as e:
                logger.warning(
                    f"Failed to write {classified_type} memory "
                    f"for conversation {conv_id}: {e}"
                )
                user_report["errors"].append({
                    "type": f"mem0_{classified_type}_error",
                    "conversation_id": conv_id,
                    "message": str(e),
                })

            # Update last processed message info
            last_msg = conversation_messages[-1] if conversation_messages else None
            if isinstance(last_msg, dict):
                last_processed_id = str(last_msg.get("id", "")).strip() or None
                ca = last_msg.get("created_at")
                if isinstance(ca, str) and ca.strip():
                    last_processed_created_at = ca.strip()

            # Update conversation checkpoint
            if last_processed_id:
                conv_cp.last_processed_message_id = last_processed_id

                if conv_cp.processed_range_start is None or (
                    start_time and start_time < conv_cp.processed_range_start
                ):
                    conv_cp.processed_range_start = start_time

                if conv_cp.processed_range_end is None or (
                    last_processed_created_at and
                    last_processed_created_at > conv_cp.processed_range_end
                ):
                    conv_cp.processed_range_end = last_processed_created_at

        # Finalize user checkpoint
        cp.mark_task_success(end_time)
        try:
            ok, new_id = save_checkpoint_atomic(
                base_mem,
                user_id=user_id,
                app_id=app_id,
                checkpoint=cp,
                max_retries=3,
            )
            if not ok:
                user_report["status"] = "PARTIAL_SUCCESS"
                user_report["errors"].append(
                    {"type": "checkpoint_update_failed", "message": "Failed to save checkpoint"},
                )
        except Exception as checkpoint_error:
            user_report["status"] = "PARTIAL_SUCCESS"
            user_report["errors"].append(
                {"type": "checkpoint_update_failed", "message": str(checkpoint_error)},
            )

        # If any mem0 errors occurred during processing, downgrade to PARTIAL_SUCCESS
        mem0_errors = [
            e for e in user_report["errors"]
            if e.get("type", "").startswith("mem0_")
        ]
        if mem0_errors and user_report["status"] == "SUCCESS":
            user_report["status"] = "PARTIAL_SUCCESS"

        return user_report

    finally:
        # Always release lock
        lock_manager.release_lock(user_id, app_id, run_id)


async def _execute_extraction_async(
    base_mem: Memory,
    subtype_mems: dict[str, Any],
    task_id: str,
    run_id: str,
    user_ids: list[str],
    app_id: str,
    start_time: str,
    end_time: str,
    dify_base_url: str,
    dify_api_key: str,
    max_conversations: int,
    max_tokens_per_conversation: int,
) -> dict[str, Any]:
    """Execute extraction task in background event loop with concurrent user processing.

    This function runs in the shared background event loop and processes up to 5 users
    concurrently for faster batch processing. It wraps synchronous operations using
    asyncio.to_thread() to avoid blocking the event loop.

    Args:
        base_mem: Shared Memory instance for checkpoints and task status
        subtype_mems: Dictionary of subtype-specific Memory instances
        task_id: Unique task identifier
        run_id: Run identifier for lock management
        user_ids: List of user IDs to process
        app_id: Application ID for memory isolation
        start_time: ISO8601 start time for time range
        end_time: ISO8601 end time for time range
        dify_base_url: Dify API base URL
        dify_api_key: Dify API key
        max_conversations: Maximum conversations to process per user (prevents abuse)
        max_tokens_per_conversation: Maximum tokens per conversation for processing

    Returns:
        Final extraction report dict
    """
    try:
        # Create shared resources (thread-safe)
        dify = DifyClient(dify_base_url, dify_api_key, timeout=EXTRACTION_DIFY_TIMEOUT)
        lock_manager = LockManager(base_mem)

        started_at = time.monotonic()
        hard_time_budget_sec = float(EXTRACTION_TIME_BUDGET)

        per_user: list[dict[str, Any]] = []

        summary = {
            "processed_users": 0,
            "skipped_users": 0,
            "scanned_conversations": 0,
            "scanned_messages": 0,
            "written_memories": {"semantic": 0, "episodic": 0, "procedural": 0},
        }

        overall_status = "SUCCESS"

        # Semaphore to limit concurrent user processing
        semaphore = asyncio.Semaphore(EXTRACTION_MAX_CONCURRENT_USERS)

        async def process_user_with_semaphore(user_id: str) -> dict[str, Any]:
            """Process user with concurrency control."""
            async with semaphore:
                # Run synchronous processing in thread pool to avoid blocking event loop
                return await asyncio.to_thread(
                    _process_single_user,
                    base_mem,
                    subtype_mems,
                    user_id,
                    app_id,
                    run_id,
                    start_time,
                    end_time,
                    dify,
                    lock_manager,
                    max_conversations,
                    max_tokens_per_conversation,
                )

        # Process users in batches, respecting time budget
        remaining_users = list(user_ids)
        # Batch size equals concurrent limit for optimal resource utilization
        batch_size = EXTRACTION_MAX_CONCURRENT_USERS
        
        while remaining_users and (time.monotonic() - started_at) < hard_time_budget_sec:
            batch = remaining_users[:batch_size]
            remaining_users = remaining_users[batch_size:]
            
            # Process batch concurrently (up to 5 at a time due to semaphore)
            batch_tasks = [process_user_with_semaphore(uid) for uid in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # Aggregate results
            for user_id, result in zip(batch, batch_results, strict=True):
                if isinstance(result, Exception):
                    logger.exception(f"Error processing user {user_id}: {result}")
                    per_user.append({
                        "user_id": user_id,
                        "status": "ERROR",
                        "errors": [{"type": type(result).__name__, "message": str(result)}],
                    })
                    overall_status = "PARTIAL_SUCCESS"
                else:
                    per_user.append(result)
                    if result["status"] == "SUCCESS":
                        summary["processed_users"] += 1
                        summary["scanned_conversations"] += result.get("scanned_conversations", 0)
                        summary["scanned_messages"] += result.get("scanned_messages", 0)
                        for mem_type in ["semantic", "episodic", "procedural"]:
                            summary["written_memories"][mem_type] += result.get(
                                "written_memories", {}
                            ).get(mem_type, 0)
                    elif result.get("skipped"):
                        summary["skipped_users"] += 1
                    else:
                        overall_status = "PARTIAL_SUCCESS"
            
            # Update progress after each batch
            await asyncio.to_thread(
                update_task_progress,
                base_mem,
                task_id=task_id,
                processed_users=summary["processed_users"] + summary["skipped_users"],
                total_users=len(user_ids),
                scanned_conversations=summary["scanned_conversations"],
                scanned_messages=summary["scanned_messages"],
                written_memories=summary["written_memories"],
            )

        # Handle remaining users that exceeded time budget
        for uid in remaining_users:
            overall_status = "PARTIAL_SUCCESS"
            per_user.append(
                {
                    "user_id": uid,
                    "status": "SKIPPED",
                    "reason": "time_budget_exceeded",
                },
            )
            summary["skipped_users"] += 1

        summary["skipped_users"] = summary.get("skipped_users", 0)

        report = {
            "status": overall_status,
            "run_id": run_id,
            "start_time": start_time,
            "end_time": end_time,
            "app_id": app_id,
            "user_count": len(user_ids),
            "summary": summary,
            "per_user": per_user,
        }

        logger.info(
            "Extraction task %s completed: status=%s, processed=%d/%d users (run_id=%s)",
            task_id,
            overall_status,
            summary["processed_users"],
            len(user_ids),
            run_id,
        )

        return report
    except Exception:
        logger.exception("Extraction task %s failed (run_id=%s)", task_id, run_id)
        raise


class ExtractLongTermMemoryTool(Tool):
    """Incrementally scan Dify history for specified users and extract long-term memories.

    This tool runs asynchronously:
    - Immediately returns ACCEPTED status with task_id
    - Actual extraction runs in background thread
    - Use check_extraction_status tool to query task progress

    Design Notes:
    - Uses threading.Thread instead of asyncio event loop because:
      1. Extraction is a long-running, CPU/IO-intensive task (minutes)
      2. DifyClient and Memory operations are synchronous
      3. Converting to async would require major refactoring without clear benefits
    - Memory instances are shared between main and background threads
    - mem0's Memory class is thread-safe for concurrent read/write operations
    - Task status is persisted in Mem0 for progress tracking and recovery
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Invoke extraction tool - returns immediately with task_id, runs in background."""
        try:
            # Validate and parse parameters
            days_back = tool_parameters.get("days_back")
            try:
                days_back_int = int(days_back) if days_back is not None else 3
                days_back_int = max(1, min(7, days_back_int))
            except (TypeError, ValueError):
                days_back_int = 3

            start_time, end_time = _get_time_range_from_days(days_back_int)
            logger.info(
                f"Extraction task: processing {days_back_int} day(s) back: "
                f"{start_time} to {end_time}"
            )

            user_ids = _parse_user_ids(tool_parameters.get("user_ids"))
            if not user_ids:
                msg = "user_ids is required"
                yield self.create_json_message(
                    {"status": "ERROR", "messages": msg, "results": []}
                )
                yield self.create_text_message(f"Failed to extract: {msg}")
                return

            app_id = (tool_parameters.get("app_id") or "").strip()
            if not app_id:
                msg = "app_id is required for memory isolation"
                yield self.create_json_message(
                    {"status": "ERROR", "messages": msg, "results": []}
                )
                yield self.create_text_message(f"Failed to extract: {msg}")
                return

            dify_base_url = (tool_parameters.get("dify_base_url") or "").strip()
            if not dify_base_url:
                msg = "dify_base_url is required"
                yield self.create_json_message(
                    {"status": "ERROR", "messages": msg, "results": []}
                )
                yield self.create_text_message(f"Failed to extract: {msg}")
                return

            dify_api_key = (tool_parameters.get("dify_api_key") or "").strip()
            if not dify_api_key:
                msg = "dify_api_key is required"
                yield self.create_json_message(
                    {"status": "ERROR", "messages": msg, "results": []}
                )
                yield self.create_text_message(f"Failed to extract: {msg}")
                return

            conversations_limit = tool_parameters.get("conversations_limit")
            max_tokens_per_conversation = tool_parameters.get("max_tokens_per_conversation")

            try:
                # Parse and validate conversations_limit (10-500, default 50)
                # NOTE:
                # - We intentionally use the already-imported constant from `utils.constants`
                #   to avoid hard dependency on the top-level package name
                #   (e.g. `mem0_dify_plugin`) which may not exist in Dify's runtime.
                max_convs = (
                    int(conversations_limit)
                    if conversations_limit is not None
                    else EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT
                )
                # Clamp to valid range: 10-500
                max_convs = max(10, min(500, max_convs))
                logger.info(
                    f"Max conversations per user: {max_convs} "
                    f"(from {'config' if conversations_limit is not None else 'default constant'})"
                )
            except (TypeError, ValueError):
                max_convs = EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT
                logger.warning(
                    f"Invalid conversations_limit value, "
                    f"using default: {EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT}"
                )

            try:
                # Priority: user-provided value > YAML default > constant default
                # Note: If YAML has default, Dify will populate tool_parameters with it
                # so max_tokens_per_conversation will not be None if YAML default exists.
                # Parameter and EXTRACTION_DEFAULT_MAX_TOKENS are both in thousands (K),
                # convert to actual token count here.
                max_tokens_k = (
                    int(max_tokens_per_conversation)
                    if max_tokens_per_conversation is not None
                    else EXTRACTION_DEFAULT_MAX_TOKENS
                )
                # Allow range: 1K to 200K tokens (support various model context windows)
                max_tokens_k = max(1, min(200, max_tokens_k))
                # Convert from K to actual token count
                max_tokens = max_tokens_k * 1000

                # Log source for debugging (YAML default vs constant fallback)
                source = "constant fallback"
                if max_tokens_per_conversation is not None:
                    # Check if it matches YAML default (64K) or is a custom value
                    if max_tokens_k == 64:
                        source = "YAML default"
                    else:
                        source = "user-provided"
                logger.info(
                    "Token limit per conversation: %dK (%d tokens) (from %s)",
                    max_tokens_k,
                    max_tokens,
                    source,
                )
            except (TypeError, ValueError):
                max_tokens_k = EXTRACTION_DEFAULT_MAX_TOKENS
                max_tokens = max_tokens_k * 1000
                logger.warning(
                    f"Invalid max_tokens_per_conversation value, "
                    f"using constant fallback: {max_tokens_k}K ({max_tokens} tokens)"
                )

            user_ids = _dedup_keep_order(user_ids)

            # Generate task_id and run_id
            task_id = f"extract_{uuid.uuid4().hex[:12]}"
            run_id = (tool_parameters.get("run_id") or "").strip()
            if not run_id:
                run_id = task_id
            logger.info(f"Starting extraction task: task_id={task_id}, run_id={run_id}")

            # Create Memory instances (shared across foreground and background)
            base_cfg = build_local_mem0_config(self.runtime.credentials)
            base_mem = Memory.from_config(base_cfg)
            subtype_mems = build_subtype_memories(self.runtime.credentials)

            # Create initial task status
            task_status = ExtractionTaskStatus(
                task_id=task_id,
                run_id=run_id,
                status="running",
                started_at=datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
                progress=0.0,
                user_count=len(user_ids),
                processed_users=0,
                skipped_users=0,
                scanned_conversations=0,
                scanned_messages=0,
                written_memories={"semantic": 0, "episodic": 0, "procedural": 0},
            )

            # Save initial task status
            save_task_status(base_mem, task_status=task_status)

            # Submit to background event loop (reuse existing infrastructure)
            async def _bg_task_async() -> None:
                """Background task execution in shared event loop.
                
                This coroutine runs in the shared background event loop managed by
                BackgroundEventLoop, reusing the same infrastructure as add_memory
                and other async tools.
                """
                try:
                    logger.info(
                        "Background extraction task %s started in event loop (run_id=%s)",
                        task_id,
                        run_id,
                    )
                    report = await _execute_extraction_async(
                        base_mem=base_mem,
                        subtype_mems=subtype_mems,
                        task_id=task_id,
                        run_id=run_id,
                        user_ids=user_ids,
                        app_id=app_id,
                        start_time=start_time,
                        end_time=end_time,
                        dify_base_url=dify_base_url,
                        dify_api_key=dify_api_key,
                        max_conversations=max_convs,
                        max_tokens_per_conversation=max_tokens,
                    )
                    # Mark task as completed
                    await asyncio.to_thread(
                        mark_task_completed,
                        base_mem,
                        task_id=task_id,
                        final_report=report,
                    )
                    logger.info(
                        "Background extraction task %s completed: status=%s, "
                        "processed_users=%d (run_id=%s)",
                        task_id,
                        report.get("status"),
                        report.get("summary", {}).get("processed_users", 0),
                        run_id,
                    )
                except Exception as bg_error:
                    logger.exception(
                        "Background extraction task %s failed (run_id=%s)",
                        task_id,
                        run_id,
                    )
                    await asyncio.to_thread(
                        mark_task_failed,
                        base_mem,
                        task_id=task_id,
                        error=str(bg_error),
                    )

            # Get shared background event loop (same as add_memory, etc.)
            loop = BackgroundEventLoop.ensure_loop()
            
            # Submit coroutine to background loop and track it
            future = asyncio.run_coroutine_threadsafe(_bg_task_async(), loop)
            TaskTracker.track_bg_task(
                future,
                f"extract_long_term_memory(task_id={task_id}, users={len(user_ids)})",
            )

            logger.info(
                "Extraction task %s submitted to background event loop "
                "(users=%d, max_concurrent=%d, run_id=%s)",
                task_id,
                len(user_ids),
                EXTRACTION_MAX_CONCURRENT_USERS,
                run_id,
            )

            # Immediately return ACCEPTED status
            yield self.create_json_message(
                {
                    "status": "ACCEPTED",
                    "task_id": task_id,
                    "run_id": run_id,
                    "message": (
                        "Extraction task has been accepted and is running in background. "
                        "Use check_extraction_status tool to query progress."
                    ),
                    "user_count": len(user_ids),
                    "start_time": start_time,
                    "end_time": end_time,
                }
            )
            yield self.create_text_message(
                f"Extraction task accepted: task_id={task_id}, "
                f"processing {len(user_ids)} user(s). "
                f"Use check_extraction_status tool to monitor progress."
            )

        except Exception as e:
            logger.exception("Extract long-term memory failed")
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []},
            )
            yield self.create_text_message(f"Failed to extract: {error_message}")

