"""Message format conversion utilities for Dify and Mem0.

This module provides utilities for converting between Dify message formats
and Mem0-compatible message formats, as well as helper functions for
counting memory operation results.
"""

from __future__ import annotations

from typing import Any


def dify_msg_to_mem0_messages(
    segment_messages: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Best-effort normalization from Dify message objects to mem0 {role, content}.
    
    Supports multiple Dify message formats:
    1. Query/answer pairs: {"query": "...", "answer": "..."}
    2. Role/content format: {"role": "user|assistant", "content": "..."}
    3. Alternative fields: {"from": "...", "text": "..."}
    
    Args:
        segment_messages: List of Dify message dictionaries.
        
    Returns:
        List of Mem0-compatible messages with {role, content} format.
        
    Examples:
        >>> msgs = [{"query": "Hi", "answer": "Hello"}]
        >>> dify_msg_to_mem0_messages(msgs)
        [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]
    """
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

        role = (
            str(m.get("role") or m.get("from") or m.get("type") or "").strip().lower()
        )
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


def count_add_results(res: object) -> int:
    """Count effective memory operations from Mem0 add() result.
    
    Counts the number of ADD and UPDATE events in the Mem0 response,
    excluding NONE events which indicate no changes were made.
    
    Args:
        res: Mem0 add() result dictionary or None.
        
    Returns:
        Number of effective memory operations (ADD or UPDATE).
        
    Examples:
        >>> result = {"results": [{"event": "ADD"}, {"event": "UPDATE"}]}
        >>> count_add_results(result)
        2
        
        >>> result = {"results": [{"event": "NONE"}]}
        >>> count_add_results(result)
        0
    """
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


def count_add_event_stats(res: object) -> dict[str, int]:
    """Count all events from Mem0 add() result (including NONE).

    Args:
        res: Mem0 add() result dictionary or None.

    Returns:
        Dict of event name -> count (uppercased).
    """
    if not isinstance(res, dict):
        return {}
    results = res.get("results")
    if not isinstance(results, list):
        return {}
    counts: dict[str, int] = {}
    for r in results:
        if not isinstance(r, dict):
            continue
        event = str(r.get("event") or "UNKNOWN").upper()
        counts[event] = counts.get(event, 0) + 1
    return counts

