from __future__ import annotations

from utils import mem0_client


class DummyMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.tool_calls = None


class DummyChoice:
    def __init__(self, content: str) -> None:
        self.message = DummyMessage(content)


class DummyResponse:
    def __init__(self, content: str) -> None:
        self.choices = [DummyChoice(content)]


class DummyLLM:
    pass


def test_patch_llm_compat_adds_parse_response() -> None:
    llm = DummyLLM()
    mem0_client._patch_llm_compat(llm)

    assert hasattr(llm, "_parse_response")
    response = DummyResponse("pong")
    assert llm._parse_response(response, None) == "pong"


def test_patch_llm_compat_does_not_override_existing() -> None:
    llm = DummyLLM()

    def _existing_parse_response(response, tools):  # noqa: ANN001
        return "keep"

    llm._parse_response = _existing_parse_response
    mem0_client._patch_llm_compat(llm)

    assert llm._parse_response is _existing_parse_response

