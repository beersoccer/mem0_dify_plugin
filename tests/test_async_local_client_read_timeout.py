from __future__ import annotations

import asyncio

import pytest

from utils.mem0_client import AsyncMem0Client


class FakeAsyncMemory:
    def __init__(self) -> None:
        self.acquired: asyncio.Event | None = None
        self.sleep_s: float = 0.0

    async def search(self, query: str, **kwargs: object) -> object:  # noqa: ARG002
        if self.acquired is not None:
            self.acquired.set()
        if self.sleep_s:
            await asyncio.sleep(self.sleep_s)
        return {"results": []}


def test_search_timeout_covers_create(monkeypatch: pytest.MonkeyPatch) -> None:
    # Avoid requiring real provider credentials in tests.
    import utils.mem0_client as mem0_client

    monkeypatch.setattr(mem0_client, "build_local_mem0_config", lambda _c: {})

    async def _run() -> None:
        client = AsyncMem0Client({})

        async def _slow_create(self: AsyncMem0Client) -> object:  # noqa: ARG001
            await asyncio.sleep(1.0)
            return object()

        # Force create() to be slow; search() should time out before using memory.
        monkeypatch.setattr(client, "create", _slow_create.__get__(client, AsyncMem0Client))

        with pytest.raises(asyncio.TimeoutError):
            await client.search({"query": "q", "user_id": "u"}, timeout_s=0.01)

    asyncio.run(_run())


def test_search_timeout_covers_semaphore_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    import utils.mem0_client as mem0_client

    monkeypatch.setattr(mem0_client, "build_local_mem0_config", lambda _c: {})

    async def _run() -> None:
        client = AsyncMem0Client({})
        client._semaphore = asyncio.Semaphore(1)  # noqa: SLF001

        mem = FakeAsyncMemory()
        mem.acquired = asyncio.Event()
        mem.sleep_s = 0.2
        client.memory = mem  # make create() return fast

        t1 = asyncio.create_task(client.search({"query": "q", "user_id": "u"}, timeout_s=1.0))
        await mem.acquired.wait()  # first call holds the semaphore now

        with pytest.raises(asyncio.TimeoutError):
            await client.search({"query": "q2", "user_id": "u"}, timeout_s=0.01)

        t1.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t1

    asyncio.run(_run())


