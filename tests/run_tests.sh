#!/bin/bash
# Unified test runner for local and CI profiles.
# Recommended: activate venv manually, then run pytest directly.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

CHECK_ENV_ONLY=false
USE_FORKED=false
E2E_MODE=false
SUITE=""
FORCE_NETWORK=false
PYTEST_TIMEOUT_OVERRIDE=""
OUTPUT_FILE=""
ENV_FILE=""
CLEANUP_MODE="none"
PYTEST_ARGS=()
HAS_PYTEST_TIMEOUT=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --check-env)
            CHECK_ENV_ONLY=true
            shift
            ;;
        --suite)
            SUITE="$2"
            shift 2
            ;;
        --require-network)
            FORCE_NETWORK=true
            shift
            ;;
        --timeout)
            PYTEST_TIMEOUT_OVERRIDE="$2"
            shift 2
            ;;
        --forked)
            USE_FORKED=true
            shift
            ;;
        --e2e)
            E2E_MODE=true
            shift
            ;;
        --output-file)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        --cleanup)
            CLEANUP_MODE="$2"
            shift 2
            ;;
        --help)
            cat << EOF
Unified test runner for mem0_dify_plugin.

Usage:
  ./tests/run_tests.sh [options] [pytest args...]

Options:
  --check-env         Check virtual environment only
  --suite NAME        unit | integration | acceptance
  --require-network   Export REQUIRE_DIFY_NETWORK=1
  --timeout SECONDS   Override pytest-timeout seconds
  --forked            Run pytest with --forked
  --e2e               Backward-compatible alias for --suite e2e
  --output-file FILE  Tee output to file
  --env-file FILE     Explicit env file for real suites (e.g. tests/.env.local)
  --cleanup MODE      post-test cleanup mode: none | manifest | force-all
  --help              Show help

Examples:
  ./tests/run_tests.sh --suite unit -v
  ./tests/run_tests.sh --suite integration --env-file tests/.env.remote --require-network
  ./tests/run_tests.sh --suite acceptance --env-file tests/.env.local
  ./tests/run_tests.sh --suite integration --env-file tests/.env.local --cleanup manifest
  ./tests/run_tests.sh --suite integration --env-file tests/.env.local --cleanup force-all
  ./tests/run_tests.sh --suite acceptance --env-file tests/.env.remote --timeout 240
EOF
            exit 0
            ;;
        *)
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

check_venv() {
    if [ ! -d ".venv" ]; then
        echo "❌ Error: virtual environment .venv not found"
        echo "Create one with: uv venv"
        return 1
    fi
    if [[ -z "$VIRTUAL_ENV" ]]; then
        echo "⚠️  Virtualenv not activated: $PROJECT_ROOT/.venv"
    else
        echo "✅ Virtualenv active: $VIRTUAL_ENV"
    fi
    if [ ! -f ".venv/bin/pytest" ]; then
        echo "❌ pytest not found in .venv"
        return 1
    fi
    if .venv/bin/python -c "import pytest_timeout" 2>/dev/null; then
        HAS_PYTEST_TIMEOUT=true
    fi
    if [ "$USE_FORKED" = true ] || [ "$E2E_MODE" = true ] || [[ "$SUITE" =~ ^(e2e|acceptance)$ ]]; then
        if ! .venv/bin/python -c "import pytest_forked" 2>/dev/null; then
            echo "❌ pytest-forked not installed"
            return 1
        fi
    fi
    return 0
}

normalize_artifacts_dir() {
    local raw_dir="$1"
    if [ -z "$raw_dir" ]; then
        return 0
    fi
    if [[ "$raw_dir" = /* ]]; then
        echo "$raw_dir"
    elif [[ "$raw_dir" == tests/* ]]; then
        echo "$raw_dir"
    else
        echo "tests/$raw_dir"
    fi
}

infer_profile_from_env_file() {
    local env_file="$1"
    local profile

    if [ -z "$env_file" ] || [ ! -f "$env_file" ]; then
        if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
            echo "ci"
        else
            echo "local"
        fi
        return 0
    fi

    profile="$(
        python3 - "$env_file" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
value = ""
for line in path.read_text(encoding="utf-8").splitlines():
    raw = line.strip()
    if not raw or raw.startswith("#") or "=" not in raw:
        continue
    key, _, val = raw.partition("=")
    if key.strip() == "TEST_PROFILE":
        value = val.strip().strip('"').strip("'").lower()
        break
print(value)
PY
)"

    case "$profile" in
        local|remote|ci)
            echo "$profile"
            ;;
        *)
            echo ""
            ;;
    esac
}

if [ "$CHECK_ENV_ONLY" = true ]; then
    check_venv
    exit $?
fi

if ! check_venv; then
    exit 1
fi

if [ "$FORCE_NETWORK" = true ]; then
    export REQUIRE_DIFY_NETWORK=1
fi

if [ "$E2E_MODE" = true ]; then
    echo "⚠️  The --e2e flag has been removed. Use --suite integration or --suite acceptance instead."
    exit 1
fi

case "$CLEANUP_MODE" in
    none|manifest|force-all) ;;
    *)
        echo "❌ Invalid cleanup mode: $CLEANUP_MODE (expected: none|manifest|force-all)"
        exit 1
        ;;
esac

ACTIVE_PROFILE=""
if [ -n "$ENV_FILE" ]; then
    ACTIVE_PROFILE="$(infer_profile_from_env_file "$ENV_FILE")"
    if [ -z "$ACTIVE_PROFILE" ]; then
        echo "❌ Invalid or missing TEST_PROFILE in env file: $ENV_FILE (expected: local|remote|ci)"
        exit 1
    fi
fi
if [ -z "$ACTIVE_PROFILE" ]; then
    if [ -f "tests/.env.local" ]; then
        ENV_FILE="tests/.env.local"
    elif [ -f "tests/.env.remote" ]; then
        ENV_FILE="tests/.env.remote"
    fi
fi
if [ -z "$ACTIVE_PROFILE" ] && [ -n "$ENV_FILE" ]; then
    ACTIVE_PROFILE="$(infer_profile_from_env_file "$ENV_FILE")"
    if [ -z "$ACTIVE_PROFILE" ]; then
        echo "❌ Invalid or missing TEST_PROFILE in env file: $ENV_FILE (expected: local|remote|ci)"
        exit 1
    fi
fi
if [ -z "$ACTIVE_PROFILE" ]; then
    ACTIVE_PROFILE="$(infer_profile_from_env_file "")"
fi

# Artifact directory can be configured in environment/.env.
# If absent, fallback to deterministic default under tests/.
if [ -z "${TEST_ARTIFACTS_DIR:-}" ]; then
    ARTIFACT_ENV_FILE="$ENV_FILE"
    if [ -z "$ARTIFACT_ENV_FILE" ]; then
        case "$ACTIVE_PROFILE" in
            local)
                ARTIFACT_ENV_FILE="tests/.env.local"
                ;;
            remote|ci)
                ARTIFACT_ENV_FILE="tests/.env.remote"
                ;;
        esac
    fi
    if [ -n "$ARTIFACT_ENV_FILE" ] && [ -f "$ARTIFACT_ENV_FILE" ]; then
        TEST_ARTIFACTS_DIR_FROM_FILE="$(
            python3 - "$ARTIFACT_ENV_FILE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
value = ""
for line in path.read_text(encoding="utf-8").splitlines():
    raw = line.strip()
    if not raw or raw.startswith("#") or "=" not in raw:
        continue
    key, _, val = raw.partition("=")
    if key.strip() == "TEST_ARTIFACTS_DIR":
        value = val.strip().strip('"').strip("'")
        break
print(value)
PY
)"
        if [ -n "$TEST_ARTIFACTS_DIR_FROM_FILE" ]; then
            export TEST_ARTIFACTS_DIR="$TEST_ARTIFACTS_DIR_FROM_FILE"
        fi
    fi
fi
if [ -z "${TEST_ARTIFACTS_DIR:-}" ]; then
    export TEST_ARTIFACTS_DIR="artifacts/$ACTIVE_PROFILE"
fi
TEST_ARTIFACTS_DIR="$(normalize_artifacts_dir "$TEST_ARTIFACTS_DIR")"
export TEST_ARTIFACTS_DIR
mkdir -p "$TEST_ARTIFACTS_DIR"

# Load per-suite pytest timeout overrides from the env file (if not already set
# in the process environment, e.g. by the caller or CI).
_TIMEOUT_ENV_FILE="${ENV_FILE:-}"
if [ -z "$_TIMEOUT_ENV_FILE" ]; then
    case "$ACTIVE_PROFILE" in
        local)  _TIMEOUT_ENV_FILE="tests/.env.local" ;;
        remote|ci) _TIMEOUT_ENV_FILE="tests/.env.remote" ;;
    esac
fi
if [ -n "$_TIMEOUT_ENV_FILE" ] && [ -f "$_TIMEOUT_ENV_FILE" ]; then
    _read_timeout() {
        local key="$1"
        python3 - "$_TIMEOUT_ENV_FILE" "$key" <<'PY'
from pathlib import Path
import sys
path, key = Path(sys.argv[1]), sys.argv[2]
for line in path.read_text(encoding="utf-8").splitlines():
    raw = line.strip()
    if not raw or raw.startswith("#") or "=" not in raw:
        continue
    k, _, v = raw.partition("=")
    if k.strip() == key:
        print(v.strip().strip('"').strip("'"))
        break
PY
    }
    if [ -z "${PYTEST_TIMEOUT_INTEGRATION:-}" ]; then
        _v="$(_read_timeout PYTEST_TIMEOUT_INTEGRATION)"
        [ -n "$_v" ] && export PYTEST_TIMEOUT_INTEGRATION="$_v"
    fi
    if [ -z "${PYTEST_TIMEOUT_ACCEPTANCE:-}" ]; then
        _v="$(_read_timeout PYTEST_TIMEOUT_ACCEPTANCE)"
        [ -n "$_v" ] && export PYTEST_TIMEOUT_ACCEPTANCE="$_v"
    fi
fi

if [ -n "$SUITE" ] && [ ${#PYTEST_ARGS[@]} -eq 0 ]; then
    case "$SUITE" in
        unit)
            PYTEST_ARGS=("tests/unit/" "-v")
            ;;
        integration)
            # Run all tests under tests/integration/ (not only @pytest.mark.dify_api).
            # Previously `-m dify_api` deselected test_dify_integration.py and
            # test_time_range_filtering.py because only test_dify_seed_api.py was marked.
            PYTEST_ARGS=("tests/integration/" "-v")
            ;;
        e2e)
            echo "⚠️  The 'e2e' suite has been merged into 'integration' and 'acceptance'."
            echo "   Run --suite integration for scan/connectivity tests."
            echo "   Run --suite acceptance for memory extraction quality tests."
            exit 1
            ;;
        acceptance)
            # acceptance tests do not import dify_plugin, so fork isolation is not needed.
            # Running in a single process allows session-scoped fixtures to share seed data.
            PYTEST_ARGS=("tests/acceptance/" "-m" "workflow_acceptance" "-v" "-s")
            ;;
        *)
            echo "❌ Unknown suite: $SUITE"
            exit 1
            ;;
    esac
fi

REAL_SUITE=false
if [[ "$SUITE" =~ ^(integration|acceptance)$ ]] || [[ "${PYTEST_ARGS[*]}" =~ tests/(integration|acceptance)/ ]]; then
    REAL_SUITE=true
fi
if [ "$REAL_SUITE" = true ]; then
    if [ -z "$ENV_FILE" ]; then
        if [ -f "tests/.env.local" ]; then
            ENV_FILE="tests/.env.local"
        elif [ -f "tests/.env.remote" ]; then
            ENV_FILE="tests/.env.remote"
        fi
    fi

    if [ -n "$ENV_FILE" ]; then
        if [ ! -f "$ENV_FILE" ]; then
            echo "❌ Env file not found: $ENV_FILE"
            exit 1
        fi
        ACTIVE_PROFILE="$(infer_profile_from_env_file "$ENV_FILE")"
        if [ -z "$ACTIVE_PROFILE" ]; then
            echo "❌ Invalid or missing TEST_PROFILE in env file: $ENV_FILE (expected: local|remote|ci)"
            exit 1
        fi
    fi

    HAS_ENV_FILE=false
    HAS_DIFY_ENV=false
    [ -f "tests/.env.local" ] && HAS_ENV_FILE=true
    [ -f "tests/.env.remote" ] && HAS_ENV_FILE=true
    [ -n "${DIFY_BASE_URL:-}" ] && [ -n "${DIFY_API_KEY:-}" ] && HAS_DIFY_ENV=true
    if [ "$HAS_ENV_FILE" = false ] && [ "$HAS_DIFY_ENV" = false ]; then
        echo "❌ Real-environment tests need tests/.env.local or tests/.env.remote, or DIFY_BASE_URL+DIFY_API_KEY env vars"
        exit 1
    fi
fi

if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "Auto-activating virtualenv..."
    source .venv/bin/activate
fi

PYTEST_CMD=("pytest")
PYTEST_TIMEOUT=""
if [ -n "$PYTEST_TIMEOUT_OVERRIDE" ]; then
    PYTEST_TIMEOUT="$PYTEST_TIMEOUT_OVERRIDE"
else
    case "$SUITE" in
        integration)
            PYTEST_TIMEOUT="${PYTEST_TIMEOUT_INTEGRATION:-120}"
            ;;
        acceptance)
            PYTEST_TIMEOUT="${PYTEST_TIMEOUT_ACCEPTANCE:-180}"
            ;;
    esac
fi
if [ -n "$PYTEST_TIMEOUT" ] && [ "$HAS_PYTEST_TIMEOUT" = true ]; then
    PYTEST_CMD+=("--timeout=$PYTEST_TIMEOUT")
fi
if [ -n "$PYTEST_TIMEOUT" ] && [ "$HAS_PYTEST_TIMEOUT" = false ]; then
    echo "⚠️ pytest-timeout is not installed; skipping --timeout=$PYTEST_TIMEOUT"
fi

if [ "$USE_FORKED" = true ]; then
    PYTEST_CMD+=("--forked")
    export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
fi
PYTEST_CMD+=("${PYTEST_ARGS[@]}")

echo "======================================"
if [ -n "$SUITE" ]; then
    echo "Running suite: $SUITE"
else
    echo "Running tests"
fi
echo "Profile: $ACTIVE_PROFILE"
if [ -n "$ENV_FILE" ]; then
    echo "Env file: $ENV_FILE"
fi
if [ "${REQUIRE_DIFY_NETWORK:-0}" = "1" ]; then
    echo "Network policy: fail when unreachable"
fi
if [ -n "$PYTEST_TIMEOUT" ]; then
    echo "Pytest timeout: ${PYTEST_TIMEOUT}s"
fi
if [ -n "$OUTPUT_FILE" ]; then
    echo "Output file: $OUTPUT_FILE"
fi
echo "Artifacts dir: $TEST_ARTIFACTS_DIR"
if [ "$CLEANUP_MODE" != "none" ]; then
    if [ "$CLEANUP_MODE" = "force-all" ]; then
        echo "Residual cleanup: force-all"
    else
        echo "Residual cleanup: manifest-driven"
    fi
fi
echo "======================================"
echo "Command: ${PYTEST_CMD[*]}"
echo ""

set +e
if [ -n "$OUTPUT_FILE" ]; then
    "${PYTEST_CMD[@]}" 2>&1 | tee "$OUTPUT_FILE"
    EXIT_CODE=${PIPESTATUS[0]}
else
    "${PYTEST_CMD[@]}"
    EXIT_CODE=$?
fi
set -e

CLEANUP_EXIT_CODE=0
if [ "$CLEANUP_MODE" != "none" ] && [ "$REAL_SUITE" = true ]; then
    echo ""
    echo "Running residual seeded-conversation cleanup..."
    set +e
    CLEANUP_ARGS=(
        "--execute"
        "--artifacts-dir" "$TEST_ARTIFACTS_DIR"
    )
    if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
        CLEANUP_ARGS+=("--env-file" "$ENV_FILE")
    fi
    if [ "$CLEANUP_MODE" = "force-all" ]; then
        CLEANUP_ARGS+=("--force-all")
    fi
    .venv/bin/python tests/cleanup_seed_residuals.py "${CLEANUP_ARGS[@]}"
    CLEANUP_EXIT_CODE=$?
    set -e
    if [ $CLEANUP_EXIT_CODE -ne 0 ]; then
        echo "⚠️ Residual cleanup finished with errors (exit code: $CLEANUP_EXIT_CODE)"
    else
        echo "✅ Residual cleanup completed"
    fi
fi

if [ $EXIT_CODE -eq 0 ] && [ $CLEANUP_EXIT_CODE -ne 0 ]; then
    EXIT_CODE=$CLEANUP_EXIT_CODE
fi

echo ""
echo "======================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Tests completed"
else
    echo "❌ Tests failed (exit code: $EXIT_CODE)"
fi
if [ -n "$OUTPUT_FILE" ]; then
    echo "Saved output to: $OUTPUT_FILE"
fi
echo "======================================"

exit $EXIT_CODE

