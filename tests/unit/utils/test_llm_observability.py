from __future__ import annotations

from typing import Any

import pytest

import utils.config_builder as config_builder
from utils import mem0_client
from utils.logging_utils import REDACTED_VALUE, format_for_logging


class DummyMessage:
    def __init__(self, content: str, reasoning_content: str | None = None) -> None:
        self.content = content
        self.reasoning_content = reasoning_content


class DummyChoice:
    def __init__(self, content: str, reasoning_content: str | None = None) -> None:
        self.message = DummyMessage(content, reasoning_content)


class DummyResponse:
    def __init__(self, content: str, reasoning_content: str | None = None) -> None:
        self.choices = [DummyChoice(content, reasoning_content)]

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        assert mode == "json"
        message = self.choices[0].message
        return {
            "choices": [
                {
                    "message": {
                        "content": message.content,
                        "reasoning_content": message.reasoning_content,
                    }
                }
            ]
        }


class DummySyncCompletions:
    def __init__(self, response: DummyResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> DummyResponse:
        self.calls.append(kwargs)
        return self.response


class DummyAsyncCompletions(DummySyncCompletions):
    async def create(self, **kwargs: Any) -> DummyResponse:
        self.calls.append(kwargs)
        return self.response


class DummyChat:
    def __init__(self, completions: Any) -> None:
        self.completions = completions


class DummyClient:
    def __init__(self, completions: Any, base_url: str) -> None:
        self.chat = DummyChat(completions)
        self.base_url = base_url


class DummyConfig:
    def __init__(self, model: str) -> None:
        self.model = model


class DummyLLM:
    def __init__(self, completions: Any, base_url: str, model: str) -> None:
        self.client = DummyClient(completions, base_url)
        self.config = DummyConfig(model)


def _capture_info_logs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    messages: list[str] = []

    def _record(message: str, *args: Any, **_kwargs: Any) -> None:
        messages.append(message % args if args else message)

    monkeypatch.setattr(mem0_client.logger, "info", _record)
    return messages


def test_format_for_logging_redacts_nested_credentials() -> None:
    text = format_for_logging(
        {
            "model": "glm-test",
            "api_key": "sk-secret",
            "max_tokens": 2000,
            "headers": {"Authorization": "Bearer private"},
            "vector_store": {
                "password": "database-secret",
                "host": "pgvector",
            },
        }
    )

    assert "glm-test" in text
    assert "pgvector" in text
    assert "2000" in text
    assert REDACTED_VALUE in text
    assert "sk-secret" not in text
    assert "Bearer private" not in text
    assert "database-secret" not in text


def test_sync_observer_logs_exact_endpoint_request_and_glm_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = DummyResponse("final answer", "reasoning details")
    completions = DummySyncCompletions(response)
    llm = DummyLLM(
        completions,
        "https://ark.cn-beijing.volces.com/api/v3/",
        "glm-model",
    )
    logs = _capture_info_logs(monkeypatch)

    mem0_client._install_llm_observability(llm)
    result = llm.client.chat.completions.create(
        model="glm-model",
        messages=[{"role": "user", "content": "hello"}],
        response_format={"type": "json_object"},
        extra_headers={"Authorization": "Bearer hidden"},
    )

    assert result is response
    combined = "\n".join(logs)
    assert (
        "endpoint=https://ark.cn-beijing.volces.com/api/v3/chat/completions"
        in combined
    )
    assert '"response_format": {"type": "json_object"}' in combined
    assert '"reasoning_content": "reasoning details"' in combined
    assert '"content": "final answer"' in combined
    assert "reasoning_content_present" in combined
    assert "Bearer hidden" not in combined
    assert REDACTED_VALUE in combined


def test_observer_is_installed_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    completions = DummySyncCompletions(DummyResponse("ok"))
    llm = DummyLLM(completions, "https://api.deepseek.com", "deepseek-v4-pro")
    _capture_info_logs(monkeypatch)

    mem0_client._install_llm_observability(llm)
    first_wrapper = llm.client.chat.completions.create
    mem0_client._install_llm_observability(llm)

    assert llm.client.chat.completions.create is first_wrapper
    llm.client.chat.completions.create(model="deepseek-v4-pro", messages=[])
    assert len(completions.calls) == 1


@pytest.mark.asyncio
async def test_async_observer_logs_response(monkeypatch: pytest.MonkeyPatch) -> None:
    response = DummyResponse("async final", "async reasoning")
    completions = DummyAsyncCompletions(response)
    llm = DummyLLM(completions, "https://api.deepseek.com", "deepseek-v4-pro")
    logs = _capture_info_logs(monkeypatch)

    mem0_client._install_llm_observability(llm)
    result = await llm.client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert result is response
    combined = "\n".join(logs)
    assert "endpoint=https://api.deepseek.com/chat/completions" in combined
    assert "async final" in combined
    assert "async reasoning" in combined


def test_config_info_log_redacts_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    def _record(message: str, *args: Any, **_kwargs: Any) -> None:
        messages.append(message % args if args else message)

    monkeypatch.setattr(config_builder.logger, "info", _record)
    config_builder._built_config_cache.clear()
    credentials = {
        "local_llm_json_secret": (
            '{"provider":"openai","config":{"model":"glm-test",'
            '"api_key":"sk-llm-secret",'
            '"openai_base_url":"https://example.com/api/v3"}}'
        ),
        "local_embedder_json_secret": (
            '{"provider":"openai","config":{"model":"text-embedding-test",'
            '"embedding_dims":4096}}'
        ),
        "local_vector_db_json_secret": (
            '{"provider":"pgvector","config":{"dbname":"dify",'
            '"user":"postgres","password":"db-secret","host":"pgvector",'
            '"port":"5432","collection_name":"mem0",'
            '"embedding_model_dims":4096}}'
        ),
    }

    config_builder.build_local_mem0_config(credentials)

    combined = "\n".join(messages)
    assert "glm-test" in combined
    assert "https://example.com/api/v3" in combined
    assert "pgvector" in combined
    assert "sk-llm-secret" not in combined
    assert "db-secret" not in combined
    assert REDACTED_VALUE in combined
