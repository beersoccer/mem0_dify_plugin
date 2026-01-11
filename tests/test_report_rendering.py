from __future__ import annotations

from datetime import datetime, timedelta, timezone

from logs.analyze_mem0_log import render_markdown_performance_report
from logs.log_analyzer import AnalysisResult, EventKind, LogEvent


def test_report_markdown_formatting_no_top_query_and_no_rank_col() -> None:
    tz = timezone(timedelta(hours=8))
    base = datetime(2025, 12, 22, 2, 0, 0, tzinfo=timezone.utc)

    # Build a small set of events that will produce:
    # - hourly stats table
    # - peak hour details (Top Search/Add users)
    events = [
        LogEvent(
            ts=base,
            kind=EventKind.SEARCH_COMPLETED,
            plugin="mem0ai",
            version="0.1.7",
            user_id="u1",
            query="我是谁...",
            found=0,
            timeout_s=None,
            pending_tasks=None,
            raw="",
        ),
        LogEvent(
            ts=base,
            kind=EventKind.SEARCH_TIMEOUT,
            plugin="mem0ai",
            version="0.1.7",
            user_id="u1",
            query="我是谁...",
            found=None,
            timeout_s=5.0,
            pending_tasks=None,
            raw="",
        ),
        LogEvent(
            ts=base,
            kind=EventKind.ADD_SUBMIT,
            plugin="mem0ai",
            version="0.1.7",
            user_id="u2",
            query=None,
            found=None,
            timeout_s=None,
            pending_tasks=3,
            raw="",
        ),
    ]

    result = AnalysisResult(
        start_ts=events[0].ts,
        end_ts=events[-1].ts,
        total_events=len(events),
        plugin_versions={"mem0ai": {"0.1.7"}},
        search_completed=1,
        search_completed_found_gt0=0,
        search_completed_found_eq0=1,
        search_timeout=1,
        search_failed=0,
        degraded_completed_from_timeout=0,
        degraded_completed_from_failed=0,
        add_submit=1,
        pending_tasks_values=[3],
        search_by_hour={},
        peak_events_per_second=(base.replace(microsecond=0), 3),
        peak_pending_tasks=(base, 3),
        top_timeout_users=[("u1", 1)],
    )

    md = render_markdown_performance_report(result, events=events, tz=tz)

    # 1) 删除 Top Search query 小节
    assert "Top Search query（Top 10）" not in md

    # 2) 大表去掉 Top排名列，并把小时用行内代码包裹（避免换行）
    assert "Top排名(按total)" not in md
    assert "| 小时(北京时间) | total(Search+Add) |" in md
    assert "`2025-12-22" in md

    # 3) 时间展示不应包含 `+08:00`
    assert "+08:00" not in md

    # 4) 峰值小时详情仍以表格展示 Top 用户
    assert "| user_id | 次数 |" in md


