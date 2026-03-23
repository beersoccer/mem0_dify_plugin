from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _sanitize(name: str) -> str:
    allowed = []
    for ch in name:
        if ch.isalnum() or ch in {"-", "_", "."}:
            allowed.append(ch)
        else:
            allowed.append("_")
    return "".join(allowed).strip("._") or "artifact"


def _default_profile() -> str:
    return "ci" if os.getenv("GITHUB_ACTIONS") == "true" else "local"


def _normalize_profile(raw: str) -> str:
    profile = (raw or "").strip().lower()
    return profile if profile in {"local", "remote", "ci"} else _default_profile()


def artifacts_dir() -> Path | None:
    tests_dir = Path(__file__).resolve().parents[1]
    raw = (os.getenv("TEST_ARTIFACTS_DIR") or "").strip()
    if raw:
        candidate = Path(raw)
        if candidate.is_absolute():
            path = candidate
        elif candidate.parts and candidate.parts[0] == "tests":
            path = Path(__file__).resolve().parents[2] / candidate
        else:
            path = tests_dir / candidate
    else:
        profile = _normalize_profile(os.getenv("TEST_PROFILE") or "")
        path = tests_dir / "artifacts" / profile
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json_artifact(name: str, payload: Any) -> Path | None:
    """写入固定名称 artifact，每次覆盖，不追加时间戳。"""
    base = artifacts_dir()
    if base is None:
        return None
    file_path = base / f"{_sanitize(name)}.json"
    file_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return file_path

