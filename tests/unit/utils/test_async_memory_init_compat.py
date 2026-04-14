from __future__ import annotations

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
