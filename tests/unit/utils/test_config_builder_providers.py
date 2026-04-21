"""Tests for provider configuration support in config_builder.py.

Verifies that all mainstream mem0-supported providers (LLMs, Vector Databases,
Embedding Models, Rerankers) can be correctly parsed and assembled by
build_local_mem0_config(). These tests act as a compatibility gate during
version upgrades — if a provider string or required field changes, these tests
catch the drift before it reaches production.

Provider name strings are canonical: a wrong provider name causes mem0 to raise
"Unknown provider" at runtime, so exact matching is critical.

Sources:
  https://docs.mem0.ai/components/llms/overview
  https://docs.mem0.ai/components/embeddings/overview
  https://docs.mem0.ai/components/vectordbs/overview
  https://docs.mem0.ai/components/rerankers/overview
"""

from __future__ import annotations

import json
from typing import Any

import pytest

import utils.config_builder as cb
from utils.config_builder import build_local_mem0_config
from utils.pgvector_config import normalize_pgvector_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build(
    llm: dict[str, Any],
    embedder: dict[str, Any],
    vector_store: dict[str, Any],
    reranker: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build config from component dicts, clearing cache to ensure isolation."""
    creds: dict[str, Any] = {
        "local_llm_json_secret": json.dumps(llm),
        "local_embedder_json_secret": json.dumps(embedder),
        "local_vector_db_json_secret": json.dumps(vector_store),
    }
    if reranker is not None:
        creds["local_reranker_json_secret"] = json.dumps(reranker)
    cb._built_config_cache.clear()
    return build_local_mem0_config(creds)


# ---------------------------------------------------------------------------
# Shared baseline components (used as non-varying context in focused tests)
# ---------------------------------------------------------------------------

_BASE_LLM = {
    "provider": "openai",
    "config": {"model": "gpt-4o-mini", "temperature": 0.1, "max_tokens": 2000},
}
_BASE_EMBEDDER = {
    "provider": "openai",
    "config": {"model": "text-embedding-3-small", "embedding_dims": 1536},
}
_BASE_QDRANT = {
    "provider": "qdrant",
    "config": {"collection_name": "mem0", "host": "localhost", "port": 6333},
}


# ===========================================================================
# LLM provider tests
# ===========================================================================

class TestLLMProviders:
    """Verify all mainstream LLM providers are parsed correctly.

    Each test confirms:
    1. The provider name string is preserved exactly (canonical name match)
    2. The model field is preserved
    3. The config dict is structured correctly
    """

    LLM_CONFIGS: list[tuple[str, dict[str, Any]]] = [
        ("openai", {
            "provider": "openai",
            "config": {
                "model": "gpt-4o-mini",
                "temperature": 0.1,
                "max_tokens": 2000,
                "api_key": "sk-test",
            },
        }),
        ("anthropic", {
            "provider": "anthropic",
            "config": {
                "model": "claude-opus-4-6",
                "temperature": 0.1,
                "max_tokens": 2000,
                "api_key": "sk-ant-test",
            },
        }),
        ("azure_openai", {
            "provider": "azure_openai",
            "config": {
                "model": "gpt-4o-mini",
                "temperature": 0.1,
                "max_tokens": 2000,
                "azure_kwargs": {
                    "azure_deployment": "my-deployment",
                    "api_version": "2024-02-01",
                    "azure_endpoint": "https://my.openai.azure.com",
                    "api_key": "azure-key",
                },
            },
        }),
        ("ollama", {
            "provider": "ollama",
            "config": {
                "model": "llama3.1:latest",
                "temperature": 0.1,
                "max_tokens": 2000,
                "ollama_base_url": "http://localhost:11434",
            },
        }),
        ("gemini", {
            "provider": "gemini",
            "config": {
                "model": "gemini-2.0-flash-001",
                "temperature": 0.2,
                "max_tokens": 2000,
                "api_key": "google-key",
            },
        }),
        ("deepseek", {
            "provider": "deepseek",
            "config": {
                "model": "deepseek-chat",
                "temperature": 0.1,
                "max_tokens": 2000,
                "api_key": "ds-key",
            },
        }),
        ("groq", {
            "provider": "groq",
            "config": {
                "model": "llama-3.1-70b-versatile",
                "temperature": 0.1,
                "max_tokens": 2000,
                "api_key": "groq-key",
            },
        }),
        ("litellm", {
            "provider": "litellm",
            "config": {
                "model": "gpt-4o-mini",
                "temperature": 0.1,
                "max_tokens": 2000,
            },
        }),
        ("mistral", {
            "provider": "mistral",
            "config": {
                "model": "mistral-large-latest",
                "temperature": 0.1,
                "max_tokens": 2000,
                "api_key": "mistral-key",
            },
        }),
        ("together", {
            "provider": "together",
            "config": {
                "model": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
                "temperature": 0.1,
                "max_tokens": 2000,
                "api_key": "together-key",
            },
        }),
    ]

    @pytest.mark.parametrize("name,llm_cfg", LLM_CONFIGS, ids=[x[0] for x in LLM_CONFIGS])
    def test_llm_provider_name_and_model_preserved(
        self, name: str, llm_cfg: dict[str, Any]
    ) -> None:
        """Provider name and model field are preserved exactly after parsing."""
        config = _build(llm_cfg, _BASE_EMBEDDER, _BASE_QDRANT)
        llm = config["llm"]
        assert llm["provider"] == name, (
            f"Provider name mismatch: expected '{name}', got '{llm['provider']}'. "
            "This is the canonical string mem0 uses to load the implementation."
        )
        assert isinstance(llm["config"], dict)
        assert llm["config"]["model"] == llm_cfg["config"]["model"]

    def test_openai_temperature_and_max_tokens_preserved(self) -> None:
        config = _build(_BASE_LLM, _BASE_EMBEDDER, _BASE_QDRANT)
        llm_cfg = config["llm"]["config"]
        assert llm_cfg["temperature"] == 0.1
        assert llm_cfg["max_tokens"] == 2000

    def test_azure_openai_azure_kwargs_fully_preserved(self) -> None:
        """azure_kwargs nested dict must be preserved — it carries all Azure-specific auth."""
        llm = {
            "provider": "azure_openai",
            "config": {
                "model": "gpt-4o-mini",
                "azure_kwargs": {
                    "azure_deployment": "my-deployment",
                    "api_version": "2024-02-01",
                    "azure_endpoint": "https://my.openai.azure.com",
                    "api_key": "azure-key",
                },
            },
        }
        config = _build(llm, _BASE_EMBEDDER, _BASE_QDRANT)
        az = config["llm"]["config"]["azure_kwargs"]
        assert az["azure_deployment"] == "my-deployment"
        assert az["api_version"] == "2024-02-01"
        assert az["azure_endpoint"] == "https://my.openai.azure.com"

    def test_ollama_base_url_preserved(self) -> None:
        """ollama_base_url must reach the final config so mem0 connects to the right server."""
        llm = {
            "provider": "ollama",
            "config": {
                "model": "llama3.1:latest",
                "ollama_base_url": "http://localhost:11434",
            },
        }
        config = _build(llm, _BASE_EMBEDDER, _BASE_QDRANT)
        assert config["llm"]["config"]["ollama_base_url"] == "http://localhost:11434"

    def test_anthropic_api_key_preserved(self) -> None:
        llm = {
            "provider": "anthropic",
            "config": {"model": "claude-opus-4-6", "api_key": "sk-ant-test"},
        }
        config = _build(llm, _BASE_EMBEDDER, _BASE_QDRANT)
        assert config["llm"]["config"]["api_key"] == "sk-ant-test"


# ===========================================================================
# Embedding Model provider tests
# ===========================================================================

class TestEmbedderProviders:
    """Verify all mainstream embedding model providers are parsed correctly."""

    EMBEDDER_CONFIGS: list[tuple[str, dict[str, Any]]] = [
        ("openai_small", {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small",
                "embedding_dims": 1536,
                "api_key": "sk-test",
            },
        }),
        ("openai_large", {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-large",
                "embedding_dims": 3072,
            },
        }),
        ("azure_openai", {
            "provider": "azure_openai",
            "config": {
                "model": "text-embedding-3-large",
                "embedding_dims": 3072,
                "azure_kwargs": {
                    "api_version": "2024-02-01",
                    "azure_deployment": "embed-deploy",
                    "azure_endpoint": "https://my.openai.azure.com",
                    "api_key": "azure-key",
                },
            },
        }),
        ("ollama_mxbai", {
            "provider": "ollama",
            "config": {
                "model": "mxbai-embed-large",
                "embedding_dims": 1024,
                "ollama_base_url": "http://localhost:11434",
            },
        }),
        ("ollama_nomic", {
            "provider": "ollama",
            "config": {
                "model": "nomic-embed-text:latest",
                "embedding_dims": 768,
            },
        }),
        ("gemini", {
            "provider": "gemini",
            "config": {
                "model": "models/gemini-embedding-001",
                "embedding_dims": 1536,
                "api_key": "google-key",
            },
        }),
        ("huggingface", {
            "provider": "huggingface",
            "config": {
                "model": "sentence-transformers/all-MiniLM-L6-v2",
                "embedding_dims": 384,
            },
        }),
        ("together", {
            "provider": "together",
            "config": {
                "model": "togethercomputer/m2-bert-80M-32k-retrieval",
                "embedding_dims": 768,
                "api_key": "together-key",
            },
        }),
    ]

    @pytest.mark.parametrize(
        "name,emb_cfg",
        EMBEDDER_CONFIGS,
        ids=[x[0] for x in EMBEDDER_CONFIGS],
    )
    def test_embedder_provider_name_and_model_preserved(
        self, name: str, emb_cfg: dict[str, Any]
    ) -> None:
        """Provider name and model field are preserved exactly after parsing."""
        config = _build(_BASE_LLM, emb_cfg, _BASE_QDRANT)
        emb = config["embedder"]
        assert emb["provider"] == emb_cfg["provider"], (
            f"Provider name mismatch for '{name}': expected '{emb_cfg['provider']}', "
            f"got '{emb['provider']}'."
        )
        assert isinstance(emb["config"], dict)
        assert emb["config"]["model"] == emb_cfg["config"]["model"]

    def test_openai_embedding_dims_preserved(self) -> None:
        """embedding_dims controls vector dimensionality — must match the vector DB."""
        emb = {
            "provider": "openai",
            "config": {"model": "text-embedding-3-large", "embedding_dims": 3072},
        }
        config = _build(_BASE_LLM, emb, _BASE_QDRANT)
        assert config["embedder"]["config"]["embedding_dims"] == 3072

    def test_azure_openai_embedder_azure_kwargs_preserved(self) -> None:
        """azure_kwargs for embedder must be preserved (auth/endpoint for Azure)."""
        emb = {
            "provider": "azure_openai",
            "config": {
                "model": "text-embedding-3-large",
                "azure_kwargs": {
                    "api_version": "2024-02-01",
                    "azure_deployment": "embed-deploy",
                    "azure_endpoint": "https://my.openai.azure.com",
                    "api_key": "azure-key",
                },
            },
        }
        config = _build(_BASE_LLM, emb, _BASE_QDRANT)
        az = config["embedder"]["config"]["azure_kwargs"]
        assert az["azure_deployment"] == "embed-deploy"
        assert az["api_version"] == "2024-02-01"

    def test_ollama_embedder_base_url_preserved(self) -> None:
        emb = {
            "provider": "ollama",
            "config": {
                "model": "nomic-embed-text:latest",
                "ollama_base_url": "http://localhost:11434",
            },
        }
        config = _build(_BASE_LLM, emb, _BASE_QDRANT)
        assert config["embedder"]["config"]["ollama_base_url"] == "http://localhost:11434"

    def test_gemini_model_path_preserved(self) -> None:
        """Gemini model uses path-style name 'models/gemini-embedding-001'."""
        emb = {
            "provider": "gemini",
            "config": {"model": "models/gemini-embedding-001"},
        }
        config = _build(_BASE_LLM, emb, _BASE_QDRANT)
        assert config["embedder"]["config"]["model"] == "models/gemini-embedding-001"


# ===========================================================================
# Vector Database provider tests
# ===========================================================================

class TestVectorDBProviders:
    """Verify all mainstream vector DB providers are parsed correctly (non-pgvector)."""

    VECTOR_DB_CONFIGS: list[tuple[str, dict[str, Any]]] = [
        ("qdrant_host_port", {
            "provider": "qdrant",
            "config": {
                "collection_name": "mem0",
                "host": "localhost",
                "port": 6333,
                "embedding_model_dims": 1536,
            },
        }),
        ("qdrant_url_api_key", {
            "provider": "qdrant",
            "config": {
                "collection_name": "mem0",
                "url": "https://my-cluster.qdrant.io:6333",
                "api_key": "qdrant-cloud-key",
                "embedding_model_dims": 1536,
            },
        }),
        ("qdrant_on_disk", {
            "provider": "qdrant",
            "config": {
                "collection_name": "mem0",
                "url": "https://my-cluster.qdrant.io",
                "api_key": "qdrant-key",
                "embedding_model_dims": 1536,
                "on_disk": True,
            },
        }),
        ("chroma_local", {
            "provider": "chroma",
            "config": {
                "collection_name": "memories",
                "path": "./chroma_db",
            },
        }),
        ("chroma_server", {
            "provider": "chroma",
            "config": {
                "collection_name": "memories",
                "host": "localhost",
                "port": 8000,
            },
        }),
        ("chroma_cloud", {
            "provider": "chroma",
            "config": {
                "collection_name": "memories",
                "api_key": "chroma-cloud-key",
                "tenant": "my-tenant",
            },
        }),
        ("milvus_local", {
            "provider": "milvus",
            "config": {
                "collection_name": "mem0",
                "url": "http://localhost:19530",
                "embedding_model_dims": 1536,
                "metric_type": "L2",
            },
        }),
        ("milvus_zilliz", {
            "provider": "milvus",
            "config": {
                "collection_name": "mem0",
                "url": "https://my-cluster.zillizcloud.com",
                "token": "zilliz-token",
                "embedding_model_dims": 1536,
            },
        }),
        ("weaviate_local", {
            "provider": "weaviate",
            "config": {
                "collection_name": "Mem0",
                "cluster_url": "http://localhost:8080",
                "embedding_model_dims": 1536,
            },
        }),
        ("weaviate_cloud", {
            "provider": "weaviate",
            "config": {
                "collection_name": "Mem0",
                "cluster_url": "https://my-cluster.weaviate.io",
                "auth_client_secret": "weaviate-key",
                "embedding_model_dims": 1536,
            },
        }),
        ("mongodb", {
            "provider": "mongodb",
            "config": {
                "collection_name": "memories",
                "db_name": "mem0_db",
                "embedding_model_dims": 1536,
                "connection_string": "mongodb://localhost:27017",
            },
        }),
        ("redis", {
            "provider": "redis",
            "config": {
                "collection_name": "memories",
                "embedding_model_dims": 1536,
                "url": "redis://localhost:6379",
            },
        }),
        ("elasticsearch", {
            "provider": "elasticsearch",
            "config": {
                "collection_name": "memories",
                "embedding_model_dims": 1536,
                "host": "localhost",
                "port": 9200,
            },
        }),
        ("opensearch", {
            "provider": "opensearch",
            "config": {
                "collection_name": "memories",
                "embedding_model_dims": 1536,
                "host": "localhost",
                "port": 9200,
            },
        }),
    ]

    @pytest.mark.parametrize(
        "name,vs_cfg",
        VECTOR_DB_CONFIGS,
        ids=[x[0] for x in VECTOR_DB_CONFIGS],
    )
    def test_vector_db_provider_name_preserved(
        self, name: str, vs_cfg: dict[str, Any]
    ) -> None:
        """Provider name is preserved exactly — mem0 uses it to load the DB backend."""
        config = _build(_BASE_LLM, _BASE_EMBEDDER, vs_cfg)
        vs = config["vector_store"]
        assert vs["provider"] == vs_cfg["provider"], (
            f"Provider name mismatch for '{name}': expected '{vs_cfg['provider']}', "
            f"got '{vs['provider']}'."
        )
        assert isinstance(vs["config"], dict)

    def test_qdrant_collection_name_preserved(self) -> None:
        vs = {
            "provider": "qdrant",
            "config": {"collection_name": "my_memories", "host": "localhost", "port": 6333},
        }
        config = _build(_BASE_LLM, _BASE_EMBEDDER, vs)
        assert config["vector_store"]["config"]["collection_name"] == "my_memories"

    def test_qdrant_embedding_dims_preserved(self) -> None:
        """embedding_model_dims drives index creation — must survive config building."""
        vs = {
            "provider": "qdrant",
            "config": {
                "host": "localhost",
                "port": 6333,
                "embedding_model_dims": 768,
            },
        }
        config = _build(_BASE_LLM, _BASE_EMBEDDER, vs)
        assert config["vector_store"]["config"]["embedding_model_dims"] == 768

    def test_qdrant_api_key_preserved(self) -> None:
        vs = {
            "provider": "qdrant",
            "config": {
                "url": "https://my-cluster.qdrant.io",
                "api_key": "secret-key",
                "embedding_model_dims": 1536,
            },
        }
        config = _build(_BASE_LLM, _BASE_EMBEDDER, vs)
        assert config["vector_store"]["config"]["api_key"] == "secret-key"

    def test_milvus_metric_type_preserved(self) -> None:
        vs = {
            "provider": "milvus",
            "config": {
                "url": "http://localhost:19530",
                "metric_type": "COSINE",
                "embedding_model_dims": 1536,
            },
        }
        config = _build(_BASE_LLM, _BASE_EMBEDDER, vs)
        assert config["vector_store"]["config"]["metric_type"] == "COSINE"

    def test_weaviate_auth_client_secret_preserved(self) -> None:
        vs = {
            "provider": "weaviate",
            "config": {
                "cluster_url": "https://my.weaviate.io",
                "auth_client_secret": "wv-key",
                "embedding_model_dims": 1536,
            },
        }
        config = _build(_BASE_LLM, _BASE_EMBEDDER, vs)
        assert config["vector_store"]["config"]["auth_client_secret"] == "wv-key"

    def test_chroma_path_preserved(self) -> None:
        vs = {
            "provider": "chroma",
            "config": {"collection_name": "test", "path": "./my_chroma_db"},
        }
        config = _build(_BASE_LLM, _BASE_EMBEDDER, vs)
        assert config["vector_store"]["config"]["path"] == "./my_chroma_db"


# ===========================================================================
# pgvector-specific tests (normalisation pipeline)
# ===========================================================================

class TestPGVectorConfig:
    """pgvector has its own normalisation pipeline — tests cover all connection paths.

    Connection priority (highest → lowest):
      1. connection_pool  (pre-built pool object)
      2. connection_string  (PostgreSQL DSN)
      3. Individual params  (user/password/host/port/dbname)
    """

    def test_pgvector_provider_name_is_exact(self) -> None:
        """'pgvector' is the exact canonical provider string used by mem0."""
        vs = {
            "provider": "pgvector",
            "config": {
                "connection_string": "postgresql://user:pass@localhost:5432/postgres",
                "collection_name": "mem0",
                "embedding_model_dims": 1536,
            },
        }
        config = _build(_BASE_LLM, _BASE_EMBEDDER, vs)
        assert config["vector_store"]["provider"] == "pgvector"

    def test_pgvector_connection_string_accepted_and_normalised(self) -> None:
        """connection_string path: accepted, keepalive params injected."""
        raw = {
            "connection_string": "postgresql://user:pass@localhost:5432/postgres",
            "collection_name": "memories",
            "embedding_model_dims": 1536,
        }
        result = normalize_pgvector_config(raw, create_pool=False)
        cs = result["connection_string"]
        assert cs.startswith("postgresql://")
        # TCP keepalive best-practice params must be injected
        assert "keepalives=1" in cs
        assert "keepalives_idle=30" in cs
        assert "keepalives_interval=10" in cs
        assert "keepalives_count=3" in cs

    def test_pgvector_individual_params_build_connection_string(self) -> None:
        """user/password/host/port/dbname are assembled into a connection_string."""
        raw = {
            "user": "mem0user",
            "password": "secret",
            "host": "db.example.com",
            "port": "5432",
            "dbname": "mem0db",
            "collection_name": "memories",
            "embedding_model_dims": 1536,
        }
        result = normalize_pgvector_config(raw, create_pool=False)
        assert "connection_string" in result
        cs = result["connection_string"]
        assert "mem0user" in cs
        assert "db.example.com" in cs
        assert "mem0db" in cs

    def test_pgvector_sslmode_injected_into_connection_string(self) -> None:
        """sslmode appears as query param in the built connection_string."""
        raw = {
            "user": "user",
            "password": "pass",
            "host": "secure.example.com",
            "port": "5432",
            "dbname": "postgres",
            "sslmode": "require",
            "collection_name": "mem0",
        }
        result = normalize_pgvector_config(raw, create_pool=False)
        cs = result.get("connection_string", "")
        assert "sslmode=require" in cs

    def test_pgvector_connection_pool_takes_highest_priority(self) -> None:
        """Pre-built connection_pool bypasses all other connection logic."""
        fake_pool = object()
        raw = {
            "connection_pool": fake_pool,
            "connection_string": "postgresql://user:pass@localhost:5432/postgres",
            "user": "user",
            "password": "pass",
            "collection_name": "mem0",
            "embedding_model_dims": 1536,
        }
        result = normalize_pgvector_config(raw, create_pool=False)
        assert result["connection_pool"] is fake_pool
        # Individual connection params should be stripped
        assert "user" not in result
        assert "password" not in result

    def test_pgvector_defaults_to_hnsw_index_when_unspecified(self) -> None:
        """No index specified → defaults to hnsw=True, diskann=False.
        Matches Mem0's PGVectorConfig defaults to prevent 'no index' surprises.
        """
        raw = {
            "connection_pool": object(),
            "collection_name": "mem0",
        }
        result = normalize_pgvector_config(raw, create_pool=False)
        assert result.get("hnsw") is True
        assert result.get("diskann") is False

    def test_pgvector_explicit_diskann_true_is_preserved(self) -> None:
        raw = {
            "connection_pool": object(),
            "collection_name": "mem0",
            "diskann": True,
            "hnsw": False,
        }
        result = normalize_pgvector_config(raw, create_pool=False)
        assert result["diskann"] is True
        assert result["hnsw"] is False

    def test_pgvector_explicit_hnsw_false_is_preserved(self) -> None:
        raw = {
            "connection_pool": object(),
            "collection_name": "mem0",
            "hnsw": False,
            "diskann": False,
        }
        result = normalize_pgvector_config(raw, create_pool=False)
        assert result["hnsw"] is False
        assert result["diskann"] is False

    def test_pgvector_collection_name_preserved(self) -> None:
        raw = {
            "connection_pool": object(),
            "collection_name": "my_custom_collection",
            "embedding_model_dims": 1536,
        }
        result = normalize_pgvector_config(raw, create_pool=False)
        assert result["collection_name"] == "my_custom_collection"

    def test_pgvector_embedding_model_dims_preserved(self) -> None:
        raw = {
            "connection_pool": object(),
            "collection_name": "mem0",
            "embedding_model_dims": 768,
        }
        result = normalize_pgvector_config(raw, create_pool=False)
        assert result["embedding_model_dims"] == 768

    def test_pgvector_missing_user_password_returns_without_connection_string(self) -> None:
        """Individual params path without user/password cannot build a connection_string."""
        raw = {
            "host": "localhost",
            "port": "5432",
            # intentionally missing user and password
            "collection_name": "mem0",
        }
        result = normalize_pgvector_config(raw, create_pool=False)
        # Without credentials, normalisation returns original or skips DSN building
        assert "connection_string" not in result or result is raw

    def test_pgvector_minconn_maxconn_defaults_set(self) -> None:
        """minconn/maxconn defaults are set even when not explicitly provided."""
        raw = {
            "connection_pool": object(),
            "collection_name": "mem0",
        }
        result = normalize_pgvector_config(raw, create_pool=False)
        # Plugin-defined defaults should be set
        assert "minconn" in result
        assert "maxconn" in result
        assert isinstance(result["minconn"], int)
        assert isinstance(result["maxconn"], int)

    def test_pgvector_normalisation_via_build_local_config(self) -> None:
        """pgvector normalisation is triggered inside build_local_mem0_config."""
        vs = {
            "provider": "pgvector",
            "config": {
                "connection_string": "postgresql://user:pass@localhost:5432/postgres",
                "collection_name": "mem0",
                "embedding_model_dims": 1536,
            },
        }
        config = _build(_BASE_LLM, _BASE_EMBEDDER, vs)
        vs_cfg = config["vector_store"]["config"]
        # After normalisation, keepalive params should be present
        cs = vs_cfg.get("connection_string", "")
        assert "keepalives=1" in cs


# ===========================================================================
# Reranker provider tests
# ===========================================================================

class TestRerankerProviders:
    """Verify all mainstream reranker providers are parsed correctly.

    Reranker is optional — tests verify both presence and absence.
    """

    RERANKER_CONFIGS: list[tuple[str, dict[str, Any]]] = [
        ("cohere_english", {
            "provider": "cohere",
            "config": {
                "model": "rerank-english-v3.0",
                "api_key": "cohere-key",
                "top_k": 5,
            },
        }),
        ("cohere_multilingual", {
            "provider": "cohere",
            "config": {
                "model": "rerank-multilingual-v3.0",
                "top_k": 10,
                "return_documents": False,
            },
        }),
        ("zero_entropy", {
            "provider": "zero_entropy",
            "config": {
                "model": "zerank-1",
                "api_key": "ze-key",
                "top_k": 5,
            },
        }),
        ("zero_entropy_small", {
            "provider": "zero_entropy",
            "config": {
                "model": "zerank-1-small",
                "top_k": 10,
            },
        }),
        ("sentence_transformer", {
            "provider": "sentence_transformer",
            "config": {
                "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
                "device": "cpu",
            },
        }),
        ("huggingface", {
            "provider": "huggingface",
            "config": {
                "model": "BAAI/bge-reranker-large",
                "device": "cpu",
            },
        }),
    ]

    @pytest.mark.parametrize(
        "name,reranker_cfg",
        RERANKER_CONFIGS,
        ids=[x[0] for x in RERANKER_CONFIGS],
    )
    def test_reranker_provider_name_preserved(
        self, name: str, reranker_cfg: dict[str, Any]
    ) -> None:
        """Provider name is preserved exactly — used by mem0 to load the reranker."""
        config = _build(_BASE_LLM, _BASE_EMBEDDER, _BASE_QDRANT, reranker=reranker_cfg)
        assert "reranker" in config
        rr = config["reranker"]
        assert rr["provider"] == reranker_cfg["provider"], (
            f"Reranker provider mismatch for '{name}': "
            f"expected '{reranker_cfg['provider']}', got '{rr['provider']}'."
        )
        assert isinstance(rr["config"], dict)
        assert rr["config"]["model"] == reranker_cfg["config"]["model"]

    def test_cohere_top_k_preserved(self) -> None:
        reranker = {
            "provider": "cohere",
            "config": {"model": "rerank-english-v3.0", "top_k": 7},
        }
        config = _build(_BASE_LLM, _BASE_EMBEDDER, _BASE_QDRANT, reranker=reranker)
        assert config["reranker"]["config"]["top_k"] == 7

    def test_cohere_return_documents_preserved(self) -> None:
        reranker = {
            "provider": "cohere",
            "config": {
                "model": "rerank-english-v3.0",
                "return_documents": True,
                "max_chunks_per_doc": 10,
            },
        }
        config = _build(_BASE_LLM, _BASE_EMBEDDER, _BASE_QDRANT, reranker=reranker)
        rr_cfg = config["reranker"]["config"]
        assert rr_cfg["return_documents"] is True
        assert rr_cfg["max_chunks_per_doc"] == 10

    def test_zero_entropy_model_variants(self) -> None:
        """Both zerank-1 and zerank-1-small are valid model names."""
        for model in ("zerank-1", "zerank-1-small"):
            reranker = {"provider": "zero_entropy", "config": {"model": model}}
            config = _build(_BASE_LLM, _BASE_EMBEDDER, _BASE_QDRANT, reranker=reranker)
            assert config["reranker"]["config"]["model"] == model

    def test_sentence_transformer_device_preserved(self) -> None:
        reranker = {
            "provider": "sentence_transformer",
            "config": {
                "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
                "device": "cpu",
                "batch_size": 32,
            },
        }
        config = _build(_BASE_LLM, _BASE_EMBEDDER, _BASE_QDRANT, reranker=reranker)
        rr_cfg = config["reranker"]["config"]
        assert rr_cfg["device"] == "cpu"
        assert rr_cfg["batch_size"] == 32

    def test_no_reranker_key_absent_from_config(self) -> None:
        """When no reranker credential is provided, 'reranker' key must be absent."""
        config = _build(_BASE_LLM, _BASE_EMBEDDER, _BASE_QDRANT)
        assert "reranker" not in config

    def test_reranker_empty_string_treated_as_absent(self) -> None:
        """Empty string credential means no reranker (same as absent)."""
        creds = {
            "local_llm_json_secret": json.dumps(_BASE_LLM),
            "local_embedder_json_secret": json.dumps(_BASE_EMBEDDER),
            "local_vector_db_json_secret": json.dumps(_BASE_QDRANT),
            "local_reranker_json_secret": "",
        }
        cb._built_config_cache.clear()
        config = build_local_mem0_config(creds)
        assert "reranker" not in config


# ===========================================================================
# Full config assembly tests
# ===========================================================================

class TestFullConfigAssembly:
    """Verify complete config dicts assembled correctly with real-world combinations."""

    def test_required_top_level_keys_always_present(self) -> None:
        config = _build(_BASE_LLM, _BASE_EMBEDDER, _BASE_QDRANT)
        assert "llm" in config
        assert "embedder" in config
        assert "vector_store" in config

    def test_with_reranker_includes_reranker_key(self) -> None:
        reranker = {"provider": "cohere", "config": {"model": "rerank-english-v3.0", "top_k": 5}}
        config = _build(_BASE_LLM, _BASE_EMBEDDER, _BASE_QDRANT, reranker=reranker)
        assert "reranker" in config

    def test_fully_local_ollama_stack(self) -> None:
        """Common self-hosted setup: Ollama LLM + Ollama embedder + Qdrant."""
        llm = {
            "provider": "ollama",
            "config": {"model": "llama3.1:latest", "ollama_base_url": "http://localhost:11434"},
        }
        embedder = {
            "provider": "ollama",
            "config": {
                "model": "nomic-embed-text:latest",
                "embedding_dims": 768,
                "ollama_base_url": "http://localhost:11434",
            },
        }
        vs = {
            "provider": "qdrant",
            "config": {
                "collection_name": "test",
                "host": "localhost",
                "port": 6333,
                "embedding_model_dims": 768,
            },
        }
        config = _build(llm, embedder, vs)
        assert config["llm"]["provider"] == "ollama"
        assert config["embedder"]["provider"] == "ollama"
        assert config["vector_store"]["provider"] == "qdrant"

    def test_openai_llm_with_pgvector_and_cohere_reranker(self) -> None:
        """Typical cloud setup: OpenAI + pgvector + Cohere reranker."""
        vs = {
            "provider": "pgvector",
            "config": {
                "connection_string": "postgresql://user:pass@localhost:5432/postgres",
                "collection_name": "mem0",
                "embedding_model_dims": 1536,
            },
        }
        reranker = {
            "provider": "cohere",
            "config": {"model": "rerank-english-v3.0", "top_k": 5},
        }
        config = _build(_BASE_LLM, _BASE_EMBEDDER, vs, reranker=reranker)
        assert config["llm"]["provider"] == "openai"
        assert config["vector_store"]["provider"] == "pgvector"
        assert config["reranker"]["provider"] == "cohere"

    def test_anthropic_with_qdrant_and_zero_entropy_reranker(self) -> None:
        llm = {"provider": "anthropic", "config": {"model": "claude-opus-4-6"}}
        reranker = {"provider": "zero_entropy", "config": {"model": "zerank-1", "top_k": 5}}
        config = _build(llm, _BASE_EMBEDDER, _BASE_QDRANT, reranker=reranker)
        assert config["llm"]["provider"] == "anthropic"
        assert config["reranker"]["provider"] == "zero_entropy"

    def test_dict_input_equivalent_to_json_string_input(self) -> None:
        """Both dict and JSON-string credential values produce the same output."""
        dict_creds = {
            "local_llm_json_secret": _BASE_LLM,
            "local_embedder_json_secret": _BASE_EMBEDDER,
            "local_vector_db_json_secret": _BASE_QDRANT,
        }
        str_creds = {
            "local_llm_json_secret": json.dumps(_BASE_LLM),
            "local_embedder_json_secret": json.dumps(_BASE_EMBEDDER),
            "local_vector_db_json_secret": json.dumps(_BASE_QDRANT),
        }
        cb._built_config_cache.clear()
        config_dict = build_local_mem0_config(dict_creds)
        cb._built_config_cache.clear()
        config_str = build_local_mem0_config(str_creds)

        assert config_dict["llm"] == config_str["llm"]
        assert config_dict["embedder"] == config_str["embedder"]
        assert config_dict["vector_store"]["provider"] == config_str["vector_store"]["provider"]


# ===========================================================================
# Validation and error handling
# ===========================================================================

class TestConfigValidation:
    """Verify that invalid configs are rejected with descriptive errors."""

    def test_missing_llm_raises_value_error(self) -> None:
        creds = {
            "local_embedder_json_secret": json.dumps(_BASE_EMBEDDER),
            "local_vector_db_json_secret": json.dumps(_BASE_QDRANT),
        }
        cb._built_config_cache.clear()
        with pytest.raises(ValueError, match="[Ll][Ll][Mm]"):
            build_local_mem0_config(creds)

    def test_missing_embedder_raises_value_error(self) -> None:
        creds = {
            "local_llm_json_secret": json.dumps(_BASE_LLM),
            "local_vector_db_json_secret": json.dumps(_BASE_QDRANT),
        }
        cb._built_config_cache.clear()
        with pytest.raises(ValueError, match="[Ee]mbedder"):
            build_local_mem0_config(creds)

    def test_missing_vector_db_raises_value_error(self) -> None:
        creds = {
            "local_llm_json_secret": json.dumps(_BASE_LLM),
            "local_embedder_json_secret": json.dumps(_BASE_EMBEDDER),
        }
        cb._built_config_cache.clear()
        with pytest.raises(ValueError, match="[Vv]ector"):
            build_local_mem0_config(creds)

    def test_invalid_json_raises_value_error(self) -> None:
        creds = {
            "local_llm_json_secret": "not valid json {{{",
            "local_embedder_json_secret": json.dumps(_BASE_EMBEDDER),
            "local_vector_db_json_secret": json.dumps(_BASE_QDRANT),
        }
        cb._built_config_cache.clear()
        with pytest.raises(ValueError):
            build_local_mem0_config(creds)

    def test_missing_provider_field_raises_value_error(self) -> None:
        no_provider = {"config": {"model": "gpt-4o-mini"}}  # 'provider' key absent
        creds = {
            "local_llm_json_secret": json.dumps(no_provider),
            "local_embedder_json_secret": json.dumps(_BASE_EMBEDDER),
            "local_vector_db_json_secret": json.dumps(_BASE_QDRANT),
        }
        cb._built_config_cache.clear()
        with pytest.raises(ValueError):
            build_local_mem0_config(creds)

    def test_missing_config_dict_raises_value_error(self) -> None:
        no_config = {"provider": "openai"}  # 'config' key absent
        creds = {
            "local_llm_json_secret": json.dumps(no_config),
            "local_embedder_json_secret": json.dumps(_BASE_EMBEDDER),
            "local_vector_db_json_secret": json.dumps(_BASE_QDRANT),
        }
        cb._built_config_cache.clear()
        with pytest.raises(ValueError):
            build_local_mem0_config(creds)

    def test_config_value_as_non_dict_raises_value_error(self) -> None:
        config_is_list = {"provider": "openai", "config": ["model", "gpt-4o-mini"]}
        creds = {
            "local_llm_json_secret": json.dumps(config_is_list),
            "local_embedder_json_secret": json.dumps(_BASE_EMBEDDER),
            "local_vector_db_json_secret": json.dumps(_BASE_QDRANT),
        }
        cb._built_config_cache.clear()
        with pytest.raises(ValueError):
            build_local_mem0_config(creds)

    def test_json_with_markdown_code_fences_accepted(self) -> None:
        """Users often paste JSON wrapped in markdown code fences — must be tolerated."""
        fenced = f"```json\n{json.dumps(_BASE_LLM)}\n```"
        creds = {
            "local_llm_json_secret": fenced,
            "local_embedder_json_secret": json.dumps(_BASE_EMBEDDER),
            "local_vector_db_json_secret": json.dumps(_BASE_QDRANT),
        }
        cb._built_config_cache.clear()
        config = build_local_mem0_config(creds)
        assert config["llm"]["provider"] == "openai"

    def test_json_with_single_quotes_accepted(self) -> None:
        """Python-literal style (single quotes) must be tolerated via ast.literal_eval."""
        single_quote_json = "{'provider': 'openai', 'config': {'model': 'gpt-4o-mini'}}"
        creds = {
            "local_llm_json_secret": single_quote_json,
            "local_embedder_json_secret": json.dumps(_BASE_EMBEDDER),
            "local_vector_db_json_secret": json.dumps(_BASE_QDRANT),
        }
        cb._built_config_cache.clear()
        config = build_local_mem0_config(creds)
        assert config["llm"]["provider"] == "openai"

    def test_legacy_field_names_still_accepted(self) -> None:
        """Legacy local_llm_json / local_embedder_json / local_vector_db_json still work."""
        creds = {
            "local_llm_json": json.dumps(_BASE_LLM),
            "local_embedder_json": json.dumps(_BASE_EMBEDDER),
            "local_vector_db_json": json.dumps(_BASE_QDRANT),
        }
        cb._built_config_cache.clear()
        config = build_local_mem0_config(creds)
        assert config["llm"]["provider"] == "openai"

    def test_secret_fields_take_priority_over_legacy_fields(self) -> None:
        """New _secret fields override legacy fields when both are present."""
        creds = {
            "local_llm_json_secret": json.dumps(
                {"provider": "anthropic", "config": {"model": "claude-opus-4-6"}}
            ),
            "local_llm_json": json.dumps(_BASE_LLM),  # should be ignored
            "local_embedder_json_secret": json.dumps(_BASE_EMBEDDER),
            "local_vector_db_json_secret": json.dumps(_BASE_QDRANT),
        }
        cb._built_config_cache.clear()
        config = build_local_mem0_config(creds)
        assert config["llm"]["provider"] == "anthropic"

    def test_empty_provider_string_raises_value_error(self) -> None:
        empty_provider = {"provider": "", "config": {"model": "gpt-4o-mini"}}
        creds = {
            "local_llm_json_secret": json.dumps(empty_provider),
            "local_embedder_json_secret": json.dumps(_BASE_EMBEDDER),
            "local_vector_db_json_secret": json.dumps(_BASE_QDRANT),
        }
        cb._built_config_cache.clear()
        with pytest.raises(ValueError):
            build_local_mem0_config(creds)
