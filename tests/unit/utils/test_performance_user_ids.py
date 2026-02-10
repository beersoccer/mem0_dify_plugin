from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[3] / "performance" / "user_ids.py"
    spec = importlib.util.spec_from_file_location("performance_user_ids", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_user_ids_from_count() -> None:
    module = _load_module()
    assert module.build_user_ids("3") == ["user1", "user2", "user3"]


def test_build_user_ids_from_list() -> None:
    module = _load_module()
    assert module.build_user_ids("alice, bob") == ["alice", "bob"]


def test_build_user_ids_from_empty() -> None:
    module = _load_module()
    assert module.build_user_ids("") == ["test_user"]

