from __future__ import annotations

from utils import mem0_client


class DummyLLM:
    pass


class DummyMemory:
    def __init__(self) -> None:
        self.llm = DummyLLM()


def test_sync_client_uses_config_override(monkeypatch) -> None:
    def _fail_build_local(_credentials):  # noqa: ANN001
        raise AssertionError("build_local_mem0_config should not be called")

    monkeypatch.setattr(mem0_client, "build_local_mem0_config", _fail_build_local)
    monkeypatch.setattr(mem0_client.Memory, "from_config", lambda _cfg: DummyMemory())

    client = mem0_client.SyncMem0Client(
        credentials={},
        enable_keepalive=False,
        config_override={"llm": {}, "embedder": {}, "vector_store": {}},
    )

    assert isinstance(client.memory, DummyMemory)

