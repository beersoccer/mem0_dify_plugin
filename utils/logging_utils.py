"""Helpers for producing useful logs without exposing credentials."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

REDACTED_VALUE = "[REDACTED]"
DEFAULT_LOG_VALUE_MAX_CHARS = 60000

_SENSITIVE_KEYS = {
    "access_key",
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "connection_string",
    "credential",
    "database_url",
    "dsn",
    "http_client_proxies",
    "password",
    "passwd",
    "private_key",
    "proxies",
    "proxy",
    "secret",
    "token",
}
_SENSITIVE_SUFFIXES = (
    "_access_key",
    "_access_token",
    "_api_key",
    "_client_secret",
    "_credential",
    "_password",
    "_private_key",
    "_secret",
    "_token",
)


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_SUFFIXES)


def redact_for_logging(value: Any, _seen: set[int] | None = None) -> Any:
    """Convert nested values to log-safe JSON-compatible structures."""
    if value is None or isinstance(value, str | int | float | bool):
        return value

    seen = _seen if _seen is not None else set()
    value_id = id(value)
    if value_id in seen:
        return "<recursive>"

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            value = model_dump(mode="json")
        except TypeError:
            value = model_dump()

    if isinstance(value, Mapping):
        seen.add(value_id)
        try:
            return {
                str(key): (
                    REDACTED_VALUE
                    if _is_sensitive_key(key)
                    else redact_for_logging(item, seen)
                )
                for key, item in value.items()
            }
        finally:
            seen.discard(value_id)

    if isinstance(value, list | tuple | set | frozenset):
        seen.add(value_id)
        try:
            return [redact_for_logging(item, seen) for item in value]
        finally:
            seen.discard(value_id)

    return str(value)


def format_for_logging(
    value: Any,
    *,
    max_chars: int = DEFAULT_LOG_VALUE_MAX_CHARS,
) -> str:
    """Serialize a value for structured logs and cap oversized payloads."""
    try:
        text = json.dumps(
            redact_for_logging(value),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    except Exception:
        text = repr(value)

    if max_chars > 0 and len(text) > max_chars:
        omitted = len(text) - max_chars
        return f"{text[:max_chars]}... [truncated {omitted} chars]"
    return text
