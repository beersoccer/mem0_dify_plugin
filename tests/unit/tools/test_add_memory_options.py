from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tools.add_memory import AddMemoryTool
from utils.mem0_client import AsyncMem0Client, SyncMem0Client


class RecordingSyncMemory:
    def __init__(self) -> None:
        self.config = SimpleNamespace(custom_fact_extraction_prompt="default prompt")
        self.calls: list[dict] = []

    def add(self, messages, **kwargs):  # noqa: ANN001
        self.calls.append(
            {
                "prompt": self.config.custom_fact_extraction_prompt,
                "messages": messages,
                "kwargs": kwargs,
            }
        )
        return {"results": []}


class RecordingAsyncMemory:
    def __init__(self) -> None:
        self.config = SimpleNamespace(custom_fact_extraction_prompt="default prompt")
        self.calls: list[dict] = []

    async def add(self, messages, **kwargs):  # noqa: ANN001
        self.calls.append(
            {
                "prompt": self.config.custom_fact_extraction_prompt,
                "messages": messages,
                "kwargs": kwargs,
            }
        )
        return {"results": []}


def _tool() -> AddMemoryTool:
    runtime = MagicMock()
    runtime.credentials = {}
    return AddMemoryTool(runtime=runtime, session=MagicMock())


def test_build_payload_defaults_to_infer_enabled() -> None:
    payload = _tool()._build_payload(
        [{"role": "user", "content": "Remember this"}],
        "user-1",
        {},
    )

    assert payload["infer"] is True
    assert "custom_fact_extraction_prompt" not in payload


@pytest.mark.parametrize("value", [False, "false", "0", "off"])
def test_build_payload_supports_raw_storage_mode(value) -> None:  # noqa: ANN001
    payload = _tool()._build_payload(
        [{"role": "user", "content": "Store this verbatim"}],
        "user-1",
        {
            "infer": value,
            "custom_fact_extraction_prompt": "This must be ignored",
        },
    )

    assert payload["infer"] is False
    assert "custom_fact_extraction_prompt" not in payload


def test_build_payload_includes_trimmed_custom_prompt() -> None:
    payload = _tool()._build_payload(
        [{"role": "user", "content": "Remember my preference"}],
        "user-1",
        {
            "infer": True,
            "custom_fact_extraction_prompt": "  Extract preferences only.  ",
        },
    )

    assert payload["custom_fact_extraction_prompt"] == "Extract preferences only."


def test_sync_add_applies_prompt_without_mutating_shared_memory() -> None:
    memory = RecordingSyncMemory()
    client = object.__new__(SyncMem0Client)
    client.memory = memory

    client.add(
        {
            "messages": [{"role": "user", "content": "I like jazz"}],
            "user_id": "user-1",
            "infer": True,
            "custom_fact_extraction_prompt": "Extract music preferences only.",
        }
    )

    assert memory.calls[0]["prompt"] == "Extract music preferences only."
    assert memory.config.custom_fact_extraction_prompt == "default prompt"
    assert memory.calls[0]["kwargs"]["infer"] is True


def test_sync_raw_add_ignores_prompt_and_preserves_messages() -> None:
    memory = RecordingSyncMemory()
    client = object.__new__(SyncMem0Client)
    client.memory = memory
    messages = [
        {"role": "user", "content": "raw user text"},
        {"role": "assistant", "content": "raw assistant text"},
    ]

    client.add(
        {
            "messages": messages,
            "user_id": "user-1",
            "infer": False,
            "custom_fact_extraction_prompt": "Should not be used.",
        }
    )

    assert memory.calls[0]["prompt"] == "default prompt"
    assert memory.calls[0]["messages"] == messages
    assert memory.calls[0]["kwargs"]["infer"] is False


@pytest.mark.asyncio
async def test_async_add_applies_prompt_without_mutating_shared_memory() -> None:
    memory = RecordingAsyncMemory()
    client = object.__new__(AsyncMem0Client)
    client.memory = memory
    client.max_ops = 1
    client._semaphore = asyncio.Semaphore(1)

    async def _create():
        return memory

    client.create = _create

    await client.add(
        {
            "messages": [{"role": "user", "content": "I prefer dark mode"}],
            "user_id": "user-1",
            "infer": True,
            "custom_fact_extraction_prompt": "Extract UI preferences only.",
        },
        timeout_s=5,
    )

    assert memory.calls[0]["prompt"] == "Extract UI preferences only."
    assert memory.config.custom_fact_extraction_prompt == "default prompt"
    assert memory.calls[0]["kwargs"]["infer"] is True
