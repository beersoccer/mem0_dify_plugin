from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.update_memory import UpdateMemoryTool


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


def test_update_memory_rejects_non_uuid_memory_id() -> None:
    mock_runtime = MagicMock()
    mock_runtime.credentials = {}
    mock_session = MagicMock()
    tool = UpdateMemoryTool(runtime=mock_runtime, session=mock_session)

    with patch("tools.update_memory.get_sync_client") as mock_client:
        messages = list(
            tool._invoke(
                {
                    "memory_id": "extract_db075755aa22",
                    "text": "test",
                }
            )
        )

    assert len(messages) == 2
    text = _extract_text_message(messages[1])
    assert "memory_id must be a valid UUID" in text
    mock_client.assert_not_called()

