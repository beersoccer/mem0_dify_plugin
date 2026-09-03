from __future__ import annotations

import pytest
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from provider.mem0ai import Mem0Provider


def test_validate_credentials_rejects_embedder_provider_in_vector_field(
    monkeypatch,
) -> None:
    import provider.mem0ai as provider_mod

    monkeypatch.setattr(
        provider_mod,
        "build_local_mem0_config",
        lambda _credentials: {
            "vector_store": {
                "provider": "openai",
                "config": {"model": "embedding-model"},
            }
        },
    )

    provider = object.__new__(Mem0Provider)
    with pytest.raises(
        ToolProviderCredentialValidationError,
        match="Vector Database Configuration uses provider 'openai'",
    ):
        provider._validate_credentials({"log_level": "INFO"})
