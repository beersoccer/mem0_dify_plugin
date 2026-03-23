"""Acceptance tests: workflow-driven memory lifecycle.

Seeds its own independent conversations from the ``acceptance_lifecycle``
section of ``conversation_seed_cases.yaml`` (user IDs carry the ``-w`` suffix).
This is completely isolated from ``test_memory_extraction_quality`` which seeds
``acceptance_extraction`` users (``-x`` suffix).

Triggers the Dify extraction workflow with the seeded user IDs and verifies
that Mem0 contains at least the expected number of memories per user.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

import pytest

from tests.helpers.artifacts import write_json_artifact
from tests.helpers.dify_cleanup import cleanup_seeded_conversations
from tests.helpers.dify_env import (
    get_poll_interval,
    get_primary_test_user,
    get_stall_timeout,
    get_workflow_max_wait,
    require_mem0_credentials,
)
from tests.helpers.dify_seed import load_seed_cases, seed_chatflow_cases
from tests.helpers.mem0_cleanup import cleanup_mem0_state, count_user_memories
from tests.helpers.workflow_runner import (
    assert_workflow_expectations,
    load_workflow_cases,
    require_workflow_cases,
    resolve_workflow_case_user_id,
    run_workflow_case,
)
from utils.dify_client import DifyClient

pytestmark = [pytest.mark.workflow_acceptance, pytest.mark.requires_remote, pytest.mark.slow]

_SEED_CASES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "conversation_seed_cases.yaml"


def test_workflow_memory_lifecycle_cases(
    acceptance_workflow_client: DifyClient,
    acceptance_chat_client: DifyClient,
    acceptance_env_config: dict[str, str],
) -> None:
    cases = require_workflow_cases(
        load_workflow_cases(
            Path(__file__).resolve().parents[1] / "fixtures" / "workflow_cases.yaml",
            section="memory_lifecycle",
        ),
        section="memory_lifecycle",
    )
    env_config = acceptance_env_config
    workflow_client = acceptance_workflow_client
    credentials = require_mem0_credentials(env_config)
    app_id = (env_config.get("DIFY_CHATFLOW_APP_ID") or "").strip() or None

    # Seed this test's own independent conversations.
    seed_cases = load_seed_cases(_SEED_CASES_PATH, section="acceptance_lifecycle")
    if not seed_cases:
        pytest.skip("No enabled cases in acceptance_lifecycle section")
    seed = seed_chatflow_cases(acceptance_chat_client, cases=seed_cases, run_id=uuid4().hex)
    write_json_artifact("acceptance-lifecycle-seed-manifest", seed.to_dict())
    if not seed.conversations:
        pytest.skip("No conversations were seeded for acceptance_lifecycle")

    # Build the seeded user list for the workflow.
    # The JSON array string must fit within the Dify workflow `users` input
    # variable limit. With 3 short user_id_templates (+"-w") this is ~69 chars (<128).
    seeded_user_ids = seed.user_ids
    users_json = json.dumps(seeded_user_ids, ensure_ascii=False)

    run_id = seed.run_id
    context = {
        "run_id": run_id,
        "short_run_id": run_id[:8],
        "user_id": get_primary_test_user(env_config),
    }
    write_json_artifact(
        "acceptance-lifecycle-context",
        {
            "run_id": run_id,
            "app_id": app_id,
            "seeded_user_ids": seeded_user_ids,
            "section": "memory_lifecycle",
        },
    )

    touched_users: set[str] = set()
    try:
        for case in cases:
            resolve_workflow_case_user_id(case, context=context)
            touched_users.update(seeded_user_ids)

            case_with_users = {
                **case,
                "inputs": {**(case.get("inputs") or {}), "users": users_json},
            }

            result = run_workflow_case(
                workflow_client,
                case=case_with_users,
                context=context,
                max_wait_s=get_workflow_max_wait(env_config),
                poll_interval_s=get_poll_interval(env_config),
                stall_timeout_s=get_stall_timeout(env_config),
            )
            assert_workflow_expectations(result, case)

            memory_assertions = case.get("memory_assertions") or {}
            min_memories = int(memory_assertions.get("min_memories", 0) or 0)
            if min_memories > 0:
                # The extraction tool runs in async mode: the workflow returns
                # "succeeded" immediately while the actual extraction continues in a
                # background thread inside the plugin process.  Poll Mem0 until
                # memories appear or the budget runs out.
                poll_interval = get_poll_interval(env_config)
                async_wait_budget = get_workflow_max_wait(env_config)
                async_deadline = time.monotonic() + async_wait_budget
                for user_id in seeded_user_ids:
                    while True:
                        current = count_user_memories(
                            credentials,
                            user_id=user_id,
                            app_id=app_id,
                        )
                        if current >= min_memories:
                            break
                        remaining = async_deadline - time.monotonic()
                        if remaining <= 0:
                            assert current >= min_memories, (
                                f"User {user_id!r} has {current} memories after "
                                f"{async_wait_budget:.0f}s wait, expected >= {min_memories}"
                            )
                        time.sleep(min(poll_interval, remaining))
    finally:
        if touched_users:
            mem0_cleanup = cleanup_mem0_state(
                credentials,
                user_ids=sorted(touched_users),
                app_id=app_id,
                task_ids=[],
            )
            write_json_artifact(
                "acceptance-lifecycle-mem0-cleanup",
                {
                    "run_id": run_id,
                    "touched_users": sorted(touched_users),
                    "app_id": app_id,
                    "summary": mem0_cleanup,
                },
            )
        dify_cleanup = cleanup_seeded_conversations(
            acceptance_chat_client, manifest=seed, verify=False
        )
        write_json_artifact("acceptance-lifecycle-dify-cleanup", dify_cleanup)
