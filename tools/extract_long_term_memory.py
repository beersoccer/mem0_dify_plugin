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
import logging
import math
import threading
import time
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from dify_plugin import Tool

from utils.background_loop import BackgroundEventLoop
from utils.checkpoint import AsyncCheckpointManager, SyncCheckpointManager
from utils.config_builder import is_async_mode
from utils.constants import (
    EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT,
    EXTRACTION_DEFAULT_MAX_TOKENS,
    EXTRACTION_DIFY_TIMEOUT,
    EXTRACTION_MAX_CONCURRENT_USERS,
    EXTRACTION_TIME_BUDGET,
    MAX_CONCURRENT_MEMORY_OPERATIONS,
    MAX_PENDING_TASKS_MULTIPLIER,
    WRITE_OPERATION_TIMEOUT,
)
from utils.dify_client import DifyAPIError, DifyClient
from utils.distributed_lock import AsyncLockManager, SyncLockManager
from utils.extraction import UserCheckpoint, scan_user_conversations_incremental
from utils.extraction_helpers import (
    count_message_tokens,
    get_last_message_checkpoint,
    get_time_range_from_days,
    update_conv_checkpoint,
)
from utils.helpers import _parse_user_ids, dedup_keep_order
from utils.helpers import parse_positive_int
from utils.logger import get_logger
from utils.mem0_client import (
    AsyncMem0Client,
    SyncMem0Client,
)
from utils.mem0_extraction import (
    AsyncMemoryClassificationManager,
    AsyncMemoryWriter,
    SyncMemoryClassificationManager,
    SyncMemoryWriter,
    build_memory_metadata,
    build_subtype_async_clients,
    build_subtype_sync_clients,
)
from utils.message_utils import (
    count_add_event_stats,
    count_add_results,
    dify_msg_to_mem0_messages,
)
from utils.task_status import (
    AsyncTaskStatusManager,
    ExtractionTaskStatus,
    SyncTaskStatusManager,
)
from utils.task_tracker import TaskTracker

if TYPE_CHECKING:
    from collections.abc import Generator

    from dify_plugin.entities.tool import ToolInvokeMessage

logger = get_logger(__name__)


# Message conversion functions moved to utils/message_utils.py for better testability
# Token counting and truncation functions moved to utils/extraction_helpers.py
# Time range and timestamp comparison functions moved to utils/extraction_helpers.py




def _process_single_user_sync(
    base_client: SyncMem0Client,
    subtype_clients: dict[str, SyncMem0Client],
    user_id: str,
    app_id: str,
    run_id: str,
    start_time: str,
    end_time: str,
    dify: DifyClient,
    lock_manager: SyncLockManager,
    max_conversations: int,
    max_tokens_per_conversation: int,
    lock_ttl_sec: int,
) -> dict[str, Any]:
    """Process a single user's conversations (sync version using SyncMem0Client).
    
    This function uses SyncMem0Client, consistent with other tools like add_memory,
    search_memory, etc. All operations are synchronous and block until completion.
    
    Args:
        base_client: SyncMem0Client for checkpoints
        subtype_clients: Dictionary of subtype-specific SyncMem0Client instances
        user_id: User ID to process
        app_id: Application ID
        run_id: Run identifier for lock management
        start_time: ISO8601 start time
        end_time: ISO8601 end time
        dify: Dify API client
        lock_manager: Lock manager instance
        max_conversations: Maximum conversations to process (prevents abuse)
        max_tokens_per_conversation: Maximum tokens per conversation for processing
        lock_ttl_sec: Lock TTL in seconds (calculated as 1.2 * time_budget, rounded up)
        
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
        ttl_seconds=lock_ttl_sec,
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
        # Load checkpoint (use base_client.memory)
        base_mem = base_client.memory
        logger.info("[run:%s] Processing user %s: loading checkpoint", run_id, user_id)
        checkpoint_mgr = SyncCheckpointManager(base_mem)
        cp_id, cp = checkpoint_mgr.load(user_id=user_id, app_id=app_id)
        if cp is None:
            cp = UserCheckpoint()
            logger.debug("[run:%s] No existing checkpoint for user %s", run_id, user_id)

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

            if not conversation_messages:
                continue

            last_processed_id, last_processed_created_at = get_last_message_checkpoint(
                conversation_messages
            )

            # Log conversation processing details only if debug level is enabled
            if logger.isEnabledFor(logging.DEBUG):
                total_tokens = count_message_tokens(conversation_messages)
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
                update_conv_checkpoint(
                    conv_cp,
                    last_processed_id=last_processed_id,
                    last_processed_created_at=last_processed_created_at,
                    start_time=start_time,
                )
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
            semantic_client = subtype_clients["semantic"]
            classification_mgr = SyncMemoryClassificationManager(semantic_client.memory)
            classified_type, should_extract = classification_mgr.classify(
                messages=mem0_msgs,
                context={
                    "user_id": user_id,
                    "conversation_id": conv_id,
                    "message_id_range": message_id_range,
                },
            )
            
            # Skip if no significant content, classification failed, or not worth extracting
            if classified_type is None or not should_extract:
                # Still update checkpoint to avoid reprocessing
                update_conv_checkpoint(
                    conv_cp,
                    last_processed_id=last_processed_id,
                    last_processed_created_at=last_processed_created_at,
                    start_time=start_time,
                )
                continue

            # STEP 2: Extract memory using only the classified type
            md = build_memory_metadata(
                subtype=classified_type,
                memory_origin="implicit",
            )
            
            try:
                subtype_client = subtype_clients[classified_type]
                writer = SyncMemoryWriter(subtype_client)
                res = writer.add_memory(
                    messages=mem0_msgs,
                    user_id=user_id,
                    agent_id=app_id,
                    metadata=md,
                )
                event_stats = count_add_event_stats(res)
                logger.info(
                    "[run:%s] Mem0 add events (sync): %s",
                    run_id,
                    event_stats,
                )
                c = count_add_results(res)
                if c == 0:
                    logger.warning(
                        "[run:%s] Memory classification approved but no memories created. "
                        "Type: %s, Conversation: %s. "
                        "Mem0 events: %s.",
                        run_id,
                        classified_type,
                        conv_id,
                        event_stats,
                    )
                    user_report.setdefault("warnings", []).append({
                        "type": f"mem0_{classified_type}_empty_result",
                        "conversation_id": conv_id,
                        "message": "Classification approved but no memories created",
                    })
                else:
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
                    "[run:%s] Failed to write %s memory for conversation %s: %s",
                    run_id,
                    classified_type,
                    conv_id,
                    e,
                )
                user_report["errors"].append({
                    "type": f"mem0_{classified_type}_error",
                    "conversation_id": conv_id,
                    "message": str(e),
                })

            # Update conversation checkpoint
            update_conv_checkpoint(
                conv_cp,
                last_processed_id=last_processed_id,
                last_processed_created_at=last_processed_created_at,
                start_time=start_time,
            )

        if stop_reason == "max_conversations_reached" and stats.resume_conversation_cursor:
            cp.resume_conversation_cursor = stats.resume_conversation_cursor
            cp.resume_run_at = end_time
            cp.resume_start_time = start_time
        else:
            cp.resume_conversation_cursor = None
            cp.resume_run_at = None
            cp.resume_start_time = None

        try:
            checkpoint_mgr = SyncCheckpointManager(base_mem)
            ok, new_id = checkpoint_mgr.save_atomic(
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
            and not e.get("type", "").endswith("_empty_result")
        ]
        if mem0_errors and user_report["status"] == "SUCCESS":
            user_report["status"] = "PARTIAL_SUCCESS"

        return user_report

    finally:
        # Always release lock
        lock_manager.release_lock(user_id, app_id, run_id)


async def _process_single_user_async(
    base_client: AsyncMem0Client,
    subtype_clients: dict[str, AsyncMem0Client],
    user_id: str,
    app_id: str,
    run_id: str,
    start_time: str,
    end_time: str,
    dify: DifyClient,
    lock_manager: AsyncLockManager,
    max_conversations: int,
    max_tokens_per_conversation: int,
    lock_ttl_sec: int,
) -> dict[str, Any]:
    """Process a single user's conversations (async version).
    
    This is the async version using AsyncMem0Client, providing:
    - Automatic timeout protection
    - Queue overload checking
    - Semaphore-controlled concurrency
    - Explicit resource management
    
    Args:
        base_client: AsyncMem0Client for checkpoints
        subtype_clients: Dictionary of subtype-specific AsyncMem0Client instances
        user_id: User ID to process
        app_id: Application ID
        run_id: Run identifier for lock management
        start_time: ISO8601 start time
        end_time: ISO8601 end time
        dify: Dify API client
        lock_manager: Lock manager instance
        max_conversations: Maximum conversations to process (prevents abuse)
        max_tokens_per_conversation: Maximum tokens per conversation for processing
        lock_ttl_sec: Lock TTL in seconds (calculated as 1.2 * time_budget, rounded up)
        
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
    lock_acquired, existing_lock = await lock_manager.acquire_lock(
        user_id=user_id,
        app_id=app_id,
        holder_id=run_id,
        ttl_seconds=lock_ttl_sec,
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
        # Ensure base client is initialized
        await base_client.create()
        base_mem = base_client.memory
        
        # Load checkpoint (async version)
        logger.info("[run:%s] Processing user %s: loading checkpoint", run_id, user_id)
        checkpoint_mgr = AsyncCheckpointManager(base_mem)
        cp_id, cp = await checkpoint_mgr.load(user_id=user_id, app_id=app_id)
        if cp is None:
            cp = UserCheckpoint()
            logger.debug("[run:%s] No existing checkpoint for user %s", run_id, user_id)

        # Process user
        logger.info(
            "[run:%s] Scanning conversations for user %s (time_range: %s to %s)",
            run_id,
            user_id,
            start_time,
            end_time,
        )
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
            logger.info(
                "[run:%s] Scanned %d conversations, %d messages for user %s",
                run_id,
                stats.scanned_conversations,
                stats.scanned_messages,
                user_id,
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
        for conv_id, conversation_messages in conversations_data.items():
            conv_cp = cp.get_conv(conv_id)

            if not conversation_messages:
                continue

            last_processed_id, last_processed_created_at = get_last_message_checkpoint(
                conversation_messages
            )

            # Log conversation processing details only if debug level is enabled
            if logger.isEnabledFor(logging.DEBUG):
                total_tokens = count_message_tokens(conversation_messages)
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
                update_conv_checkpoint(
                    conv_cp,
                    last_processed_id=last_processed_id,
                    last_processed_created_at=last_processed_created_at,
                    start_time=start_time,
                )
                continue

            # Build message ID range for metadata
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

            # STEP 1: Classify conversation (async)
            semantic_client = subtype_clients["semantic"]
            await semantic_client.create()
            classification_mgr = AsyncMemoryClassificationManager(semantic_client.memory)
            classified_type, should_extract = await classification_mgr.classify(
                messages=mem0_msgs,
                context={
                    "user_id": user_id,
                    "conversation_id": conv_id,
                    "message_id_range": message_id_range,
                },
            )
            
            # Skip if no significant content, classification failed, or not worth extracting
            if classified_type is None or not should_extract:
                # Still update checkpoint to avoid reprocessing
                update_conv_checkpoint(
                    conv_cp,
                    last_processed_id=last_processed_id,
                    last_processed_created_at=last_processed_created_at,
                    start_time=start_time,
                )
                continue

            logger.debug(
                "[run:%s] Conversation %s classified as %s memory and approved for extraction",
                run_id,
                conv_id,
                classified_type,
            )

            # STEP 2: Extract memory using only the classified type (async)
            md = build_memory_metadata(
                subtype=classified_type,
                memory_origin="implicit",
            )
            
            try:
                subtype_client = subtype_clients[classified_type]
                writer = AsyncMemoryWriter(subtype_client)
                res = await writer.add_memory(
                    messages=mem0_msgs,
                    user_id=user_id,
                    agent_id=app_id,
                    metadata=md,
                    timeout_s=WRITE_OPERATION_TIMEOUT,
                )
                event_stats = count_add_event_stats(res)
                logger.info(
                    "[run:%s] Mem0 add events (async): %s",
                    run_id,
                    event_stats,
                )
                c = count_add_results(res)
                if c == 0:
                    logger.warning(
                        "[run:%s] Memory classification approved but no memories created. "
                        "Type: %s, Conversation: %s. "
                        "Mem0 events: %s.",
                        run_id,
                        classified_type,
                        conv_id,
                        event_stats,
                    )
                    user_report.setdefault("warnings", []).append({
                        "type": f"mem0_{classified_type}_empty_result",
                        "conversation_id": conv_id,
                        "message": "Classification approved but no memories created",
                    })
                else:
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
                    "[run:%s] Failed to write %s memory for conversation %s: %s",
                    run_id,
                    classified_type,
                    conv_id,
                    e,
                )
                user_report["errors"].append({
                    "type": f"mem0_{classified_type}_error",
                    "conversation_id": conv_id,
                    "message": str(e),
                })

            # Update conversation checkpoint
            update_conv_checkpoint(
                conv_cp,
                last_processed_id=last_processed_id,
                last_processed_created_at=last_processed_created_at,
                start_time=start_time,
            )

        if stop_reason == "max_conversations_reached" and stats.resume_conversation_cursor:
            cp.resume_conversation_cursor = stats.resume_conversation_cursor
            cp.resume_run_at = end_time
            cp.resume_start_time = start_time
        else:
            cp.resume_conversation_cursor = None
            cp.resume_run_at = None
            cp.resume_start_time = None

        try:
            checkpoint_mgr = AsyncCheckpointManager(base_mem)
            ok, new_id = await checkpoint_mgr.save_atomic(
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
            and not e.get("type", "").endswith("_empty_result")
        ]
        if mem0_errors and user_report["status"] == "SUCCESS":
            user_report["status"] = "PARTIAL_SUCCESS"

        return user_report

    finally:
        # Always release lock
        await lock_manager.release_lock(user_id, app_id, run_id)


async def _execute_extraction_async(
    base_client: AsyncMem0Client,
    subtype_clients: dict[str, AsyncMem0Client],
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
    time_budget_sec: int,
) -> dict[str, Any]:
    """Execute extraction task in background event loop (async version).

    This function uses AsyncMem0Client for:
    - Automatic timeout protection
    - Queue overload checking
    - Semaphore-controlled concurrency
    - Explicit resource management

    Args:
        base_client: AsyncMem0Client for checkpoints and task status
        subtype_clients: Dictionary of subtype-specific AsyncMem0Client instances
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
        time_budget_sec: Time budget in seconds (lock TTL = 1.2 * time_budget, rounded up)

    Returns:
        Final extraction report dict
    """
    try:
        # Ensure base client is initialized
        await base_client.create()
        base_mem = base_client.memory
        
        # Create shared resources (thread-safe)
        dify = DifyClient(dify_base_url, dify_api_key, timeout=EXTRACTION_DIFY_TIMEOUT)
        lock_manager = AsyncLockManager(base_mem)

        started_at = time.monotonic()
        hard_time_budget_sec = float(time_budget_sec)
        # Calculate lock TTL as 1.2 times time budget, rounded up to integer
        lock_ttl_sec = math.ceil(time_budget_sec * 1.2)

        per_user: list[dict[str, Any]] = []

        summary = {
            "processed_users": 0,
            "skipped_users": 0,
            "scanned_conversations": 0,
            "scanned_messages": 0,
            "processed_conversations": 0,
            "processed_messages": 0,
            "written_memories": {"semantic": 0, "episodic": 0, "procedural": 0},
        }

        overall_status = "SUCCESS"

        # Semaphore to limit concurrent user processing
        semaphore = asyncio.Semaphore(EXTRACTION_MAX_CONCURRENT_USERS)

        async def process_user_with_semaphore(user_id: str) -> dict[str, Any]:
            """Process user with concurrency control (async)."""
            async with semaphore:
                return await _process_single_user_async(
                    base_client,
                    subtype_clients,
                    user_id,
                    app_id,
                    run_id,
                    start_time,
                    end_time,
                    dify,
                    lock_manager,
                    max_conversations,
                    max_tokens_per_conversation,
                    lock_ttl_sec,
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
                    logger.exception(
                        "[run:%s] Error processing user %s: %s",
                        run_id,
                        user_id,
                        result,
                    )
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
                        summary["processed_conversations"] += result.get(
                            "conversations_with_messages", 0
                        )
                        summary["processed_messages"] += result.get(
                            "messages_in_time_range", 0
                        )
                        for mem_type in ["semantic", "episodic", "procedural"]:
                            summary["written_memories"][mem_type] += result.get(
                                "written_memories", {}
                            ).get(mem_type, 0)
                    elif result["status"] == "PARTIAL_SUCCESS":
                        # PARTIAL_SUCCESS also counts as processed
                        # (user was processed but with some errors)
                        summary["processed_users"] += 1
                        summary["scanned_conversations"] += result.get("scanned_conversations", 0)
                        summary["scanned_messages"] += result.get("scanned_messages", 0)
                        summary["processed_conversations"] += result.get(
                            "conversations_with_messages", 0
                        )
                        summary["processed_messages"] += result.get(
                            "messages_in_time_range", 0
                        )
                        for mem_type in ["semantic", "episodic", "procedural"]:
                            summary["written_memories"][mem_type] += result.get(
                                "written_memories", {}
                            ).get(mem_type, 0)
                        overall_status = "PARTIAL_SUCCESS"
                    elif result.get("skipped"):
                        summary["skipped_users"] += 1
                    else:
                        overall_status = "PARTIAL_SUCCESS"
            
            # Update progress after each batch
            task_status_mgr = AsyncTaskStatusManager(base_mem)
            await task_status_mgr.update_progress(
                task_id=task_id,
                processed_users=summary["processed_users"] + summary["skipped_users"],
                total_users=len(user_ids),
                scanned_conversations=summary["scanned_conversations"],
                scanned_messages=summary["scanned_messages"],
                processed_conversations=summary["processed_conversations"],
                processed_messages=summary["processed_messages"],
                written_memories=summary["written_memories"],
            )
            logger.info(
                "[run:%s] Batch progress: processed=%d/%d users, "
                "conversations=%d, messages=%d, memories=%d",
                run_id,
                summary["processed_users"] + summary["skipped_users"],
                len(user_ids),
                summary["scanned_conversations"],
                summary["scanned_messages"],
                sum(summary["written_memories"].values()),
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
            "[run:%s] Extraction task %s completed: status=%s, processed=%d/%d users",
            run_id,
            task_id,
            overall_status,
            summary["processed_users"],
            len(user_ids),
        )

        return report
    except Exception:
        logger.exception("[run:%s] Extraction task %s failed", run_id, task_id)
        raise
    finally:
        # Resource cleanup is now handled by the caller
        # (clients are created specifically for this task and will be closed after execution)
        pass


def _execute_extraction_sync(
    base_client: SyncMem0Client,
    subtype_clients: dict[str, SyncMem0Client],
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
    time_budget_sec: int,
) -> dict[str, Any]:
    """Execute extraction task using SyncMem0Client (fully synchronous).
    
    This function uses SyncMem0Client, consistent with other tools. All operations
    are synchronous and block until completion. Used when async_mode=false.
    
    Note: Sync mode has no timeout protection and is only recommended for
    small-scale testing (<10 users). Production environments should use async_mode=true.
    
    Args:
        base_client: SyncMem0Client for checkpoints and task status
        subtype_clients: Dictionary of subtype-specific SyncMem0Client instances
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
        time_budget_sec: Time budget in seconds (lock TTL = 1.2 * time_budget, rounded up)

    Returns:
        Final extraction report dict
    """
    try:
        base_mem = base_client.memory
        
        # Create shared resources (thread-safe)
        dify = DifyClient(dify_base_url, dify_api_key, timeout=EXTRACTION_DIFY_TIMEOUT)
        lock_manager = SyncLockManager(base_mem)

        started_at = time.monotonic()
        hard_time_budget_sec = float(time_budget_sec)
        # Calculate lock TTL as 1.2 times time budget, rounded up to integer
        lock_ttl_sec = math.ceil(time_budget_sec * 1.2)

        logger.info(
            "[run:%s] Starting extraction execution: %d users, time_budget=%ds, lock_ttl=%ds",
            run_id,
            len(user_ids),
            time_budget_sec,
            lock_ttl_sec,
        )

        per_user: list[dict[str, Any]] = []

        summary = {
            "processed_users": 0,
            "skipped_users": 0,
            "scanned_conversations": 0,
            "scanned_messages": 0,
            "processed_conversations": 0,
            "processed_messages": 0,
            "written_memories": {"semantic": 0, "episodic": 0, "procedural": 0},
        }

        overall_status = "SUCCESS"

        # Process users sequentially (sync mode - simple and straightforward)
        # For sync mode with <10 users, sequential processing is acceptable
        for user_id in user_ids:
            # Check time budget
            if (time.monotonic() - started_at) >= hard_time_budget_sec:
                logger.warning(
                    "[run:%s] Time budget exceeded, skipping remaining %d users",
                    run_id,
                    len(user_ids) - len(per_user),
                )
                for uid in user_ids[len(per_user):]:
                    overall_status = "PARTIAL_SUCCESS"
                    per_user.append(
                        {
                            "user_id": uid,
                            "status": "SKIPPED",
                            "reason": "time_budget_exceeded",
                        },
                    )
                    summary["skipped_users"] += 1
                break
            
            # Process user synchronously
            try:
                result = _process_single_user_sync(
                    base_client,
                    subtype_clients,
                    user_id,
                    app_id,
                    run_id,
                    start_time,
                    end_time,
                    dify,
                    lock_manager,
                    max_conversations,
                    max_tokens_per_conversation,
                    lock_ttl_sec,
                )
                per_user.append(result)
                
                if result["status"] == "SUCCESS":
                    summary["processed_users"] += 1
                    summary["scanned_conversations"] += result.get("scanned_conversations", 0)
                    summary["scanned_messages"] += result.get("scanned_messages", 0)
                    summary["processed_conversations"] += result.get(
                        "conversations_with_messages", 0
                    )
                    summary["processed_messages"] += result.get(
                        "messages_in_time_range", 0
                    )
                    for mem_type in ["semantic", "episodic", "procedural"]:
                        summary["written_memories"][mem_type] += result.get(
                            "written_memories", {}
                        ).get(mem_type, 0)
                elif result["status"] == "PARTIAL_SUCCESS":
                    summary["processed_users"] += 1
                    summary["scanned_conversations"] += result.get("scanned_conversations", 0)
                    summary["scanned_messages"] += result.get("scanned_messages", 0)
                    summary["processed_conversations"] += result.get(
                        "conversations_with_messages", 0
                    )
                    summary["processed_messages"] += result.get(
                        "messages_in_time_range", 0
                    )
                    for mem_type in ["semantic", "episodic", "procedural"]:
                        summary["written_memories"][mem_type] += result.get(
                            "written_memories", {}
                        ).get(mem_type, 0)
                    overall_status = "PARTIAL_SUCCESS"
                elif result.get("skipped"):
                    summary["skipped_users"] += 1
                else:
                    overall_status = "PARTIAL_SUCCESS"
            except Exception as e:
                logger.exception(
                    "[run:%s] Error processing user %s: %s",
                    run_id,
                    user_id,
                    e,
                )
                per_user.append({
                    "user_id": user_id,
                    "status": "ERROR",
                    "errors": [{"type": type(e).__name__, "message": str(e)}],
                })
                overall_status = "PARTIAL_SUCCESS"
            
            # Update progress after each user
            task_status_mgr = SyncTaskStatusManager(base_mem)
            task_status_mgr.update_progress(
                task_id=task_id,
                processed_users=summary["processed_users"] + summary["skipped_users"],
                total_users=len(user_ids),
                scanned_conversations=summary["scanned_conversations"],
                scanned_messages=summary["scanned_messages"],
                processed_conversations=summary["processed_conversations"],
                processed_messages=summary["processed_messages"],
                written_memories=summary["written_memories"],
            )
            logger.info(
                "[run:%s] Progress: processed=%d/%d users, "
                "conversations=%d, messages=%d, memories=%d",
                run_id,
                summary["processed_users"] + summary["skipped_users"],
                len(user_ids),
                summary["scanned_conversations"],
                summary["scanned_messages"],
                sum(summary["written_memories"].values()),
            )

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
            "[run:%s] Extraction task %s completed: status=%s, processed=%d/%d users",
            run_id,
            task_id,
            overall_status,
            summary["processed_users"],
            len(user_ids),
        )

        return report
    except Exception:
        logger.exception("[run:%s] Extraction task %s failed", run_id, task_id)
        raise


class ExtractLongTermMemoryTool(Tool):
    """Incrementally scan Dify history for specified users and extract long-term memories.

    This tool supports both sync and async modes:
    - Immediately returns ACCEPTED status with task_id
    - Actual extraction runs in background (async: event loop, sync: thread)
    - Use check_extraction_status tool to query task progress

    Mode Selection:
    - Async Mode (async_mode=true, recommended): Uses AsyncMem0Client with automatic
      timeout protection, queue overload checking, and explicit resource management.
      Suitable for production and large-scale batch processing (10+ users).
    - Sync Mode (async_mode=false): Uses SyncMem0Client, consistent with other tools.
      Only recommended for testing with <10 users. No timeout protection.

    Design Notes:
    - Async mode: Uses BackgroundEventLoop (same infrastructure as add_memory, etc.)
    - Sync mode: Uses threading.Thread for background execution (fully synchronous)
    - Both modes reuse SyncMem0Client/AsyncMem0Client mechanisms for consistency
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
                days_back_int = int(days_back) if days_back is not None else 1
                days_back_int = max(1, min(7, days_back_int))
            except (TypeError, ValueError):
                days_back_int = 1

            start_time, end_time = get_time_range_from_days(days_back_int)

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
                # Parse and validate conversations_limit (10-500, default 20)
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
            except (TypeError, ValueError):
                max_convs = EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT
                logger.warning(
                    "Invalid conversations_limit value, using default: %d",
                    EXTRACTION_DEFAULT_CONVERSATIONS_LIMIT,
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
            except (TypeError, ValueError):
                max_tokens_k = EXTRACTION_DEFAULT_MAX_TOKENS
                max_tokens = max_tokens_k * 1000
                logger.warning(
                    "Invalid max_tokens_per_conversation value, using default: %dK",
                    max_tokens_k,
                )

            # Parse time_budget parameter (user input in minutes, convert to seconds immediately)
            time_budget_param = tool_parameters.get("time_budget")
            try:
                # Priority: user-provided value > YAML default > constant default
                # User input is in minutes, convert to seconds immediately for internal use
                if time_budget_param is not None:
                    time_budget_min = float(time_budget_param)
                    # Minimum: 5 minutes (suggested lower bound)
                    # No upper limit enforced - allow users to set larger values if needed
                    time_budget_min = max(5.0, time_budget_min)
                    time_budget_sec = int(time_budget_min * 60)
                else:
                    # Use constant default (already in seconds)
                    time_budget_sec = EXTRACTION_TIME_BUDGET
            except (TypeError, ValueError):
                time_budget_sec = EXTRACTION_TIME_BUDGET
                logger.warning(
                    "Invalid time_budget value, using default: %d seconds",
                    time_budget_sec,
                )

            user_ids = dedup_keep_order(user_ids)

            # Check user count for sync mode warning
            async_mode = is_async_mode(self.runtime.credentials)
            if not async_mode and len(user_ids) >= 10:
                logger.warning(
                    "Sync mode with %d users "
                    "(recommended: <10 for testing, use async_mode=true for production)",
                    len(user_ids),
                )

            # Generate task_id and run_id
            task_id = f"extract_{uuid.uuid4().hex[:12]}"
            run_id = (tool_parameters.get("run_id") or "").strip()
            if not run_id:
                run_id = task_id
            logger.info(
                "Starting extraction task: task_id=%s, run_id=%s, mode=%s, users=%d",
                task_id,
                run_id,
                "async" if async_mode else "sync",
                len(user_ids),
            )

            task_status = ExtractionTaskStatus(
                task_id=task_id,
                run_id=run_id,
                status="running",

                started_at=datetime.now().astimezone().isoformat(),
                updated_at=datetime.now().astimezone().isoformat(),
                progress=0.0,
                user_count=len(user_ids),
                processed_users=0,
                skipped_users=0,
                scanned_conversations=0,
                scanned_messages=0,
                written_memories={"semantic": 0, "episodic": 0, "procedural": 0},
                range_start=start_time,
                range_end=end_time,
            )

            if async_mode:
                async def _bg_task_async() -> None:
                    base_client = None
                    subtype_clients = None
                    task_status_mgr = None
                    
                    try:
                        from utils.config_builder import (
                            build_local_mem0_config_without_pool,
                        )

                        base_client = AsyncMem0Client(
                            self.runtime.credentials, enable_keepalive=False
                        )
                        base_client.config = build_local_mem0_config_without_pool(
                            self.runtime.credentials
                        )
                        await base_client.create()
                        
                        subtype_clients = await build_subtype_async_clients(
                            self.runtime.credentials,
                            base_client=base_client,
                        )
                        
                        task_status_mgr = AsyncTaskStatusManager(base_client.memory)
                        await task_status_mgr.save(task_status=task_status)
                        
                        report = await _execute_extraction_async(
                            base_client=base_client,
                            subtype_clients=subtype_clients,
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
                            time_budget_sec=time_budget_sec,
                        )
                        task_status_mgr = AsyncTaskStatusManager(base_client.memory)
                        await task_status_mgr.mark_completed(
                            task_id=task_id,
                            final_report=report,
                        )
                    except Exception as bg_error:
                        logger.exception(
                            "Background extraction task %s failed (mode=async, run_id=%s)",
                            task_id,
                            run_id,
                        )
                        # Try to mark task as failed (best effort, only if clients are ready)
                        if base_client is not None and base_client.memory is not None:
                            try:
                                if task_status_mgr is None:
                                    task_status_mgr = AsyncTaskStatusManager(base_client.memory)
                                await task_status_mgr.mark_failed(
                                    task_id=task_id,
                                    error=str(bg_error),
                                )
                            except Exception:
                                logger.exception(
                                    "Failed to mark task as failed using existing client"
                                )
                    finally:
                        # Clean up subtype clients first (they share base_client's connection pool)
                        if subtype_clients is not None:
                            for subtype_client in subtype_clients.values():
                                try:
                                    await subtype_client.aclose()
                                except Exception:
                                    logger.exception(
                                        "Error closing subtype client for task %s",
                                        task_id,
                                    )
                        
                        # Clean up base client (closes shared connection pool)
                        if base_client is not None:
                            try:
                                await base_client.aclose()
                            except Exception:
                                logger.exception(
                                    "Error closing base client for task %s",
                                    task_id,
                                )
                        
                        logger.info(
                            "Extraction task %s resources cleaned up (mode=async)",
                            task_id,
                        )

                # Get shared background event loop
                # Pre-enqueue overload guard (early reject) - avoid starting a heavy background job
                # when the plugin daemon is already saturated.
                pending = TaskTracker.get_pending_tasks_count()
                max_ops = parse_positive_int(
                    self.runtime.credentials.get("max_concurrent_memory_operations"),
                    MAX_CONCURRENT_MEMORY_OPERATIONS,
                    logger=logger,
                    config_name="max_concurrent_memory_operations",
                )
                max_pending = max_ops * MAX_PENDING_TASKS_MULTIPLIER
                if pending > max_pending:
                    logger.warning(
                        "Extraction task rejected before enqueue: queue overloaded "
                        "(pending=%d, max=%d, users=%d, run_id=%s)",
                        pending,
                        max_pending,
                        len(user_ids),
                        run_id,
                    )
                    yield self.create_json_message(
                        {
                            "status": "OVERLOAD",
                            "message": (
                                f"Queue overloaded: {pending} pending tasks "
                                f"(max: {max_pending}). Please retry later."
                            ),
                            "user_count": len(user_ids),
                            "mode": "async",
                        }
                    )
                    yield self.create_text_message(
                        "System overloaded, extraction task was not enqueued. Please retry later."
                    )
                    return

                loop = BackgroundEventLoop.ensure_loop()
                
                # Submit coroutine to background loop and track it
                future = asyncio.run_coroutine_threadsafe(_bg_task_async(), loop)
                TaskTracker.track_bg_task(
                    future,
                    f"extract_long_term_memory(task_id={task_id}, users={len(user_ids)})",
                )
            else:
                def _bg_task_sync() -> None:
                    base_client = None
                    subtype_clients = None
                    task_status_mgr = None
                    
                    try:
                        # Create base_client with independent connection pool
                        # Use build_local_mem0_config_without_pool() to ensure we get
                        # a config without the cached connection pool, which will be
                        # recreated as a new independent pool
                        from mem0 import Memory

                        from utils.config_builder import (
                            build_local_mem0_config_without_pool,
                        )

                        config = build_local_mem0_config_without_pool(
                            self.runtime.credentials
                        )

                        # SyncMem0Client.__init__ creates Memory immediately, so we
                        # create it first, then replace with one using independent pool
                        base_client = SyncMem0Client(
                            self.runtime.credentials, enable_keepalive=False
                        )
                        base_client.memory = Memory.from_config(config)

                        subtype_clients = build_subtype_sync_clients(
                            self.runtime.credentials,
                            base_client=base_client,
                        )
                        
                        task_status_mgr = SyncTaskStatusManager(base_client.memory)
                        task_status_mgr.save(task_status=task_status)
                        
                        # Execute synchronously
                        report = _execute_extraction_sync(
                            base_client=base_client,
                            subtype_clients=subtype_clients,
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
                            time_budget_sec=time_budget_sec,
                        )
                        task_status_mgr = SyncTaskStatusManager(base_client.memory)
                        task_status_mgr.mark_completed(
                            task_id=task_id,
                            final_report=report,
                        )
                    except Exception as bg_error:
                        logger.exception(
                            "Background extraction task %s failed (mode=sync, run_id=%s)",
                            task_id,
                            run_id,
                        )
                        # Try to mark task as failed (best effort, only if clients are ready)
                        if base_client is not None and base_client.memory is not None:
                            try:
                                if task_status_mgr is None:
                                    task_status_mgr = SyncTaskStatusManager(base_client.memory)
                                task_status_mgr.mark_failed(
                                    task_id=task_id,
                                    error=str(bg_error),
                                )
                            except Exception:
                                logger.exception(
                                    "Failed to mark task as failed using existing client"
                                )
                    finally:
                        # Clean up subtype clients first (they share base_client's connection pool)
                        if subtype_clients is not None:
                            for subtype_client in subtype_clients.values():
                                try:
                                    subtype_client.close()
                                except Exception:
                                    logger.exception(
                                        "Error closing subtype client for task %s",
                                        task_id,
                                    )
                        
                        # Clean up base client (closes shared connection pool)
                        if base_client is not None:
                            try:
                                base_client.close()
                            except Exception:
                                logger.exception(
                                    "Error closing base client for task %s",
                                    task_id,
                                )
                        
                        logger.info(
                            "Extraction task %s resources cleaned up (mode=sync)",
                            task_id,
                        )

                # Start background thread (daemon=True so it doesn't block shutdown)
                thread = threading.Thread(
                    target=_bg_task_sync,
                    name=f"extract_long_term_memory_{task_id}",
                    daemon=True,
                )
                thread.start()

            logger.info(
                "Extraction task %s submitted (mode=%s, users=%d, max_concurrent=%d, run_id=%s)",
                task_id,
                "async" if async_mode else "sync",
                len(user_ids),
                EXTRACTION_MAX_CONCURRENT_USERS,
                run_id,
            )

            mode_note = ""
            if not async_mode:
                mode_note = (
                    " Note: Sync mode is active. This mode is only recommended for "
                    "testing with <10 users. For production environments, use async_mode=true."
                )
            
            yield self.create_json_message(
                {
                    "status": "ACCEPTED",
                    "task_id": task_id,
                    "run_id": run_id,
                    "message": (
                        "Extraction task has been accepted and is running in background. "
                        "Use check_extraction_status tool to query progress."
                        + mode_note
                    ),
                    "user_count": len(user_ids),
                    "start_time": start_time,
                    "end_time": end_time,
                    "mode": "async" if async_mode else "sync",
                }
            )
            yield self.create_text_message(
                f"Extraction task accepted: task_id={task_id}, "
                f"processing {len(user_ids)} user(s) in {'async' if async_mode else 'sync'} mode. "
                f"Use check_extraction_status tool to monitor progress."
                + (f"\n{mode_note}" if mode_note else "")
            )

        except Exception as e:
            logger.exception("Extract long-term memory failed")
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []},
            )
            yield self.create_text_message(f"Failed to extract: {error_message}")

