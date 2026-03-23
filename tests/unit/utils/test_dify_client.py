"""Tests for DifyClient base URL handling."""

from __future__ import annotations

import urllib.parse

import pytest

from utils.dify_client import DifyClient


class _DummyResponse:
    def __init__(self, payload: bytes, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _DummyResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_base_url_requires_v1_suffix() -> None:
    """Ensure base_url must end with /v1."""
    with pytest.raises(ValueError, match="end with /v1"):
        DifyClient(base_url="http://localhost", api_key="test-key")


def test_get_json_uses_v1_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure requests keep /v1 in the base URL."""
    captured_urls: list[str] = []

    def fake_urlopen(req, timeout=0):  # noqa: ANN001
        captured_urls.append(req.full_url)
        return _DummyResponse(b'{"data": []}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = DifyClient(base_url="http://localhost/v1", api_key="test-key")
    client.list_conversations(user_id="user-1")

    assert captured_urls
    parsed = urllib.parse.urlparse(captured_urls[0])
    assert parsed.scheme == "http"
    assert parsed.netloc == "localhost"
    assert parsed.path == "/v1/conversations"
    qs = urllib.parse.parse_qs(parsed.query)
    assert qs["user"] == ["user-1"]
    assert qs["limit"] == ["20"]
    assert qs["sort_by"] == ["-updated_at"]


def test_send_chat_message_posts_expected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout=0):  # noqa: ANN001
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = req.data
        return _DummyResponse(b'{"conversation_id":"conv-1","message_id":"msg-1"}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = DifyClient(base_url="http://localhost/v1", api_key="test-key")
    response = client.send_chat_message(
        query="hello",
        user_id="user-1",
        conversation_id="conv-0",
    )

    assert response["conversation_id"] == "conv-1"
    assert captured["url"] == "http://localhost/v1/chat-messages"
    assert captured["method"] == "POST"
    assert captured["body"] is not None


def test_delete_conversation_uses_delete_with_user_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout=0):  # noqa: ANN001
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = req.data
        return _DummyResponse(b"", status=204)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = DifyClient(base_url="http://localhost/v1", api_key="test-key")
    client.delete_conversation(conversation_id="conv-1", user_id="user-1")

    assert captured["url"] == "http://localhost/v1/conversations/conv-1"
    assert captured["method"] == "DELETE"
    assert captured["body"] == b'{"user": "user-1"}'


def test_run_workflow_blocking_posts_expected_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout=0):  # noqa: ANN001
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = req.data
        return _DummyResponse(b'{"workflow_run_id":"wf-1","data":{"status":"running"}}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = DifyClient(base_url="http://localhost/v1", api_key="test-key")
    response = client.run_workflow_blocking(
        inputs={"query": "hello"},
        user_id="workflow-user",
    )

    assert response["workflow_run_id"] == "wf-1"
    assert captured["url"] == "http://localhost/v1/workflows/run"
    assert captured["method"] == "POST"
    assert captured["body"] == (
        b'{"inputs": {"query": "hello"}, "response_mode": "blocking", '
        b'"user": "workflow-user"}'
    )


def test_get_workflow_run_detail_uses_expected_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_urls: list[str] = []

    def fake_urlopen(req, timeout=0):  # noqa: ANN001
        captured_urls.append(req.full_url)
        return _DummyResponse(b'{"id":"wf-1","status":"succeeded"}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = DifyClient(base_url="http://localhost/v1", api_key="test-key")
    response = client.get_workflow_run_detail(workflow_run_id="wf-1")

    assert response["status"] == "succeeded"
    assert captured_urls == ["http://localhost/v1/workflows/run/wf-1"]

