"""Dify tool for retrieving memory history from Mem0."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from dify_plugin import Tool
from utils.config_builder import is_async_mode
from utils.constants import READ_OPERATION_TIMEOUT
from utils.helpers import parse_timeout
from utils.logger import get_logger
from utils.mem0_client import get_async_client, get_sync_client
from utils.memory_tool_helpers import (
    build_status_and_message,
    execute_async_read_operation,
    init_request_context,
    validate_memory_id,
    yield_error,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from dify_plugin.entities.tool import ToolInvokeMessage

logger = get_logger(__name__)


class GetMemoryHistoryTool(Tool):
    """Tool that retrieves the change history of a specific memory by ID."""

    def _execute_sync_history(
        self,
        memory_id: str,
        request_id: str,
        mode_str: str,
        start_time: float,
    ) -> list[dict[str, Any]]:
        """Execute history in sync mode and return results."""
        client = get_sync_client(self.runtime.credentials)
        try:
            return client.history(memory_id)
        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] History operation failed with error: %s "
                "(mode: %s, memory_id: %s, duration: %.2fs)",
                request_id,
                type(e).__name__,
                mode_str,
                memory_id,
                elapsed,
            )
            return []

    def _normalize_history(
        self,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Normalize history results to standard format."""
        history = []
        for h in results or []:
            if not isinstance(h, dict):
                continue
            history.append(
                {
                    "memory_id": h.get("memory_id"),
                    "old_memory": h.get("old_memory"),
                    "new_memory": h.get("new_memory"),
                    "event": h.get("event"),
                    "created_at": h.get("created_at"),
                    "updated_at": h.get("updated_at"),
                    "is_deleted": h.get("is_deleted", False),
                },
            )
        return history

    def _format_text_output(
        self,
        history: list[dict[str, Any]],
        memory_id: str,
    ) -> str:
        """Format history as text output."""
        text_response = f"Found {len(history)} history records for memory {memory_id}\n\n"
        if history:
            for idx, h in enumerate(history, 1):
                text_response += (
                    f"{idx}. Memory ID: {h.get('memory_id', '')}\n"
                    f"   Old Memory: {h.get('old_memory', '')}\n"
                    f"   New Memory: {h.get('new_memory', '')}\n"
                    f"   Event: {h.get('event', '')}\n"
                    f"   Created: {h.get('created_at', '')}\n"
                    f"   Updated: {h.get('updated_at', '')}\n"
                    f"   Is Deleted: {h.get('is_deleted', False)}\n\n"
                )
        return text_response

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        # Initialize request context
        request_id, start_time = init_request_context(tool_parameters)

        # Validate memory_id
        memory_id = validate_memory_id(tool_parameters)
        if not memory_id:
            yield from yield_error(
                self, request_id, "memory_id is required", "get memory history", [],
            )
            return

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"

            # Log operation start
            logger.info(
                "[req:%s] Get memory history started (mode: %s, memory_id: %s)",
                request_id,
                mode_str,
                memory_id,
            )

            timeout = parse_timeout(
                tool_parameters.get("timeout"),
                READ_OPERATION_TIMEOUT,
                logger,
                "history",
            )

            # Execute history operation
            results: list[dict[str, Any]] = []
            error_type: str | None = None
            if async_mode:
                client = get_async_client(self.runtime.credentials)
                results, error_type = execute_async_read_operation(
                    self,
                    client.history,
                    (memory_id,),
                    {"timeout_s": timeout},
                    timeout,
                    request_id,
                    mode_str,
                    start_time,
                    f"get_memory_history(memory_id={memory_id})",
                )
            else:
                results = self._execute_sync_history(
                    memory_id, request_id, mode_str, start_time,
                )

            # Normalize results
            history = self._normalize_history(results)

            # Log history information (only for sync mode; async mode logs in callback)
            if not async_mode:
                elapsed = time.time() - start_time
                logger.info(
                    "[req:%s] Get memory history completed (mode: %s, memory_id: %s, "
                    "records: %d, duration: %.2fs)",
                    request_id,
                    mode_str,
                    memory_id,
                    len(history),
                    elapsed,
                )

            # Build result with appropriate status and message
            success_msg = f"Found {len(history)} history records"
            status, messages = build_status_and_message(error_type, success_msg)

            yield self.create_json_message({
                "status": status,
                "messages": messages,
                "results": history,
            })

            # Text output
            text_output = self._format_text_output(history, memory_id)
            yield self.create_text_message(text_output)

        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Get memory history failed (memory_id: %s, duration: %.2fs)",
                request_id,
                memory_id,
                elapsed,
            )
            error_message = f"Error: {e!s}"
            yield from yield_error(self, request_id, error_message, "get memory history", [])
