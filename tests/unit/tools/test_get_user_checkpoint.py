from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.get_user_checkpoint import GetUserCheckpointTool
from utils.extraction import ConversationCheckpoint, UserCheckpoint


def _extract_text_message(message: object) -> str:
    if isinstance(message, str):
        return message
    for attr in ("message", "text"):
        value = getattr(message, attr, None)
        if isinstance(value, str):
            return value
        nested_text = getattr(value, "text", None)
        if isinstance(nested_text, str):
            return nested_text
    return str(message)


def test_get_user_checkpoint_success() -> None:
    mock_runtime = MagicMock()
    mock_runtime.credentials = {}
    mock_session = MagicMock()
    tool = GetUserCheckpointTool(runtime=mock_runtime, session=mock_session)

    checkpoint = UserCheckpoint(
        conversations={
            "c1": ConversationCheckpoint(
                last_processed_message_id="m1",
                processed_range_start="2026-02-06T00:00:00+00:00",
                processed_range_end="2026-02-07T00:00:00+00:00",
            )
        },
    )

    with (
        patch(
            "tools.get_user_checkpoint.build_local_mem0_config_without_pool",
            return_value={},
        ),
        patch("tools.get_user_checkpoint.SyncMem0Client") as mock_client_cls,
        patch("tools.get_user_checkpoint.SyncCheckpointManager") as mock_mgr_cls,
    ):
        mock_client = MagicMock()
        mock_client.memory = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_mgr = MagicMock()
        mock_mgr.load.return_value = ("cp_1", checkpoint)
        mock_mgr_cls.return_value = mock_mgr

        messages = list(tool._invoke({"user_id": "u1", "app_id": "a1"}))

    assert len(messages) == 2
    mock_mgr.load.assert_called_once_with(user_id="u1", app_id="a1")
    mock_client_cls.assert_called_once_with(
        mock_runtime.credentials,
        enable_keepalive=False,
        config_override={},
    )
    mock_client.close.assert_called_once()
    text = _extract_text_message(messages[1])
    assert "Checkpoint for user u1" in text
    assert "Conversations: 1" in text


def test_get_user_checkpoint_missing_user_id() -> None:
    mock_runtime = MagicMock()
    mock_runtime.credentials = {}
    mock_session = MagicMock()
    tool = GetUserCheckpointTool(runtime=mock_runtime, session=mock_session)

    messages = list(tool._invoke({}))
    assert len(messages) == 2
    text = _extract_text_message(messages[1])
    assert "user_id is required" in text

