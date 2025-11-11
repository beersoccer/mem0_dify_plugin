from collections.abc import Generator
import asyncio
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.config_builder import is_async_mode
from utils.mem0_client import AsyncLocalClient, LocalClient

class GetMemoryHistoryTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        memory_id = tool_parameters["memory_id"]

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            if async_mode:
                client = AsyncLocalClient(self.runtime.credentials)
                loop = AsyncLocalClient.ensure_bg_loop()
                results = asyncio.run_coroutine_threadsafe(client.history(memory_id), loop).result()
            else:
                client = LocalClient(self.runtime.credentials)
                results = client.history(memory_id)

            yield self.create_json_message({
                "status": "success",
                "memory_id": memory_id,
                "history_count": len(results or []),
                "history": [
                    {
                        "id": h.get("id"),
                        "memory_id": h.get("memory_id"),
                        "prev_value": h.get("prev_value"),
                        "new_value": h.get("new_value"),
                        "event": h.get("event"),
                        "timestamp": h.get("timestamp"),
                        "is_deleted": h.get("is_deleted", False),
                    }
                    for h in (results or [])
                    if isinstance(h, dict)
                ],
            })

            text_response = f"Memory History for ID: {memory_id}\n\n"
            text_response += f"Total changes: {len(results or [])}\n\n"
            if results:
                for idx, h in enumerate(results, 1):
                    text_response += f"{idx}. Event: {h.get('event', 'N/A')}\n"
                    if h.get("prev_value"):
                        text_response += f"   Previous: {h['prev_value']}\n"
                    if h.get("new_value"):
                        text_response += f"   New: {h['new_value']}\n"
                    if h.get("timestamp"):
                        text_response += f"   Timestamp: {h['timestamp']}\n"
                    text_response += "\n"
            else:
                text_response += "No history found for this memory."

            yield self.create_text_message(text_response)

        except Exception as e:
            error_message = f"Error: {str(e)}"
            yield self.create_json_message({"status": "error", "error": error_message})
            yield self.create_text_message(f"Failed to get memory history: {error_message}")
