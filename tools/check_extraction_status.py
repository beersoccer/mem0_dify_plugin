"""Dify tool: check status of async extraction tasks.

This tool allows querying the status and progress of extraction tasks
that are running in the background.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dify_plugin import Tool

from utils.config_builder import build_local_mem0_config
from utils.helpers import (
    compute_duration_seconds,
    format_duration_mmss,
    format_task_time_range,
    resolve_task_time_range,
    strip_tz_offset,
    trim_midnight_timestamp,
)
from utils.logger import get_logger
from utils.mem0_client import Memory
from utils.task_status import SyncTaskStatusManager

if TYPE_CHECKING:
    from collections.abc import Generator

    from dify_plugin.entities.tool import ToolInvokeMessage

logger = get_logger(__name__)


class CheckExtractionStatusTool(Tool):
    """Check the status of an extraction task."""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Query extraction task status."""
        try:
            task_id = (tool_parameters.get("task_id") or "").strip()
            if not task_id:
                msg = "task_id is required"
                yield self.create_json_message(
                    {"status": "ERROR", "messages": msg, "results": []}
                )
                yield self.create_text_message(f"Failed to check status: {msg}")
                return

            # Load task status from Mem0
            base_cfg = build_local_mem0_config(self.runtime.credentials)
            base_mem = Memory.from_config(base_cfg)

            task_status_mgr = SyncTaskStatusManager(base_mem)
            _, task_status = task_status_mgr.load(task_id=task_id)

            if not task_status:
                logger.info("Check task status: task_id=%s, status=not_found", task_id)
                yield self.create_json_message(
                    {
                        "status": "NOT_FOUND",
                        "task_id": task_id,
                        "message": (
                            f"Task {task_id} not found. It may have been completed "
                            "and cleaned up, or never existed."
                        ),
                    }
                )
                yield self.create_text_message(
                    f"Task {task_id} not found. It may have been completed and cleaned up."
                )
                return

            # Build response
            duration_seconds = compute_duration_seconds(
                task_status.started_at, task_status.updated_at
            )
            duration_display = format_duration_mmss(duration_seconds)
            range_start, range_end = resolve_task_time_range(
                task_status.range_start,
                task_status.range_end,
                task_status.final_report,
            )
            def _format_range_value(value: object) -> str | None:
                if not value or not isinstance(value, str):
                    return None
                value = strip_tz_offset(value)
                return trim_midnight_timestamp(value)

            start_display = _format_range_value(range_start)
            end_display = _format_range_value(range_end)
            if start_display is None:
                start_display, end_display = format_task_time_range(
                    range_start, range_end
                )
            time_range_display = None
            if start_display is not None:
                end_value = end_display or "N/A"
                time_range_display = f"{start_display} -> {end_value}"

            response = {
                "status": "SUCCESS",
                "task_id": task_status.task_id,
                "run_id": task_status.run_id,
                "task_status": task_status.status,  # running/completed/failed
                "progress": round(task_status.progress, 2),  # 0.0-1.0
                "started_at": task_status.started_at,
                "updated_at": task_status.updated_at,
                "range_start": range_start,
                "range_end": range_end,
                "time_range_display": time_range_display,
                "duration_seconds": duration_seconds,
                "duration_display": duration_display,
                "user_count": task_status.user_count,
                "processed_users": task_status.processed_users,
                "skipped_users": task_status.skipped_users,
                "scanned_conversations": task_status.scanned_conversations,
                "scanned_messages": task_status.scanned_messages,
                "processed_conversations": task_status.processed_conversations,
                "processed_messages": task_status.processed_messages,
                "written_memories": task_status.written_memories,
            }

            if task_status.error:
                response["error"] = task_status.error

            if task_status.final_report:
                response["final_report"] = task_status.final_report

            # Build human-readable message
            status_msg = f"Task: {task_id}"
            status_msg += f"\nStatus: {task_status.status.upper()}"
            if task_status.status == "running":
                status_msg += f" ({task_status.progress * 100:.1f}% complete)"
            if time_range_display is not None:
                status_msg += f"\nTime: {time_range_display}"
            if duration_display is not None:
                status_msg += f"\nDuration: {duration_display}"
            status_msg += (
                f"\nUsers: {task_status.processed_users}/{task_status.user_count} "
                "(processed/scanned)"
            )
            status_msg += (
                f"\nConversations: {task_status.processed_conversations}/"
                f"{task_status.scanned_conversations} (processed/scanned)"
            )
            status_msg += (
                f"\nMessages: {task_status.processed_messages}/"
                f"{task_status.scanned_messages} (processed/scanned)"
            )
            status_msg += f"\nMemories: {task_status.written_memories}"

            if task_status.error:
                status_msg += f"\nError: {task_status.error}"

            logger.info(
                "Check task status: task_id=%s, status=%s",
                task_id,
                task_status.status,
            )
            yield self.create_json_message(response)
            yield self.create_text_message(status_msg)

        except Exception as e:
            logger.exception("Check extraction status failed")
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []},
            )
            yield self.create_text_message(f"Failed to check status: {error_message}")


