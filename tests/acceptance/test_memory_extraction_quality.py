"""Acceptance tests: memory classification and extraction quality.

Seeds its own independent conversations from the ``acceptance_extraction``
section of ``conversation_seed_cases.yaml`` (user IDs carry the ``-x`` suffix).
This is completely isolated from ``test_workflow_memory_lifecycle`` which seeds
``acceptance_lifecycle`` users (``-w`` suffix).

Verifies that the Python-side LLM classifier assigns the correct memory type
and that at least one memory is successfully extracted per conversation.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from tests.helpers.artifacts import write_json_artifact
from tests.helpers.dify_cleanup import cleanup_seeded_conversations
from tests.helpers.dify_env import require_mem0_credentials
from tests.helpers.dify_seed import load_seed_cases, seed_chatflow_cases
from tests.helpers.mem0_cleanup import cleanup_mem0_state
from utils.dify_client import DifyClient
from utils.extraction import scan_user_conversations_incremental
from utils.mem0_client import SyncMem0Client
from utils.mem0_extraction import (
    SyncMemoryClassificationManager,
    SyncMemoryWriter,
    build_memory_metadata,
    build_subtype_sync_clients,
)
from utils.message_utils import count_add_results, dify_msg_to_mem0_messages

pytestmark = [pytest.mark.workflow_acceptance, pytest.mark.slow]

_SEED_CASES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "conversation_seed_cases.yaml"


def test_memory_classification_and_extraction(
    acceptance_chat_client: DifyClient,
    acceptance_env_config: dict[str, str],
) -> None:
    """For each seeded conversation, verify classifier assigns the expected memory
    type and that at least one memory is extracted.

    Acceptance criteria (soft — logged but not hard failures):
    - Classification accuracy >= 80 % across all typed cases.
    - Every conversation with expected_memory_type must produce >= 1 memory.

    Hard failures:
    - At least one conversation must be classified and extracted successfully.
    """
    env_config = acceptance_env_config
    dify_client = acceptance_chat_client
    mem0_credentials = require_mem0_credentials(env_config)
    app_id = (env_config.get("DIFY_CHATFLOW_APP_ID") or "").strip() or None

    # Seed this test's own independent conversations.
    cases = load_seed_cases(_SEED_CASES_PATH, section="acceptance_extraction")
    if not cases:
        pytest.skip("No enabled cases in acceptance_extraction section")
    acceptance_seed = seed_chatflow_cases(dify_client, cases=cases, run_id=uuid4().hex)
    write_json_artifact("acceptance-extraction-seed-manifest", acceptance_seed.to_dict())
    if not acceptance_seed.conversations:
        pytest.skip("No conversations were seeded for acceptance_extraction")

    start_time = acceptance_seed.started_at_with_buffer(-60)
    end_time = acceptance_seed.finished_at_with_buffer(60)

    from utils.config_builder import build_local_mem0_config_without_pool

    config = build_local_mem0_config_without_pool(mem0_credentials)
    base_client = SyncMem0Client(mem0_credentials, enable_keepalive=False, config_override=config)
    subtype_clients = build_subtype_sync_clients(mem0_credentials, base_client=base_client)

    total = 0
    classification_correct = 0
    extraction_successful = 0
    touched_users: set[str] = set()
    results_log: list[dict] = []

    try:
        for seeded in acceptance_seed.conversations:  # type: ignore[union-attr]
            conversations_data, _, _ = scan_user_conversations_incremental(
                dify_client,
                user_id=seeded.user_id,
                run_at=end_time,
                user_checkpoint=None,
                start_time=start_time,
                app_id=app_id,
                max_conversations=10,
            )

            messages = conversations_data.get(seeded.conversation_id)
            if not messages:
                results_log.append({"case": seeded.case_name, "status": "no_messages"})
                continue

            mem0_msgs = dify_msg_to_mem0_messages(messages)
            if not mem0_msgs:
                results_log.append({"case": seeded.case_name, "status": "empty_after_conversion"})
                continue

            total += 1
            expected_type = seeded.expected_memory_type

            classification_mgr = SyncMemoryClassificationManager(subtype_clients["semantic"].memory)
            classified_type, should_extract = classification_mgr.classify(messages=mem0_msgs)

            classified_upper = (classified_type or "").upper()
            class_correct = bool(expected_type and classified_upper == expected_type)
            if class_correct:
                classification_correct += 1

            if not should_extract or not classified_type:
                results_log.append({
                    "case": seeded.case_name,
                    "expected": expected_type,
                    "classified": classified_upper,
                    "class_correct": class_correct,
                    "status": "skipped_by_classifier",
                })
                continue

            metadata = build_memory_metadata(subtype=classified_type, memory_origin="implicit")
            writer = SyncMemoryWriter(subtype_clients[classified_type])
            result = writer.add_memory(
                messages=mem0_msgs,
                user_id=seeded.user_id,
                agent_id=app_id,
                metadata=metadata,
            )
            touched_users.add(seeded.user_id)
            memory_count = count_add_results(result)
            if memory_count > 0:
                extraction_successful += 1

            results_log.append({
                "case": seeded.case_name,
                "expected": expected_type,
                "classified": classified_upper,
                "class_correct": class_correct,
                "memories_extracted": memory_count,
                "status": "ok" if memory_count > 0 else "no_memories",
            })

    finally:
        if touched_users:
            mem0_cleanup = cleanup_mem0_state(
                mem0_credentials,
                user_ids=sorted(touched_users),
                app_id=app_id,
                task_ids=[],
            )
            write_json_artifact(
                "acceptance-extraction-mem0-cleanup",
                {"touched_users": sorted(touched_users), "summary": mem0_cleanup},
            )
        dify_cleanup = cleanup_seeded_conversations(
            dify_client, manifest=acceptance_seed, verify=False
        )
        write_json_artifact("acceptance-extraction-dify-cleanup", dify_cleanup)

    write_json_artifact("acceptance-extraction-results", {"results": results_log})

    typed_total = sum(1 for r in results_log if r.get("expected"))
    class_rate = (classification_correct / typed_total * 100) if typed_total else 0.0

    assert total > 0, "No conversations could be scanned — check seed and time window"
    assert extraction_successful > 0, (
        f"No memories were extracted across {total} conversations. Results: {results_log}"
    )
    assert class_rate >= 80.0, (
        f"Classification accuracy {class_rate:.1f}% is below 80% "
        f"({classification_correct}/{typed_total} correct). Results: {results_log}"
    )
