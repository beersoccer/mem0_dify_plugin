"""Dify tool: check status of async extraction tasks.

This tool allows querying the status and progress of extraction tasks
that are running in the background.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dify_plugin import Tool

from utils.config_builder import build_local_mem0_config
from utils.logger import get_logger
from utils.mem0_client import Memory
from utils.task_status import load_task_status

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

            _, task_status = load_task_status(base_mem, task_id=task_id)

            if not task_status:
                yield self.create_json_message(
                    {
                        "status": "NOT_FOUND",
                        "task_id": task_id,
                        "message": f"Task {task_id} not found. It may have been completed and cleaned up, or never existed.",
                    }
                )
                yield self.create_text_message(
                    f"Task {task_id} not found. It may have been completed and cleaned up."
                )
                return

            # Build response
            response = {
                "status": "SUCCESS",
                "task_id": task_status.task_id,
                "run_id": task_status.run_id,
                "task_status": task_status.status,  # running/completed/failed
                "progress": round(task_status.progress, 2),  # 0.0-1.0
                "started_at": task_status.started_at,
                "updated_at": task_status.updated_at,
                "user_count": task_status.user_count,
                "processed_users": task_status.processed_users,
                "skipped_users": task_status.skipped_users,
                "scanned_conversations": task_status.scanned_conversations,
                "scanned_messages": task_status.scanned_messages,
                "written_memories": task_status.written_memories,
            }

            if task_status.error:
                response["error"] = task_status.error

            if task_status.final_report:
                response["final_report"] = task_status.final_report

            # Build human-readable message
            status_msg = f"Task {task_id} status: {task_status.status.upper()}"
            if task_status.status == "running":
                status_msg += f" ({task_status.progress * 100:.1f}% complete)"
            status_msg += f"\nProcessed: {task_status.processed_users}/{task_status.user_count} users"
            status_msg += f"\nScanned: {task_status.scanned_conversations} conversations, {task_status.scanned_messages} messages"
            status_msg += f"\nWritten memories: {task_status.written_memories}"

            if task_status.error:
                status_msg += f"\nError: {task_status.error}"

            yield self.create_json_message(response)
            yield self.create_text_message(status_msg)

        except Exception as e:
            logger.exception("Check extraction status failed")
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []},
            )
            yield self.create_text_message(f"Failed to check status: {error_message}")


