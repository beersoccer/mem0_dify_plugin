from __future__ import annotations

from provider.mem0ai import Mem0Provider


def test_validate_credentials_uses_static_config_only(monkeypatch) -> None:
    import provider.mem0ai as provider_mod

    captured: dict[str, object] = {}

    def _fake_build(credentials):  # noqa: ANN001
        captured["credentials"] = credentials
        return {"vector_store": {"provider": "pgvector", "config": {}}}

    monkeypatch.setattr(provider_mod, "build_local_mem0_config", _fake_build)

    provider = object.__new__(Mem0Provider)
    credentials = {"async_mode": True, "log_level": "INFO"}
    provider._validate_credentials(credentials)

    assert captured["credentials"] is credentials
