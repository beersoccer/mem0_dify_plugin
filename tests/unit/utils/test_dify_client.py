"""Tests for DifyClient base URL handling."""

from __future__ import annotations

import urllib.parse

import pytest

from utils.dify_client import DifyClient


class _DummyResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_DummyResponse":
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

