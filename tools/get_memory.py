"""Dify tool for retrieving a specific memory from Mem0 by ID."""

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
    execute_async_read_operation,
    init_request_context,
    validate_memory_id,
    yield_error,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from dify_plugin.entities.tool import ToolInvokeMessage

logger = get_logger(__name__)


class GetMemoryTool(Tool):
    """Tool that retrieves a specific memory by its ID."""

    def _execute_sync_get(
        self,
        memory_id: str,
        request_id: str,
        mode_str: str,
        start_time: float,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Execute get in sync mode and return (result, error_type)."""
        client = get_sync_client(self.runtime.credentials)
        result: dict[str, Any] | None = None
        error_type: str | None = None
        try:
            result = client.get(memory_id)
        except (ValueError, AttributeError):
            elapsed = time.time() - start_time
            logger.warning(
                "[req:%s] Memory not found (memory_id: %s, duration: %.2fs)",
                request_id,
                memory_id,
                elapsed,
            )
            error_type = "NOT_FOUND"
            result = None
        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Get operation failed with error: %s "
                "(mode: %s, memory_id: %s, duration: %.2fs)",
                request_id,
                type(e).__name__,
                mode_str,
                memory_id,
                elapsed,
            )
            error_type = "ERROR"
            result = None

        return (result, error_type)

    def _normalize_result(
        self,
        result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Normalize get result to standard format."""
        if not result or not isinstance(result, dict):
            return {}
        return {
            "id": result.get("id"),
            "memory": result.get("memory"),
            "metadata": result.get("metadata", {}),
            "created_at": result.get("created_at"),
            "updated_at": result.get("updated_at", ""),
        }

    def _build_status_and_message(
        self,
        error_type: str | None,
        memory_id: str,
        result: dict[str, Any] | None,
    ) -> tuple[str, str]:
        """Build status and message from error type and result."""
        if not result or not isinstance(result, dict):
            if error_type == "TIMEOUT":
                return ("TIMEOUT", f"Operation timed out while retrieving memory: {memory_id}")
            if error_type == "OVERLOAD":
                return ("OVERLOAD", f"System overloaded, unable to retrieve memory: {memory_id}")
            if error_type == "NOT_FOUND":
                return ("NOT_FOUND", f"Memory not found: {memory_id}")
            if error_type == "ERROR":
                return ("ERROR", f"Operation failed while retrieving memory: {memory_id}")
            return ("NOT_FOUND", f"Memory not found: {memory_id}")
        return ("SUCCESS", "Memory retrieved successfully")

    def _format_text_output(
        self,
        result: dict[str, Any],
    ) -> str:
        """Format memory result as text output."""
        return (
            f"Memory Details:\n\n"
            f"ID: {result.get('id', '')}\n"
            f"Memory: {result.get('memory', '')}\n"
            f"Metadata: {result.get('metadata', {})}\n"
            f"Created: {result.get('created_at', '')}\n"
            f"Updated: {result.get('updated_at', '')}\n"
        )

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        # Initialize request context
        request_id, start_time = init_request_context(tool_parameters)

        # Validate memory_id
        memory_id = validate_memory_id(tool_parameters)
        if not memory_id:
            yield from yield_error(self, request_id, "memory_id is required", "get memory", {})
            return

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"
            timeout = parse_timeout(
                tool_parameters.get("timeout"),
                READ_OPERATION_TIMEOUT,
                logger,
                "get",
            )

            # Log operation start
            logger.info(
                "[req:%s] Get memory started (mode: %s, memory_id: %s)",
                request_id,
                mode_str,
                memory_id,
            )

            # Execute get operation
            result: dict[str, Any] | None = None
            error_type: str | None = None
            if async_mode:
                client = get_async_client(self.runtime.credentials)
                result, error_type = execute_async_read_operation(
                    self,
                    client.get,
                    (memory_id,),
                    {"timeout_s": timeout},
                    timeout,
                    request_id,
                    mode_str,
                    start_time,
                    f"get_memory(memory_id={memory_id})",
                )
            else:
                result, error_type = self._execute_sync_get(
                    memory_id, request_id, mode_str, start_time,
                )

            # Check if memory exists or if operation failed
            if not result or not isinstance(result, dict):
                elapsed = time.time() - start_time
                status, messages = self._build_status_and_message(error_type, memory_id, result)
                logger.warning(
                    "[req:%s] Get memory result: %s (memory_id: %s, duration: %.2fs)",
                    request_id,
                    status,
                    memory_id,
                    elapsed,
                )
                yield self.create_json_message({
                    "status": status,
                    "messages": messages,
                    "results": {},
                })
                yield self.create_text_message(f"Error: {messages}")
                return

            # Log completion (only for sync mode; async mode logs in callback)
            if not async_mode:
                elapsed = time.time() - start_time
                logger.info(
                    "[req:%s] Get memory completed (mode: %s, memory_id: %s, duration: %.2fs)",
                    request_id,
                    mode_str,
                    memory_id,
                    elapsed,
                )

            # Normalize and return result
            normalized_result = self._normalize_result(result)
            status, messages = self._build_status_and_message(error_type, memory_id, result)

            yield self.create_json_message({
                "status": status,
                "messages": messages,
                "results": normalized_result,
            })

            text_output = self._format_text_output(normalized_result)
            yield self.create_text_message(text_output)

        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Get memory failed (memory_id: %s, duration: %.2fs)",
                request_id,
                memory_id,
                elapsed,
            )
            error_message = f"Error: {e!s}"
            yield from yield_error(self, request_id, error_message, "get memory", {})
