"""Dify tool to package search payload for mem0 client and return results."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from dify_plugin import Tool
from utils.config_builder import is_async_mode
from utils.constants import READ_OPERATION_TIMEOUT, SEARCH_DEFAULT_TOP_K
from utils.helpers import format_recent_timestamp, log_thread_info, parse_timeout
from utils.logger import get_logger
from utils.mem0_client import get_async_client, get_sync_client
from utils.memory_tool_helpers import (
    build_status_and_message,
    execute_async_read_operation,
    init_request_context,
    yield_error,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from dify_plugin.entities.tool import ToolInvokeMessage

logger = get_logger(__name__)


class SearchMemoryTool(Tool):
    """Tool that builds a search payload and delegates to mem0_client.search."""

    def _validate_parameters(
        self,
        tool_parameters: dict[str, Any],
    ) -> tuple[str, str] | None:
        """Validate required parameters and return (query, user_id) or None if invalid."""
        query = tool_parameters.get("query", "")
        if not query:
            return None

        user_id = tool_parameters.get("user_id")
        if not user_id:
            return None

        return (query, user_id)

    def _build_payload(
        self,
        tool_parameters: dict[str, Any],
        query: str,
        user_id: str,
    ) -> tuple[dict[str, Any], str | None]:
        """Build search payload from parameters. Returns (payload, error_msg) or (payload, None)."""
        payload: dict[str, Any] = {"query": query, "user_id": user_id}

        # Optional advanced filters (JSON)
        filters_value = tool_parameters.get("filters")
        if filters_value:
            try:
                payload["filters"] = (
                    json.loads(filters_value)
                    if isinstance(filters_value, str)
                    else filters_value
                )
            except json.JSONDecodeError as json_err:
                return (payload, f"Invalid JSON in filters: {json_err}")

        # Optional scoping fields
        # NOTE: run_id is NOT included in payload - it's only used for request tracing
        agent_id = tool_parameters.get("agent_id")
        if agent_id:
            payload["agent_id"] = agent_id

        # Optional top_k -> limit mapping for mem0_client (default 5)
        top_k = tool_parameters.get("top_k")
        if top_k is None:
            payload["limit"] = SEARCH_DEFAULT_TOP_K
        else:
            try:
                payload["limit"] = int(top_k)
            except (TypeError, ValueError):
                payload["limit"] = top_k

        return (payload, None)

    def _execute_sync_search(
        self,
        payload: dict[str, Any],
        user_id: str,
        request_id: str,
        mode_str: str,
        start_time: float,
    ) -> list[dict[str, Any]]:
        """Execute search in sync mode and return results."""
        client = get_sync_client(self.runtime.credentials)
        try:
            return client.search(payload)
        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Search operation failed with error: %s "
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
        """Normalize search results to standard format."""
        norm_results = []
        for r in results or []:
            if not isinstance(r, dict):
                continue
            timestamp = format_recent_timestamp(
                r.get("created_at"),
                r.get("updated_at"),
            )
            entry = {
                "id": r.get("id"),
                "memory": r.get("memory"),
                "score": r.get("score", 0.0),
                "metadata": r.get("metadata", {}),
            }
            if timestamp:
                entry["timestamp"] = timestamp
            norm_results.append(entry)
        return norm_results

    def _format_text_output(
        self,
        payload: dict[str, Any],
        norm_results: list[dict[str, Any]],
    ) -> str:
        """Format search results as text output."""
        lines = [f"Query: {payload.get('query', '')}", "", "Results:"]
        if norm_results:
            for idx, r in enumerate(norm_results, 1):
                lines.append("")
                lines.append(f"{idx}. Memory: {r.get('memory', '')}")
                score = r.get("score")
                if isinstance(score, (int, float)):
                    lines.append(f"   Score: {score:.2f}")
                md = r.get("metadata")
                if md:
                    lines.append(f"   Metadata: {md}")
                ts_value = r.get("timestamp")
                if ts_value:
                    lines.append(f"   Timestamp: {ts_value}")
        else:
            lines.append("")
            lines.append("No results found.")
        return "\n".join(lines)

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        # Initialize request context
        request_id, start_time = init_request_context(tool_parameters)

        # Validate required fields
        validation_result = self._validate_parameters(tool_parameters)
        if validation_result is None:
            query = tool_parameters.get("query", "")
            error_msg = "query is required" if not query else "user_id is required"
            yield from yield_error(self, request_id, error_msg, "search memory", [])
            return
        query, user_id = validation_result

        # Build payload
        payload, build_error = self._build_payload(tool_parameters, query, user_id)
        if build_error:
            logger.exception("[req:%s] Search memory failed: %s", request_id, build_error)
            yield from yield_error(self, request_id, build_error, "search memory", [])
            return

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"
            timeout = parse_timeout(
                tool_parameters.get("timeout"),
                READ_OPERATION_TIMEOUT,
                logger,
                "search",
            )

            # Log operation start
            logger.info(
                "[req:%s] Search started (mode: %s, user_id: %s)",
                request_id,
                mode_str,
                user_id,
            )

            # Execute search
            results: list[dict[str, Any]] = []
            error_type: str | None = None
            if async_mode:
                client = get_async_client(self.runtime.credentials)
                results, error_type = execute_async_read_operation(
                    self,
                    client.search,
                    (payload,),
                    {"timeout_s": timeout},
                    timeout,
                    request_id,
                    mode_str,
                    start_time,
                    f"search_memory(user_id={user_id})",
                )
            else:
                results = self._execute_sync_search(
                    payload, user_id, request_id, mode_str, start_time,
                )

            # Normalize results
            norm_results = self._normalize_results(results)

            # Log search results (only for sync mode; async mode logs in callback)
            if not async_mode:
                elapsed = time.time() - start_time
                logger.info(
                    "[req:%s] Search completed (mode: %s, user_id: %s, "
                    "found %d results, duration: %.2fs)",
                    request_id,
                    mode_str,
                    user_id,
                    len(norm_results),
                    elapsed,
                )

            # Build result with appropriate status and message
            success_msg = f"Found {len(norm_results)} matching memories"
            status, messages = build_status_and_message(error_type, success_msg)

            yield self.create_json_message({
                "status": status,
                "messages": messages,
                "results": norm_results,
            })

            # Text output (detailed for downstream workflow consumption)
            text_output = self._format_text_output(payload, norm_results)
            yield self.create_text_message(text_output)

            # Log thread information when method completes
            log_thread_info(logger, request_id, "COMPLETED", start_time)

        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Search failed (user_id: %s, duration: %.2fs)",
                request_id,
                user_id,
                elapsed,
            )
            error_message = f"Error: {e!s}"
            yield from yield_error(self, request_id, error_message, "search memory", [])
