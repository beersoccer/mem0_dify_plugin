from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import MagicMock

import pytest

from utils.mem0_client import AsyncMem0Client


@pytest.mark.asyncio
async def test_create_supports_async_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    import utils.mem0_client as mem0_client

    fake_memory = MagicMock()
    fake_memory.llm = None

    monkeypatch.setattr(mem0_client, "build_local_mem0_config", lambda _c: {})

    async def _fake_from_config(config: dict[str, object]) -> object:
        assert config == {}
        return fake_memory

    monkeypatch.setattr(mem0_client.AsyncMemory, "from_config", _fake_from_config)

    client = AsyncMem0Client({})

    try:
        created = await client.create()
        assert created is fake_memory
        assert client.memory is fake_memory
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_create_supports_sync_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    import utils.mem0_client as mem0_client

    fake_memory = MagicMock()
    fake_memory.llm = None

    monkeypatch.setattr(mem0_client, "build_local_mem0_config", lambda _c: {})

    def _fake_from_config(config: dict[str, object]) -> object:
        assert config == {}
        return fake_memory

    monkeypatch.setattr(mem0_client.AsyncMemory, "from_config", _fake_from_config)

    client = AsyncMem0Client({})

    try:
        created = await client.create()
        assert created is fake_memory
        assert client.memory is fake_memory
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_sync_from_config_does_not_block_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import utils.mem0_client as mem0_client

    fake_memory = MagicMock()
    fake_memory.llm = None
    entered = threading.Event()
    release = threading.Event()

    monkeypatch.setattr(mem0_client, "build_local_mem0_config", lambda _c: {})

    def _fake_from_config(_config: dict[str, object]) -> object:
        entered.set()
        release.wait(timeout=1.0)
        return fake_memory

    monkeypatch.setattr(mem0_client.AsyncMemory, "from_config", _fake_from_config)
    client = AsyncMem0Client({}, enable_keepalive=False)
    create_task = asyncio.create_task(client.create())

    try:
        assert await asyncio.to_thread(entered.wait, 0.5)
        start = time.monotonic()
        await asyncio.sleep(0.01)
        assert time.monotonic() - start < 0.2
    finally:
        release.set()
        await create_task
        await client.aclose()


@pytest.mark.asyncio
async def test_concurrent_create_calls_share_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import utils.mem0_client as mem0_client

    fake_memory = MagicMock()
    fake_memory.llm = None
    call_count = 0

    monkeypatch.setattr(mem0_client, "build_local_mem0_config", lambda _c: {})

    def _fake_from_config(_config: dict[str, object]) -> object:
        nonlocal call_count
        call_count += 1
        time.sleep(0.05)
        return fake_memory

    monkeypatch.setattr(mem0_client.AsyncMemory, "from_config", _fake_from_config)
    client = AsyncMem0Client({}, enable_keepalive=False)

    try:
        first, second = await asyncio.gather(client.create(), client.create())
        assert first is fake_memory
        assert second is fake_memory
        assert call_count == 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_timed_out_create_does_not_restart_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import utils.mem0_client as mem0_client

    fake_memory = MagicMock()
    fake_memory.llm = None
    call_count = 0

    monkeypatch.setattr(mem0_client, "build_local_mem0_config", lambda _c: {})

    def _fake_from_config(_config: dict[str, object]) -> object:
        nonlocal call_count
        call_count += 1
        time.sleep(0.05)
        return fake_memory

    monkeypatch.setattr(mem0_client.AsyncMemory, "from_config", _fake_from_config)
    client = AsyncMem0Client({}, enable_keepalive=False)

    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(client.create(), timeout=0.01)
        assert await client.create() is fake_memory
        assert call_count == 1
    finally:
        await client.aclose()
