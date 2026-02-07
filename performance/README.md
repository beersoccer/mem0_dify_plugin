# Performance Testing

This directory contains performance and load testing scripts for the Mem0 Dify plugin.

## Locust Load Testing

### Installation

```bash
pip install locust
```

### Quick Start

```bash
# Set your API key
export DIFY_API_KEY='<your-dify-api-key>'

# Run with web UI (opens http://localhost:8089)
locust -f performance/locustfile.py --host=http://localhost
```

### Headless Mode

```bash
# Run without web UI
locust -f performance/locustfile.py \
    --host=http://localhost \
    --users 10 \
    --spawn-rate 2 \
    --run-time 60s \
    --headless
```

### Generate Reports

```bash
# Generate HTML and CSV reports
locust -f performance/locustfile.py \
    --host=http://localhost \
    --users 20 \
    --spawn-rate 5 \
    --run-time 120s \
    --headless \
    --html=report.html \
    --csv=results
```

### Configuration

You can configure test parameters in two ways:

**Option 1: Use `.env` file (Recommended)**

Create a `.env` file in the `performance/` directory with your configuration:

```bash
# performance/.env
DIFY_API_KEY="<your-dify-api-key>"
DIFY_BASE_URL="http://<your-dify-host>/v1"  # Base URL for remote testing (overrides --host if set)
DIFY_ENDPOINT="/chat-messages"
DIFY_QUERY="<your-custom-query>"
DIFY_USER_ID="<user_a>"  # Single user, or comma-separated list: "<user_a>,<user_b>"
DIFY_RESPONSE_MODE="streaming"
DIFY_MIN_TURNS=3  # Minimum number of follow-up conversation turns (default: 3)
DIFY_MAX_TURNS=5  # Maximum number of follow-up conversation turns (default: 5)
```

The script will automatically load variables from `performance/.env` if it exists.

**Note**: 
- The conversation will have 3-5 follow-up turns (randomly selected) after the initial message. This simulates multi-turn conversations that can trigger long-term memory extraction.
- If `DIFY_USER_ID` contains multiple users (comma-separated), each request will randomly select one user from the list. This allows testing with different user contexts.
- Use a base URL ending with `/v1` and endpoints starting with `/chat-messages` and `/messages/...` to match the Dify API structure.

**Option 2: Set environment variables directly**

```bash
DIFY_API_KEY='<your-dify-api-key>' \
DIFY_BASE_URL='http://<your-dify-host>/v1' \
DIFY_ENDPOINT='/chat-messages' \
DIFY_QUERY='<your-custom-query>' \
DIFY_USER_ID='<user_a>' \
DIFY_RESPONSE_MODE='streaming' \
DIFY_MIN_TURNS=3 \
DIFY_MAX_TURNS=5 \
locust -f performance/locustfile.py --host=http://localhost
```

## Why Separate from `tests/`?

- **Clear separation**: Unit tests (pytest) vs performance tests (Locust)
- **No conflicts**: pytest won't try to collect Locust files
- **No skip logic needed**: Clean, simple code without runtime detection
- **Better organization**: Different test types in different directories
