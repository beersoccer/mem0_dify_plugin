from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.delete_memory import DeleteMemoryTool
from tools.get_memory import GetMemoryTool
from tools.update_memory import UpdateMemoryTool
from utils.memory_tool_helpers import (
    memory_matches_scope,
    validate_memory_scope,
)

MEMORY_ID = "31d18038-dce6-4a43-9090-92a0d95a3e90"


def _tool(tool_cls):  # noqa: ANN001, ANN202
    runtime = MagicMock()
    runtime.credentials = {}
    tool = tool_cls(runtime=runtime, session=MagicMock())
    tool.create_json_message = lambda payload: payload
    tool.create_text_message = lambda text: text
    return tool


def test_validate_memory_scope_requires_and_trims_both_ids() -> None:
    assert validate_memory_scope(
        {"user_id": " user-1 ", "agent_id": " bot-1 "}
    ) == ("user-1", "bot-1", None)
    assert validate_memory_scope({"agent_id": "bot-1"}) == (
        None,
        None,
        "user_id is required",
    )
    assert validate_memory_scope({"user_id": "user-1"}) == (
        "user-1",
        None,
        "agent_id is required",
    )


def test_memory_matches_scope_requires_exact_pair() -> None:
    memory = {"user_id": "user-1", "agent_id": "bot-1"}

    assert memory_matches_scope(memory, user_id="user-1", agent_id="bot-1")
    assert not memory_matches_scope(memory, user_id="user-1", agent_id="bot-2")
    assert not memory_matches_scope(memory, user_id="user-2", agent_id="bot-1")
    assert not memory_matches_scope(
        {"user_id": "user-1"},
        user_id="user-1",
        agent_id="bot-1",
    )


def test_get_memory_hides_memory_from_another_robot() -> None:
    tool = _tool(GetMemoryTool)
    client = MagicMock()
    client.get.return_value = {
        "id": MEMORY_ID,
        "memory": "private fact",
        "user_id": "user-1",
        "agent_id": "bot-2",
    }

    with (
        patch("tools.get_memory.is_async_mode", return_value=False),
        patch("tools.get_memory.get_sync_client", return_value=client),
    ):
        messages = list(
            tool._invoke(
                {
                    "memory_id": MEMORY_ID,
                    "user_id": "user-1",
                    "agent_id": "bot-1",
                }
            )
        )

    assert messages[0]["status"] == "NOT_FOUND"
    assert messages[0]["results"] == {}


def test_update_memory_rejects_another_robot_without_mutating() -> None:
    tool = _tool(UpdateMemoryTool)
    client = MagicMock()
    client.get.return_value = {
        "id": MEMORY_ID,
        "memory": "private fact",
        "user_id": "user-1",
        "agent_id": "bot-2",
    }

    with (
        patch("tools.update_memory.is_async_mode", return_value=False),
        patch("tools.update_memory.get_sync_client", return_value=client),
    ):
        messages = list(
            tool._invoke(
                {
                    "memory_id": MEMORY_ID,
                    "text": "changed",
                    "user_id": "user-1",
                    "agent_id": "bot-1",
                }
            )
        )

    assert messages[0]["status"] == "NOT_FOUND"
    client.update.assert_not_called()


def test_delete_memory_rejects_another_robot_without_mutating() -> None:
    tool = _tool(DeleteMemoryTool)
    client = MagicMock()
    client.get.return_value = {
        "id": MEMORY_ID,
        "memory": "private fact",
        "user_id": "user-1",
        "agent_id": "bot-2",
    }

    with (
        patch("tools.delete_memory.is_async_mode", return_value=False),
        patch("tools.delete_memory.get_sync_client", return_value=client),
    ):
        messages = list(
            tool._invoke(
                {
                    "memory_id": MEMORY_ID,
                    "user_id": "user-1",
                    "agent_id": "bot-1",
                }
            )
        )

    assert messages[0]["status"] == "NOT_FOUND"
    client.delete.assert_not_called()


def test_get_memory_async_hides_memory_from_another_robot() -> None:
    tool = _tool(GetMemoryTool)
    client = MagicMock()
    other_robot_memory = {
        "id": MEMORY_ID,
        "memory": "private fact",
        "user_id": "user-1",
        "agent_id": "bot-2",
    }

    with (
        patch("tools.get_memory.is_async_mode", return_value=True),
        patch("tools.get_memory.get_async_client", return_value=client),
        patch(
            "tools.get_memory.execute_async_read_operation",
            return_value=(other_robot_memory, None),
        ),
    ):
        messages = list(
            tool._invoke(
                {
                    "memory_id": MEMORY_ID,
                    "user_id": "user-1",
                    "agent_id": "bot-1",
                }
            )
        )

    assert messages[0]["status"] == "NOT_FOUND"
    assert messages[0]["results"] == {}


def test_update_memory_async_rejects_another_robot_without_mutating() -> None:
    tool = _tool(UpdateMemoryTool)
    client = MagicMock()
    other_robot_memory = {
        "id": MEMORY_ID,
        "memory": "private fact",
        "user_id": "user-1",
        "agent_id": "bot-2",
    }

    with (
        patch("tools.update_memory.is_async_mode", return_value=True),
        patch("tools.update_memory.get_async_client", return_value=client),
        patch(
            "tools.update_memory.execute_async_read_operation",
            return_value=(other_robot_memory, None),
        ),
    ):
        messages = list(
            tool._invoke(
                {
                    "memory_id": MEMORY_ID,
                    "text": "changed",
                    "user_id": "user-1",
                    "agent_id": "bot-1",
                }
            )
        )

    assert messages[0]["status"] == "NOT_FOUND"
    client.update.assert_not_called()


def test_delete_memory_async_rejects_another_robot_without_mutating() -> None:
    tool = _tool(DeleteMemoryTool)
    client = MagicMock()
    other_robot_memory = {
        "id": MEMORY_ID,
        "memory": "private fact",
        "user_id": "user-1",
        "agent_id": "bot-2",
    }

    with (
        patch("tools.delete_memory.is_async_mode", return_value=True),
        patch("tools.delete_memory.get_async_client", return_value=client),
        patch(
            "tools.delete_memory.execute_async_read_operation",
            return_value=(other_robot_memory, None),
        ),
    ):
        messages = list(
            tool._invoke(
                {
                    "memory_id": MEMORY_ID,
                    "user_id": "user-1",
                    "agent_id": "bot-1",
                }
            )
        )

    assert messages[0]["status"] == "NOT_FOUND"
    client.delete.assert_not_called()
