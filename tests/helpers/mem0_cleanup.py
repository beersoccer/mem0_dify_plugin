from __future__ import annotations

from typing import Any

from utils.access_log import access_log_filters
from utils.checkpoint import checkpoint_filters
from utils.config_builder import build_local_mem0_config_without_pool
from utils.mem0_client import SyncMem0Client
from utils.task_status import TASK_STATUS_USER_ID, task_status_filters


def _make_client(credentials: dict[str, Any]) -> SyncMem0Client:
    """Create a fresh, standalone SyncMem0Client for test cleanup operations.

    Uses build_local_mem0_config_without_pool to create an independent connection
    pool that is not shared with the global config cache. This prevents close()
    from poisoning the cached pool object used by other clients.
    """
    config = build_local_mem0_config_without_pool(credentials)
    return SyncMem0Client(credentials, enable_keepalive=False, config_override=config)


def _extract_results(result: Any) -> list[dict[str, Any]]:
    items = result.get("results", []) if isinstance(result, dict) else []
    return [item for item in items if isinstance(item, dict)]


def _delete_items(mem: Any, *, user_id: str, filters: dict[str, Any], agent_id: str | None = None) -> int:
    kwargs: dict[str, Any] = {
        "user_id": user_id,
        "limit": 100,
        "filters": filters,
    }
    if agent_id:
        kwargs["agent_id"] = agent_id
    items = _extract_results(mem.get_all(**kwargs))
    deleted = 0
    for item in items:
        memory_id = str(item.get("id") or "").strip()
        if not memory_id:
            continue
        mem.delete(memory_id)
        deleted += 1
    return deleted


def _lock_filters(user_id: str, app_id: str | None) -> dict[str, Any]:
    return {
        "AND": [
            {"__internal": {"eq": True}},
            {"internal_type": {"eq": "distributed_lock"}},
            {"lock_resource": {"eq": "extraction"}},
            {"user_id": {"eq": user_id}},
            {"app_id": {"eq": app_id or "*"}},
        ]
    }


def cleanup_mem0_state(
    credentials: dict[str, str],
    *,
    user_ids: list[str],
    app_id: str | None,
    task_ids: list[str] | None = None,
) -> dict[str, Any]:
    client = _make_client(credentials)
    mem = client.memory
    summary = {
        "memories_deleted": 0,
        "checkpoints_deleted": 0,
        "access_logs_deleted": 0,
        "locks_deleted": 0,
        "task_status_deleted": 0,
    }

    try:
        for user_id in user_ids:
            result = client.delete_all(
                {"user_id": user_id, **({"agent_id": app_id} if app_id else {})}
            )
            if isinstance(result, dict):
                summary["memories_deleted"] += int(
                    result.get("deleted_count", result.get("count", 0)) or 0
                )

            summary["checkpoints_deleted"] += _delete_items(
                mem,
                user_id=user_id,
                agent_id=app_id,
                filters=checkpoint_filters(),
            )
            summary["access_logs_deleted"] += _delete_items(
                mem,
                user_id=user_id,
                agent_id=app_id,
                filters=access_log_filters(),
            )
            summary["locks_deleted"] += _delete_items(
                mem,
                user_id=user_id,
                filters=_lock_filters(user_id, app_id),
            )

        for task_id in task_ids or []:
            summary["task_status_deleted"] += _delete_items(
                mem,
                user_id=TASK_STATUS_USER_ID,
                filters=task_status_filters(task_id=task_id),
            )
    finally:
        client.close()

    return summary


def count_user_memories(
    credentials: dict[str, str],
    *,
    user_id: str,
    app_id: str | None,
) -> int:
    client = _make_client(credentials)
    try:
        result = client.get_all(
            {"user_id": user_id, **({"agent_id": app_id} if app_id else {})}
        )
        if not isinstance(result, list):
            return 0
        return len([item for item in result if isinstance(item, dict)])
    finally:
        client.close()
