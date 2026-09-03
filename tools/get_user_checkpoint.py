"""Dify tool: get user checkpoint for extraction runs."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from dify_plugin import Tool

from utils.checkpoint import SyncCheckpointManager
from utils.config_builder import build_local_mem0_config_without_pool
from utils.logger import get_logger
from utils.mem0_client import SyncMem0Client

if TYPE_CHECKING:
    from collections.abc import Generator

    from dify_plugin.entities.tool import ToolInvokeMessage

logger = get_logger(__name__)


class GetUserCheckpointTool(Tool):
    """Get extraction checkpoint for a user (optionally scoped by app)."""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            user_id = (tool_parameters.get("user_id") or "").strip()
            if not user_id:
                msg = "user_id is required"
                yield self.create_json_message(
                    {"status": "ERROR", "messages": msg, "results": []}
                )
                yield self.create_text_message(f"Failed to get checkpoint: {msg}")
                return

            app_id = (tool_parameters.get("app_id") or "").strip()
            if not app_id:
                msg = "app_id is required"
                yield self.create_json_message(
                    {"status": "ERROR", "messages": msg, "results": []}
                )
                yield self.create_text_message(f"Failed to get checkpoint: {msg}")
                return

            base_cfg = build_local_mem0_config_without_pool(self.runtime.credentials)
            client = SyncMem0Client(
                self.runtime.credentials,
                enable_keepalive=False,
                config_override=base_cfg,
            )
            base_mem = client.memory

            checkpoint_mgr = SyncCheckpointManager(base_mem)
            checkpoint_id, checkpoint = checkpoint_mgr.load(
                user_id=user_id, app_id=app_id
            )

            if not checkpoint:
                logger.info(
                    "Get checkpoint: status=NOT_FOUND, user_id=%s, app_id=%s",
                    user_id,
                    app_id or "None",
                )
                yield self.create_json_message(
                    {
                        "status": "NOT_FOUND",
                        "user_id": user_id,
                    "app_id": app_id,
                        "message": "Checkpoint not found.",
                    }
                )
                yield self.create_text_message(
                f"Checkpoint not found for user {user_id} (app_id={app_id or 'None'})"
                )
                return

            cp_dict = asdict(checkpoint)
            conversations = cp_dict.get("conversations") or {}
            conversations_count = (
                len(conversations) if isinstance(conversations, dict) else 0
            )

            response = {
                "status": "SUCCESS",
                "user_id": user_id,
                "app_id": app_id,
                "checkpoint_id": checkpoint_id,
                "checkpoint": cp_dict,
                "conversations_count": conversations_count,
            }

            text_msg = (
                f"Checkpoint for user {user_id} (app_id={app_id or 'None'})"
                f"\nConversations: {conversations_count}"
            )
            if checkpoint.resume_run_at or checkpoint.resume_conversation_cursor:
                text_msg += (
                    f"\nResume run at: {checkpoint.resume_run_at or 'N/A'}"
                    f"\nResume cursor: {checkpoint.resume_conversation_cursor or 'N/A'}"
                )

            logger.info(
                "Get checkpoint: status=SUCCESS, user_id=%s, app_id=%s, checkpoint_id=%s",
                user_id,
                app_id or "None",
                checkpoint_id,
            )
            yield self.create_json_message(response)
            yield self.create_text_message(text_msg)
            return

        except Exception as e:
            logger.exception(
                "Get checkpoint: status=ERROR, user_id=%s, app_id=%s",
                user_id if "user_id" in locals() else "unknown",
                app_id if "app_id" in locals() else "unknown",
            )
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []},
            )
            yield self.create_text_message(f"Failed to get checkpoint: {error_message}")
        finally:
            if "client" in locals() and client is not None:
                client.close()

