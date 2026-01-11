"""Checkpoint storage in Mem0 for Dify consolidation runs (no external DB).

Checkpoint is stored as an internal Mem0 memory with metadata markers (SPEC.md):
- metadata.__internal = true
- metadata.internal_type = "checkpoint"
- metadata.checkpoint_key = "dify_consolidation_v1"
- metadata.user_id = <user_id>
- metadata.app_id = <app_id or "*">
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from mem0 import Memory

from .consolidation import ConversationCheckpoint, UserCheckpoint

CHECKPOINT_KEY = "dify_consolidation_v1"


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

    items_sorted = sorted([x for x in items if isinstance(x, dict)], key=_key, reverse=True)
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
        version=str(data.get("version") or "v1"),
    )
    conversations = data.get("conversations") or {}
    if isinstance(conversations, dict):
        for cid, cpd in conversations.items():
            if not isinstance(cpd, dict):
                continue
            cp.conversations[str(cid)] = ConversationCheckpoint(
                last_processed_message_id=cpd.get("last_processed_message_id"),
                last_processed_message_created_at=cpd.get("last_processed_message_created_at"),
                last_seen_updated_at=cpd.get("last_seen_updated_at"),
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
    """Persist checkpoint; returns (ok, checkpoint_id)."""
    payload = asdict(checkpoint)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    md = checkpoint_metadata(user_id=user_id, app_id=app_id)

    if checkpoint_id:
        mem.update(checkpoint_id, text)
        return True, checkpoint_id

    # Create new internal memory; infer=False to avoid LLM calls.
    res = mem.add(text, user_id=user_id, metadata=md, infer=False)
    new_id: str | None = None
    if isinstance(res, dict):
        results = res.get("results")
        if isinstance(results, list) and results:
            new_id = str(results[0].get("id") or "").strip() or None
        elif isinstance(results, dict):
            new_id = str(results.get("id") or "").strip() or None
    return True, new_id


