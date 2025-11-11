from collections.abc import Generator
import asyncio
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.config_builder import is_async_mode
from utils.mem0_client import AsyncLocalClient, LocalClient


class GetAllMemoriesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Build params
        params: dict[str, Any] = {}
        if tool_parameters.get("user_id"):
            params["user_id"] = tool_parameters["user_id"]
        if tool_parameters.get("agent_id"):
            params["agent_id"] = tool_parameters["agent_id"]
        if tool_parameters.get("run_id"):
            params["run_id"] = tool_parameters["run_id"]
        if tool_parameters.get("limit"):
            # accepted but currently ignored by client; kept for backward compatibility
            params["limit"] = tool_parameters.get("limit")

        # Validate at least one identifier
        if not any([params.get("user_id"), params.get("agent_id"), params.get("run_id")]):
            error_message = "At least one of user_id, agent_id, or run_id must be provided"
            yield self.create_json_message({"status": "error", "error": error_message})
            yield self.create_text_message(f"Error: {error_message}")
            return

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            if async_mode:
                client = AsyncLocalClient(self.runtime.credentials)
                loop = AsyncLocalClient.ensure_bg_loop()
                results = asyncio.run_coroutine_threadsafe(client.get_all(params), loop).result()
            else:
                client = LocalClient(self.runtime.credentials)
                results = client.get_all(params)

            # JSON output
            memories = []
            for r in results or []:
                if not isinstance(r, dict):
                    continue
                memories.append({
                    "id": r.get("id"),
                    "memory": r.get("memory"),
                    "hash": r.get("hash", ""),
                    "metadata": r.get("metadata", {}),
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at", ""),
                    "user_id": r.get("user_id"),
                    "agent_id": r.get("agent_id"),
                    "run_id": r.get("run_id"),
                })

            yield self.create_json_message({
                "status": "success",
                "count": len(memories),
                "memories": memories,
            })

            # Text output
            text_response = f"Found {len(memories)} memories\n\n"
            if memories:
                for idx, r in enumerate(memories, 1):
                    text_response += f"{idx}. {r.get('memory', '')}\n"
                    text_response += f"   ID: {r.get('id', '')}\n"
                    if r.get("user_id"):
                        text_response += f"   User ID: {r['user_id']}\n"
                    if r.get("agent_id"):
                        text_response += f"   Agent ID: {r['agent_id']}\n"
                    if r.get("metadata"):
                        text_response += f"   Metadata: {r['metadata']}\n"
                    text_response += f"   Created: {r.get('created_at', '')}\n\n"
            else:
                text_response += "No memories found."

            yield self.create_text_message(text_response)

        except Exception as e:
            error_message = f"Error: {str(e)}"
            yield self.create_json_message({"status": "error", "error": error_message})
            yield self.create_text_message(f"Failed to get memories: {error_message}")
