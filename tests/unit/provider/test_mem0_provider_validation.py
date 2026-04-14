from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from provider.mem0ai import Mem0Provider


def test_validate_credentials_async_mode_uses_async_client_search(monkeypatch) -> None:
    import provider.mem0ai as provider_mod

    captured: dict[str, object] = {}
    fake_loop = object()
    fake_future = MagicMock()
    fake_future.result.return_value = {"results": []}

    class FakeClient:
        def ensure_bg_loop(self) -> object:
            captured["ensure_bg_loop_called"] = True
            return fake_loop

        async def search(self, payload: dict[str, object], timeout_s: int) -> dict[str, object]:
            captured["search_payload"] = payload
            captured["search_timeout"] = timeout_s
            return {"results": []}

    def _fake_run_coroutine_threadsafe(coro, loop):  # noqa: ANN001
        assert asyncio.iscoroutine(coro)
        captured["loop"] = loop
        coro.close()
        return fake_future

    monkeypatch.setattr(provider_mod, "get_async_client", lambda _credentials: FakeClient())
    monkeypatch.setattr(provider_mod.asyncio, "run_coroutine_threadsafe", _fake_run_coroutine_threadsafe)

    provider = object.__new__(Mem0Provider)
    provider._validate_credentials({"async_mode": True, "log_level": "INFO"})

    assert captured["ensure_bg_loop_called"] is True
    assert captured["loop"] is fake_loop
    assert fake_future.result.call_count == 1
