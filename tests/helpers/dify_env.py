from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

from performance.user_ids import build_user_ids
from utils.dify_client import DifyAPIError, DifyClient

DEFAULT_HTTP_TIMEOUT = 20.0
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_WORKFLOW_MAX_WAIT = 120.0
DEFAULT_STALL_TIMEOUT = 30.0
DEFAULT_PYTEST_TIMEOUT_INTEGRATION = "120"
DEFAULT_PYTEST_TIMEOUT_E2E = "300"
DEFAULT_PYTEST_TIMEOUT_ACCEPTANCE = "180"


def _resolve_env_file(explicit_env_file: str = "") -> Path | None:
    tests_dir = Path(__file__).resolve().parents[1]
    project_root = tests_dir.parent
    explicit_env_file = explicit_env_file.strip()

    candidates: list[Path] = []
    if explicit_env_file:
        explicit_path = Path(explicit_env_file)
        if explicit_path.is_absolute():
            candidates.append(explicit_path)
        else:
            # Support both repo-root relative (e.g. tests/.env.local)
            # and tests-dir relative (e.g. .env.local) styles.
            candidates.append(project_root / explicit_path)
            candidates.append(tests_dir / explicit_path)
    else:
        candidates.append(tests_dir / ".env.local")
        candidates.append(tests_dir / ".env.remote")
    return next((candidate for candidate in candidates if candidate.exists()), None)


def _load_env_file(env_path: Path | None) -> dict[str, str]:
    if env_path is None:
        return {}

    loaded: dict[str, str] = {}
    with env_path.open(encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, _, value = raw.partition("=")
            loaded[key.strip()] = value.strip().strip('"').strip("'")
    return loaded


def load_env_config(explicit_env_file: str = "") -> dict[str, str]:
    """Load test config from env file and process OS env vars.

    File priority:
    - explicit env file from caller argument.
    - tests/.env.local when explicit file is absent.
    - tests/.env.remote when local file is absent.

    OS environment variables override file values so CI can inject secrets
    without mutating local files or committing secret files.
    """
    env_path = _resolve_env_file(explicit_env_file)
    config = _load_env_file(env_path)
    for key, value in os.environ.items():
        if key.startswith(("DIFY_", "MEM0_", "TEST_", "ALLOW_", "REQUIRE_")):
            # Keep profile source of truth in env file.
            if key == "TEST_PROFILE":
                continue
            config[key] = value
    return config


def normalize_base_url(raw_base_url: str | None) -> str:
    base_url = (raw_base_url or "").strip()
    if not base_url:
        return ""
    if not base_url.startswith("http"):
        base_url = f"http://{base_url}"
    base_url = base_url.rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return base_url


def get_test_profile(env: dict[str, str]) -> str:
    profile = (env.get("TEST_PROFILE") or "").strip().lower()
    if profile in {"local", "remote", "ci"}:
        return profile
    return "ci" if os.getenv("GITHUB_ACTIONS") == "true" else "local"


def parse_bool(raw_value: str | None, default: bool = False) -> bool:
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "y", "on"}


def is_localhost_url(base_url: str) -> bool:
    hostname = (urlparse(base_url).hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "::1"}


def get_dify_base_url(env: dict[str, str]) -> str:
    return normalize_base_url(env.get("DIFY_BASE_URL"))


def get_dify_chatflow_api_key(env: dict[str, str]) -> str:
    return (env.get("DIFY_CHATFLOW_API_KEY") or "").strip()


def get_dify_workflow_api_key(env: dict[str, str]) -> str:
    return (env.get("DIFY_WORKFLOW_API_KEY") or "").strip()


def get_test_users(env: dict[str, str]) -> list[str]:
    raw_value = (
        env.get("DIFY_TEST_USERS")
        or env.get("DIFY_USER_IDS")
        or env.get("DIFY_USER_ID")
        or "test_user"
    )
    return build_user_ids(raw_value, default_user="test_user")


def get_primary_test_user(env: dict[str, str]) -> str:
    if env.get("DIFY_USER_ID"):
        return env["DIFY_USER_ID"].strip()
    return get_test_users(env)[0]


def get_http_timeout(env: dict[str, str]) -> float:
    raw_timeout = env.get("DIFY_HTTP_TIMEOUT")
    try:
        return float(raw_timeout) if raw_timeout else DEFAULT_HTTP_TIMEOUT
    except ValueError:
        return DEFAULT_HTTP_TIMEOUT


def get_poll_interval(env: dict[str, str]) -> float:
    raw_value = env.get("DIFY_POLL_INTERVAL")
    try:
        return float(raw_value) if raw_value else DEFAULT_POLL_INTERVAL
    except ValueError:
        return DEFAULT_POLL_INTERVAL


def get_workflow_max_wait(env: dict[str, str]) -> float:
    raw_value = env.get("DIFY_WORKFLOW_MAX_WAIT")
    try:
        return float(raw_value) if raw_value else DEFAULT_WORKFLOW_MAX_WAIT
    except ValueError:
        return DEFAULT_WORKFLOW_MAX_WAIT


def get_stall_timeout(env: dict[str, str]) -> float:
    raw_value = env.get("DIFY_STALL_TIMEOUT")
    try:
        return float(raw_value) if raw_value else DEFAULT_STALL_TIMEOUT
    except ValueError:
        return DEFAULT_STALL_TIMEOUT


def network_required(env: dict[str, str]) -> bool:
    profile = get_test_profile(env)
    default_required = profile in {"remote", "ci"}
    return parse_bool(env.get("REQUIRE_DIFY_NETWORK"), default=default_required)


def localhost_allowed(env: dict[str, str]) -> bool:
    return parse_bool(env.get("ALLOW_LOCALHOST_DIFY"), default=False)


def build_mem0_credentials(env: dict[str, str]) -> dict[str, str]:
    return {
        "local_llm_json_secret": env.get("MEM0_LLM_CONFIG", ""),
        "local_embedder_json_secret": env.get("MEM0_EMBEDDER_CONFIG", ""),
        "local_vector_db_json_secret": env.get("MEM0_VECTOR_DB_CONFIG", ""),
        "local_graph_db_json_secret": env.get("MEM0_GRAPH_DB_CONFIG", ""),
        "local_reranker_json_secret": env.get("MEM0_RERANKER_CONFIG", ""),
    }


def require_mem0_credentials(env: dict[str, str]) -> dict[str, str]:
    credentials = build_mem0_credentials(env)
    required_suffixes = (
        "llm_json_secret",
        "embedder_json_secret",
        "vector_db_json_secret",
    )
    missing = [
        key for key, value in credentials.items() if key.endswith(required_suffixes) and not value
    ]
    if missing:
        pytest.skip(
            "Mem0 credentials are missing for real-environment tests: "
            + ", ".join(missing)
        )
    return credentials


def create_dify_client(env: dict[str, str]) -> DifyClient:
    """Return a DifyClient authenticated with DIFY_CHATFLOW_API_KEY."""
    base_url = get_dify_base_url(env)
    api_key = get_dify_chatflow_api_key(env)
    if not base_url or not api_key:
        pytest.skip("DIFY_BASE_URL/DIFY_CHATFLOW_API_KEY are required")
    return DifyClient(base_url=base_url, api_key=api_key, timeout=get_http_timeout(env))


def create_workflow_client(env: dict[str, str]) -> DifyClient:
    """Return a DifyClient authenticated with DIFY_WORKFLOW_API_KEY."""
    base_url = get_dify_base_url(env)
    api_key = get_dify_workflow_api_key(env)
    if not base_url or not api_key:
        pytest.skip("DIFY_BASE_URL/DIFY_WORKFLOW_API_KEY are required")
    return DifyClient(base_url=base_url, api_key=api_key, timeout=get_http_timeout(env))


def preflight_chat_client(
    env: dict[str, str],
    client: DifyClient,
    *,
    suite_name: str,
    user_id: str | None = None,
) -> None:
    base_url = client.base_url
    if is_localhost_url(base_url) and not localhost_allowed(env):
        message = (
            f"{suite_name}: {base_url} points to localhost. "
            "Set ALLOW_LOCALHOST_DIFY=1 to allow local real-environment tests."
        )
        if network_required(env):
            pytest.fail(message)
        pytest.skip(message)

    probe_user = user_id or get_primary_test_user(env)
    try:
        client.list_conversations(user_id=probe_user, limit=1)
    except (DifyAPIError, ValueError) as exc:
        message = f"{suite_name}: unable to reach Dify Chat API at {base_url}: {exc}"
        if network_required(env):
            pytest.fail(message)
        pytest.skip(message)


def preflight_workflow_client(
    env: dict[str, str],
    client: DifyClient,
    *,
    suite_name: str,
    user_id: str | None = None,
) -> None:
    base_url = client.base_url
    if is_localhost_url(base_url) and not localhost_allowed(env):
        message = (
            f"{suite_name}: {base_url} points to localhost. "
            "Set ALLOW_LOCALHOST_DIFY=1 to allow local real-environment tests."
        )
        if network_required(env):
            pytest.fail(message)
        pytest.skip(message)

    try:
        info = client.get_app_info()
        mode = str(info.get("mode") or "").lower()
        if mode and mode != "workflow":
            message = (
                f"{suite_name}: DIFY_WORKFLOW_API_KEY points to a '{mode}' app at {base_url}. "
                "Expected a 'workflow' type app."
            )
            if network_required(env):
                pytest.fail(message)
            pytest.skip(message)
    except (DifyAPIError, ValueError) as exc:
        message = (
            f"{suite_name}: unable to reach Dify Workflow API endpoint at "
            f"{base_url}: {exc}"
        )
        if network_required(env):
            pytest.fail(message)
        pytest.skip(message)


def get_pytest_timeout_for_suite(suite: str) -> str:
    normalized = (suite or "").strip().lower()
    if normalized in {"integration", "dify_api"}:
        return DEFAULT_PYTEST_TIMEOUT_INTEGRATION
    if normalized in {"e2e", "extraction", "extraction_e2e"}:
        return DEFAULT_PYTEST_TIMEOUT_E2E
    if normalized in {"acceptance", "workflow", "workflow_acceptance"}:
        return DEFAULT_PYTEST_TIMEOUT_ACCEPTANCE
    return DEFAULT_PYTEST_TIMEOUT_INTEGRATION
