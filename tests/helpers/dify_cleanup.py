from __future__ import annotations

from typing import Any

from utils.dify_client import DifyClient

from .dify_seed import SeedManifest


def conversation_exists(client: DifyClient, *, user_id: str, conversation_id: str) -> bool:
    cursor: str | None = None
    pages = 0
    while pages < 20:
        page = client.list_conversations(user_id=user_id, limit=100, last_id=cursor)
        for item in page.items:
            if str(item.get("id") or "") == conversation_id:
                return True
        if not page.has_more or not page.next_cursor:
            return False
        cursor = page.next_cursor
        pages += 1
    return False


def cleanup_seeded_conversations(
    client: DifyClient,
    *,
    manifest: SeedManifest,
    verify: bool = True,
) -> dict[str, Any]:
    deleted = 0
    verified_absent = 0
    failures: list[str] = []

    for item in manifest.conversations:
        try:
            client.delete_conversation(
                conversation_id=item.conversation_id,
                user_id=item.user_id,
            )
            deleted += 1
            if verify and not conversation_exists(
                client,
                user_id=item.user_id,
                conversation_id=item.conversation_id,
            ):
                verified_absent += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{item.user_id}/{item.conversation_id}: {exc}"
            )

    return {
        "deleted": deleted,
        "verified_absent": verified_absent,
        "failures": failures,
    }
