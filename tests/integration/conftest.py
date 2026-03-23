"""Integration test fixtures shared across the integration test suite.

Session-scoped fixtures seed Dify conversations once per test run and clean up
afterwards. Test functions declare ``integration_seed`` as a parameter to
receive the :class:`SeedManifest` object directly — no ``os.environ`` writes,
no ``.env.generated`` file.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.artifacts import write_json_artifact
from tests.helpers.dify_cleanup import cleanup_seeded_conversations
from tests.helpers.dify_env import (
    create_dify_client,
    get_primary_test_user,
    load_env_config,
    preflight_chat_client,
)
from tests.helpers.dify_seed import SeedManifest, load_seed_cases, seed_chatflow_cases

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
_SEED_CASES_PATH = _FIXTURES_DIR / "conversation_seed_cases.yaml"


@pytest.fixture(scope="session")
def integration_env_config() -> dict[str, str]:
    """Session-scoped env config loaded once for the entire integration run."""
    return load_env_config()


@pytest.fixture(scope="session")
def dify_client_session(integration_env_config: dict[str, str]):
    """Session-scoped DifyClient, shared across all integration fixtures."""
    client = create_dify_client(integration_env_config)
    preflight_chat_client(
        integration_env_config,
        client,
        suite_name="integration.session",
        user_id=get_primary_test_user(integration_env_config),
    )
    return client


@pytest.fixture(scope="session")
def integration_seed(dify_client_session) -> SeedManifest:
    """Seed Dify conversations once per session, yield SeedManifest, then clean up.

    Downstream fixtures and test functions receive the manifest object directly.
    Time boundaries (``started_at`` / ``finished_at``) are accessed via the
    helper methods :py:meth:`SeedManifest.started_at_with_buffer` and
    :py:meth:`SeedManifest.finished_at_with_buffer`.
    """
    cases = load_seed_cases(_SEED_CASES_PATH)
    manifest = seed_chatflow_cases(dify_client_session, cases=cases, extra_per_user=2)
    write_json_artifact("integration-session-seed-manifest", manifest.to_dict())
    try:
        yield manifest
    finally:
        result = cleanup_seeded_conversations(
            dify_client_session, manifest=manifest, verify=False
        )
        write_json_artifact("integration-session-cleanup-summary", result)
