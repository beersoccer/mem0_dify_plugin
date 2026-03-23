from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.helpers.artifacts import write_json_artifact
from utils.dify_client import DifyAPIError, DifyClient


def load_workflow_cases(path: Path, section: str) -> list[dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases = raw.get(section) if isinstance(raw, dict) else []
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


def _dig(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def wait_for_workflow_completion(
    client: DifyClient,
    *,
    workflow_run_id: str,
    max_wait_s: float,
    poll_interval_s: float,
    stall_timeout_s: float,
) -> dict[str, Any]:
    started = time.monotonic()
    last_progress = started
    last_state: tuple[Any, Any, Any] | None = None

    while True:
        detail = client.get_workflow_run_detail(workflow_run_id=workflow_run_id)
        data = detail.get("data") if isinstance(detail.get("data"), dict) else detail
        if not isinstance(data, dict):
            raise DifyAPIError(
                f"Unexpected workflow detail payload for {workflow_run_id}: {detail!r}"
            )

        state = (data.get("status"), data.get("elapsed_time"), data.get("finished_at"))
        if state != last_state:
            last_state = state
            last_progress = time.monotonic()

        status = str(data.get("status") or "").lower()
        if status in {"succeeded", "failed", "stopped", "completed"}:
            return data

        now = time.monotonic()
        if now - started > max_wait_s:
            raise TimeoutError(
                f"Workflow run {workflow_run_id} did not finish within {max_wait_s:.0f}s"
            )
        if now - last_progress > stall_timeout_s:
            raise TimeoutError(
                f"Workflow run {workflow_run_id} stalled for more than {stall_timeout_s:.0f}s"
            )
        time.sleep(poll_interval_s)


def run_workflow_case(
    client: DifyClient,
    *,
    case: dict[str, Any],
    context: dict[str, str],
    max_wait_s: float,
    poll_interval_s: float,
    stall_timeout_s: float,
) -> dict[str, Any]:
    case_name = str(case.get("name") or "workflow_case")
    user_id = resolve_workflow_case_user_id(case, context=context)
    inputs = _format_value(case.get("inputs") or {}, context)
    response: dict[str, Any] | None = None
    workflow_run_id = ""
    try:
        response = client.run_workflow_blocking(inputs=inputs, user_id=user_id)
        write_json_artifact(
            f"workflow-initial-{case_name}",
            {
                "case_name": case_name,
                "user_id": user_id,
                "inputs": inputs,
                "response": response,
                "context": context,
            },
        )

        initial_data = response.get("data") if isinstance(response.get("data"), dict) else response
        if not isinstance(initial_data, dict):
            raise DifyAPIError(f"Unexpected workflow response payload: {response!r}")

        workflow_run_id = str(
            initial_data.get("workflow_run_id")
            or initial_data.get("id")
            or response.get("workflow_run_id")
            or ""
        ).strip()
        if not workflow_run_id:
            write_json_artifact(f"workflow-final-{case_name}", initial_data)
            return initial_data

        result = wait_for_workflow_completion(
            client,
            workflow_run_id=workflow_run_id,
            max_wait_s=max_wait_s,
            poll_interval_s=poll_interval_s,
            stall_timeout_s=stall_timeout_s,
        )
        write_json_artifact(
            f"workflow-final-{case_name}",
            {
                "case_name": case_name,
                "workflow_run_id": workflow_run_id,
                "result": result,
                "context": context,
            },
        )
        return result
    except Exception as exc:  # noqa: BLE001
        write_json_artifact(
            f"workflow-failure-{case_name}",
            {
                "case_name": case_name,
                "user_id": user_id,
                "inputs": inputs,
                "context": context,
                "workflow_run_id": workflow_run_id or None,
                "initial_response": response,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
        raise


def resolve_workflow_case_user_id(case: dict[str, Any], *, context: dict[str, str]) -> str:
    value = case.get("user_id")
    if not value:
        value = case.get("user_id_template") or context["user_id"]
    return str(_format_value(value, context))


def assert_workflow_expectations(result: dict[str, Any], case: dict[str, Any]) -> None:
    expected_status = str(case.get("expected_status") or "succeeded").lower()
    actual_status = str(result.get("status") or "").lower()
    assert actual_status == expected_status

    for dotted_path in case.get("expected_output_keys") or []:
        assert _dig(result, str(dotted_path)) is not None

    for dotted_path, expected_substring in (case.get("expected_output_contains") or {}).items():
        value = _dig(result, str(dotted_path))
        assert value is not None
        assert str(expected_substring) in str(value)


def require_workflow_cases(cases: list[dict[str, Any]], *, section: str) -> list[dict[str, Any]]:
    if cases:
        return cases
    pytest.skip(
        f"No enabled workflow cases found in section '{section}'. "
        "Update tests/fixtures/workflow_cases.yaml to enable real acceptance cases."
    )
