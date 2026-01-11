"""Mem0 provider for Dify plugin system (local mode only).

This module implements a tool provider for Mem0 in local mode. The provider
handles credential validation and provides an interface for Dify to interact
with Mem0's memory capabilities in a self-hosted/local setup.
"""

from __future__ import annotations

import asyncio
from concurrent import futures
from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from utils.config_builder import is_async_mode
from utils.constants import READ_OPERATION_TIMEOUT
from utils.logger import get_logger, set_log_level
from utils.mem0_client import (
    get_async_client,
    get_sync_client,
)

logger = get_logger(__name__)

# Legacy configuration fields that have been removed
LEGACY_FIELDS = [
    "local_llm_json",
    "local_embedder_json",
    "local_vector_db_json",
    "local_graph_db_json",
    "local_reranker_json",
]


def _get_legacy_fields_error_message(
    original_error: str | None = None,
) -> str:
    """Generate a friendly error message for legacy configuration fields.

    Args:
        original_error: Optional original error message from Dify framework.

    Returns:
        A formatted error message with solution steps.

    """
    error_part = f"Error: {original_error}\n\n" if original_error else ""
    return (
        "Legacy configuration fields detected. "
        "These fields have been removed in the new version.\n\n"
        f"{error_part}"
        "Solution:\n"
        "1. Please delete the old credentials configuration\n"
        "2. Reconfigure using the new configuration fields in the plugin settings"
    )


class Mem0Provider(ToolProvider):
    """Tool provider for Mem0 (local).

    Validates simplified JSON configs for local LLM/Embedder/Reranker/Vector/Graph
    and performs a lightweight sanity search to ensure configuration is valid.
    """

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        # Set log level from credentials (can be changed online)
        log_level = credentials.get("log_level", "INFO")
        set_log_level(log_level)

        logger.debug("Validating Mem0 provider credentials")

        # Use a longer timeout for validation to allow for vector DB initialization
        # (e.g., Pinecone connection setup, index creation, etc.)
        validation_timeout = READ_OPERATION_TIMEOUT * 2  # 30 seconds

        try:
            async_mode = is_async_mode(credentials)
            mode = "async" if async_mode else "sync"
            logger.debug("Validating credentials in %s mode", mode)
            if async_mode:
                client = get_async_client(credentials)
                loop = client.ensure_bg_loop()
                # Perform a small no-op search to validate providers
                _ = asyncio.run_coroutine_threadsafe(
                    client.search({"query": "test", "user_id": "validation_test"}),
                    loop,
                ).result(timeout=validation_timeout)
            else:
                client = get_sync_client(credentials)
                _ = client.search({"query": "test", "user_id": "validation_test"})
            logger.debug("Credentials validated successfully")
        except futures.TimeoutError as e:
            # Handle timeout errors specifically for better error messages
            error_msg = (
                f"Credential validation timed out after {validation_timeout} seconds. "
                "This may indicate:\n"
                "1. Network connectivity issues to the vector database service\n"
                "2. Slow response from the vector database service\n"
                "3. Vector database service is unavailable\n"
                "Please check your network connection and vector database configuration."
            )
            logger.exception("Credential validation timed out")
            raise ToolProviderCredentialValidationError(error_msg) from e
        except ToolProviderCredentialValidationError as e:
            # Check if this is a "credential not found in provider" error
            # which typically indicates legacy configuration fields
            error_msg = str(e)
            is_credential_not_found = (
                "not found in provider" in error_msg.lower()
                or (
                    "credential" in error_msg.lower()
                    and "not found" in error_msg.lower()
                )
            )
            if is_credential_not_found:
                # Provide a friendly message to guide users to reconfigure
                friendly_msg = _get_legacy_fields_error_message(error_msg)
                logger.exception("Credential validation failed: legacy fields detected")
                raise ToolProviderCredentialValidationError(friendly_msg) from e
            # For other ToolProviderCredentialValidationError, re-raise as-is
            raise
        except Exception as e:
            # Handle other types of errors
            logger.exception("Credential validation failed")
            raise ToolProviderCredentialValidationError(str(e)) from e
