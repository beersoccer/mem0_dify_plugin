from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from tools.forget_memories import ForgetMemoriesTool


def _extract_json_payload(message: object) -> dict:
    if isinstance(message, dict):
        return message
    nested_message = getattr(message, "message", None)
    json_object = getattr(nested_message, "json_object", None)
    if isinstance(json_object, dict):
        return json_object
    for attr in ("message", "data", "payload", "content"):
        value = getattr(message, attr, None)
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
    return {}


def _build_tool() -> ForgetMemoriesTool:
    mock_runtime = MagicMock()
    mock_runtime.credentials = {}
    mock_session = MagicMock()
    return ForgetMemoriesTool(runtime=mock_runtime, session=mock_session)


def test_forget_memories_dry_run_does_not_delete_or_save() -> None:
    tool = _build_tool()
    mem = MagicMock()
    mem.get_all.side_effect = [
        {"results": [{"id": "m1", "memory": "old fact", "metadata": {}, "created_at": "t"}]},
        {"results": [{"id": "cp-old", "created_at": "old"}, {"id": "cp-new", "created_at": "new"}]},
    ]
    client = MagicMock(memory=mem)
    mgr = MagicMock()
    mgr.load.return_value = ("log-1", {"m1": {"recall_count": 0}})

    with (
        patch("tools.forget_memories.init_request_context", return_value=("req-1", 0.0)),
        patch("tools.forget_memories.validate_user_id", return_value="u1"),
        patch("tools.forget_memories.get_sync_client", return_value=client),
        patch("tools.forget_memories.SyncAccessLogManager", return_value=mgr),
        patch("tools.forget_memories.should_forget", return_value=True),
        patch("tools.forget_memories.retention_info", return_value={"forget": True}),
        patch("tools.forget_memories.days_since", return_value=1.0),
    ):
        messages = list(tool._invoke({"user_id": "u1", "dry_run": True}))

    # No deletion and no access-log save in dry-run mode.
    mem.delete.assert_not_called()
    mgr.save.assert_not_called()

    payload = _extract_json_payload(messages[0])
    assert payload.get("status") == "SUCCESS"
    result = payload.get("results", {})
    assert result.get("deleted_count") == 1
    assert result.get("checkpoints_cleaned") == 1
    assert result.get("dry_run") is True
    assert len(result.get("would_delete", [])) == 1


def test_forget_memories_updates_log_with_only_successfully_deleted_ids() -> None:
    tool = _build_tool()
    mem = MagicMock()
    mem.get_all.side_effect = [
        {
            "results": [
                {"id": "m1", "memory": "old-1", "metadata": {}, "created_at": "t1"},
                {"id": "m2", "memory": "old-2", "metadata": {}, "created_at": "t2"},
            ]
        },
        {"results": []},  # no checkpoints in this test
    ]

    def _delete_side_effect(mem_id: str) -> None:
        if mem_id == "m1":
            raise RuntimeError("delete failed")

    mem.delete.side_effect = _delete_side_effect

    client = MagicMock(memory=mem)
    mgr = MagicMock()
    mgr.load.return_value = (
        "log-1",
        {"m1": {"x": 1}, "m2": {"x": 2}, "keep": {"x": 3}},
    )

    with (
        patch("tools.forget_memories.init_request_context", return_value=("req-1", 0.0)),
        patch("tools.forget_memories.validate_user_id", return_value="u1"),
        patch("tools.forget_memories.get_sync_client", return_value=client),
        patch("tools.forget_memories.SyncAccessLogManager", return_value=mgr),
        patch("tools.forget_memories.should_forget", return_value=True),
        patch("tools.forget_memories.retention_info", return_value={"forget": True}),
    ):
        list(tool._invoke({"user_id": "u1", "dry_run": False}))

    # Only m2 delete succeeds, so save() must keep m1 and remove m2.
    assert mem.delete.call_count == 2
    mgr.save.assert_called_once()
    save_kwargs = mgr.save.call_args.kwargs
    assert save_kwargs["log_dict"] == {"m1": {"x": 1}, "keep": {"x": 3}}


def test_forget_memories_deletes_old_checkpoints_in_real_run() -> None:
    tool = _build_tool()
    mem = MagicMock()
    mem.get_all.side_effect = [
        {"results": []},  # no regular memories
        {
            "results": [
                {"id": "cp-new", "updated_at": "2026-03-01T00:00:00Z"},
                {"id": "cp-old-1", "updated_at": "2026-02-01T00:00:00Z"},
                {"id": "cp-old-2", "updated_at": "2026-01-01T00:00:00Z"},
            ]
        },
    ]
    client = MagicMock(memory=mem)
    mgr = MagicMock()
    mgr.load.return_value = ("log-1", {})

    with (
        patch("tools.forget_memories.init_request_context", return_value=("req-1", 0.0)),
        patch("tools.forget_memories.validate_user_id", return_value="u1"),
        patch("tools.forget_memories.get_sync_client", return_value=client),
        patch("tools.forget_memories.SyncAccessLogManager", return_value=mgr),
        patch("tools.forget_memories.days_since", return_value=1.0),
    ):
        messages = list(tool._invoke({"user_id": "u1", "dry_run": False}))

    # Newest checkpoint is fresh, so only stale duplicates are deleted.
    deleted_ids = [call.args[0] for call in mem.delete.call_args_list]
    assert deleted_ids == ["cp-old-1", "cp-old-2"]

    payload = _extract_json_payload(messages[0])
    assert payload.get("status") == "SUCCESS"
    assert payload.get("results", {}).get("checkpoints_cleaned") == 2
