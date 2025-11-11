from collections.abc import Generator
import asyncio
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.config_builder import is_async_mode
from utils.mem0_client import AsyncLocalClient, LocalClient

class DeleteAllMemoriesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Build params
        params: dict[str, Any] = {}
        if tool_parameters.get("user_id"):
            params["user_id"] = tool_parameters["user_id"]
        if tool_parameters.get("agent_id"):
            params["agent_id"] = tool_parameters["agent_id"]
        if tool_parameters.get("run_id"):
            params["run_id"] = tool_parameters["run_id"]

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
                result = asyncio.run_coroutine_threadsafe(client.delete_all(params), loop).result()
            else:
                client = LocalClient(self.runtime.credentials)
                result = client.delete_all(params)

            yield self.create_json_message({
                "status": "success",
                "message": "All memories deleted successfully",
                "filters": params,
                "result": result,
            })

            text_response = "All memories deleted successfully!\n\nFilters applied:\n"
            for key, value in params.items():
                text_response += f"- {key}: {value}\n"
            yield self.create_text_message(text_response)

        except Exception as e:
            error_message = f"Error: {str(e)}"
            yield self.create_json_message({"status": "error", "error": error_message})
            yield self.create_text_message(f"Failed to delete memories: {error_message}")
