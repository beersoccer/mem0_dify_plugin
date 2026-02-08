"""Checkpoint storage in Mem0 for Dify extraction runs (no external DB).

Checkpoint is stored as an internal Mem0 memory with metadata markers (SPEC.md):
- metadata.__internal = true
- metadata.internal_type = "checkpoint"
- metadata.version = "v1"

App scoping uses Mem0's agent_id (agent_id = app_id when provided).

Enhanced with atomic save and rollback mechanism for robustness.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from .extraction import ConversationCheckpoint, UserCheckpoint
from .logger import get_logger
from .mem0_client import Memory

if TYPE_CHECKING:
    from mem0 import AsyncMemory
else:
    AsyncMemory = None  # type: ignore

logger = get_logger(__name__)
CHECKPOINT_VERSION = "v1"


def checkpoint_metadata() -> dict[str, Any]:
    return {
        "__internal": True,
        "internal_type": "checkpoint",
        "version": CHECKPOINT_VERSION,
    }


def checkpoint_filters() -> dict[str, Any]:
    # Mem0 filters operate on metadata keys directly in local mode.
    # Use string "true" to match mem0's stored metadata formatting.
    return {
        "__internal": "true",
        "internal_type": "checkpoint",
        "version": CHECKPOINT_VERSION,
    }


def _checkpoint_agent_id(app_id: str | None) -> str | None:
    return app_id or None


def _extract_memory_text(obj: dict[str, Any]) -> str:
    return str(obj.get("memory") or obj.get("text") or obj.get("content") or "")


class SyncCheckpointManager:
    """Synchronous checkpoint manager for Memory instances."""

    def __init__(self, mem: Memory) -> None:
        """Initialize checkpoint manager.

        Args:
            mem: Synchronous Memory instance
        """
        self.mem = mem

    def load(
        self,
        *,
        user_id: str,
        app_id: str | None,
    ) -> tuple[str | None, UserCheckpoint | None]:
        """Load checkpoint memory (id, checkpoint) if present.

        Args:
            user_id: User ID
            app_id: App ID

        Returns:
            (checkpoint_id, checkpoint): Tuple of checkpoint ID and checkpoint object
        """
        items = self._load_items(user_id=user_id)
        if not items:
            return None, None

        # Prefer newest by created_at/updated_at if available; else first.
        def _key(x: dict[str, Any]) -> str:
            return str(x.get("updated_at") or x.get("created_at") or "")

        items_sorted = sorted(items, key=_key, reverse=True)
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
            conversations={},
            resume_conversation_cursor=data.get("resume_conversation_cursor"),
            resume_run_at=data.get("resume_run_at"),
            resume_start_time=data.get("resume_start_time"),
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

    def _load_items(self, *, user_id: str) -> list[dict[str, Any]]:
        result = self.mem.get_all(
            user_id=user_id,
            limit=5,
            filters=checkpoint_filters(),
        )
        items = result.get("results", []) if isinstance(result, dict) else []
        if isinstance(items, list) and items:
            return [x for x in items if isinstance(x, dict)]
        return []

    def save(
        self,
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

        Args:
            checkpoint_id: Existing checkpoint ID to replace (if any)
            user_id: User ID
            app_id: App ID
            checkpoint: Checkpoint object to save

        Returns:
            (success, checkpoint_id): Tuple of success flag and new checkpoint ID
        """
        payload = asdict(checkpoint)
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        md = checkpoint_metadata()

        # If updating existing checkpoint, delete it first to avoid embedding
        # mem0's update() method calls embedding_model.embed() which is unnecessary
        # for internal metadata that should be stored as-is
        if checkpoint_id:
            try:
                self.mem.delete(checkpoint_id)
            except Exception:
                # If delete fails (e.g., already deleted), continue to add new one
                logger.warning(
                    f"Failed to delete old checkpoint {checkpoint_id}, will add new one"
                )

        # Create new internal memory; infer=False to avoid LLM calls and embedding
        res = self.mem.add(
            text,
            user_id=user_id,
            agent_id=_checkpoint_agent_id(app_id),
            metadata=md,
            infer=False,
        )
        new_id: str | None = None
        if isinstance(res, dict):
            results = res.get("results")
            if isinstance(results, list) and results:
                new_id = str(results[0].get("id") or "").strip() or None
            elif isinstance(results, dict):
                new_id = str(results.get("id") or "").strip() or None
        return True, new_id

    def save_atomic(
        self,
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
            user_id: User ID
            app_id: App ID
            checkpoint: New checkpoint object
            max_retries: Maximum retry attempts

        Returns:
            (success, checkpoint_id): Returns (True, id) on success, (False, None) on failure
        """
        # 1. Load existing checkpoint as backup
        old_cp_id, old_cp = self.load(user_id=user_id, app_id=app_id)

        # 2. Attempt to save (with retries)
        for attempt in range(max_retries):
            try:
                ok, new_id = self.save(
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
                    logger.warning(
                        f"Rolling back to previous checkpoint for user {user_id}"
                    )
                    try:
                        self.save(
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


class AsyncCheckpointManager:
    """Asynchronous checkpoint manager for AsyncMemory instances."""

    def __init__(self, mem: AsyncMemory) -> None:
        """Initialize async checkpoint manager.

        Args:
            mem: Asynchronous AsyncMemory instance
        """
        self.mem = mem

    async def load(
        self,
        *,
        user_id: str,
        app_id: str | None,
    ) -> tuple[str | None, UserCheckpoint | None]:
        """Load checkpoint memory (id, checkpoint) if present.

        Args:
            user_id: User ID
            app_id: App ID

        Returns:
            (checkpoint_id, checkpoint): Tuple of checkpoint ID and checkpoint object
        """
        items = await self._load_items(user_id=user_id)
        if not items:
            return None, None

        # Prefer newest by created_at/updated_at if available; else first.
        def _key(x: dict[str, Any]) -> str:
            return str(x.get("updated_at") or x.get("created_at") or "")

        items_sorted = sorted(items, key=_key, reverse=True)
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

    async def _load_items(self, *, user_id: str) -> list[dict[str, Any]]:
        result = await self.mem.get_all(
            user_id=user_id,
            limit=5,
            filters=checkpoint_filters(),
        )
        items = result.get("results", []) if isinstance(result, dict) else []
        if isinstance(items, list) and items:
            return [x for x in items if isinstance(x, dict)]
        return []

    async def save(
        self,
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

        Args:
            checkpoint_id: Existing checkpoint ID to replace (if any)
            user_id: User ID
            app_id: App ID
            checkpoint: Checkpoint object to save

        Returns:
            (success, checkpoint_id): Tuple of success flag and new checkpoint ID
        """
        payload = asdict(checkpoint)
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        md = checkpoint_metadata()

        # If updating existing checkpoint, delete it first to avoid embedding
        # mem0's update() method calls embedding_model.embed() which is unnecessary
        # for internal metadata that should be stored as-is
        if checkpoint_id:
            try:
                await self.mem.delete(checkpoint_id)
            except Exception:
                # If delete fails (e.g., already deleted), continue to add new one
                logger.warning(
                    f"Failed to delete old checkpoint {checkpoint_id}, will add new one"
                )

        # Create new internal memory; infer=False to avoid LLM calls and embedding
        res = await self.mem.add(
            text,
            user_id=user_id,
            agent_id=_checkpoint_agent_id(app_id),
            metadata=md,
            infer=False,
        )
        new_id: str | None = None
        if isinstance(res, dict):
            results = res.get("results")
            if isinstance(results, list) and results:
                new_id = str(results[0].get("id") or "").strip() or None
            elif isinstance(results, dict):
                new_id = str(results.get("id") or "").strip() or None
        return True, new_id

    async def save_atomic(
        self,
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
            user_id: User ID
            app_id: App ID
            checkpoint: New checkpoint object
            max_retries: Maximum retry attempts

        Returns:
            (success, checkpoint_id): Returns (True, id) on success, (False, None) on failure
        """
        # 1. Load existing checkpoint as backup
        old_cp_id, old_cp = await self.load(user_id=user_id, app_id=app_id)

        # 2. Attempt to save (with retries)
        for attempt in range(max_retries):
            try:
                ok, new_id = await self.save(
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
                    await asyncio.sleep(delay)
                    continue

                # Last attempt failed, try to rollback
                if old_cp:
                    logger.warning(
                        f"Rolling back to previous checkpoint for user {user_id}"
                    )
                    try:
                        await self.save(
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
