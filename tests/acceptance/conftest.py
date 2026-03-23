"""Session-scoped client fixtures for the acceptance test suite.

Each acceptance test seeds its own independent conversations so that Mem0 state
is fully isolated between tests — no shared seed data, no ordering constraints.

  test_workflow_plugin_smoke       — smoke only, no Mem0 writes
  test_workflow_memory_lifecycle   — seeds acceptance_lifecycle users, tests workflow path
  test_memory_extraction_quality   — seeds acceptance_extraction users, tests Python path

Both seeding tests may run in any order and clean up after themselves independently.
"""
from __future__ import annotations

import pytest

from tests.helpers.dify_env import (
    create_dify_client,
    create_workflow_client,
    get_primary_test_user,
    load_env_config,
    preflight_chat_client,
    preflight_workflow_client,
)
from utils.dify_client import DifyClient


@pytest.fixture(scope="session")
def acceptance_env_config() -> dict[str, str]:
    return load_env_config()


@pytest.fixture(scope="session")
def acceptance_chat_client(acceptance_env_config: dict[str, str]) -> DifyClient:
    """Session-scoped chatflow client shared across acceptance tests."""
    client = create_dify_client(acceptance_env_config)
    preflight_chat_client(
        acceptance_env_config,
        client,
        suite_name="acceptance.session",
        user_id=get_primary_test_user(acceptance_env_config),
    )
    return client


@pytest.fixture(scope="session")
def acceptance_workflow_client(acceptance_env_config: dict[str, str]) -> DifyClient:
    """Session-scoped workflow client shared across acceptance tests."""
    client = create_workflow_client(acceptance_env_config)
    preflight_workflow_client(
        acceptance_env_config,
        client,
        suite_name="acceptance.session",
        user_id=get_primary_test_user(acceptance_env_config),
    )
    return client
