"""Access log storage in Mem0 for tracking memory recall quality.

The access log is stored as an internal Mem0 memory with metadata markers:
- metadata.__internal = true
- metadata.internal_type = "access_log"
- metadata.version = "v1"

Each user+app combination has exactly one access log blob.  The blob content
is a JSON object keyed by memory ID:

    {
      "<mem_id>": {
        "last_recalled_at": "<ISO-8601>",
        "recall_count": <int>,
        "quality_ema": <float>
      },
      ...
    }

App scoping uses Mem0's agent_id (agent_id = app_id when provided).  This
mirrors the checkpoint pattern so that each agent/application maintains its
own independent access log, even for the same user.

The delete+add(infer=False) pattern is used for updates to avoid triggering
LLM inference or embedding generation.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .logger import get_logger
from .mem0_client import Memory

if TYPE_CHECKING:
    from mem0 import AsyncMemory
else:
    AsyncMemory = None  # type: ignore

logger = get_logger(__name__)
ACCESS_LOG_VERSION = "v1"


def access_log_metadata() -> dict[str, Any]:
    return {
        "__internal": "true",
        "internal_type": "access_log",
        "version": ACCESS_LOG_VERSION,
    }


def access_log_filters() -> dict[str, Any]:
    return {
        "__internal": "true",
        "internal_type": "access_log",
        "version": ACCESS_LOG_VERSION,
    }


def _extract_memory_text(obj: dict[str, Any]) -> str:
    return str(obj.get("memory") or obj.get("text") or obj.get("content") or "")


class SyncAccessLogManager:
    """Synchronous access log manager for Memory instances."""

    def __init__(self, mem: Memory) -> None:
        self.mem = mem

    def load(
        self,
        *,
        user_id: str,
        app_id: str | None,
    ) -> tuple[str | None, dict[str, Any]]:
        """Load access log for a user+app.

        Returns:
            (log_id, log_dict): ID of the blob memory and the parsed log dict.
                                log_dict is empty if no log exists yet.
        """
        items = self._load_items(user_id=user_id, app_id=app_id)
        if not items:
            return None, {}

        def _key(x: dict[str, Any]) -> str:
            return str(x.get("updated_at") or x.get("created_at") or "")

        chosen = sorted(items, key=_key, reverse=True)[0]
        log_id = str(chosen.get("id") or "").strip() or None
        raw = _extract_memory_text(chosen)
        if not raw:
            return log_id, {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Access log blob corrupted for user %s, resetting", user_id)
            return log_id, {}
        if not isinstance(data, dict):
            return log_id, {}
        return log_id, data

    def _load_items(self, *, user_id: str, app_id: str | None = None) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "user_id": user_id,
            "limit": 5,
            "filters": access_log_filters(),
        }
        if app_id:
            kwargs["agent_id"] = app_id
        result = self.mem.get_all(**kwargs)
        items = result.get("results", []) if isinstance(result, dict) else []
        if isinstance(items, list) and items:
            return [x for x in items if isinstance(x, dict)]
        return []

    def save(
        self,
        *,
        log_id: str | None,
        user_id: str,
        app_id: str | None,
        log_dict: dict[str, Any],
    ) -> tuple[bool, str | None]:
        """Persist access log; returns (ok, new_log_id).

        Uses delete+add(infer=False) to avoid LLM/embedding overhead.
        """
        text = json.dumps(log_dict, ensure_ascii=False, sort_keys=True)
        md = access_log_metadata()

        if log_id:
            try:
                self.mem.delete(log_id)
            except Exception:
                logger.warning("Failed to delete old access log %s, will add new one", log_id)

        res = self.mem.add(
            text,
            user_id=user_id,
            agent_id=app_id or None,
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

    def update(
        self,
        *,
        user_id: str,
        app_id: str | None,
        updates: dict[str, dict[str, Any]],
    ) -> None:
        """Load the access log, apply updates for the given mem_ids, and save.

        Args:
            user_id: User ID.
            app_id: App ID (maps to agent_id).
            updates: Mapping of mem_id -> new entry fields to merge.
                     Each value should be a complete entry dict produced by
                     memory_forgetting.update_entry().
        """
        if not updates:
            return
        try:
            log_id, log_dict = self.load(user_id=user_id, app_id=app_id)
            for mem_id, entry in updates.items():
                log_dict[mem_id] = entry
            self.save(log_id=log_id, user_id=user_id, app_id=app_id, log_dict=log_dict)
        except Exception:
            logger.exception(
                "Failed to update access log for user %s app %s", user_id, app_id
            )


class AsyncAccessLogManager:
    """Asynchronous access log manager for AsyncMemory instances."""

    def __init__(self, mem: AsyncMemory) -> None:
        self.mem = mem

    async def load(
        self,
        *,
        user_id: str,
        app_id: str | None,
    ) -> tuple[str | None, dict[str, Any]]:
        """Load access log for a user+app.

        Returns:
            (log_id, log_dict): ID of the blob memory and the parsed log dict.
                                log_dict is empty if no log exists yet.
        """
        items = await self._load_items(user_id=user_id, app_id=app_id)
        if not items:
            return None, {}

        def _key(x: dict[str, Any]) -> str:
            return str(x.get("updated_at") or x.get("created_at") or "")

        chosen = sorted(items, key=_key, reverse=True)[0]
        log_id = str(chosen.get("id") or "").strip() or None
        raw = _extract_memory_text(chosen)
        if not raw:
            return log_id, {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Access log blob corrupted for user %s, resetting", user_id)
            return log_id, {}
        if not isinstance(data, dict):
            return log_id, {}
        return log_id, data

    async def _load_items(self, *, user_id: str, app_id: str | None = None) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "user_id": user_id,
            "limit": 5,
            "filters": access_log_filters(),
        }
        if app_id:
            kwargs["agent_id"] = app_id
        result = await self.mem.get_all(**kwargs)
        items = result.get("results", []) if isinstance(result, dict) else []
        if isinstance(items, list) and items:
            return [x for x in items if isinstance(x, dict)]
        return []

    async def save(
        self,
        *,
        log_id: str | None,
        user_id: str,
        app_id: str | None,
        log_dict: dict[str, Any],
    ) -> tuple[bool, str | None]:
        """Persist access log; returns (ok, new_log_id).

        Uses delete+add(infer=False) to avoid LLM/embedding overhead.
        """
        text = json.dumps(log_dict, ensure_ascii=False, sort_keys=True)
        md = access_log_metadata()

        if log_id:
            try:
                await self.mem.delete(log_id)
            except Exception:
                logger.warning("Failed to delete old access log %s, will add new one", log_id)

        res = await self.mem.add(
            text,
            user_id=user_id,
            agent_id=app_id or None,
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

    async def update(
        self,
        *,
        user_id: str,
        app_id: str | None,
        updates: dict[str, dict[str, Any]],
    ) -> None:
        """Load the access log, apply updates for the given mem_ids, and save.

        Args:
            user_id: User ID.
            app_id: App ID (maps to agent_id).
            updates: Mapping of mem_id -> new entry fields to merge.
                     Each value should be a complete entry dict produced by
                     memory_forgetting.update_entry().
        """
        if not updates:
            return
        try:
            log_id, log_dict = await self.load(user_id=user_id, app_id=app_id)
            for mem_id, entry in updates.items():
                log_dict[mem_id] = entry
            await self.save(log_id=log_id, user_id=user_id, app_id=app_id, log_dict=log_dict)
        except Exception:
            logger.exception(
                "Failed to update access log for user %s app %s", user_id, app_id
            )
