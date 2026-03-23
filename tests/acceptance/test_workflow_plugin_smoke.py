"""Acceptance tests: workflow smoke.

Uses the session-scoped ``acceptance_workflow_client`` fixture from conftest.py.
Verifies that the extraction workflow can be triggered and returns a successful
status with a minimal single-user input.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from tests.helpers.dify_env import (
    get_poll_interval,
    get_primary_test_user,
    get_stall_timeout,
    get_workflow_max_wait,
)
from tests.helpers.workflow_runner import (
    assert_workflow_expectations,
    load_workflow_cases,
    require_workflow_cases,
    run_workflow_case,
)
from utils.dify_client import DifyClient

pytestmark = [pytest.mark.workflow_acceptance, pytest.mark.requires_remote, pytest.mark.slow]


def test_workflow_smoke_cases(
    acceptance_workflow_client: DifyClient,
    acceptance_env_config: dict[str, str],
) -> None:
    cases = require_workflow_cases(
        load_workflow_cases(
            Path(__file__).resolve().parents[1] / "fixtures" / "workflow_cases.yaml",
            section="smoke",
        ),
        section="smoke",
    )
    env_config = acceptance_env_config
    workflow_client = acceptance_workflow_client
    run_id = uuid4().hex
    context = {
        "run_id": run_id,
        "short_run_id": run_id[:8],
        "user_id": get_primary_test_user(env_config),
    }
    for case in cases:
        result = run_workflow_case(
            workflow_client,
            case=case,
            context=context,
            max_wait_s=get_workflow_max_wait(env_config),
            poll_interval_s=get_poll_interval(env_config),
            stall_timeout_s=get_stall_timeout(env_config),
        )
        assert_workflow_expectations(result, case)
