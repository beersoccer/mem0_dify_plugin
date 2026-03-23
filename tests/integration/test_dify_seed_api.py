from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.artifacts import write_json_artifact
from tests.helpers.dify_cleanup import cleanup_seeded_conversations, conversation_exists
from tests.helpers.dify_env import (
    create_dify_client,
    get_primary_test_user,
    load_env_config,
    preflight_chat_client,
)
from tests.helpers.dify_seed import load_seed_cases, seed_chatflow_cases

pytestmark = [pytest.mark.dify_api, pytest.mark.slow]


@pytest.fixture
def env_config() -> dict[str, str]:
    return load_env_config()


@pytest.fixture
def dify_client(env_config: dict[str, str]):
    client = create_dify_client(env_config)
    preflight_chat_client(
        env_config,
        client,
        suite_name="integration.dify_api.seed_cleanup",
        user_id=get_primary_test_user(env_config),
    )
    return client


def test_seed_then_cleanup_conversation_lifecycle(dify_client) -> None:
    cases = load_seed_cases(
        Path(__file__).resolve().parents[1] / "fixtures" / "conversation_seed_cases.yaml"
    )
    manifest = seed_chatflow_cases(dify_client, cases=cases[:1])
    # Record seeded targets once using the shared manifest type.
    write_json_artifact("integration-seed-manifest", manifest.to_dict())
    assert manifest.run_id
    assert manifest.conversations
    seeded = manifest.conversations[0]
    assert seeded.conversation_id
    assert seeded.user_id
    assert seeded.message_ids

    result = cleanup_seeded_conversations(dify_client, manifest=manifest, verify=True)
    write_json_artifact("integration-cleanup-summary", result)
    assert result["deleted"] == 1
    assert result["verified_absent"] == 1
    assert not result["failures"]
    assert not conversation_exists(
        dify_client,
        user_id=seeded.user_id,
        conversation_id=seeded.conversation_id,
    )
