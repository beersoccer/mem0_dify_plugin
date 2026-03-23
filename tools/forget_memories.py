"""Dify tool to forget stale memories and clean up old checkpoints.

Flow:
  1. get_all(user_id, agent_id=app_id) — fetch all non-internal memories
  2. access_log.load(user_id, app_id) — load recall quality log
  3. For each memory call should_forget(); collect to-delete list
  4. Delete forgotten memories; update access log (remove deleted mem_ids)
  5. Clean up old checkpoints (keep newest 1; also delete newest if older than TTL)

Intended for scheduled (weekly or bi-weekly) execution.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from dify_plugin import Tool

from utils.access_log import SyncAccessLogManager
from utils.checkpoint import checkpoint_filters
from utils.constants import FORGET_CHECKPOINT_TTL_DAYS
from utils.helpers import days_since
from utils.logger import get_logger
from utils.mem0_client import get_sync_client
from utils.memory_forgetting import forget_params, retention_info, should_forget
from utils.memory_tool_helpers import (
    _is_internal_metadata,
    init_request_context,
    validate_user_id,
    yield_error,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from dify_plugin.entities.tool import ToolInvokeMessage

logger = get_logger(__name__)

_GET_ALL_LIMIT: int = 10_000


def _parse_checkpoint_ttl(credentials: dict[str, Any]) -> int:
    try:
        val = int(credentials.get("checkpoint_ttl_days", FORGET_CHECKPOINT_TTL_DAYS))
        return max(1, val)
    except (TypeError, ValueError):
        return FORGET_CHECKPOINT_TTL_DAYS


def _parse_memory_ttl(credentials: dict[str, Any]) -> int | None:
    """Parse memory_ttl_days from credentials.

    Returns None when the field is absent or empty, meaning no hard TTL is
    applied and memories are only removed by the forgetting curve.
    """
    raw = credentials.get("memory_ttl_days", "")
    if not raw or str(raw).strip() == "":
        return None
    try:
        val = int(raw)
        return max(1, val) if val > 0 else None
    except (TypeError, ValueError):
        return None


def _clean_old_checkpoints(
    mem: Any,
    user_id: str,
    app_id: str | None,
    checkpoint_ttl_days: int,
    dry_run: bool,
    request_id: str,
) -> int:
    """Delete expired or superseded checkpoints.

    Strategy:
    - Delete all but the newest checkpoint.
    - Also delete the newest if its age exceeds checkpoint_ttl_days (expired).
    Returns the count of checkpoints deleted (or would-delete in dry_run).
    """
    try:
        kwargs: dict[str, Any] = {
            "user_id": user_id,
            "limit": 100,
            "filters": checkpoint_filters(),
        }
        if app_id:
            kwargs["agent_id"] = app_id
        raw = mem.get_all(**kwargs)
        items: list[dict[str, Any]] = []
        if isinstance(raw, dict):
            candidates = raw.get("results", [])
        else:
            candidates = raw or []
        for item in candidates or []:
            if isinstance(item, dict):
                items.append(item)

        if not items:
            return 0

        def _key(x: dict[str, Any]) -> str:
            return str(x.get("updated_at") or x.get("created_at") or "")

        items_sorted = sorted(items, key=_key, reverse=True)
        # All but newest are always stale duplicates
        to_delete = items_sorted[1:]
        # Newest is expired if older than TTL
        newest = items_sorted[0]
        newest_age = days_since(newest.get("updated_at") or newest.get("created_at"))
        if newest_age > checkpoint_ttl_days:
            to_delete = items_sorted  # delete all, including newest

        if dry_run:
            return len(to_delete)

        count = 0
        for item in to_delete:
            cp_id = str(item.get("id") or "").strip()
            if not cp_id:
                continue
            try:
                mem.delete(cp_id)
                count += 1
            except Exception:
                logger.exception(
                    "[req:%s] Failed to delete old checkpoint %s", request_id, cp_id
                )
        return count
    except Exception:
        logger.exception("[req:%s] Failed to clean old checkpoints", request_id)
        return 0


class ForgetMemoriesTool(Tool):
    """Forget stale memories via Ebbinghaus retention curve and clean old checkpoints."""

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        request_id, start_time = init_request_context(tool_parameters)

        user_id = validate_user_id(tool_parameters)
        if not user_id:
            yield from yield_error(
                self, request_id, "user_id is required", "forget memories", {}
            )
            return

        app_id: str | None = tool_parameters.get("app_id") or None
        dry_run: bool = bool(tool_parameters.get("dry_run", False))

        try:
            params = forget_params()
            checkpoint_ttl_days = _parse_checkpoint_ttl(self.runtime.credentials)
            memory_ttl_days = _parse_memory_ttl(self.runtime.credentials)

            client = get_sync_client(self.runtime.credentials)
            mem = client.memory

            # 1. Get all non-internal memories for this user (+ app scope)
            get_all_kwargs: dict[str, Any] = {
                "user_id": user_id,
                "limit": _GET_ALL_LIMIT,
            }
            if app_id:
                get_all_kwargs["agent_id"] = app_id
            raw_result = mem.get_all(**get_all_kwargs)
            all_memories: list[dict[str, Any]] = []
            if isinstance(raw_result, dict):
                raw_items = raw_result.get("results", [])
            else:
                raw_items = raw_result or []
            for item in raw_items or []:
                if isinstance(item, dict) and not _is_internal_metadata(
                    item.get("metadata")
                ):
                    all_memories.append(item)

            logger.info(
                "[req:%s] Evolve memories: %d candidate memories for user %s (app_id=%s)",
                request_id,
                len(all_memories),
                user_id,
                app_id,
            )

            # 2. Load access log
            mgr = SyncAccessLogManager(mem)
            log_id, log_dict = mgr.load(user_id=user_id, app_id=app_id)

            # 3. Evaluate each memory
            to_delete: list[dict[str, Any]] = []
            to_retain_ids: list[str] = []

            for mem_item in all_memories:
                mem_id = str(mem_item.get("id") or "").strip()
                if not mem_id:
                    continue
                entry = log_dict.get(mem_id, {})
                created_at = mem_item.get("created_at") or mem_item.get("updated_at")
                metadata = mem_item.get("metadata") or {}
                memory_subtype: str | None = metadata.get("memory_subtype") or None
                if should_forget(
                    entry,
                    created_at,
                    params,
                    memory_ttl_days=memory_ttl_days,
                    memory_subtype=memory_subtype,
                ):
                    info = retention_info(
                        entry,
                        created_at,
                        params,
                        memory_ttl_days=memory_ttl_days,
                        memory_subtype=memory_subtype,
                    )
                    to_delete.append(
                        {
                            "id": mem_id,
                            "memory": mem_item.get("memory", ""),
                            "retention_info": info,
                        }
                    )
                else:
                    to_retain_ids.append(mem_id)

            deleted_count = 0
            deleted_ids: set[str] = set()
            if not dry_run:
                # 4. Delete forgotten memories
                for item in to_delete:
                    try:
                        mem.delete(item["id"])
                        deleted_count += 1
                        deleted_ids.add(item["id"])
                    except Exception:
                        logger.exception(
                            "[req:%s] Failed to delete memory %s",
                            request_id,
                            item["id"],
                        )

                # 5. Update access log: remove entries for successfully deleted memories
                if deleted_count > 0:
                    new_log = {k: v for k, v in log_dict.items() if k not in deleted_ids}
                    try:
                        mgr.save(
                            log_id=log_id,
                            user_id=user_id,
                            app_id=app_id,
                            log_dict=new_log,
                        )
                    except Exception:
                        logger.exception(
                            "[req:%s] Failed to save updated access log", request_id
                        )

            # 6. Clean up old checkpoints
            checkpoints_cleaned = _clean_old_checkpoints(
                mem, user_id, app_id, checkpoint_ttl_days, dry_run, request_id
            )

            effective_deleted = deleted_count if not dry_run else len(to_delete)
            elapsed = time.time() - start_time
            logger.info(
                "[req:%s] Evolve memories done (user_id=%s, deleted=%d, retained=%d, "
                "checkpoints_cleaned=%d, dry_run=%s, duration=%.2fs)",
                request_id,
                user_id,
                effective_deleted,
                len(to_retain_ids),
                checkpoints_cleaned,
                dry_run,
                elapsed,
            )

            result: dict[str, Any] = {
                "deleted_count": effective_deleted,
                "retained_count": len(to_retain_ids),
                "checkpoints_cleaned": checkpoints_cleaned,
                "dry_run": dry_run,
            }
            if dry_run:
                result["would_delete"] = to_delete

            yield self.create_json_message(
                {"status": "SUCCESS", "messages": {}, "results": result}
            )

            action = "Would delete" if dry_run else "Deleted"
            yield self.create_text_message(
                f"{action} {effective_deleted} memories, "
                f"retained {len(to_retain_ids)}, "
                f"cleaned {checkpoints_cleaned} old checkpoint(s)."
            )

        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Evolve memories failed (user_id=%s, duration=%.2fs)",
                request_id,
                user_id,
                elapsed,
            )
            yield from yield_error(
                self, request_id, f"Error: {e!s}", "forget memories", {}
            )
