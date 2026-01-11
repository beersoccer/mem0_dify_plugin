"""Dify tool for updating a memory in Mem0 by ID."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from dify_plugin import Tool
from utils.config_builder import is_async_mode
from utils.constants import UPDATE_ACCEPT_RESULT, WRITE_OPERATION_TIMEOUT
from utils.helpers import parse_timeout
from utils.logger import get_logger
from utils.mem0_client import (
    get_async_client,
    get_sync_client,
)
from utils.memory_tool_helpers import (
    init_request_context,
    yield_error,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from dify_plugin.entities.tool import ToolInvokeMessage

logger = get_logger(__name__)


class UpdateMemoryTool(Tool):
    """Tool that updates a memory by ID."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Invoke the tool.

        Args:
            tool_parameters (dict): Tool parameters.

        Returns:
            Generator[ToolInvokeMessage, None, None]: Generator of tool invoke messages.

        """
        # Initialize request context
        request_id, start_time = init_request_context(tool_parameters)

        memory_id = tool_parameters.get("memory_id")
        if not memory_id:
            yield from yield_error(self, request_id, "memory_id is required", "update memory", {})
            return

        text = tool_parameters.get("text")
        if not text:
            yield from yield_error(self, request_id, "text is required", "update memory", {})
            return

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"

            timeout = parse_timeout(
                tool_parameters.get("timeout"),
                WRITE_OPERATION_TIMEOUT,
                logger,
                "update",
            )

            # Log operation start
            logger.info(
                "[req:%s] Update memory started (mode: %s, memory_id: %s)",
                request_id,
                mode_str,
                memory_id,
            )

            if not async_mode:
                # Sync mode: directly call update and catch exceptions
                client = get_sync_client(self.runtime.credentials)
                try:
                    result = client.update(memory_id, {"text": text})
                    elapsed = time.time() - start_time
                    logger.info(
                        "[req:%s] Update memory completed "
                        "(mode: %s, memory_id: %s, duration: %.2fs)",
                        request_id,
                        mode_str,
                        memory_id,
                        elapsed,
                    )
                    yield self.create_json_message({
                        "status": "SUCCESS",
                        "messages": {"memory_id": memory_id, "text": text},
                        "results": result,
                    })
                    yield self.create_text_message(
                        f"Memory {memory_id} updated to '{text}' successfully!",
                    )
                except (ValueError, AttributeError):
                    # Mem0 throws ValueError or AttributeError when memory not found
                    elapsed = time.time() - start_time
                    logger.warning(
                        "[req:%s] Memory not found (memory_id: %s, duration: %.2fs)",
                        request_id,
                        memory_id,
                        elapsed,
                    )
                    error_message = f"Memory not found: {memory_id}"
                    yield self.create_json_message(
                        {"status": "NOT_FOUND", "messages": error_message, "results": {}},
                    )
                    yield self.create_text_message(f"Error: {error_message}")
            else:
                client = get_async_client(self.runtime.credentials)
                # Submit update to background event loop without awaiting (non-blocking)
                # Fire-and-forget: exceptions in background execution won't be caught here
                loop = client.ensure_bg_loop()
                future = asyncio.run_coroutine_threadsafe(
                    client.update(memory_id, {"text": text}, timeout_s=timeout),
                    loop,
                )
                client.track_bg_task(
                    future,
                    f"update_memory(memory_id={memory_id}, req_id={request_id})",
                )

                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": {"memory_id": memory_id, "text": text},
                    **UPDATE_ACCEPT_RESULT,
                })
                yield self.create_text_message(
                    "Memory update has been accepted and will be processed asynchronously.",
                )

        except Exception as e:
            # Catch all other exceptions to ensure workflow continues
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Update memory failed (memory_id: %s, duration: %.2fs)",
                request_id,
                memory_id,
                elapsed,
            )
            error_message = f"Error: {e!s}"
            yield from yield_error(self, request_id, error_message, "update memory", {})
