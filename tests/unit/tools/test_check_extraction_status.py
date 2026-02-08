from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from tools.check_extraction_status import CheckExtractionStatusTool
from utils.helpers import (
    compute_duration_seconds,
    format_duration_mmss,
    format_task_time_range,
    resolve_task_time_range,
)
from utils.task_status import ExtractionTaskStatus


def _extract_text_message(message: object) -> str:
    if isinstance(message, str):
        return message
    for attr in ("message", "text"):
        value = getattr(message, attr, None)
        if isinstance(value, str):
            return value
        nested_text = getattr(value, "text", None)
        if isinstance(nested_text, str):
            return nested_text
    return str(message)


def test_check_status_includes_actual_processed_counts() -> None:
    mock_runtime = MagicMock()
    mock_runtime.credentials = {}
    mock_session = MagicMock()
    tool = CheckExtractionStatusTool(runtime=mock_runtime, session=mock_session)

    status = ExtractionTaskStatus(
        task_id="task1",
        run_id="run1",
        status="completed",
        started_at="2026-02-04T00:00:00+08:00",
        updated_at="2026-02-06T00:00:00+08:00",
        progress=1.0,
        user_count=2,
        processed_users=2,
        skipped_users=0,
        scanned_conversations=100,
        scanned_messages=251,
        processed_conversations=80,
        processed_messages=200,
        written_memories={"episodic": 29, "procedural": 108, "semantic": 43},
    )

    with (
        patch(
            "tools.check_extraction_status.build_local_mem0_config_without_pool",
            return_value={},
        ),
        patch("tools.check_extraction_status.SyncMem0Client") as mock_client_cls,
        patch("tools.check_extraction_status.SyncTaskStatusManager") as mock_mgr_cls,
    ):
        mock_client = MagicMock()
        mock_client.memory = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_mgr = MagicMock()
        mock_mgr.load.return_value = ("mem_id", status)
        mock_mgr_cls.return_value = mock_mgr

        messages = list(tool._invoke({"task_id": "task1"}))

    assert len(messages) == 2
    text = _extract_text_message(messages[1])
    assert "Users: 2/2 (processed/scanned)" in text
    assert "Conversations: 80/100 (processed/scanned)" in text
    assert "Messages: 200/251 (processed/scanned)" in text
    mock_client_cls.assert_called_once_with(
        mock_runtime.credentials,
        enable_keepalive=False,
        config_override={},
    )
    mock_client.close.assert_called_once()


def test_compute_duration_seconds_with_updated_at() -> None:
    duration = compute_duration_seconds(
        "2026-02-06T00:00:00+00:00", "2026-02-06T00:00:10+00:00"
    )
    assert duration == 10


def test_compute_duration_seconds_missing_start() -> None:
    assert compute_duration_seconds(None, "2026-02-06T00:00:10+00:00") is None


def test_format_duration_mmss() -> None:
    assert format_duration_mmss(10) == "00:10"
    assert format_duration_mmss(70) == "01:10"
    assert format_duration_mmss(3661) == "01:01:01"
    assert format_duration_mmss(None) is None


def test_format_task_time_range() -> None:
    expected_start = datetime.fromisoformat(
        "2026-02-06T00:00:00+00:00"
    ).astimezone().isoformat(timespec="seconds")
    expected_end = datetime.fromisoformat(
        "2026-02-06T00:00:10+00:00"
    ).astimezone().isoformat(timespec="seconds")
    start, end = format_task_time_range(
        "2026-02-06T00:00:00+00:00", "2026-02-06T00:00:10+00:00"
    )
    assert start == expected_start
    assert end == expected_end


def test_time_range_midnight_trimmed_in_status() -> None:
    mock_runtime = MagicMock()
    mock_runtime.credentials = {}
    mock_session = MagicMock()
    tool = CheckExtractionStatusTool(runtime=mock_runtime, session=mock_session)

    status = ExtractionTaskStatus(
        task_id="task1",
        run_id="run1",
        status="completed",
        started_at="2026-02-05T00:00:00+08:00",
        updated_at="2026-02-07T00:00:00+08:00",
        progress=1.0,
        user_count=2,
        processed_users=2,
        skipped_users=0,
        scanned_conversations=100,
        scanned_messages=251,
        processed_conversations=0,
        processed_messages=0,
        written_memories={"episodic": 0, "procedural": 0, "semantic": 0},
        range_start="2026-02-05T00:00:00+08:00",
        range_end="2026-02-07T00:00:00+08:00",
    )

    with (
        patch(
            "tools.check_extraction_status.build_local_mem0_config_without_pool",
            return_value={},
        ),
        patch("tools.check_extraction_status.SyncMem0Client") as mock_client_cls,
        patch("tools.check_extraction_status.SyncTaskStatusManager") as mock_mgr_cls,
    ):
        mock_client = MagicMock()
        mock_client.memory = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_mgr = MagicMock()
        mock_mgr.load.return_value = ("mem_id", status)
        mock_mgr_cls.return_value = mock_mgr

        messages = list(tool._invoke({"task_id": "task1"}))

    text = _extract_text_message(messages[1])
    assert "Time: 2026-02-05 -> 2026-02-07" in text
    mock_client_cls.assert_called_once_with(
        mock_runtime.credentials,
        enable_keepalive=False,
        config_override={},
    )
    mock_client.close.assert_called_once()


def test_format_task_time_range_missing_start() -> None:
    start, end = format_task_time_range(None, "2026-02-06T00:00:10+00:00")
    assert start is None
    assert end is None


def test_format_task_time_range_missing_end() -> None:
    expected_start = datetime.fromisoformat(
        "2026-02-06T00:00:00+00:00"
    ).astimezone().isoformat(timespec="seconds")
    start, end = format_task_time_range("2026-02-06T00:00:00+00:00", None)
    assert start == expected_start
    assert end is None


def test_resolve_task_time_range_prefers_status_fields() -> None:
    start, end = resolve_task_time_range(
        "2026-02-06T00:00:00+00:00",
        "2026-02-06T00:00:10+00:00",
        {
            "start_time": "2026-02-01T00:00:00+00:00",
            "end_time": "2026-02-02T00:00:00+00:00",
        },
    )
    assert start == "2026-02-06T00:00:00+00:00"
    assert end == "2026-02-06T00:00:10+00:00"


def test_resolve_task_time_range_falls_back_to_report() -> None:
    start, end = resolve_task_time_range(
        None,
        None,
        {
            "start_time": "2026-02-01T00:00:00+00:00",
            "end_time": "2026-02-02T00:00:00+00:00",
        },
    )
    assert start == "2026-02-01T00:00:00+00:00"
    assert end == "2026-02-02T00:00:00+00:00"


def test_resolve_task_time_range_empty() -> None:
    start, end = resolve_task_time_range(None, None, None)
    assert start is None
    assert end is None

