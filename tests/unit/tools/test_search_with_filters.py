"""Regression test for search with filters bug.

This test ensures that user_id/agent_id/run_id are always passed to mem0
even when filters are provided, preventing ValidationError.
"""

from __future__ import annotations

import pytest

from utils.mem0_client import AsyncMem0Client


@pytest.mark.asyncio
async def test_search_with_filters_includes_user_id():
    """Test that search passes user_id to mem0 even when filters are provided.
    
    Regression test for bug where user_id was not passed to mem0 when filters
    were present, causing ValidationError: "At least one of 'user_id', 'agent_id',
    or 'run_id' must be provided."
    """
    # Create client with minimal config
    config = {
        "mem0_api_key": "",
        "mem0_base_url": "",
        "mem0_org_id": "",
        "mem0_project_id": "",
        "provider": "local",
        "local_llm_json_secret": {
            "provider": "ollama",
            "config": {"model": "qwen2.5:latest"},
        },
        "local_embedder_json_secret": {
            "provider": "ollama",
            "config": {"model": "nomic-embed-text:latest"},
        },
        "local_vector_db_json_secret": {
            "provider": "qdrant",
            "config": {"collection_name": "test_search_filters"},
        },
        "version": "v1.1",
    }
    
    client = AsyncMem0Client(config)
    
    try:
        # Initialize memory
        await client.get_memory()
        
        # Build payload with user_id AND filters
        payload = {
            "query": "test query",
            "user_id": "test_user_123",
            "filters": {
                "NOT": [{"__internal": {"eq": True}}]
            },
            "limit": 5,
        }
        
        # This should NOT raise ValidationError
        # The bug was that when filters were present, user_id was not passed to mem0
        results = await client.search(payload)
        
        # Verify results is a list (even if empty)
        assert isinstance(results, list)
        
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_search_with_filters_includes_agent_id():
    """Test that search passes agent_id to mem0 even when filters are provided."""
    config = {
        "mem0_api_key": "",
        "mem0_base_url": "",
        "mem0_org_id": "",
        "mem0_project_id": "",
        "provider": "local",
        "local_llm_json_secret": {
            "provider": "ollama",
            "config": {"model": "qwen2.5:latest"},
        },
        "local_embedder_json_secret": {
            "provider": "ollama",
            "config": {"model": "nomic-embed-text:latest"},
        },
        "local_vector_db_json_secret": {
            "provider": "qdrant",
            "config": {"collection_name": "test_search_filters_agent"},
        },
        "version": "v1.1",
    }
    
    client = AsyncMem0Client(config)
    
    try:
        await client.get_memory()
        
        payload = {
            "query": "test query",
            "agent_id": "test_agent_456",
            "filters": {
                "NOT": [{"__internal": {"eq": True}}]
            },
        }
        
        # Should not raise ValidationError
        results = await client.search(payload)
        assert isinstance(results, list)
        
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_search_without_filters_includes_user_id():
    """Test that search passes user_id to mem0 when filters are NOT provided."""
    config = {
        "mem0_api_key": "",
        "mem0_base_url": "",
        "mem0_org_id": "",
        "mem0_project_id": "",
        "provider": "local",
        "local_llm_json_secret": {
            "provider": "ollama",
            "config": {"model": "qwen2.5:latest"},
        },
        "local_embedder_json_secret": {
            "provider": "ollama",
            "config": {"model": "nomic-embed-text:latest"},
        },
        "local_vector_db_json_secret": {
            "provider": "qdrant",
            "config": {"collection_name": "test_search_no_filters"},
        },
        "version": "v1.1",
    }
    
    client = AsyncMem0Client(config)
    
    try:
        await client.get_memory()
        
        # Payload without filters
        payload = {
            "query": "test query",
            "user_id": "test_user_789",
        }
        
        # Should not raise ValidationError
        results = await client.search(payload)
        assert isinstance(results, list)
        
    finally:
        await client.aclose()

