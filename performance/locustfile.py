"""Locust performance test for Dify chatflow API endpoints.

This script uses Locust, a mature Python load testing framework, to test
HTTP endpoints with configurable concurrency and request patterns.

Installation:
    pip install locust

Usage:
    # Set API key
    export DIFY_API_KEY='your-api-key'

    # Run with web UI (default: http://localhost:8089)
    locust -f performance/locustfile.py --host=http://localhost

    # Run headless (no web UI) with custom parameters
    locust -f performance/locustfile.py \
        --host=http://localhost \
        --users 10 \
        --spawn-rate 2 \
        --run-time 60s \
        --headless

    # Run with custom endpoint and generate HTML report
    locust -f performance/locustfile.py \
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
    DIFY_USER_ID='test_user' \
    DIFY_RESPONSE_MODE='streaming' \
    locust -f performance/locustfile.py --host=http://localhost
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import ClassVar

from dotenv import load_dotenv
from locust import HttpUser, TaskSet, between, events, task

# Load environment variables from .env file in performance directory
env_file = Path(__file__).parent / ".env"
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

        # Parse questions from DIFY_QUERY (pipe-delimited)
        query_str = os.getenv(
            "DIFY_QUERY",
            "What are the specs of the iPhone 17 Pro Max?",
        )
        self.questions = [q.strip() for q in query_str.split("|") if q.strip()]
        if not self.questions:
            self.questions = ["What are the specs of the iPhone 17 Pro Max?"]

        # Configurable payload template
        self.response_mode = os.getenv("DIFY_RESPONSE_MODE", "streaming")
        
        # Parse user_id(s) - can be comma-separated list for random selection
        user_id_str = os.getenv("DIFY_USER_ID", "test_user")
        self.user_ids = [uid.strip() for uid in user_id_str.split(",") if uid.strip()]
        if not self.user_ids:
            self.user_ids = ["test_user"]
        
        # Multi-turn conversation settings
        # min_turns and max_turns define the range for follow-up conversation rounds
        self.min_turns = int(os.getenv("DIFY_MIN_TURNS", "3"))
        self.max_turns = int(os.getenv("DIFY_MAX_TURNS", "5"))
        self.suggested_endpoint = "/v1/messages/{message_id}/suggested"
        
        # Create instance-specific random number generator to avoid collisions
        # when multiple users start simultaneously. Use time + process ID for seeding.
        seed = int(time.time() * 1000000) + id(self) + os.getpid()
        self.rng = random.Random(seed)


    def _get_suggested_questions(
        self,
        message_id: str,
        headers: dict[str, str],
        user_id: str,
    ) -> list[str]:
        """Fetch suggested questions from Dify API.
        
        Args:
            message_id: The message ID to get suggestions for
            headers: HTTP headers including authorization
            user_id: User ID for the request
            
        Returns:
            List of suggested questions, or empty list if request fails
        """
        endpoint = self.suggested_endpoint.format(message_id=message_id)
        url = f"{endpoint}?user={user_id}"
        
        try:
            with self.client.get(
                url,
                headers=headers,
                catch_response=True,
                name="get-suggested-questions",
            ) as response:
                if response.status_code == HTTP_OK:
                    response.success()
                    data = response.json()
                    if data.get("result") == "success":
                        suggestions = data.get("data", [])
                        return suggestions
                    print(f"[Locust] API returned non-success result: {data.get('result')}")
                else:
                    print(f"[Locust] Failed to get suggestions: HTTP {response.status_code}")
                    response.failure(f"Failed to get suggestions: {response.status_code}")
        except Exception as e:
            print(f"[Locust] Exception fetching suggestions: {e}")
        
        return []

    def _send_chat_message(
        self,
        query: str,
        conversation_id: str,
        headers: dict[str, str],
        user_id: str,
        include_files: bool = False,
    ) -> tuple[bool, str, str]:
        """Send a single chat message.
        
        Args:
            query: The question to ask
            conversation_id: Conversation ID (empty string for new conversation)
            headers: HTTP headers
            user_id: User ID for the request
            include_files: Whether to include file attachments
            
        Returns:
            Tuple of (success, message_id, new_conversation_id)
        """
        payload = {
            "inputs": {},
            "query": query,
            "response_mode": self.response_mode,
            "conversation_id": conversation_id,
            "user": user_id,
        }

        if include_files:
            payload["files"] = [
                {
                    "type": "image",
                    "transfer_method": "remote_url",
                    "url": "https://cloud.dify.ai/logo/logo-site.png",
                },
            ]

        # For streaming mode, we need to ensure the response is fully consumed
        # so that Dify can properly log the conversation
        with self.client.post(
            self.endpoint,
            json=payload,
            headers=headers,
            catch_response=True,
            name="chat-messages",
            stream=False,  # Locust will read entire response into response.text
        ) as response:
            if response.status_code == HTTP_OK:
                response.success()
                try:
                    # Handle streaming response (SSE format)
                    if self.response_mode == "streaming":
                        # Parse ENTIRE SSE stream to ensure Dify logs the conversation
                        # Dify only records logs when the client fully consumes the stream
                        message_id = ""
                        new_conversation_id = conversation_id
                        workflow_finished = False
                        
                        for line in response.text.split("\n"):
                            if line.startswith("data: "):
                                try:
                                    event_data = json.loads(line[6:])
                                    event_type = event_data.get("event")
                                    
                                    # Extract IDs from workflow_started event
                                    if event_type == "workflow_started":
                                        message_id = event_data.get("message_id", "")
                                        new_conversation_id = event_data.get(
                                            "conversation_id", conversation_id
                                        )
                                    
                                    # Track workflow completion
                                    elif event_type == "workflow_finished":
                                        workflow_finished = True
                                    
                                except Exception:
                                    continue
                        
                        # Log warning if workflow didn't finish properly
                        if message_id and not workflow_finished:
                            print(
                                f"[Locust] Warning: workflow did not finish "
                                f"(message_id: {message_id})"
                            )
                        
                        return (True, message_id, new_conversation_id)
                    else:
                        # Handle blocking response (regular JSON)
                        data = response.json()
                        message_id = data.get("message_id", "")
                        new_conversation_id = data.get("conversation_id", conversation_id)
                        return (True, message_id, new_conversation_id)
                except Exception as e:
                    print(f"[Locust] Failed to parse response: {e}")
                    print(f"[Locust] Response text: {response.text[:200]}")
                    return (False, "", conversation_id)
            elif response.status_code < HTTP_SERVER_ERROR_START:
                print(f"[Locust] Client error {response.status_code}: {response.text[:200]}")
                response.failure(f"Client error: {response.status_code}")
            else:
                print(f"[Locust] Server error {response.status_code}: {response.text[:200]}")
                response.failure(f"Server error: {response.status_code}")
        
        return (False, "", conversation_id)

    @task(1)
    def chat_message(self) -> None:
        """Send a chat message and simulate multi-turn conversation (3-5 rounds)."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Randomly select a user from the user list (using instance-specific RNG)
        user_id = self.rng.choice(self.user_ids)
        
        # Randomly decide how many follow-up turns (3-5)
        num_turns = self.rng.randint(self.min_turns, self.max_turns)
        
        # Start conversation with random question from initial list
        initial_query = self.rng.choice(self.questions)
        conversation_id = ""
        include_files = os.getenv("DIFY_NO_FILES", "").lower() != "true"
        
        print(f"\n{'='*80}")
        print("[Locust] Starting new conversation")
        print(f"[Locust] User ID: {user_id}")
        print(f"[Locust] Initial query: {initial_query}")
        print(f"[Locust] Planned follow-up turns: {num_turns}")
        print(f"{'='*80}")
        
        # Send initial message
        success, message_id, conversation_id = self._send_chat_message(
            initial_query,
            conversation_id,
            headers,
            user_id,
            include_files,
        )
        
        if not success:
            print("[Locust] ✗ Initial message failed, ending conversation\n")
            return
        
        if not message_id:
            print("[Locust] ✗ No message_id returned, ending conversation\n")
            return
        
        print("\n[Locust] ✓ INITIAL MESSAGE SUCCESS")
        print(f"[Locust]   Conversation ID: {conversation_id}")
        print(f"[Locust]   Message ID:     {message_id}")
        
        # Continue conversation for num_turns rounds
        completed_turns = 0
        for turn_num in range(num_turns):
            print(f"\n{'-'*80}")
            print(
                f"[Locust] FOLLOW-UP TURN {turn_num + 1}/{num_turns} "
                f"(conversation: {conversation_id})"
            )
            print(f"{'-'*80}")
            
            # Get suggested questions
            suggested = self._get_suggested_questions(message_id, headers, user_id)
            
            if not suggested:
                print("[Locust] ✗ No suggested questions available, ending conversation\n")
                break
            
            print(f"[Locust] Fetched {len(suggested)} suggestions: {suggested}")
            
            # Randomly select one suggested question (using instance-specific RNG)
            next_query = self.rng.choice(suggested)
            print(f"[Locust] Selected query: {next_query}")
            
            # Send follow-up message (no files in follow-ups)
            success, new_message_id, new_conversation_id = self._send_chat_message(
                next_query,
                conversation_id,
                headers,
                user_id,
                include_files=False,
            )
            
            if not success:
                print("[Locust] ✗ Follow-up message failed, ending conversation\n")
                break
            
            if not new_message_id:
                print("[Locust] ✗ No message_id returned, ending conversation\n")
                break
            
            # Update for next iteration
            message_id = new_message_id
            conversation_id = new_conversation_id
            completed_turns += 1
            
            print("\n[Locust] ✓ FOLLOW-UP SUCCESS")
            print(f"[Locust]   Conversation ID: {conversation_id}")
            print(f"[Locust]   Message ID:     {message_id}")
        
        print(f"\n{'='*80}")
        print(
            f"[Locust] Conversation ended: {completed_turns}/{num_turns} "
            "follow-up turns completed"
        )
        print(f"[Locust] Final conversation ID: {conversation_id}")
        print(f"{'='*80}\n")


@events.test_start.add_listener
def on_test_start(environment, **kwargs) -> None:
    """Event handler called when the load test starts."""
    # Override host from DIFY_BASE_URL if set
    base_url = os.getenv("DIFY_BASE_URL")
    if base_url:
        environment.host = base_url
    
    print("\n" + "#" * 80)
    print("#" + " " * 78 + "#")
    print("#" + " " * 20 + "LOCUST LOAD TEST STARTED" + " " * 34 + "#")
    print("#" + " " * 78 + "#")
    print("#" * 80)
    print(f"Host: {environment.host}")
    print(f"Users: {environment.runner.target_user_count if environment.runner else 'N/A'}")
    print("#" * 80 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs) -> None:
    """Event handler called when the load test stops (including --run-time)."""
    stats = environment.stats
    print("\n" + "#" * 80)
    print("#" + " " * 78 + "#")
    print("#" + " " * 19 + "LOCUST LOAD TEST COMPLETED" + " " * 33 + "#")
    print("#" + " " * 78 + "#")
    print("#" * 80)
    print(f"Total requests: {stats.total.num_requests}")
    print(f"Total failures: {stats.total.num_failures}")
    print(f"Average response time: {stats.total.avg_response_time:.2f}ms")
    print(f"Requests per second: {stats.total.total_rps:.2f}")
    print("#" * 80 + "\n")


@events.quitting.add_listener
def on_quitting(environment, **kwargs) -> None:
    """Event handler called when Locust is quitting (Ctrl+C)."""
    print("\n[Locust] Shutting down...\n")


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
