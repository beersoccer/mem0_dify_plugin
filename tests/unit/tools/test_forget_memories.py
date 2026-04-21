from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from tools.forget_memories import ForgetMemoriesTool, _clean_expired_locks


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


def _make_lock_memory(
    mem_id: str,
    holder_id: str,
    acquired_at: str,
    ttl_seconds: int,
) -> dict:
    """Build a fake lock memory entry for testing."""
    lock_data = {
        "lock_id": "lock:extraction:u1:*",
        "holder_id": holder_id,
        "acquired_at": acquired_at,
        "ttl_seconds": ttl_seconds,
    }
    return {
        "id": mem_id,
        "memory": json.dumps(lock_data, ensure_ascii=False),
        "metadata": {
            "__internal": True,
            "internal_type": "distributed_lock",
        },
    }


def test_clean_expired_locks_deletes_expired_only() -> None:
    """_clean_expired_locks should delete expired locks and keep active ones."""
    now = datetime.now(UTC)
    expired_time = (now - timedelta(seconds=7200)).isoformat()
    active_time = now.isoformat()

    mem = MagicMock()
    mem.get_all.return_value = {
        "results": [
            _make_lock_memory("lock-1", "run-old", expired_time, 3600),
            _make_lock_memory("lock-2", "run-active", active_time, 3600),
        ]
    }

    count = _clean_expired_locks(
        mem, user_id="u1", app_id=None, dry_run=False, request_id="req-1"
    )

    assert count == 1
    mem.delete.assert_called_once_with("lock-1")


def test_clean_expired_locks_dry_run_does_not_delete() -> None:
    """Dry run should count but not delete."""
    expired_time = (datetime.now(UTC) - timedelta(seconds=7200)).isoformat()

    mem = MagicMock()
    mem.get_all.return_value = {
        "results": [
            _make_lock_memory("lock-1", "run-old", expired_time, 3600),
        ]
    }

    count = _clean_expired_locks(
        mem, user_id="u1", app_id=None, dry_run=True, request_id="req-1"
    )

    assert count == 1
    mem.delete.assert_not_called()


def test_clean_expired_locks_corrupted_record() -> None:
    """Corrupted lock records (unparseable JSON) should be cleaned up."""
    mem = MagicMock()
    mem.get_all.return_value = {
        "results": [
            {
                "id": "lock-corrupt",
                "memory": "not-valid-json",
                "metadata": {
                    "__internal": True,
                    "internal_type": "distributed_lock",
                },
            }
        ]
    }

    count = _clean_expired_locks(
        mem, user_id="u1", app_id=None, dry_run=False, request_id="req-1"
    )

    assert count == 1
    mem.delete.assert_called_once_with("lock-corrupt")


def test_forget_memories_includes_locks_cleaned_in_result() -> None:
    """Integration: ForgetMemoriesTool result should include locks_cleaned."""
    tool = _build_tool()
    mem = MagicMock()

    # Call 1: regular memories, Call 2: checkpoints, Call 3: locks
    expired_time = (datetime.now(UTC) - timedelta(seconds=7200)).isoformat()
    mem.get_all.side_effect = [
        {"results": []},  # no regular memories
        {"results": []},  # no checkpoints
        {
            "results": [
                _make_lock_memory("lock-1", "old-run", expired_time, 3600),
            ]
        },  # one expired lock
    ]
    client = MagicMock(memory=mem)
    mgr = MagicMock()
    mgr.load.return_value = ("log-1", {})

    with (
        patch("tools.forget_memories.init_request_context", return_value=("req-1", 0.0)),
        patch("tools.forget_memories.validate_user_id", return_value="u1"),
        patch("tools.forget_memories.get_sync_client", return_value=client),
        patch("tools.forget_memories.SyncAccessLogManager", return_value=mgr),
    ):
        messages = list(tool._invoke({"user_id": "u1", "dry_run": False}))

    payload = _extract_json_payload(messages[0])
    assert payload.get("status") == "SUCCESS"
    assert payload.get("results", {}).get("locks_cleaned") == 1
