from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from utils.dify_client import DifyClient


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _to_iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


@dataclass
class SeededConversation:
    case_name: str
    user_id: str
    conversation_id: str
    message_ids: list[str]
    expected_memory_type: str = ""


@dataclass
class SeedManifest:
    run_id: str
    started_at: str
    finished_at: str
    conversations: list[SeededConversation]

    @property
    def user_ids(self) -> list[str]:
        return sorted({item.user_id for item in self.conversations})

    @property
    def primary_user_id(self) -> str:
        """返回第一个 seed 用户 ID（按字母序排序后的首位）。"""
        ids = self.user_ids
        if not ids:
            raise ValueError("SeedManifest 中没有任何对话，无法获取 primary_user_id")
        return ids[0]

    def conversations_for_user(self, user_id: str) -> list[SeededConversation]:
        """返回指定用户的所有 seeded conversation。"""
        return [c for c in self.conversations if c.user_id == user_id]

    @property
    def primary_conversations(self) -> list[SeededConversation]:
        """返回 primary_user_id 的所有 seeded conversation。"""
        return self.conversations_for_user(self.primary_user_id)

    def started_at_with_buffer(self, seconds: int = -60) -> str:
        """返回 started_at 加上偏移秒数的 ISO 时间字符串，用于时间窗口下边界。"""
        dt = _parse_iso(self.started_at)
        if dt is None:
            return self.started_at
        return _to_iso(dt + timedelta(seconds=seconds))

    def finished_at_with_buffer(self, seconds: int = 60) -> str:
        """返回 finished_at 加上偏移秒数的 ISO 时间字符串，用于时间窗口上边界。"""
        dt = _parse_iso(self.finished_at)
        if dt is None:
            return self.finished_at
        return _to_iso(dt + timedelta(seconds=seconds))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "user_ids": self.user_ids,
            "conversation_ids": [item.conversation_id for item in self.conversations],
            "conversations": [asdict(item) for item in self.conversations],
        }

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_seed_cases(path: Path, section: str = "integration") -> list[dict[str, Any]]:
    """Load seed cases from a YAML file.

    The YAML file is expected to have top-level section keys (e.g. ``integration``,
    ``acceptance``).  Falls back to a legacy ``cases`` key for backward compatibility.

    Args:
        path: Path to the YAML fixture file.
        section: Top-level section to load (default: ``"integration"``).
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return []
    # Prefer the named section; fall back to legacy "cases" key.
    cases = raw.get(section) or raw.get("cases") or []
    if not isinstance(cases, list):
        return []
    return [case for case in cases if isinstance(case, dict) and case.get("enabled", True)]


def _format_value(value: Any, context: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format(**context)
    if isinstance(value, list):
        return [_format_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: _format_value(item, context) for key, item in value.items()}
    return value


def _resolve_case_user_id(case: dict[str, Any], context: dict[str, str], index: int) -> str:
    if case.get("user_id"):
        return str(_format_value(case["user_id"], context))
    template = case.get("user_id_template") or "seed-{short_run_id}-{index}"
    scoped_context = {**context, "index": str(index)}
    return str(_format_value(template, scoped_context))


def _seed_one_conversation(
    client: DifyClient,
    *,
    case: dict[str, Any],
    context: dict[str, str],
    case_name: str,
    user_id: str,
) -> SeededConversation | None:
    """Send all turns for a single case and return a SeededConversation, or None on failure."""
    turns = case.get("turns") or []
    if not isinstance(turns, list) or not turns:
        return None

    conversation_id = ""
    message_ids: list[str] = []
    for turn in turns:
        turn_payload = turn if isinstance(turn, dict) else {"query": str(turn)}
        response = client.send_chat_message(
            query=str(_format_value(turn_payload["query"], context)),
            user_id=user_id,
            conversation_id=conversation_id or None,
            inputs=_format_value(turn_payload.get("inputs") or {}, context),
            response_mode=str(turn_payload.get("response_mode") or "blocking"),
            files=_format_value(turn_payload.get("files"), context),
            endpoint=str(turn_payload.get("endpoint") or "/chat-messages"),
        )
        conversation_id = str(response.get("conversation_id") or conversation_id)
        message_id = str(response.get("message_id") or "")
        if message_id:
            message_ids.append(message_id)

    if not conversation_id:
        return None
    return SeededConversation(
        case_name=case_name,
        user_id=user_id,
        conversation_id=conversation_id,
        message_ids=message_ids,
        expected_memory_type=str(case.get("memory_type") or "").upper(),
    )


def seed_chatflow_cases(
    client: DifyClient,
    *,
    cases: list[dict[str, Any]],
    run_id: str | None = None,
    extra_per_user: int = 0,
) -> SeedManifest:
    """Seed conversations from *cases* and optionally create extra conversations.

    Args:
        client: DifyClient instance.
        cases: List of case dicts loaded from YAML.
        run_id: Optional fixed run ID (generated if omitted).
        extra_per_user: Number of additional conversations to create for the
            first resolved user (the ``primary_user``). Useful when tests need
            a minimum conversation count (e.g. pagination tests require ≥ 3).
    """
    scoped_run_id = run_id or uuid4().hex
    context = {
        "run_id": scoped_run_id,
        "short_run_id": scoped_run_id[:8],
    }
    started_at = utc_now_iso()
    seeded: list[SeededConversation] = []

    for index, case in enumerate(cases, start=1):
        user_id = _resolve_case_user_id(case, context, index)
        result = _seed_one_conversation(
            client,
            case=case,
            context=context,
            case_name=str(case.get("name") or f"case-{index}"),
            user_id=user_id,
        )
        if result:
            seeded.append(result)

    # Extra conversations for the primary user to satisfy pagination requirements.
    # primary_user is determined *after* all cases are seeded so it matches
    # SeedManifest.primary_user_id (alphabetically first seeded user_id).
    if extra_per_user > 0 and seeded:
        primary_user = sorted({c.user_id for c in seeded})[0]
        # Reuse the first case's turn template; override with a single turn for speed.
        extra_case = {**cases[0], "turns": (cases[0].get("turns") or [{}])[:1]}
        for i in range(extra_per_user):
            result = _seed_one_conversation(
                client,
                case=extra_case,
                context=context,
                case_name=f"extra-{i + 1}",
                user_id=primary_user,
            )
            if result:
                seeded.append(result)

    return SeedManifest(
        run_id=scoped_run_id,
        started_at=started_at,
        finished_at=utc_now_iso(),
        conversations=seeded,
    )
