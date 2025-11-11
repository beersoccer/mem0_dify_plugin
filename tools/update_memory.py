from collections.abc import Generator
import asyncio
from typing import Any
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.config_builder import is_async_mode
from utils.mem0_client import AsyncLocalClient, LocalClient

class UpdateMemoryTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        memory_id = tool_parameters["memory_id"]
        text = tool_parameters["text"]

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            if async_mode:
                client = AsyncLocalClient(self.runtime.credentials)
                loop = AsyncLocalClient.ensure_bg_loop()
                result = asyncio.run_coroutine_threadsafe(
                    client.update(memory_id, {"text": text}),
                    loop,
                ).result()
            else:
                client = LocalClient(self.runtime.credentials)
                result = client.update(memory_id, {"text": text})

            yield self.create_json_message({
                "status": "success",
                "memory": {
                    "id": result.get("id"),
                    "memory": result.get("memory"),
                    "hash": result.get("hash", ""),
                    "metadata": result.get("metadata", {}),
                    "created_at": result.get("created_at"),
                    "updated_at": result.get("updated_at", ""),
                    "user_id": result.get("user_id"),
                    "agent_id": result.get("agent_id"),
                    "run_id": result.get("run_id"),
                }
            })

            text_response = f"Memory updated successfully!\n\n"
            if result.get("id"):
                text_response += f"ID: {result['id']}\n"
            if result.get("memory"):
                text_response += f"Updated Memory: {result['memory']}\n"
            if result.get("updated_at"):
                text_response += f"Updated At: {result['updated_at']}\n"

            yield self.create_text_message(text_response)

        except Exception as e:
            error_message = f"Error: {str(e)}"
            yield self.create_json_message({"status": "error", "error": error_message})
            yield self.create_text_message(f"Failed to update memory: {error_message}")
