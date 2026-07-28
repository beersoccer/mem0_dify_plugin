"""Dify tool for adding a memory via Mem0 client."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from dify_plugin import Tool

from utils.config_builder import is_async_mode
from utils.constants import (
    ADD_ACCEPT_RESULT,
    ADD_SKIP_RESULT,
    MAX_PENDING_TASKS_MULTIPLIER,
    WRITE_OPERATION_TIMEOUT,
)
from utils.helpers import log_thread_info, parse_timeout
from utils.logger import get_logger
from utils.mem0_client import (
    get_async_client,
    get_sync_client,
)
from utils.memory_tool_helpers import (
    init_request_context,
    validate_user_id,
    yield_error,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from dify_plugin.entities.tool import ToolInvokeMessage

logger = get_logger(__name__)


class AddMemoryTool(Tool):
    """Tool to add user/assistant messages as a memory."""

    @staticmethod
    def _parse_infer_mode(value: Any) -> bool:
        """Coerce the per-call inference option, defaulting to enabled."""
        if value is None:
            return True
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"false", "0", "no", "n", "off"}:
                return False
            if normalized in {"true", "1", "yes", "y", "on"}:
                return True
        return bool(value)

    def _build_messages(
        self,
        tool_parameters: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Build messages list from user and assistant text."""
        user_text = (tool_parameters.get("user") or "").strip()
        assistant_text = (tool_parameters.get("assistant") or "").strip()

        messages = []
        if user_text:
            messages.append({"role": "user", "content": user_text})
        if assistant_text and assistant_text != user_text:
            messages.append({"role": "assistant", "content": assistant_text})
        return messages

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        user_id: str,
        tool_parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Build payload from messages and optional parameters."""
        payload: dict[str, Any] = {"messages": messages, "user_id": user_id}

        agent_id = tool_parameters.get("agent_id")
        if agent_id:
            payload["agent_id"] = agent_id

        metadata = tool_parameters.get("metadata")
        if metadata:
            payload["metadata"] = metadata

        infer = self._parse_infer_mode(tool_parameters.get("infer"))
        payload["infer"] = infer

        custom_prompt = tool_parameters.get("custom_fact_extraction_prompt")
        if infer and isinstance(custom_prompt, str) and custom_prompt.strip():
            payload["custom_fact_extraction_prompt"] = custom_prompt.strip()

        return payload

    def _should_skip(
        self,
        messages: list[dict[str, str]],
    ) -> bool:
        """Check if memory addition should be skipped due to empty messages."""
        return not messages or not any(
            isinstance(m.get("content"), str) and m["content"].strip() for m in messages
        )

    def _execute_async_add(  # noqa: PLR0913
        self,
        payload: dict[str, Any],
        timeout: float,
        user_id: str,
        request_id: str,
        messages: list[dict[str, str]],
        start_time: float,
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Execute async memory addition."""
        client = get_async_client(self.runtime.credentials)

        # Pre-enqueue overload guard (early reject)
        pending = client.get_pending_tasks_count()
        max_pending = client.max_ops * MAX_PENDING_TASKS_MULTIPLIER
        if pending > max_pending:
            logger.warning(
                "[req:%s] Add skipped before enqueue: queue overloaded "
                "(pending=%d, max=%d, user_id: %s)",
                request_id,
                pending,
                max_pending,
                user_id,
            )
            yield self.create_json_message(
                {
                    "status": "OVERLOAD",
                    "messages": messages,
                    **ADD_SKIP_RESULT,
                }
            )
            yield self.create_text_message(
                "System overloaded, memory add skipped (not enqueued).",
            )
            log_thread_info(logger, request_id, "COMPLETED (OVERLOAD SKIPPED)", start_time)
            return

        loop = client.ensure_bg_loop()
        future = asyncio.run_coroutine_threadsafe(
            client.add(payload, timeout_s=timeout),
            loop,
        )
        client.track_bg_task(
            future,
            f"add_memory(user_id={user_id}, req_id={request_id})",
        )
        yield self.create_json_message(
            {
                "status": "SUCCESS",
                "messages": messages,
                **ADD_ACCEPT_RESULT,
            }
        )
        yield self.create_text_message(
            (
                "Memory analysis has been accepted and will be processed asynchronously."
                if payload.get("infer", True)
                else "Raw memory storage has been accepted and will be processed asynchronously."
            ),
        )
        log_thread_info(logger, request_id, "COMPLETED (ASYNC ACCEPTED)", start_time)

    def _execute_sync_add(  # noqa: PLR0913
        self,
        payload: dict[str, Any],
        user_id: str,
        request_id: str,
        mode_str: str,
        messages: list[dict[str, str]],
        start_time: float,
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Execute sync memory addition."""
        client = get_sync_client(self.runtime.credentials)
        result = client.add(payload)
        elapsed = time.time() - start_time
        logger.info(
            "[req:%s] Add memory completed (mode: %s, user_id: %s, duration: %.2fs)",
            request_id,
            mode_str,
            user_id,
            elapsed,
        )
        yield self.create_json_message(
            {
                "status": "SUCCESS",
                "messages": messages,
                "results": result,
            }
        )
        yield self.create_text_message(
            "Memory analyzed and added synchronously."
            if payload.get("infer", True)
            else "Raw conversation stored synchronously."
        )
        log_thread_info(logger, request_id, "COMPLETED", start_time)

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        # Initialize request context
        request_id, start_time = init_request_context(tool_parameters)

        # Log thread information for debugging concurrent calls
        log_thread_info(logger, request_id, "STARTED", start_time)

        # Validate user_id
        user_id = validate_user_id(tool_parameters)
        if not user_id:
            yield from yield_error(
                self, request_id, "user_id is required", "add memory", {}
            )
            return

        # Build messages and payload
        messages = self._build_messages(tool_parameters)
        payload = self._build_payload(messages, user_id, tool_parameters)

        try:
            # Skip when no messages prepared or only blank content
            if self._should_skip(messages):
                logger.debug(
                    "[req:%s] Skipping memory addition for empty messages (user_id: %s)",
                    request_id,
                    user_id,
                )
                yield self.create_json_message(
                    {
                        "status": "SUCCESS",
                        "messages": messages,
                        **ADD_SKIP_RESULT,
                    }
                )
                yield self.create_text_message(
                    "Skipped memory addition for empty messages."
                )
                return

            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"
            timeout = parse_timeout(
                tool_parameters.get("timeout"),
                WRITE_OPERATION_TIMEOUT,
                logger,
                "add",
            )

            # Log operation start
            logger.info(
                "[req:%s] Add memory started "
                "(mode: %s, infer: %s, custom_prompt: %s, user_id: %s)",
                request_id,
                mode_str,
                payload.get("infer", True),
                bool(payload.get("custom_fact_extraction_prompt")),
                user_id,
            )

            # Execute add operation
            if async_mode:
                yield from self._execute_async_add(
                    payload,
                    timeout,
                    user_id,
                    request_id,
                    messages,
                    start_time,
                )
            else:
                yield from self._execute_sync_add(
                    payload,
                    user_id,
                    request_id,
                    mode_str,
                    messages,
                    start_time,
                )

        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Add memory failed (user_id: %s, duration: %.2fs)",
                request_id,
                user_id,
                elapsed,
            )
            error_message = f"Error: {e!s}"
            yield from yield_error(self, request_id, error_message, "add memory", {})
            # Log thread information even on error
            log_thread_info(logger, request_id, "COMPLETED (ERROR)", start_time)
