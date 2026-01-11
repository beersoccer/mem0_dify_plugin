"""Dify tool: consolidate long-term memories from Dify conversation history into Mem0.

This tool is implemented according to SPEC.md:
- Input: run_at + user_ids (optional app_id / max_users_per_run / budget_tokens) + Dify API params
- Output: structured run report (SUCCESS/PARTIAL_SUCCESS/ERROR)
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from mem0 import Memory
from utils.checkpoint import load_checkpoint, save_checkpoint
from utils.config_builder import build_local_mem0_config, is_async_mode
from utils.consolidation import UserCheckpoint, scan_user_conversations_incremental
from utils.dify_client import DifyAPIError, DifyClient
from utils.helpers import parse_iso_timestamp
from utils.logger import get_logger
from utils.mem0_consolidation import (
    build_memory_metadata,
    build_subtype_memories,
    mem0_add_segment,
 )

logger = get_logger(__name__)


def _parse_user_ids(value: object) -> list[str]:
    """Parse user_ids input into a list of strings.

    Accepts:
    - list[str] (already parsed by runtime)
    - JSON array string: '["u1","u2"]'
    - comma-separated string: 'u1,u2'
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        ids: list[str] = []
        for x in value:
            if x is None:
                continue
            s = str(x).strip()
            if s:
                ids.append(s)
        return ids
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        # Try JSON list first
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        # Fallback: comma-separated
        return [s.strip() for s in text.split(",") if s.strip()]
    # Fallback: single value
    return [str(value).strip()] if str(value).strip() else []


def _build_run_id(run_at: str, user_ids: list[str], app_id: str | None) -> str:
    base = {
        "run_at": run_at,
        "user_ids": sorted(set(user_ids)),
        "app_id": app_id or "",
    }
    raw = json.dumps(base, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _dedup_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _cmp_iso(a: str | None, b: str | None) -> int:
    """Compare two ISO timestamps; returns -1/0/1 where None is smallest."""
    da = parse_iso_timestamp(a)
    db = parse_iso_timestamp(b)
    if da is None and db is None:
        return 0
    if da is None:
        return -1
    if db is None:
        return 1
    ta = da.timestamp()
    tb = db.timestamp()
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0


def _dify_msg_to_mem0_messages(segment_messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Best-effort normalization from Dify message objects to mem0 {role, content}."""
    out: list[dict[str, str]] = []
    for m in segment_messages:
        # Common Dify fields: query(answer) pairs
        query = m.get("query")
        answer = m.get("answer")
        if isinstance(query, str) and query.strip():
            out.append({"role": "user", "content": query.strip()})
        if isinstance(answer, str) and answer.strip():
            out.append({"role": "assistant", "content": answer.strip()})
            continue

        role = str(m.get("role") or m.get("from") or m.get("type") or "").strip().lower()
        content = m.get("content") or m.get("text") or ""
        if not isinstance(content, str):
            content = str(content)
        content = content.strip()
        if not content:
            continue
        if role in {"user", "human"}:
            out.append({"role": "user", "content": content})
        elif role in {"assistant", "ai"}:
            out.append({"role": "assistant", "content": content})
        else:
            # Unknown role: treat as user content to maximize recall
            out.append({"role": "user", "content": content})
    return out


def _count_add_results(res: object) -> int:
    """Count effective memory operations from Mem0 add() result."""
    if not isinstance(res, dict):
        return 0
    results = res.get("results")
    if isinstance(results, list):
        cnt = 0
        for r in results:
            if not isinstance(r, dict):
                continue
            event = str(r.get("event") or "").upper()
            if event and event != "NONE":
                cnt += 1
        return cnt
    return 0


class ConsolidateLongTermMemoryTool(Tool):
    """Incrementally scan Dify history for specified users and consolidate long-term memories."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            run_at = (tool_parameters.get("run_at") or "").strip()
            if not run_at:
                msg = "run_at is required"
                yield self.create_json_message({"status": "ERROR", "messages": msg, "results": []})
                yield self.create_text_message(f"Failed to consolidate: {msg}")
                return
            if parse_iso_timestamp(run_at) is None:
                msg = "run_at must be ISO8601"
                yield self.create_json_message({"status": "ERROR", "messages": msg, "results": []})
                yield self.create_text_message(f"Failed to consolidate: {msg}")
                return

            user_ids = _parse_user_ids(tool_parameters.get("user_ids"))
            if not user_ids:
                msg = "user_ids is required"
                yield self.create_json_message({"status": "ERROR", "messages": msg, "results": []})
                yield self.create_text_message(f"Failed to consolidate: {msg}")
                return

            dify_base_url = (tool_parameters.get("dify_base_url") or "").strip()
            if not dify_base_url:
                msg = "dify_base_url is required"
                yield self.create_json_message({"status": "ERROR", "messages": msg, "results": []})
                yield self.create_text_message(f"Failed to consolidate: {msg}")
                return

            dify_api_key = (tool_parameters.get("dify_api_key") or "").strip()
            if not dify_api_key:
                msg = "dify_api_key is required"
                yield self.create_json_message({"status": "ERROR", "messages": msg, "results": []})
                yield self.create_text_message(f"Failed to consolidate: {msg}")
                return

            app_id = (tool_parameters.get("app_id") or "").strip() or None
            max_users_per_run = tool_parameters.get("max_users_per_run")
            budget_tokens = tool_parameters.get("budget_tokens")

            # Normalize limits
            try:
                max_users = int(max_users_per_run) if max_users_per_run is not None else 100
            except (TypeError, ValueError):
                max_users = 100
            try:
                budget_total = int(budget_tokens) if budget_tokens is not None else 200_000
            except (TypeError, ValueError):
                budget_total = 200_000
            remaining_budget = max(0, budget_total)

            user_ids = _dedup_keep_order(user_ids)[: max(0, max_users)]
            run_id = _build_run_id(run_at, user_ids, app_id)

            # Create Mem0 instances: 1 base (checkpoint) + 3 subtype memories
            # (semantic/episodic/procedural)
            # Note: We run this tool in a blocking fashion even if async_mode=true,
            # to return a full report.
            _ = is_async_mode(self.runtime.credentials)  # kept for future tuning/diagnostics
            base_cfg = build_local_mem0_config(self.runtime.credentials)
            base_mem = Memory.from_config(base_cfg)
            subtype_mems = build_subtype_memories(self.runtime.credentials)

            dify = DifyClient(dify_base_url, dify_api_key)

            started_at = time.monotonic()
            hard_time_budget_sec = 55.0  # best-effort to fit MAX_REQUEST_TIMEOUT=60

            per_user: list[dict[str, Any]] = []
            checkpoint_updates: list[dict[str, Any]] = []

            summary = {
                "processed_users": 0,
                "skipped_users": 0,
                "scanned_conversations": 0,
                "scanned_messages": 0,
                "written_memories": {"semantic": 0, "episodic": 0, "procedural": 0},
                "budget_tokens": {
                    "total": budget_total,
                    "remaining": remaining_budget,
                    "spent_estimate": 0,
                },
            }

            overall_status = "SUCCESS"

            for uid in user_ids:
                if (time.monotonic() - started_at) > hard_time_budget_sec:
                    overall_status = "PARTIAL_SUCCESS"
                    per_user.append(
                        {"user_id": uid, "status": "SKIPPED", "reason": "time_budget_exceeded"},
                    )
                    summary["skipped_users"] += 1
                    continue

                user_report: dict[str, Any] = {
                    "user_id": uid,
                    "status": "SUCCESS",
                    "skipped": False,
                    "errors": [],
                    "scanned_conversations": 0,
                    "scanned_messages": 0,
                    "written_memories": {"semantic": 0, "episodic": 0, "procedural": 0},
                    "budget_remaining": remaining_budget,
                }

                # Load checkpoint (id + object)
                cp_id, cp = load_checkpoint(base_mem, user_id=uid, app_id=app_id)
                if cp is None:
                    cp = UserCheckpoint()

                # Idempotency: skip if checkpoint.last_run_at >= run_at
                if _cmp_iso(cp.last_run_at, run_at) >= 0:
                    user_report["status"] = "SKIPPED"
                    user_report["skipped"] = True
                    user_report["reason"] = "already_processed"
                    per_user.append(user_report)
                    summary["skipped_users"] += 1
                    continue

                try:
                    segments_by_conv, stats, stop_reason = scan_user_conversations_incremental(
                        dify,
                        user_id=uid,
                        run_at=run_at,
                        user_checkpoint=cp,
                        app_id=app_id,
                    )
                except DifyAPIError as e:
                    overall_status = "PARTIAL_SUCCESS"
                    user_report["status"] = "ERROR"
                    user_report["errors"].append({"type": "dify_api_error", "message": str(e)})
                    per_user.append(user_report)
                    continue
                except Exception as e:
                    overall_status = "PARTIAL_SUCCESS"
                    user_report["status"] = "ERROR"
                    user_report["errors"].append({"type": type(e).__name__, "message": str(e)})
                    per_user.append(user_report)
                    continue

                user_report["stop_reason"] = stop_reason
                user_report["scanned_conversations"] = stats.scanned_conversations
                user_report["scanned_messages"] = stats.scanned_messages
                user_report["dropped_future_messages"] = stats.dropped_future_messages
                summary["scanned_conversations"] += stats.scanned_conversations
                summary["scanned_messages"] += stats.scanned_messages

                # Process each conversation's segments
                for conv_id, segments in segments_by_conv.items():
                    conv_cp = cp.get_conv(conv_id)

                    # Track last processed message for this run
                    last_processed_id: str | None = None
                    last_processed_created_at: str | None = None

                    for seg in segments:
                        mem0_msgs = _dify_msg_to_mem0_messages(seg.messages)
                        if not mem0_msgs:
                            continue

                        message_id_range = seg.segment_id

                        # Budget heuristics per segment/subtype
                        seg_text = "\n".join(f'{m["role"]}: {m["content"]}' for m in mem0_msgs)
                        seg_cost = max(50, len(seg_text) // 4)

                        # semantic
                        if remaining_budget >= seg_cost:
                            md = build_memory_metadata(
                                subtype="semantic",
                                app_id=app_id,
                                conversation_id=conv_id,
                                segment_id=seg.segment_id,
                                run_at=run_at,
                                message_id_range=message_id_range,
                            )
                            res = mem0_add_segment(
                                mem=subtype_mems["semantic"].memory,
                                messages=mem0_msgs,
                                user_id=uid,
                                metadata=md,
                            )
                            c = _count_add_results(res)
                            summary["written_memories"]["semantic"] += c
                            user_report["written_memories"]["semantic"] += c
                            remaining_budget -= seg_cost
                        else:
                            overall_status = "PARTIAL_SUCCESS"

                        # episodic
                        if remaining_budget >= seg_cost:
                            md = build_memory_metadata(
                                subtype="episodic",
                                app_id=app_id,
                                conversation_id=conv_id,
                                segment_id=seg.segment_id,
                                run_at=run_at,
                                message_id_range=message_id_range,
                            )
                            res = mem0_add_segment(
                                mem=subtype_mems["episodic"].memory,
                                messages=mem0_msgs,
                                user_id=uid,
                                metadata=md,
                            )
                            c = _count_add_results(res)
                            summary["written_memories"]["episodic"] += c
                            user_report["written_memories"]["episodic"] += c
                            remaining_budget -= seg_cost
                        else:
                            overall_status = "PARTIAL_SUCCESS"

                        # procedural (lowest priority)
                        if remaining_budget >= seg_cost:
                            md = build_memory_metadata(
                                subtype="procedural",
                                app_id=app_id,
                                conversation_id=conv_id,
                                segment_id=seg.segment_id,
                                run_at=run_at,
                                message_id_range=message_id_range,
                            )
                            res = mem0_add_segment(
                                mem=subtype_mems["procedural"].memory,
                                messages=mem0_msgs,
                                user_id=uid,
                                metadata=md,
                            )
                            c = _count_add_results(res)
                            summary["written_memories"]["procedural"] += c
                            user_report["written_memories"]["procedural"] += c
                            remaining_budget -= seg_cost
                        else:
                            overall_status = "PARTIAL_SUCCESS"

                        # Update last processed message info from segment tail
                        last_msg = seg.messages[-1] if seg.messages else None
                        if isinstance(last_msg, dict):
                            last_processed_id = (
                                str(last_msg.get("id") or last_processed_id or "").strip()
                                or last_processed_id
                            )
                            ca = last_msg.get("created_at")
                            if isinstance(ca, str) and ca.strip():
                                last_processed_created_at = ca.strip()

                    # Apply conversation-level checkpoint updates if we processed anything
                    if last_processed_id:
                        conv_cp.last_processed_message_id = last_processed_id
                        conv_cp.last_processed_message_created_at = last_processed_created_at

                # Finalize user checkpoint and persist
                cp.last_run_at = run_at
                try:
                    ok, new_id = save_checkpoint(
                        base_mem,
                        checkpoint_id=cp_id,
                        user_id=uid,
                        app_id=app_id,
                        checkpoint=cp,
                    )
                    checkpoint_updates.append(
                        {
                            "user_id": uid,
                            "ok": ok,
                            "checkpoint_id": new_id or cp_id,
                        },
                    )
                except Exception as e:
                    overall_status = "PARTIAL_SUCCESS"
                    checkpoint_updates.append(
                        {
                            "user_id": uid,
                            "ok": False,
                            "checkpoint_id": cp_id,
                            "error": str(e),
                        },
                    )
                    user_report["status"] = "PARTIAL_SUCCESS"
                    user_report["errors"].append(
                        {"type": "checkpoint_update_failed", "message": str(e)},
                    )

                user_report["budget_remaining"] = remaining_budget
                per_user.append(user_report)
                summary["processed_users"] += 1

            summary["skipped_users"] = summary.get("skipped_users", 0)
            summary["budget_tokens"]["remaining"] = remaining_budget
            summary["budget_tokens"]["spent_estimate"] = max(0, budget_total - remaining_budget)

            report = {
                "status": overall_status,
                "run_id": run_id,
                "summary": summary,
                "per_user": per_user,
                "checkpoint_updates": checkpoint_updates,
            }

            yield self.create_json_message(report)
            yield self.create_text_message(
                f"Consolidation finished: status={overall_status}, run_id={run_id}, "
                f"processed_users={summary['processed_users']}, "
                f"written={summary['written_memories']}, remaining_budget={remaining_budget}",
            )
        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            logger.exception("Consolidate long-term memory failed")
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []},
            )
            yield self.create_text_message(f"Failed to consolidate: {error_message}")


