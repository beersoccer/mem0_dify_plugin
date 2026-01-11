"""Minimal Dify API client (self-hosted) for conversations/messages listing.

This module intentionally avoids adding new dependencies (uses Python stdlib).
It focuses on the two read-only capabilities needed by SPEC.md:
- conversations list (sort_by=-updated_at + last_id pagination)
- messages list (first_id + limit reverse pagination)
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class DifyAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class DifyPage:
    items: list[dict[str, Any]]
    next_cursor: str | None
    has_more: bool


def _coerce_items(obj: object) -> list[dict[str, Any]]:
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    return []


class DifyClient:
    """Very small synchronous client for Dify HTTP APIs."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 20.0) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout = float(timeout)
        if not self.base_url:
            msg = "base_url is required"
            raise ValueError(msg)
        if not self.api_key:
            msg = "api_key is required"
            raise ValueError(msg)

    def _get_json(self, path: str, params: dict[str, object]) -> dict[str, Any]:
        url = urllib.parse.urljoin(self.base_url + "/", path.lstrip("/"))
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
        if qs:
            url = f"{url}?{qs}"
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                body = ""
            raise DifyAPIError(f"HTTP {e.code} for {url}: {body[:500]}") from e
        except urllib.error.URLError as e:
            raise DifyAPIError(f"Failed to call {url}: {e.reason}") from e
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError as e:
            raise DifyAPIError(f"Invalid JSON from {url}: {raw[:500]}") from e
        if not isinstance(parsed, dict):
            raise DifyAPIError(f"Unexpected response type from {url}: {type(parsed).__name__}")
        return parsed

    def list_conversations(
        self,
        *,
        user_id: str,
        last_id: str | None = None,
        limit: int = 20,
        sort_by: str = "-updated_at",
    ) -> DifyPage:
        """List conversations, newest first."""
        data = self._get_json(
            "/v1/conversations",
            {
                "user": user_id,
                "last_id": last_id,
                "limit": limit,
                "sort_by": sort_by,
            },
        )
        items = _coerce_items(data.get("data") or data.get("conversations") or data.get("items"))
        next_cursor = (
            data.get("last_id")
            or data.get("next_cursor")
            or (items[-1].get("id") if items else None)
        )
        has_more = bool(data.get("has_more")) if "has_more" in data else bool(items)
        # If API provides explicit has_more=false, respect it.
        if data.get("has_more") is False:
            has_more = False
        return DifyPage(items=items, next_cursor=str(next_cursor) if next_cursor else None, has_more=has_more)

    def list_messages(
        self,
        *,
        user_id: str,
        conversation_id: str,
        first_id: str | None = None,
        limit: int = 100,
    ) -> DifyPage:
        """List messages in a conversation, reverse-paginated by first_id.

        Dify supports reverse pagination via `first_id` + `limit` (SPEC.md).
        """
        data = self._get_json(
            "/v1/messages",
            {
                "user": user_id,
                "conversation_id": conversation_id,
                "first_id": first_id,
                "limit": limit,
            },
        )
        items = _coerce_items(data.get("data") or data.get("messages") or data.get("items"))
        next_cursor = (
            data.get("first_id")
            or data.get("next_cursor")
            or (items[-1].get("id") if items else None)
        )
        has_more = bool(data.get("has_more")) if "has_more" in data else bool(items)
        if data.get("has_more") is False:
            has_more = False
        return DifyPage(items=items, next_cursor=str(next_cursor) if next_cursor else None, has_more=has_more)


