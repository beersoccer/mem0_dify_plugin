from __future__ import annotations

import json
import logging

from utils.mem0_extraction import SyncMemoryClassificationManager


class DummyLLM:
    def generate_response(self, messages, response_format=None):  # noqa: ANN001,D401
        return json.dumps(
            {
                "memory_type": "semantic",
                "should_extract": True,
                "reason": "test",
            }
        )


class DummyMemory:
    llm = DummyLLM()


def test_classification_logs_are_debug(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="utils.mem0_extraction")
    manager = SyncMemoryClassificationManager(DummyMemory())
    manager.classify(messages=[{"role": "user", "content": "I love coffee."}])

    debug_msgs = [
        record
        for record in caplog.records
        if record.levelno == logging.DEBUG
        and "Memory classification result" in record.getMessage()
    ]
    info_msgs = [
        record
        for record in caplog.records
        if record.levelno == logging.INFO
        and "Memory classification result" in record.getMessage()
    ]

    assert debug_msgs
    assert not info_msgs

