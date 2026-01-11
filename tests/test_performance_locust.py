"""Locust performance test for Dify chatflow API endpoints.

This script uses Locust, a mature Python load testing framework, to test
HTTP endpoints with configurable concurrency and request patterns.

Installation:
    pip install locust

Usage:
    # Set API key
    export DIFY_API_KEY='your-api-key'

    # Run with web UI (default: http://localhost:8089)
    locust -f tests/test_performance_locust.py --host=http://localhost

    # Run headless (no web UI) with custom parameters
    locust -f tests/test_performance_locust.py \
        --host=http://localhost \
        --users 10 \
        --spawn-rate 2 \
        --run-time 60s \
        --headless

    # Run with custom endpoint and generate HTML report
    locust -f tests/test_performance_locust.py \
        --host=http://localhost \
        --users 20 \
        --spawn-rate 5 \
        --run-time 120s \
        --headless \
        --html=report.html \
        --csv=results

    # Customize via environment variables
    DIFY_API_KEY='key' \
    DIFY_ENDPOINT='/v1/chat-messages' \
    DIFY_QUERY='Your custom query' \
    DIFY_USER_ID='user-123' \
    DIFY_RESPONSE_MODE='streaming' \
    locust -f tests/test_performance_locust.py --host=http://localhost
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from dotenv import load_dotenv
from locust import HttpUser, TaskSet, between, task

# Load environment variables from .env.dev file
env_file = Path(__file__).parent.parent / ".env.dev"
if env_file.exists():
    load_dotenv(env_file)

# HTTP status code constants
HTTP_OK = 200
HTTP_SERVER_ERROR_START = 500


class DifyChatflowTasks(TaskSet):
    """Task set for Dify chatflow API testing."""

    def on_start(self) -> None:
        """Initialize task set with configuration from environment variables."""
        # Get configuration from environment variables
        self.api_key = os.getenv("DIFY_API_KEY", "")
        api_key_error_msg = (
            "DIFY_API_KEY environment variable is required. "
            "Set it with: export DIFY_API_KEY='your-api-key'"
        )
        if not self.api_key:
            raise ValueError(api_key_error_msg)

        # Configurable endpoint (default: /v1/chat-messages)
        self.endpoint = os.getenv("DIFY_ENDPOINT", "/v1/chat-messages")

        # Configurable payload
        self.default_payload = {
            "inputs": {},
            "query": os.getenv(
                "DIFY_QUERY",
                "What are the specs of the iPhone 17 Pro Max?",
            ),
            "response_mode": os.getenv("DIFY_RESPONSE_MODE", "streaming"),
            "conversation_id": os.getenv("DIFY_CONVERSATION_ID", ""),
            "user": os.getenv("DIFY_USER_ID", "abc-123"),
        }

        # Include files if not disabled
        if os.getenv("DIFY_NO_FILES", "").lower() != "true":
            self.default_payload["files"] = [
                {
                    "type": "image",
                    "transfer_method": "remote_url",
                    "url": "https://cloud.dify.ai/logo/logo-site.png",
                },
            ]

    @task(1)
    def chat_message(self) -> None:
        """Send a chat message request to Dify chatflow endpoint."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with self.client.post(
            self.endpoint,
            json=self.default_payload,
            headers=headers,
            catch_response=True,
            name="chat-messages",
        ) as response:
            if response.status_code == HTTP_OK:
                response.success()
            elif response.status_code < HTTP_SERVER_ERROR_START:
                # Client errors (4xx) are considered failures but not server errors
                response.failure(f"Client error: {response.status_code}")
            else:
                # Server errors (5xx)
                response.failure(f"Server error: {response.status_code}")


class DifyChatflowUser(HttpUser):
    """Locust user class for Dify chatflow performance testing.

    This class represents a simulated user. Each user will execute the tasks
    defined in DifyChatflowTasks with the wait_time interval between requests.
    """

    tasks: ClassVar[list[type[TaskSet]]] = [DifyChatflowTasks]
    # Wait between 1 and 3 seconds between requests
    # Adjust this based on your testing needs
    wait_time = between(1, 3)

    def on_start(self) -> None:
        """Initialize when a simulated user starts."""
        # Can add user-specific initialization here if needed

    def on_stop(self) -> None:
        """Cleanup when a simulated user stops."""
        # Can add user-specific cleanup here if needed

