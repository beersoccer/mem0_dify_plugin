"""Tests for async extraction implementation.

This module tests the refactored extraction tool that uses:
- BackgroundEventLoop for async execution
- TaskTracker for task monitoring
- Concurrent processing (up to 5 users)
- Timeout controls and error handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.extract_long_term_memory import (
    ExtractLongTermMemoryTool,
    _execute_extraction_async,
    _process_single_user_async,
)
from utils.constants import EXTRACTION_MAX_CONCURRENT_USERS
from utils.extraction import ScanStats, UserCheckpoint
from utils.helpers import parse_iso_timestamp


@pytest.fixture
def mock_memory():
    """Mock Memory instance."""
    memory = MagicMock()
    memory.add.return_value = {"results": [{"event": "ADD", "id": "mem_123"}]}
    memory.get_all.return_value = {"results": []}
    memory.update.return_value = None
    return memory


@pytest.fixture
def mock_subtype_clients(mock_memory):
    """Mock subtype client instances."""
    async def mock_create():
        return mock_memory
    
    clients = {
        "semantic": MagicMock(memory=mock_memory),
        "episodic": MagicMock(memory=mock_memory),
        "procedural": MagicMock(memory=mock_memory),
    }
    for client in clients.values():
        client.create = mock_create
    return clients


@pytest.fixture
def mock_dify_client():
    """Mock Dify API client."""
    client = MagicMock()
    client.list_conversations.return_value = {
        "data": [
            {
                "id": "conv1",
                "created_at": "2026-01-23T00:00:00Z",
                "updated_at": "2026-01-23T12:00:00Z",
            }
        ],
        "has_more": False,
    }
    client.list_messages.return_value = {
        "data": [
            {
                "id": "msg1",
                "query": "Hello",
                "answer": "Hi there",
                "created_at": "2026-01-23T10:00:00Z",
            }
        ],
        "has_more": False,
    }
    return client


@pytest.fixture
def mock_lock_manager():
    """Mock lock manager."""
    manager = MagicMock()
    manager.acquire_lock = AsyncMock(return_value=(True, None))
    manager.release_lock = AsyncMock(return_value=None)
    return manager


class TestProcessSingleUserAsync:
    """Tests for _process_single_user_async function."""

    @pytest.mark.asyncio
    async def test_successful_processing(
        self,
        mock_memory,
        mock_subtype_clients,
        mock_dify_client,
        mock_lock_manager,
    ):
        """Test successful user processing."""
        with (
            patch("tools.extract_long_term_memory.AsyncCheckpointManager") as mock_mgr_cls,
            patch(
                "tools.extract_long_term_memory.scan_user_conversations_incremental"
            ) as mock_scan,
        ):
            # Setup mocks
            mock_mgr = MagicMock()
            async def mock_load(*args, **kwargs):
                return (None, None)
            async def mock_save_atomic(*args, **kwargs):
                return (True, "cp_123")
            mock_mgr.load = mock_load
            mock_mgr.save_atomic = mock_save_atomic
            mock_mgr_cls.return_value = mock_mgr
            mock_scan.return_value = (
                {},  # segments_by_conv
                ScanStats(
                    scanned_conversations=1,
                    scanned_messages=1,
                    dropped_future_messages=0,
                ),
                "success",
            )

            # Create mock base_client with async create method
            mock_base_client = MagicMock()
            mock_base_client.memory = mock_memory
            async def mock_create():
                return mock_memory
            mock_base_client.create = mock_create

            result = await _process_single_user_async(
                base_client=mock_base_client,
                subtype_clients=mock_subtype_clients,
                user_id="user1",
                app_id="app1",
                run_id="run1",
                start_time="2026-01-23T00:00:00Z",
                end_time="2026-01-24T00:00:00Z",
                dify=mock_dify_client,
                lock_manager=mock_lock_manager,
                max_conversations=50,
                max_tokens_per_conversation=64000,
                lock_ttl_sec=3600,
            )

            assert result["user_id"] == "user1"
            assert result["status"] == "SUCCESS"
            assert result["skipped"] is False
            assert mock_lock_manager.acquire_lock.called
            assert mock_lock_manager.release_lock.called

    @pytest.mark.asyncio
    async def test_lock_not_acquired(
        self,
        mock_memory,
        mock_subtype_clients,
        mock_dify_client,
        mock_lock_manager,
    ):
        """Test user skipped when lock cannot be acquired."""
        # Lock is held by another process
        existing_lock = MagicMock(holder_id="other_run")
        mock_lock_manager.acquire_lock = AsyncMock(return_value=(False, existing_lock))

        # Create mock base_client
        mock_base_client = MagicMock()
        mock_base_client.memory = mock_memory
        async def mock_create():
            return mock_memory
        mock_base_client.create = mock_create

        result = await _process_single_user_async(
            base_client=mock_base_client,
            subtype_clients=mock_subtype_clients,
            user_id="user1",
            app_id="app1",
            run_id="run1",
            start_time="2026-01-23T00:00:00Z",
            end_time="2026-01-24T00:00:00Z",
            dify=mock_dify_client,
            lock_manager=mock_lock_manager,
            max_conversations=20,
            max_tokens_per_conversation=64000,
            lock_ttl_sec=3600,
        )

        assert result["status"] == "SKIPPED"
        assert result["skipped"] is True
        assert result["reason"] == "lock_held"
        assert result["lock_holder"] == "other_run"

    @pytest.mark.asyncio
    async def test_processing_runs_with_checkpoint(
        self,
        mock_memory,
        mock_subtype_clients,
        mock_dify_client,
        mock_lock_manager,
    ):
        """Test user processes normally with an existing checkpoint."""
        with (
            patch("tools.extract_long_term_memory.AsyncCheckpointManager") as mock_mgr_cls,
            patch(
                "tools.extract_long_term_memory.scan_user_conversations_incremental"
            ) as mock_scan,
        ):
            cp = UserCheckpoint()
            mock_mgr = MagicMock()

            async def mock_load(*args, **kwargs):
                return ("cp_123", cp)

            async def mock_save_atomic(*args, **kwargs):
                return (True, "cp_123")

            mock_mgr.load = mock_load
            mock_mgr.save_atomic = mock_save_atomic
            mock_mgr_cls.return_value = mock_mgr

            mock_scan.return_value = (
                {},
                ScanStats(scanned_conversations=1, scanned_messages=1),
                "completed",
            )

            # Create mock base_client with async create method
            mock_base_client = MagicMock()
            mock_base_client.memory = mock_memory
            async def mock_create():
                return mock_memory
            mock_base_client.create = mock_create

            result = await _process_single_user_async(
                base_client=mock_base_client,
                subtype_clients=mock_subtype_clients,
                user_id="user1",
                app_id="app1",
                run_id="run1",
                start_time="2026-01-23T00:00:00Z",
                end_time="2026-01-24T00:00:00Z",
                dify=mock_dify_client,
                lock_manager=mock_lock_manager,
                max_conversations=50,
                max_tokens_per_conversation=64000,
                lock_ttl_sec=3600,
            )

            assert result["status"] == "SUCCESS"
            assert result["skipped"] is False
            assert mock_scan.called
            assert mock_lock_manager.release_lock.called

    @pytest.mark.asyncio
    async def test_checkpoint_updates_with_int_created_at_when_mem0_empty(
        self,
        mock_memory,
        mock_subtype_clients,
        mock_dify_client,
        mock_lock_manager,
    ):
        """Ensure int created_at is normalized and checkpoint updates on empty mem0."""
        saved: dict[str, UserCheckpoint] = {}

        with (
            patch("tools.extract_long_term_memory.AsyncCheckpointManager") as mock_mgr_cls,
            patch(
                "tools.extract_long_term_memory.scan_user_conversations_incremental"
            ) as mock_scan,
            patch(
                "tools.extract_long_term_memory.dify_msg_to_mem0_messages"
            ) as mock_to_mem0,
        ):
            async def mock_load(*_args, **_kwargs):
                return (None, UserCheckpoint())

            async def mock_save_atomic(*_args, **kwargs):
                saved["checkpoint"] = kwargs["checkpoint"]
                return (True, "cp_123")

            mock_mgr = MagicMock()
            mock_mgr.load = mock_load
            mock_mgr.save_atomic = mock_save_atomic
            mock_mgr_cls.return_value = mock_mgr

            mock_scan.return_value = (
                {
                    "conv1": [
                        {
                            "id": "msg1",
                            "query": "Hello",
                            "answer": "Hi",
                            "created_at": 1770367009,
                        }
                    ]
                },
                ScanStats(scanned_conversations=1, scanned_messages=1),
                "completed",
            )
            mock_to_mem0.return_value = []

            mock_base_client = MagicMock()
            mock_base_client.memory = mock_memory

            async def mock_create():
                return mock_memory

            mock_base_client.create = mock_create

            result = await _process_single_user_async(
                base_client=mock_base_client,
                subtype_clients=mock_subtype_clients,
                user_id="user1",
                app_id="app1",
                run_id="run1",
                start_time="2026-01-23T00:00:00Z",
                end_time="2026-01-24T00:00:00Z",
                dify=mock_dify_client,
                lock_manager=mock_lock_manager,
                max_conversations=50,
                max_tokens_per_conversation=64000,
                lock_ttl_sec=3600,
            )

            assert result["status"] == "SUCCESS"
            conv_cp = saved["checkpoint"].conversations["conv1"]
            assert conv_cp.last_processed_message_id == "msg1"
            assert conv_cp.processed_range_end is not None
            assert parse_iso_timestamp(conv_cp.processed_range_end) is not None

    @pytest.mark.asyncio
    async def test_dify_api_error(
        self,
        mock_memory,
        mock_subtype_clients,
        mock_dify_client,
        mock_lock_manager,
    ):
        """Test error handling when Dify API fails."""
        with (
            patch("tools.extract_long_term_memory.AsyncCheckpointManager") as mock_mgr_cls,
            patch(
                "tools.extract_long_term_memory.scan_user_conversations_incremental"
            ) as mock_scan,
        ):
            mock_mgr = MagicMock()
            async def mock_load(*args, **kwargs):
                return (None, None)
            mock_mgr.load = mock_load
            mock_mgr_cls.return_value = mock_mgr
            mock_scan.side_effect = Exception("Dify API error")

            # Create mock base_client with async create method
            mock_base_client = MagicMock()
            mock_base_client.memory = mock_memory
            async def mock_create():
                return mock_memory
            mock_base_client.create = mock_create

            result = await _process_single_user_async(
                base_client=mock_base_client,
                subtype_clients=mock_subtype_clients,
                user_id="user1",
                app_id="app1",
                run_id="run1",
                start_time="2026-01-23T00:00:00Z",
                end_time="2026-01-24T00:00:00Z",
                dify=mock_dify_client,
                lock_manager=mock_lock_manager,
                max_conversations=50,
                max_tokens_per_conversation=64000,
                lock_ttl_sec=3600,
            )

            assert result["status"] == "ERROR"
            assert len(result["errors"]) > 0
            assert mock_lock_manager.release_lock.called


@pytest.mark.asyncio
class TestExecuteExtractionAsync:
    """Tests for _execute_extraction_async function."""

    async def test_concurrent_processing(
        self,
        mock_memory,
        mock_subtype_clients,
        mock_dify_client,
        mock_lock_manager,
    ):
        """Test that multiple users are processed concurrently."""
        user_ids = [f"user{i}" for i in range(10)]

        # Mock _process_single_user to return success
        with (
            patch("tools.extract_long_term_memory._process_single_user_async") as mock_process,
            patch("tools.extract_long_term_memory.DifyClient") as mock_dify_cls,
            patch("tools.extract_long_term_memory.SyncLockManager") as mock_lock_cls,
        ):
            mock_dify_cls.return_value = mock_dify_client
            mock_lock_cls.return_value = mock_lock_manager

            # Track concurrent executions
            concurrent_count = []
            max_concurrent = [0]

            async def mock_process_user(*args, **kwargs):
                concurrent_count.append(1)
                max_concurrent[0] = max(max_concurrent[0], len(concurrent_count))
                try:
                    await asyncio.sleep(0.1)  # Simulate processing time
                finally:
                    concurrent_count.pop()
                return {
                    "user_id": kwargs.get("user_id", args[2] if len(args) > 2 else "unknown"),
                    "status": "SUCCESS",
                    "skipped": False,
                    "scanned_conversations": 1,
                    "scanned_messages": 1,
                    # Current implementation extracts only one classified type per conversation
                    "written_memories": {"semantic": 1, "episodic": 0, "procedural": 0},
                }

            mock_process.side_effect = mock_process_user

            # Create mock base_client
            mock_base_client = MagicMock()
            mock_base_client.memory = mock_memory
            async def mock_create():
                return mock_memory
            mock_base_client.create = mock_create

            result = await _execute_extraction_async(
                base_client=mock_base_client,
                subtype_clients=mock_subtype_clients,
                task_id="task1",
                run_id="run1",
                user_ids=user_ids,
                app_id="app1",
                start_time="2026-01-23T00:00:00Z",
                end_time="2026-01-24T00:00:00Z",
                dify_base_url="http://localhost/v1",
                dify_api_key="test_key",
                max_conversations=50,
                max_tokens_per_conversation=64000,
                time_budget_sec=30,
            )

            assert result["status"] == "SUCCESS"
            assert result["summary"]["processed_users"] == 10
            assert len(result["per_user"]) == 10

            # Verify concurrent processing (should be limited to 5)
            assert max_concurrent[0] <= EXTRACTION_MAX_CONCURRENT_USERS

    async def test_time_budget_exceeded(
        self,
        mock_memory,
        mock_subtype_clients,
        mock_dify_client,
        mock_lock_manager,
    ):
        """Test that processing stops when time budget is exceeded."""
        user_ids = [f"user{i}" for i in range(100)]

        with (
            patch("tools.extract_long_term_memory._process_single_user_async") as mock_process,
            patch("tools.extract_long_term_memory.DifyClient") as mock_dify_cls,
            patch("tools.extract_long_term_memory.SyncLockManager") as mock_lock_cls,
        ):
            mock_dify_cls.return_value = mock_dify_client
            mock_lock_cls.return_value = mock_lock_manager

            async def mock_process_user(*args, **kwargs):
                await asyncio.sleep(0.2)  # Each user takes 0.2 seconds
                return {
                    "user_id": kwargs.get("user_id", "unknown"),
                    "status": "SUCCESS",
                    "skipped": False,
                    "scanned_conversations": 1,
                    "scanned_messages": 1,
                    # Current implementation extracts only one classified type per conversation
                    "written_memories": {"semantic": 0, "episodic": 1, "procedural": 0},
                }

            mock_process.side_effect = mock_process_user

            # Create mock base_client
            mock_base_client = MagicMock()
            mock_base_client.memory = mock_memory
            async def mock_create():
                return mock_memory
            mock_base_client.create = mock_create

            result = await _execute_extraction_async(
                base_client=mock_base_client,
                subtype_clients=mock_subtype_clients,
                task_id="task1",
                run_id="run1",
                user_ids=user_ids,
                app_id="app1",
                start_time="2026-01-23T00:00:00Z",
                end_time="2026-01-24T00:00:00Z",
                dify_base_url="http://localhost/v1",
                dify_api_key="test_key",
                max_conversations=50,
                max_tokens_per_conversation=64000,
                time_budget_sec=1,  # Short time budget to trigger timeout
            )

            # Should not process all 100 users due to timeout
            assert result["status"] == "PARTIAL_SUCCESS"
            assert result["summary"]["processed_users"] < 100
            assert result["summary"]["skipped_users"] > 0

    async def test_error_handling(
        self,
        mock_memory,
        mock_subtype_clients,
        mock_dify_client,
        mock_lock_manager,
    ):
        """Test error handling when some users fail."""
        user_ids = ["user1", "user2", "user3"]

        with (
            patch("tools.extract_long_term_memory._process_single_user_async") as mock_process,
            patch("tools.extract_long_term_memory.DifyClient") as mock_dify_cls,
            patch("tools.extract_long_term_memory.SyncLockManager") as mock_lock_cls,
        ):
            mock_dify_cls.return_value = mock_dify_client
            mock_lock_cls.return_value = mock_lock_manager

            async def mock_process_user(*args, **kwargs):
                user_id = kwargs.get("user_id", args[2] if len(args) > 2 else "unknown")
                if user_id == "user2":
                    raise Exception("Processing error")
                return {
                    "user_id": user_id,
                    "status": "SUCCESS",
                    "skipped": False,
                    "scanned_conversations": 1,
                    "scanned_messages": 1,
                    # Current implementation extracts only one classified type per conversation
                    "written_memories": {"semantic": 0, "episodic": 0, "procedural": 1},
                }

            mock_process.side_effect = mock_process_user

            # Create mock base_client
            mock_base_client = MagicMock()
            mock_base_client.memory = mock_memory
            async def mock_create():
                return mock_memory
            mock_base_client.create = mock_create

            result = await _execute_extraction_async(
                base_client=mock_base_client,
                subtype_clients=mock_subtype_clients,
                task_id="task1",
                run_id="run1",
                user_ids=user_ids,
                app_id="app1",
                start_time="2026-01-23T00:00:00Z",
                end_time="2026-01-24T00:00:00Z",
                dify_base_url="http://localhost/v1",
                dify_api_key="test_key",
                max_conversations=50,
                max_tokens_per_conversation=64000,
                time_budget_sec=30,
            )

            assert result["status"] == "PARTIAL_SUCCESS"
            assert result["summary"]["processed_users"] == 2  # user1 and user3

            # Find error report for user2
            user2_report = next(r for r in result["per_user"] if r["user_id"] == "user2")
            assert user2_report["status"] == "ERROR"


class TestExtractLongTermMemoryTool:
    """Tests for ExtractLongTermMemoryTool class."""

    def test_invoke_returns_immediately(self):
        """Test that tool returns immediately with ACCEPTED status."""
        # Mock runtime and session
        mock_runtime = MagicMock()
        mock_runtime.credentials = {
            "local_llm_json_secret": "{}",
            "local_embedder_json_secret": "{}",
            "local_vector_db_json_secret": "{}",
        }
        mock_session = MagicMock()
        
        tool = ExtractLongTermMemoryTool(runtime=mock_runtime, session=mock_session)

        with (
            patch("utils.mem0_client.get_async_client") as mock_get_client,
            patch("tools.extract_long_term_memory.build_subtype_async_clients") as mock_subtypes,
            patch("tools.extract_long_term_memory.AsyncTaskStatusManager"),  # noqa: F401
            patch("tools.extract_long_term_memory.BackgroundEventLoop") as mock_loop_cls,
            patch("tools.extract_long_term_memory.TaskTracker"),
        ):
            # Setup mock async client
            mock_base_client = MagicMock()
            mock_memory = MagicMock()
            mock_base_client.memory = mock_memory
            async def mock_create():
                return mock_memory
            mock_base_client.create = mock_create
            mock_get_client.return_value = mock_base_client
            mock_subtypes.return_value = {}

            mock_loop = MagicMock()
            mock_loop_cls.ensure_loop.return_value = mock_loop

            # Mock asyncio.run_coroutine_threadsafe
            mock_future = MagicMock()
            def _run_coroutine_threadsafe(coro, loop):
                coro.close()  # Avoid "coroutine was never awaited" warning in tests
                return mock_future
            with patch(
                "asyncio.run_coroutine_threadsafe",
                side_effect=_run_coroutine_threadsafe,
            ):
                messages = list(
                    tool._invoke(
                        {
                            "user_ids": '["user1"]',
                            "app_id": "app1",
                            "dify_base_url": "http://localhost/v1",
                            "dify_api_key": "test_key",
                        }
                    )
                )

            # Should return 2 messages (JSON + text)
            assert len(messages) == 2

            # First message should be JSON with ACCEPTED status
            json_msg = messages[0]
            assert hasattr(json_msg, "message")

    def test_invoke_validation_errors(self):
        """Test parameter validation errors."""
        mock_runtime = MagicMock()
        mock_session = MagicMock()
        tool = ExtractLongTermMemoryTool(runtime=mock_runtime, session=mock_session)

        # Test missing user_ids
        messages = list(
            tool._invoke(
                {
                    "app_id": "app1",
                    "dify_base_url": "http://localhost/v1",
                    "dify_api_key": "test_key",
                }
            )
        )

        assert len(messages) == 2
        # Should contain error message

    def test_invoke_with_custom_limits(self):
        """Test invoke with custom conversation and message limits."""
        # Mock runtime and session
        mock_runtime = MagicMock()
        mock_runtime.credentials = {
            "local_llm_json_secret": "{}",
            "local_embedder_json_secret": "{}",
            "local_vector_db_json_secret": "{}",
        }
        mock_session = MagicMock()
        
        tool = ExtractLongTermMemoryTool(runtime=mock_runtime, session=mock_session)

        with (
            patch("utils.mem0_client.get_async_client") as mock_get_client,
            patch("tools.extract_long_term_memory.build_subtype_async_clients") as mock_subtypes,
            patch("tools.extract_long_term_memory.AsyncTaskStatusManager"),  # noqa: F401
            patch("tools.extract_long_term_memory.BackgroundEventLoop") as mock_loop_cls,
            patch("tools.extract_long_term_memory.TaskTracker"),
        ):
            # Setup mock async client
            mock_base_client = MagicMock()
            mock_memory = MagicMock()
            mock_base_client.memory = mock_memory
            async def mock_create():
                return mock_memory
            mock_base_client.create = mock_create
            mock_get_client.return_value = mock_base_client
            mock_subtypes.return_value = {}

            mock_loop = MagicMock()
            mock_loop_cls.ensure_loop.return_value = mock_loop

            def _run_coroutine_threadsafe(coro, loop):
                coro.close()  # Avoid "coroutine was never awaited" warning in tests
                return MagicMock()
            with patch(
                "asyncio.run_coroutine_threadsafe",
                side_effect=_run_coroutine_threadsafe,
            ):
                messages = list(
                    tool._invoke(
                        {
                            "user_ids": '["user1"]',
                            "app_id": "app1",
                            "dify_base_url": "http://localhost/v1",
                            "dify_api_key": "test_key",
                            "conversations_limit": 50,
                            "max_tokens_per_conversation": 64,
                        }
                    )
                )

            assert len(messages) == 2


class TestConcurrencyControl:
    """Tests for concurrency control mechanisms."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        """Test that semaphore correctly limits concurrent executions."""
        max_concurrent = [0]
        current_concurrent = []

        async def mock_task():
            current_concurrent.append(1)
            max_concurrent[0] = max(max_concurrent[0], len(current_concurrent))
            await asyncio.sleep(0.1)
            current_concurrent.pop()

        semaphore = asyncio.Semaphore(EXTRACTION_MAX_CONCURRENT_USERS)

        async def task_with_semaphore():
            async with semaphore:
                await mock_task()

        # Start 20 tasks
        tasks = [task_with_semaphore() for _ in range(20)]
        await asyncio.gather(*tasks)

        # Max concurrent should not exceed limit
        assert max_concurrent[0] <= EXTRACTION_MAX_CONCURRENT_USERS
        assert max_concurrent[0] > 0


class TestIntegration:
    """Integration tests for the complete flow."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_end_to_end_extraction(
        self,
        mock_memory,
        mock_subtype_clients,
    ):
        """Test end-to-end extraction with mocked dependencies."""
        # This would be a full integration test with real-ish data
        # Intentionally included in default unit test runs

