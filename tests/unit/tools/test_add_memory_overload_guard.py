from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tools.add_memory import AddMemoryTool


def test_add_memory_async_overload_skips_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When overloaded, add_memory should not enqueue a background task."""
    import tools.add_memory as add_mod

    class FakeClient:
        max_ops = 10

        def get_pending_tasks_count(self) -> int:
            return 999

        def ensure_bg_loop(self):  # pragma: no cover
            raise AssertionError("ensure_bg_loop should not be called on overload")

        def track_bg_task(self, *_a, **_kw):  # pragma: no cover
            raise AssertionError("track_bg_task should not be called on overload")

    def _boom(*_a, **_kw):  # pragma: no cover
        raise AssertionError("run_coroutine_threadsafe should not be called on overload")

    monkeypatch.setattr(add_mod, "get_async_client", lambda _c: FakeClient())
    monkeypatch.setattr(add_mod.asyncio, "run_coroutine_threadsafe", _boom)

    mock_runtime = MagicMock()
    mock_runtime.credentials = {}  # async_mode defaults to True
    tool = AddMemoryTool(runtime=mock_runtime, session=MagicMock())

    # Make message objects easy to assert on
    tool.create_json_message = lambda d: d  # type: ignore[method-assign]
    tool.create_text_message = lambda t: t  # type: ignore[method-assign]

    msgs = list(
        tool._invoke(
            {
                "user_id": "u1",
                "agent_id": "bot-1",
                "user": "hi",
                "assistant": "",
                "timeout": 1,
            }
        )
    )

    assert len(msgs) == 2
    assert isinstance(msgs[0], dict)
    assert msgs[0]["status"] == "OVERLOAD"
    assert "results" in msgs[0]
    assert isinstance(msgs[1], str)


