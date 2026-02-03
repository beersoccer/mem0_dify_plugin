"""Tests for token-based conversation truncation."""

from __future__ import annotations

from utils.extraction_helpers import (
    count_message_tokens,
    truncate_to_recent_messages,
)


def test_count_message_tokens_basic() -> None:
    """Test basic token counting."""
    messages = [
        {"query": "Hello", "answer": "Hi there!"},
        {"query": "How are you?", "answer": "I'm doing well, thank you!"},
    ]
    
    # Should count tokens for all content
    token_count = count_message_tokens(messages)
    assert token_count > 0
    assert isinstance(token_count, int)


def test_count_message_tokens_empty() -> None:
    """Test token counting with empty messages."""
    messages: list[dict[str, str]] = []
    token_count = count_message_tokens(messages)
    assert token_count == 0


def test_truncate_to_recent_messages_under_limit() -> None:
    """Test truncation when messages are under token limit."""
    messages = [
        {"id": "1", "query": "Hello"},
        {"id": "2", "answer": "Hi there!"},
        {"id": "3", "query": "How are you?"},
    ]

    # Large limit - should return all messages
    result = truncate_to_recent_messages(messages, max_tokens=100000)
    assert len(result) == 3
    assert result == messages


def test_truncate_to_recent_messages_over_limit() -> None:
    """Test truncation when messages exceed token limit."""
    # Create messages with known content
    messages = [
        {"id": "1", "query": "Message 1" * 100},  # ~200 tokens
        {"id": "2", "query": "Message 2" * 100},  # ~200 tokens
        {"id": "3", "query": "Message 3" * 100},  # ~200 tokens
        {"id": "4", "query": "Message 4" * 100},  # ~200 tokens
    ]

    # Set limit to ~400 tokens - should keep only last 2 messages
    result = truncate_to_recent_messages(messages, max_tokens=400)
    
    # Should return most recent messages that fit within limit
    assert len(result) < len(messages)
    assert len(result) >= 1  # At least one message

    # Should be in chronological order
    if len(result) >= 2:
        assert result[0]["id"] < result[1]["id"]
    
    # Should include the most recent message
    assert result[-1]["id"] == "4"


def test_truncate_to_recent_messages_preserves_order() -> None:
    """Test that truncation preserves chronological order."""
    messages = [
        {"id": "1", "query": "First"},
        {"id": "2", "query": "Second"},
        {"id": "3", "query": "Third"},
        {"id": "4", "query": "Fourth"},
    ]

    result = truncate_to_recent_messages(messages, max_tokens=50)

    # Should be in chronological order (oldest to newest)
    for i in range(len(result) - 1):
        assert int(result[i]["id"]) < int(result[i + 1]["id"])


def test_truncate_to_recent_messages_at_least_one() -> None:
    """Test that truncation always returns at least one message."""
    messages = [
        {"id": "1", "query": "Very long message " * 1000},  # Very large message
    ]

    # Even with very small limit, should return at least the last message
    result = truncate_to_recent_messages(messages, max_tokens=10)
    assert len(result) == 1
    assert result[0]["id"] == "1"


def test_count_message_tokens_with_multiple_fields() -> None:
    """Test token counting with multiple content fields."""
    messages = [
        {
            "query": "What is the weather?",
            "answer": "The weather is sunny today.",
            "content": "Additional context",
        }
    ]

    token_count = count_message_tokens(messages)
    # Should count tokens from query, answer (content field not counted in current impl)
    # With fallback estimation (4 chars/token), this should be at least 4 tokens
    assert token_count >= 4


def test_truncate_with_fallback_encoding() -> None:
    """Test that truncation works even with encoding fallback."""
    messages = [
        {"id": "1", "query": "Message 1"},
        {"id": "2", "query": "Message 2"},
        {"id": "3", "query": "Message 3"},
    ]

    # Use invalid encoding to trigger fallback
    result = truncate_to_recent_messages(
        messages, max_tokens=100, encoding_name="invalid_encoding"
    )
    
    # Should still work with fallback
    assert len(result) > 0
    assert result[-1]["id"] == "3"  # Most recent message

