from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest


def test_execute_async_read_operation_rejects_before_enqueue_when_overloaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Overload guard must run BEFORE scheduling a new background task."""
    import utils.memory_tool_helpers as helpers

    class FakeClient:
        max_ops = 10

        def get_pending_tasks_count(self) -> int:
            return 999

        def ensure_bg_loop(self):  # pragma: no cover
            raise AssertionError("ensure_bg_loop should not be called on overload")

        def track_bg_task(self, *_a, **_kw):  # pragma: no cover
            raise AssertionError("track_bg_task should not be called on overload")

    monkeypatch.setattr(helpers, "get_async_client", lambda _c: FakeClient())

    def _boom(*_a, **_kw):  # pragma: no cover
        raise AssertionError("run_coroutine_threadsafe should not be called on overload")

    monkeypatch.setattr(helpers.asyncio, "run_coroutine_threadsafe", _boom)

    tool = MagicMock()
    tool.runtime.credentials = {}

    result, error_type = helpers.execute_async_read_operation(
        tool_instance=tool,
        operation=MagicMock(),
        operation_args=(),
        operation_kwargs={},
        timeout=1.0,
        request_id="req1",
        mode_str="async",
        start_time=time.time(),
        operation_name="search_memory(user_id=u1)",
    )

    assert result is None
    assert error_type == "OVERLOAD"


