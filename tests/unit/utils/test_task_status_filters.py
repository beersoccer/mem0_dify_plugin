from __future__ import annotations

from utils.task_status import task_status_filters


def test_task_status_filters_internal_flag_is_string() -> None:
    filters = task_status_filters(task_id="t1")
    assert filters["__internal"] == "true"

