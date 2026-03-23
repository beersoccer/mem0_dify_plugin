"""Minimal Dify API client (self-hosted) for Dify HTTP APIs.

This module intentionally avoids adding new dependencies (uses Python stdlib).
It focuses on the capabilities needed by tests and extraction workflows:
- conversations list (sort_by=-updated_at + last_id pagination)
- messages list (first_id + limit reverse pagination)
- chat/chatflow message submission for deterministic test data seeding
- workflow execution and workflow run detail retrieval
- conversation deletion for teardown/cleanup

Enhanced with retry mechanism for robust API calls.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from .retry import retry_with_exponential_backoff


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

    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        """Initialize Dify API client.
        
        Args:
            base_url: Dify API base URL (format: http://host/v1)
            api_key: Dify API key
            timeout: HTTP request timeout in seconds (default: 30s)
                     Increased from 20s to handle larger conversation/message lists
        """
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout = float(timeout)
        if not self.base_url:
            msg = "base_url is required"
            raise ValueError(msg)
        if not self.base_url.endswith("/v1"):
            msg = "base_url must end with /v1"
            raise ValueError(msg)
        if not self.api_key:
            msg = "api_key is required"
            raise ValueError(msg)

    def _build_url(self, path: str, params: dict[str, object] | None = None) -> str:
        url = urllib.parse.urljoin(self.base_url + "/", path.lstrip("/"))
        if not params:
            return url
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
        if qs:
            url = f"{url}?{qs}"
        return url

    def _request(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, object] | None = None,
        json_body: dict[str, Any] | None = None,
        expected_statuses: tuple[int, ...] = (HTTPStatus.OK,),
    ) -> tuple[int, str]:
        url = self._build_url(path, params)
        body: bytes | None = None
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                status = int(getattr(resp, "status", HTTPStatus.OK))
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
        if status not in expected_statuses:
            raise DifyAPIError(
                f"Unexpected HTTP {status} for {url}; expected one of {expected_statuses}"
            )
        return status, raw

    def _get_json(self, path: str, params: dict[str, object]) -> dict[str, Any]:
        _status, raw = self._request(method="GET", path=path, params=params)
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError as e:
            raise DifyAPIError(
                f"Invalid JSON from {self._build_url(path, params)}: {raw[:500]}"
            ) from e
        if not isinstance(parsed, dict):
            raise DifyAPIError(
                f"Unexpected response type from {self._build_url(path, params)}: "
                f"{type(parsed).__name__}"
            )
        return parsed

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        _status, raw = self._request(method="POST", path=path, json_body=payload)
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError as e:
            raise DifyAPIError(
                f"Invalid JSON from {self._build_url(path)}: {raw[:500]}"
            ) from e
        if not isinstance(parsed, dict):
            raise DifyAPIError(
                f"Unexpected response type from {self._build_url(path)}: {type(parsed).__name__}"
            )
        return parsed

    def _delete(self, path: str, payload: dict[str, Any]) -> None:
        self._request(
            method="DELETE",
            path=path,
            json_body=payload,
            expected_statuses=(HTTPStatus.NO_CONTENT, HTTPStatus.OK),
        )

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1.0,
        retriable_exceptions=(DifyAPIError, urllib.error.URLError, TimeoutError),
    )
    def list_conversations(
        self,
        *,
        user_id: str,
        last_id: str | None = None,
        limit: int = 20,
        sort_by: str = "-updated_at",
    ) -> DifyPage:
        """List conversations, newest first. Retries on transient failures."""
        data = self._get_json(
            "/conversations",
            {
                "user": user_id,
                "last_id": last_id,
                "limit": limit,
                "sort_by": sort_by,
            },
        )
        items = _coerce_items(
            data.get("data") or data.get("conversations") or data.get("items")
        )
        next_cursor = (
            data.get("last_id")
            or data.get("next_cursor")
            or (items[-1].get("id") if items else None)
        )
        has_more = bool(data.get("has_more")) if "has_more" in data else bool(items)
        # If API provides explicit has_more=false, respect it.
        if data.get("has_more") is False:
            has_more = False
        return DifyPage(
            items=items,
            next_cursor=str(next_cursor) if next_cursor else None,
            has_more=has_more,
        )

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1.0,
        retriable_exceptions=(DifyAPIError, urllib.error.URLError, TimeoutError),
    )
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
        Retries on transient failures.
        """
        data = self._get_json(
            "/messages",
            {
                "user": user_id,
                "conversation_id": conversation_id,
                "first_id": first_id,
                "limit": limit,
            },
        )
        items = _coerce_items(
            data.get("data") or data.get("messages") or data.get("items")
        )
        next_cursor = (
            data.get("first_id")
            or data.get("next_cursor")
            or (items[-1].get("id") if items else None)
        )
        has_more = bool(data.get("has_more")) if "has_more" in data else bool(items)
        if data.get("has_more") is False:
            has_more = False
        return DifyPage(
            items=items,
            next_cursor=str(next_cursor) if next_cursor else None,
            has_more=has_more,
        )

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1.0,
        retriable_exceptions=(DifyAPIError, urllib.error.URLError, TimeoutError),
    )
    def send_chat_message(
        self,
        *,
        query: str,
        user_id: str,
        conversation_id: str | None = None,
        inputs: dict[str, Any] | None = None,
        response_mode: str = "blocking",
        files: list[dict[str, Any]] | None = None,
        endpoint: str = "/chat-messages",
    ) -> dict[str, Any]:
        """Send one chat/chatflow message and return the decoded JSON response."""
        payload: dict[str, Any] = {
            "inputs": inputs or {},
            "query": query,
            "response_mode": response_mode,
            "user": user_id,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if files:
            payload["files"] = files
        return self._post_json(endpoint, payload)

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1.0,
        retriable_exceptions=(DifyAPIError, urllib.error.URLError, TimeoutError),
    )
    def delete_conversation(self, *, conversation_id: str, user_id: str) -> None:
        """Delete one Dify conversation created through the service API."""
        if not conversation_id:
            raise ValueError("conversation_id is required")
        self._delete(f"/conversations/{conversation_id}", {"user": user_id})

    def get_app_info(self) -> dict[str, Any]:
        """Fetch /info for the app. Works for all app types (chat, workflow, etc.)."""
        return self._get_json("/info", {})

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1.0,
        retriable_exceptions=(DifyAPIError, urllib.error.URLError, TimeoutError),
    )
    def run_workflow_blocking(
        self,
        *,
        inputs: dict[str, Any],
        user_id: str,
    ) -> dict[str, Any]:
        """Execute a published workflow using blocking mode."""
        payload = {
            "inputs": inputs,
            "response_mode": "blocking",
            "user": user_id,
        }
        return self._post_json("/workflows/run", payload)

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1.0,
        retriable_exceptions=(DifyAPIError, urllib.error.URLError, TimeoutError),
    )
    def get_workflow_run_detail(self, *, workflow_run_id: str) -> dict[str, Any]:
        """Get workflow run detail by workflow execution id."""
        if not workflow_run_id:
            raise ValueError("workflow_run_id is required")
        return self._get_json(f"/workflows/run/{workflow_run_id}", {})
