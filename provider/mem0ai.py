"""Mem0 provider for Dify plugin system (local mode only).

This module implements a tool provider for Mem0 in local mode. The provider
handles credential validation and provides an interface for Dify to interact
with Mem0's memory capabilities in a self-hosted/local setup.
"""

from __future__ import annotations

from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from utils.config_builder import build_local_mem0_config
from utils.logger import get_logger, set_log_level

logger = get_logger(__name__)

NON_VECTOR_STORE_PROVIDERS = frozenset(
    {
        "anthropic",
        "azure_openai",
        "azure_openai_structured",
        "cohere",
        "deepseek",
        "gemini",
        "groq",
        "huggingface",
        "litellm",
        "mistral",
        "ollama",
        "openai",
        "together",
        "xai",
    }
)

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
    without performing network I/O during Dify credential saving.
    """

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        log_level = credentials.get("log_level", "INFO")
        set_log_level(log_level)

        logger.debug("Validating Mem0 provider credentials")

        try:
            config = build_local_mem0_config(credentials)
            vector_store = config.get("vector_store", {})
            vector_provider = str(vector_store.get("provider", "")).strip().lower()
            if vector_provider in NON_VECTOR_STORE_PROVIDERS:
                raise ValueError(
                    "Vector Database Configuration uses provider "
                    f"'{vector_provider}', which is an LLM/embedder provider. "
                    "Paste the PGVector JSON into the Vector Database Configuration "
                    "field and keep the OpenAI-compatible embedding JSON in the "
                    "Embedder Configuration field."
                )
            logger.debug("Credential configuration validated without remote I/O")
        except ToolProviderCredentialValidationError as e:
            # Check if this is a "credential not found in provider" error
            # which typically indicates legacy configuration fields
            error_msg = str(e)
            is_credential_not_found = "not found in provider" in error_msg.lower() or (
                "credential" in error_msg.lower() and "not found" in error_msg.lower()
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
