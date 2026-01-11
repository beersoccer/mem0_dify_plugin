"""Dify tool for retrieving all memories from Mem0 for a specific user."""

from __future__ import annotations

import json
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
    validate_user_id,
    yield_error,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from dify_plugin.entities.tool import ToolInvokeMessage

logger = get_logger(__name__)


class GetAllMemoriesTool(Tool):
    """Tool that retrieves all memories for a specific user, with optional filtering."""

    def _build_params(
        self,
        tool_parameters: dict[str, Any],
        user_id: str,
    ) -> dict[str, Any] | None:
        """Build params dict from tool_parameters. Returns None if filters JSON is invalid."""
        params: dict[str, Any] = {"user_id": user_id}

        agent_id = tool_parameters.get("agent_id")
        if agent_id:
            params["agent_id"] = agent_id

        limit = tool_parameters.get("limit")
        if limit:
            params["limit"] = limit

        # Parse filters if provided (JSON string)
        filters_str = tool_parameters.get("filters")
        if filters_str:
            try:
                params["filters"] = json.loads(filters_str)
            except json.JSONDecodeError:
                return None

        return params

    def _execute_sync_get_all(
        self,
        params: dict[str, Any],
        user_id: str,
        request_id: str,
        mode_str: str,
        start_time: float,
    ) -> list[dict[str, Any]]:
        """Execute get_all in sync mode and return results."""
        client = get_sync_client(self.runtime.credentials)
        try:
            return client.get_all(params)
        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Get all operation failed with error: %s "
                "(mode: %s, user_id: %s, duration: %.2fs)",
                request_id,
                type(e).__name__,
                mode_str,
                user_id,
                elapsed,
            )
            return []

    def _normalize_results(
        self,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Normalize get_all results to standard format."""
        memories = []
        for r in results or []:
            if not isinstance(r, dict):
                continue
            memories.append(
                {
                    "id": r.get("id"),
                    "memory": r.get("memory"),
                    "metadata": r.get("metadata", {}),
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at", ""),
                },
            )
        return memories

    def _format_text_output(
        self,
        memories: list[dict[str, Any]],
    ) -> str:
        """Format memories as text output."""
        text_response = f"Found {len(memories)} memories\n\n"
        if memories:
            for idx, r in enumerate(memories, 1):
                text_response += (
                    f"{idx}. ID: {r.get('id', '')}\n"
                    f"   Memory: {r.get('memory', '')}\n"
                    f"   Metadata: {r.get('metadata', {})}\n"
                    f"   Created: {r.get('created_at', '')}\n"
                    f"   Updated: {r.get('updated_at', '')}\n\n"
                )
        return text_response

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        # Initialize request context
        request_id, start_time = init_request_context(tool_parameters)

        # Validate required user_id
        user_id = validate_user_id(tool_parameters)
        if not user_id:
            yield from yield_error(self, request_id, "user_id is required", "get all memories", [])
            return

        # Build params
        params = self._build_params(tool_parameters, user_id)
        if params is None:
            yield from yield_error(
                self, request_id, "Invalid JSON format for filters", "get all memories", [],
            )
            return

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"

            # Log operation start
            logger.info(
                "[req:%s] Get all memories started (mode: %s, user_id: %s)",
                request_id,
                mode_str,
                user_id,
            )

            timeout = parse_timeout(
                tool_parameters.get("timeout"),
                READ_OPERATION_TIMEOUT,
                logger,
                "get_all",
            )

            # Execute get_all operation
            results: list[dict[str, Any]] = []
            error_type: str | None = None
            if async_mode:
                client = get_async_client(self.runtime.credentials)
                results, error_type = execute_async_read_operation(
                    self,
                    client.get_all,
                    (params,),
                    {"timeout_s": timeout},
                    timeout,
                    request_id,
                    mode_str,
                    start_time,
                    f"get_all_memories(user_id={user_id})",
                )
            else:
                results = self._execute_sync_get_all(
                    params, user_id, request_id, mode_str, start_time,
                )

            # Log completion (only for sync mode; async mode logs in callback)
            if not async_mode:
                elapsed = time.time() - start_time
                logger.info(
                    "[req:%s] Get all memories completed (mode: %s, found %d memories, "
                    "user_id: %s, duration: %.2fs)",
                    request_id,
                    mode_str,
                    len(results),
                    user_id,
                    elapsed,
                )

            # Normalize results
            memories = self._normalize_results(results)

            # Build result with appropriate status and message
            success_msg = f"Found {len(memories)} memories"
            status, messages = build_status_and_message(error_type, success_msg)

            yield self.create_json_message({
                "status": status,
                "messages": messages,
                "results": memories,
            })

            # Text output
            text_output = self._format_text_output(memories)
            yield self.create_text_message(text_output)

        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Get all memories failed (user_id: %s, duration: %.2fs)",
                request_id,
                user_id,
                elapsed,
            )
            error_message = f"Error: {e!s}"
            yield from yield_error(
                self,
                request_id,
                f"Failed to get memories: {error_message}",
                "get all memories",
                [],
            )
