"""Checkpoint storage in Mem0 for Dify extraction runs (no external DB).

Checkpoint is stored as an internal Mem0 memory with metadata markers (SPEC.md):
- metadata.__internal = true
- metadata.internal_type = "checkpoint"
- metadata.checkpoint_key = "dify_extraction_v1"
- metadata.user_id = <user_id>
- metadata.app_id = <app_id or "*">

Enhanced with atomic save and rollback mechanism for robustness.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from typing import Any

from .extraction import ConversationCheckpoint, UserCheckpoint
from .logger import get_logger
from .mem0_client import Memory

logger = get_logger(__name__)
CHECKPOINT_KEY = "dify_extraction_v1"


def checkpoint_metadata(*, user_id: str, app_id: str | None) -> dict[str, Any]:
    return {
        "__internal": True,
        "internal_type": "checkpoint",
        "checkpoint_key": CHECKPOINT_KEY,
        "user_id": user_id,
        "app_id": app_id or "*",
    }


def checkpoint_filters(*, user_id: str, app_id: str | None) -> dict[str, Any]:
    md = checkpoint_metadata(user_id=user_id, app_id=app_id)
    # Mem0 filters operate on metadata keys directly in local mode.
    return {
        "AND": [
            {"__internal": {"eq": True}},
            {"internal_type": {"eq": md["internal_type"]}},
            {"checkpoint_key": {"eq": md["checkpoint_key"]}},
            {"user_id": {"eq": md["user_id"]}},
            {"app_id": {"eq": md["app_id"]}},
        ],
    }


def _extract_memory_text(obj: dict[str, Any]) -> str:
    return str(obj.get("memory") or obj.get("text") or obj.get("content") or "")


def load_checkpoint(
    mem: Memory,
    *,
    user_id: str,
    app_id: str | None,
) -> tuple[str | None, UserCheckpoint | None]:
    """Load checkpoint memory (id, checkpoint) if present."""
    filters = checkpoint_filters(user_id=user_id, app_id=app_id)
    result = mem.get_all(user_id=user_id, limit=5, filters=filters)
    items = result.get("results", []) if isinstance(result, dict) else []

    if not isinstance(items, list) or not items:
        return None, None

    # Prefer newest by created_at/updated_at if available; else first.
    def _key(x: dict[str, Any]) -> str:
        return str(x.get("updated_at") or x.get("created_at") or "")

    items_sorted = sorted(
        [x for x in items if isinstance(x, dict)], key=_key, reverse=True
    )
    chosen = items_sorted[0]
    mem_id = str(chosen.get("id") or "").strip() or None
    raw = _extract_memory_text(chosen)

    if not raw:
        return mem_id, UserCheckpoint()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Corrupted checkpoint: ignore content but keep id for overwrite
        return mem_id, UserCheckpoint()
    if not isinstance(data, dict):
        return mem_id, UserCheckpoint()

    cp = UserCheckpoint(
        last_run_at=data.get("last_run_at"),
        conversations={},
    )
    conversations = data.get("conversations") or {}
    if isinstance(conversations, dict):
        for cid, cpd in conversations.items():
            if not isinstance(cpd, dict):
                continue
            cp.conversations[str(cid)] = ConversationCheckpoint(
                last_processed_message_id=cpd.get("last_processed_message_id"),
                processed_range_start=cpd.get("processed_range_start"),
                processed_range_end=cpd.get("processed_range_end"),
            )
    return mem_id, cp


def save_checkpoint(
    mem: Memory,
    *,
    checkpoint_id: str | None,
    user_id: str,
    app_id: str | None,
    checkpoint: UserCheckpoint,
) -> tuple[bool, str | None]:
    """Persist checkpoint; returns (ok, checkpoint_id).
    
    Note: We use delete+add instead of update to avoid mem0's embedding
    processing. Checkpoint data should be stored as-is without any LLM
    inference or vectorization.
    """
    payload = asdict(checkpoint)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    md = checkpoint_metadata(user_id=user_id, app_id=app_id)

    # If updating existing checkpoint, delete it first to avoid embedding
    # mem0's update() method calls embedding_model.embed() which is unnecessary
    # for internal metadata that should be stored as-is
    if checkpoint_id:
        try:
            mem.delete(checkpoint_id)
        except Exception:
            # If delete fails (e.g., already deleted), continue to add new one
            logger.warning(f"Failed to delete old checkpoint {checkpoint_id}, will add new one")

    # Create new internal memory; infer=False to avoid LLM calls and embedding
    res = mem.add(text, user_id=user_id, metadata=md, infer=False)
    new_id: str | None = None
    if isinstance(res, dict):
        results = res.get("results")
        if isinstance(results, list) and results:
            new_id = str(results[0].get("id") or "").strip() or None
        elif isinstance(results, dict):
            new_id = str(results.get("id") or "").strip() or None
    return True, new_id


def save_checkpoint_atomic(
    mem: Memory,
    *,
    user_id: str,
    app_id: str | None,
    checkpoint: UserCheckpoint,
    max_retries: int = 3,
) -> tuple[bool, str | None]:
    """Atomically save checkpoint with retry and rollback mechanism.

    Implementation strategy:
    1. Read old checkpoint (as backup)
    2. Attempt to save new checkpoint (with retries)
    3. Rollback to old checkpoint on failure

    Args:
        mem: Mem0 client
        user_id: User ID
        app_id: App ID
        checkpoint: New checkpoint object
        max_retries: Maximum retry attempts

    Returns:
        (success, checkpoint_id): Returns (True, id) on success, (False, None) on failure
    """
    # 1. Load existing checkpoint as backup
    old_cp_id, old_cp = load_checkpoint(mem, user_id=user_id, app_id=app_id)

    # 2. Attempt to save (with retries)
    for attempt in range(max_retries):
        try:
            ok, new_id = save_checkpoint(
                mem,
                checkpoint_id=old_cp_id,
                user_id=user_id,
                app_id=app_id,
                checkpoint=checkpoint,
            )

            if ok:
                logger.info(
                    f"Checkpoint saved successfully for user {user_id} "
                    f"(attempt: {attempt + 1}/{max_retries})"
                )
                return True, new_id

        except Exception as e:
            logger.error(
                f"Failed to save checkpoint (attempt {attempt + 1}/{max_retries}): {e}"
            )

            if attempt < max_retries - 1:
                # Exponential backoff
                delay = 2**attempt
                logger.info(f"Retrying in {delay}s...")
                time.sleep(delay)
                continue

            # Last attempt failed, try to rollback
            if old_cp:
                logger.warning(f"Rolling back to previous checkpoint for user {user_id}")
                try:
                    save_checkpoint(
                        mem,
                        checkpoint_id=old_cp_id,
                        user_id=user_id,
                        app_id=app_id,
                        checkpoint=old_cp,
                    )
                    logger.info("Rollback successful")
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {rollback_error}")

            return False, None

    return False, None
