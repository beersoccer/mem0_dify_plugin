from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from utils.background_loop import BackgroundEventLoop
from utils.task_status import AsyncTaskStatusManager, ExtractionTaskStatus


def _run_coroutine_in_thread(coro: Coroutine[Any, Any, Any]) -> None:
    loop = BackgroundEventLoop.ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    future.result(timeout=5.0)


def test_async_update_progress_accepts_processed_counts() -> None:
    async def _run() -> None:
        manager = AsyncTaskStatusManager(mem=MagicMock())
        status = ExtractionTaskStatus(
            task_id="task1",
            run_id="run1",
            status="running",
            started_at="2026-02-01T00:00:00Z",
            updated_at="2026-02-01T00:00:00Z",
            progress=0.0,
            user_count=2,
            processed_users=0,
            skipped_users=0,
            scanned_conversations=0,
            scanned_messages=0,
            processed_conversations=0,
            processed_messages=0,
            written_memories={"semantic": 0, "episodic": 0, "procedural": 0},
        )
        manager.load = AsyncMock(return_value=("mem_id", status))
        manager.save = AsyncMock(return_value=(True, "mem_id"))

        ok = await manager.update_progress(
            task_id="task1",
            processed_users=1,
            total_users=2,
            scanned_conversations=10,
            scanned_messages=20,
            processed_conversations=8,
            processed_messages=16,
            written_memories={"semantic": 1, "episodic": 0, "procedural": 0},
        )

        assert ok is True
        assert status.processed_conversations == 8
        assert status.processed_messages == 16
        manager.save.assert_awaited_once()

    _run_coroutine_in_thread(_run())


def test_async_mark_completed_updates_processed_counts() -> None:
    async def _run() -> None:
        manager = AsyncTaskStatusManager(mem=MagicMock())
        status = ExtractionTaskStatus(
            task_id="task1",
            run_id="run1",
            status="running",
            started_at="2026-02-01T00:00:00Z",
            updated_at="2026-02-01T00:00:00Z",
            progress=0.0,
            user_count=2,
            processed_users=0,
            skipped_users=0,
            scanned_conversations=0,
            scanned_messages=0,
            processed_conversations=0,
            processed_messages=0,
            written_memories={"semantic": 0, "episodic": 0, "procedural": 0},
        )
        manager.load = AsyncMock(return_value=("mem_id", status))
        manager.save = AsyncMock(return_value=(True, "mem_id"))
        final_report = {
            "summary": {
                "processed_users": 2,
                "skipped_users": 0,
                "scanned_conversations": 100,
                "scanned_messages": 200,
                "processed_conversations": 80,
                "processed_messages": 160,
                "written_memories": {"semantic": 1, "episodic": 2, "procedural": 3},
            }
        }

        ok = await manager.mark_completed(task_id="task1", final_report=final_report)

        assert ok is True
        assert status.status == "completed"
        assert status.processed_conversations == 80
        assert status.processed_messages == 160
        manager.save.assert_awaited_once()

    _run_coroutine_in_thread(_run())

