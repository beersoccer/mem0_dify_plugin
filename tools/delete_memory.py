from collections.abc import Generator
import asyncio
from typing import Any
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.config_builder import is_async_mode
from utils.mem0_client import AsyncLocalClient, LocalClient

class DeleteMemoryTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        memory_id = tool_parameters["memory_id"]

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            if async_mode:
                client = AsyncLocalClient(self.runtime.credentials)
                loop = AsyncLocalClient.ensure_bg_loop()
                _ = asyncio.run_coroutine_threadsafe(client.delete(memory_id), loop).result()
            else:
                client = LocalClient(self.runtime.credentials)
                _ = client.delete(memory_id)

            yield self.create_json_message({
                "status": "success",
                "message": f"Memory '{memory_id}' deleted successfully",
                "memory_id": memory_id
            })

            yield self.create_text_message(f"Memory deleted successfully!\n\nDeleted Memory ID: {memory_id}")

        except Exception as e:
            error_message = f"Error: {str(e)}"
            yield self.create_json_message({"status": "error", "error": error_message})
            yield self.create_text_message(f"Failed to delete memory: {error_message}")
