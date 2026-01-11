"""PGVector configuration normalization for Mem0.

This module handles all pgvector-specific configuration processing, including:
- Connection string building from individual parameters
- Connection pool creation and management
- Parameter validation and normalization

Reference: Mem0 pgvector configuration documentation
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse, urlunparse

from .constants import PGVECTOR_MAX_CONNECTIONS, PGVECTOR_MIN_CONNECTIONS
from .logger import get_logger

logger = get_logger(__name__)


def _extract_pool_parameters(
    normalized: dict[str, Any],
) -> tuple[dict[str, Any] | None, bool, bool]:
    """Extract and process connection pool parameters.

    Args:
        normalized: Normalized config dict (will be modified, pool params removed).

    Returns:
        Tuple of (pool_params, psycopg3_available, psycopg2_available).
        - pool_params: Dict with all pool parameters, or None if both unavailable.
        - psycopg3_available: Whether psycopg3 is available.
        - psycopg2_available: Whether psycopg2 is available.

    """
    # Try to import psycopg3
    psycopg3_available = False
    psycopg2_available = False

    try:
        from psycopg_pool import ConnectionPool as Psycopg3Pool
        psycopg3_available = True
    except ImportError:
        pass

    # Try to import psycopg2
    try:
        import psycopg2.pool  # noqa: F401
        psycopg2_available = True
    except ImportError:
        pass

    if not psycopg3_available and not psycopg2_available:
        return None, False, False

    # Extract pool size from minconn/maxconn (mem0 native parameters)
    pool_min_size = int(normalized.get("minconn", PGVECTOR_MIN_CONNECTIONS))
    pool_max_size = int(normalized.get("maxconn", PGVECTOR_MAX_CONNECTIONS))

    # Base pool parameters (common to both psycopg3 and psycopg2)
    pool_params = {
        "min_size": pool_min_size,
        "max_size": pool_max_size,
    }

    # Advanced psycopg3 ConnectionPool parameters (only for psycopg3)
    if psycopg3_available:
        pool_max_lifetime = float(normalized.pop("pool_max_lifetime", None) or 3600.0)
        pool_max_idle = float(normalized.pop("pool_max_idle", None) or 600.0)
        pool_timeout = float(normalized.pop("pool_timeout", None) or 30.0)
        pool_reconnect_timeout = float(
            normalized.pop("pool_reconnect_timeout", None) or 300.0,
        )
        pool_max_waiting = int(normalized.pop("pool_max_waiting", None) or 0)

        pool_open = normalized.pop("pool_open", None)
        if pool_open is None:
            pool_open = True

        pool_check = normalized.pop("pool_check", None)
        if pool_check is False:
            pool_check = None
        elif pool_check in (None, True):
            pool_check = Psycopg3Pool.check_connection
        # else: pool_check is a callable, use it as-is

        pool_params.update({
            "max_lifetime": pool_max_lifetime,
            "max_idle": pool_max_idle,
            "timeout": pool_timeout,
            "reconnect_timeout": pool_reconnect_timeout,
            "max_waiting": pool_max_waiting,
            "open": pool_open,
            "check": pool_check,
        })

    return pool_params, psycopg3_available, psycopg2_available


def _create_connection_pool(
    connection_string: str,
    pool_params: dict[str, Any],
    *,
    psycopg3_available: bool,
    psycopg2_available: bool,
) -> object | None:
    """Create psycopg3 or psycopg2 connection pool.

    Args:
        connection_string: PostgreSQL connection string.
        pool_params: Connection pool parameters dict.
        psycopg3_available: Whether psycopg3 is available.
        psycopg2_available: Whether psycopg2 is available.

    Returns:
        ConnectionPool object, or None if creation failed.

    """
    # Try psycopg3 first
    if psycopg3_available:
        try:
            from psycopg_pool import ConnectionPool

            pool_kwargs = {
                "conninfo": connection_string,
                **pool_params,
            }

            connection_pool = ConnectionPool(**pool_kwargs)

            logger.info(
                "Created psycopg3 ConnectionPool: min_size=%d, max_size=%d, "
                "max_lifetime=%.1f, max_idle=%.1f, timeout=%.1f, "
                "reconnect_timeout=%.1f. Connection string: %s",
                pool_params["min_size"],
                pool_params["max_size"],
                pool_params.get("max_lifetime", 0),
                pool_params.get("max_idle", 0),
                pool_params.get("timeout", 0),
                pool_params.get("reconnect_timeout", 0),
                _mask_password_in_dsn(connection_string),
            )
        except Exception:
            logger.exception(
                "Failed to create psycopg3 ConnectionPool. Connection string: %s",
                _mask_password_in_dsn(connection_string),
            )
        else:
            return connection_pool

    # Fallback to psycopg2
    if psycopg2_available:
        try:
            from psycopg2.pool import ThreadedConnectionPool

            connection_pool = ThreadedConnectionPool(
                minconn=pool_params["min_size"],
                maxconn=pool_params["max_size"],
                dsn=connection_string,
            )

            logger.info(
                "Created psycopg2 ThreadedConnectionPool: minconn=%d, maxconn=%d. "
                "Connection string: %s",
                pool_params["min_size"],
                pool_params["max_size"],
                _mask_password_in_dsn(connection_string),
            )
        except Exception:
            logger.exception(
                "Failed to create psycopg2 ThreadedConnectionPool. Connection string: %s",
                _mask_password_in_dsn(connection_string),
            )
        else:
            return connection_pool

    return None


def _validate_pgvector_connection_params(normalized: dict[str, Any]) -> list[str] | None:
    """Validate required pgvector connection parameters.

    Args:
        normalized: Config dict containing pgvector connection parameters.

    Returns:
        List of missing parameter names, or None if all required params are present.

    """
    user = normalized.get("user") or ""
    password = normalized.get("password") or ""

    missing_params = []
    if not user:
        missing_params.append("user")
    if not password:
        missing_params.append("password")
    # host and port have defaults (localhost and 5432), so we only validate if explicitly empty
    if "host" in normalized and not normalized.get("host"):
        missing_params.append("host")
    if "port" in normalized and not normalized.get("port"):
        missing_params.append("port")

    if missing_params:
        logger.warning(
            "Insufficient pgvector connection parameters (required: %s)",
            ", ".join(missing_params),
        )
        return missing_params
    return None


def _extract_query_params_from_url(connection_string: str) -> list[str]:
    """Extract query parameters from connection string URL as a list.

    Args:
        connection_string: PostgreSQL connection string.

    Returns:
        List of query parameters in "key=value" format.

    """
    parsed = urlparse(connection_string)
    existing_params = parse_qs(parsed.query, keep_blank_values=True)
    return [
        f"{k}={quote_plus(str(v[0] if v else ''))}"
        for k, v in existing_params.items()
    ]


def _rebuild_url_with_query_params(
    connection_string: str,
    query_params: list[str],
) -> str:
    """Rebuild connection string URL with updated query parameters.

    Args:
        connection_string: Original PostgreSQL connection string.
        query_params: Query parameters list in "key=value" format.

    Returns:
        Reconstructed connection string with updated query parameters.

    """
    parsed = urlparse(connection_string)
    new_query = "&".join(query_params) if query_params else ""
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        ),
    )


def _add_pgvector_tcp_keepalive_params(query_params: list[str]) -> list[str]:
    """Add TCP keepalive parameters to query parameters list if not already present.

    Args:
        query_params: Existing query parameters list (format: "key=value").

    Returns:
        Updated query parameters list.

    """
    # Check existing parameters to avoid duplicates
    existing_params_lower = "&".join(query_params).lower()

    keepalive_defaults = [
        ("keepalives", "1"),
        ("keepalives_idle", "30"),
        ("keepalives_interval", "10"),
        ("keepalives_count", "3"),
        ("connect_timeout", "5"),
    ]

    for param_name, param_value in keepalive_defaults:
        # Check if parameter already exists in query_params list
        # Use "param_name=" pattern to avoid false positives (e.g., "nokeepalives")
        param_pattern = f"{param_name}="
        if param_pattern not in existing_params_lower:
            query_params.append(f"{param_name}={param_value}")

    return query_params


def _normalize_connection_string_with_keepalive(connection_string: str) -> str:
    """Normalize connection string by adding TCP keepalive parameters if not present.

    This ensures connection strings follow the same best practices regardless of
    how they are provided (as connection_string or built from individual parameters).

    Args:
        connection_string: PostgreSQL connection string.

    Returns:
        Normalized connection string with keepalive parameters added if missing.

    """
    # Extract query parameters, add keepalive params, and rebuild URL
    query_params = _extract_query_params_from_url(connection_string)
    query_params = _add_pgvector_tcp_keepalive_params(query_params)
    return _rebuild_url_with_query_params(connection_string, query_params)


def _mask_password_in_dsn(dsn: str) -> str:
    """Mask password in DSN for safe logging.

    Args:
        dsn: PostgreSQL connection string.

    Returns:
        DSN with password masked as '***'.

    """
    # Pattern: postgresql://user:password@host:port/dbname
    # Replace password part with ***
    pattern = r"(postgresql://[^:]+:)([^@]+)(@)"
    return re.sub(pattern, r"\1***\3", dsn)


def _build_pgvector_connection_string(normalized: dict[str, Any]) -> str | None:
    """Build PostgreSQL connection string for pgvector from individual parameters.

    Args:
        normalized: Config dict containing pgvector connection parameters.

    Returns:
        PostgreSQL connection string, or None if parameters are insufficient.

    """
    dbname_raw = normalized.get("dbname") or normalized.get("database") or "postgres"
    user = normalized.get("user") or ""
    password = normalized.get("password") or ""
    host = normalized.get("host") or "localhost"
    port = str(normalized.get("port") or "5432")
    sslmode = normalized.get("sslmode")

    # Validate all required parameters according to Mem0 documentation
    missing_params = _validate_pgvector_connection_params(normalized)
    if missing_params:
        return None

    # Extract database name and query parameters from dbname if it contains query string
    dbname = dbname_raw
    params_from_dbname = {}
    if "?" in dbname:
        dbname_parts = dbname.split("?", 1)
        dbname = dbname_parts[0]
        query_string_in_dbname = dbname_parts[1]
        # Parse query parameters from dbname
        params_from_dbname = parse_qs(query_string_in_dbname, keep_blank_values=True)
        # Convert list values to single values (parse_qs returns lists)
        params_from_dbname = {k: v[0] if v else "" for k, v in params_from_dbname.items()}
        logger.debug(
            "Extracted query parameters from dbname: %s",
            list(params_from_dbname.keys()),
        )

    # Build connection_string from individual parameters
    user_enc = quote_plus(str(user))
    pwd_enc = quote_plus(str(password))
    dbname_enc = quote_plus(dbname)
    dsn = f"postgresql://{user_enc}:{pwd_enc}@{host}:{port}/{dbname_enc}"

    # Collect all query parameters
    query_params_dict = {}

    # First, add parameters from dbname (if any)
    # This includes all query parameters extracted from dbname (e.g., sslmode, keepalives, etc.)
    query_params_dict.update(params_from_dbname)

    # Then, add sslmode from config (overrides if present in dbname)
    # Using dict assignment ensures no duplicate sslmode parameter
    if sslmode:
        query_params_dict["sslmode"] = str(sslmode)

    # Build query parameters list (use encoded values for consistency)
    query_params_list = [f"{k}={quote_plus(str(v))}" for k, v in query_params_dict.items()]

    # Add TCP keepalive parameters (best practice defaults) if not already present
    query_params_list = _add_pgvector_tcp_keepalive_params(query_params_list)

    # Build final connection string
    if query_params_list:
        dsn = f"{dsn}?{'&'.join(query_params_list)}"

    logger.debug(
        "Built connection_string from individual parameters: %s",
        _mask_password_in_dsn(dsn),
    )
    return dsn


def _remove_connection_params(
    normalized: dict[str, Any],
    *,
    also_remove_pool_params: bool = False,
) -> None:
    """Remove connection parameters from config.

    Args:
        normalized: Config dict (will be modified).
        also_remove_pool_params: Whether to also remove pool parameters.

    """
    keys_to_remove = ["user", "password", "host", "port", "sslmode"]

    if also_remove_pool_params:
        keys_to_remove.extend([
            "connection_string",
            "pool_max_lifetime",
            "pool_max_idle",
            "pool_timeout",
            "pool_reconnect_timeout",
            "pool_max_waiting",
            "pool_open",
            "pool_check",
        ])

    for key in keys_to_remove:
        normalized.pop(key, None)


def _create_and_set_pool(
    normalized: dict[str, Any],
    connection_string: str,
) -> None:
    """Create connection pool and set it in normalized config.

    Args:
        normalized: Config dict (will be modified).
        connection_string: PostgreSQL connection string.

    """
    pool_params, psycopg3_available, psycopg2_available = _extract_pool_parameters(normalized)

    if not psycopg3_available and not psycopg2_available:
        logger.warning(
            "Neither psycopg3 nor psycopg2 is available. Using connection_string only. "
            "Install psycopg[pool] or psycopg2 to enable connection pool features. "
            "Connection string: %s",
            _mask_password_in_dsn(connection_string),
        )
        return

    connection_pool = _create_connection_pool(
        connection_string,
        pool_params,
        psycopg3_available=psycopg3_available,
        psycopg2_available=psycopg2_available,
    )

    if connection_pool:
        normalized["connection_pool"] = connection_pool
    else:
        logger.warning(
            "Failed to create connection pool. Falling back to connection_string only. "
            "Connection string: %s",
            _mask_password_in_dsn(connection_string),
        )


def _handle_connection_string(normalized: dict[str, Any]) -> None:
    """Handle connection_string case by creating connection pool.

    Args:
        normalized: Config dict (will be modified).

    """
    connection_string = normalized["connection_string"]
    normalized_connection_string = _normalize_connection_string_with_keepalive(
        connection_string,
    )

    if normalized_connection_string != connection_string:
        logger.debug(
            "Added TCP keepalive parameters to connection_string: %s",
            _mask_password_in_dsn(normalized_connection_string),
        )
        normalized["connection_string"] = normalized_connection_string
    else:
        logger.debug(
            "Using connection_string (second priority) to create connection pool: %s",
            _mask_password_in_dsn(connection_string),
        )

    _create_and_set_pool(normalized, normalized_connection_string)
    _remove_connection_params(normalized)


def _handle_individual_params(
    normalized: dict[str, Any],
    original_config: dict[str, Any],
) -> dict[str, Any]:
    """Handle individual connection parameters case.

    Args:
        normalized: Config dict (will be modified).
        original_config: Original config to return if parameters are insufficient.

    Returns:
        Normalized config dict, or original_config if parameters are insufficient.

    """
    connection_string = _build_pgvector_connection_string(normalized)
    if connection_string is None:
        return original_config

    normalized["connection_string"] = connection_string
    _create_and_set_pool(normalized, connection_string)
    _remove_connection_params(normalized)
    return normalized


def normalize_pgvector_config(
    config: dict[str, Any],
) -> dict[str, Any]:
    """Normalize pgvector config according to Mem0 official documentation.

    Supports three connection methods (in priority order):
    1. connection_pool (highest priority) - psycopg2 or psycopg3 connection pool object
       (auto-created when connection_string is provided, or can be provided directly)
    2. connection_string - PostgreSQL connection string
    3. Individual parameters - user, password, host, port, dbname, sslmode

    When connection_string is provided, automatically creates a psycopg3 ConnectionPool
    (or psycopg2 ThreadedConnectionPool if psycopg3 is unavailable) with configurable
    pool parameters.

    TCP keepalive parameters are automatically added to connection strings if not present,
    ensuring consistent best practices regardless of configuration method (connection_string
    or individual parameters).

    Connection pool parameters (in JSON config, same level as connection_string):
    - minconn: Minimum connections for mem0 PGVector (default: 10)
    - maxconn: Maximum connections for mem0 PGVector (default: 40)
    - pool_max_lifetime, pool_max_idle, pool_timeout, etc.: Advanced psycopg3
      ConnectionPool parameters (optional, for fine-tuning)

    Args:
        config: Raw pgvector configuration dictionary.

    Returns:
        Normalized pgvector configuration dictionary.

    Reference: Mem0 pgvector configuration documentation

    """
    normalized: dict[str, Any] = {}

    # Valid pgvector config keys according to official documentation
    # Standard parameters (documented in Mem0 official docs):
    valid_keys = (
        "dbname",  # Database name (default: "postgres")
        "collection_name",  # Collection name (default: "mem0")
        "embedding_model_dims",  # Embedding dimensions (default: 1536)
        "user",  # Database user (required)
        "password",  # Database password (required)
        "host",  # Database host (required)
        "port",  # Database port (required)
        "diskann",  # Use DiskANN for vector search (default: True)
        "hnsw",  # Use HNSW for vector search (default: False)
        "sslmode",  # SSL mode (optional)
        "connection_string",  # PostgreSQL connection string (overrides individual params)
        "connection_pool",  # psycopg2/psycopg3 connection pool object (highest priority)
        # Extended parameters (used by mem0 internally, not in official docs):
        "minconn",  # Minimum connections in pool (mem0 internal, default: 10)
        "maxconn",  # Maximum connections in pool (mem0 internal, default: 40)
        "metric",  # Vector similarity metric (mem0 internal)
        # psycopg3 ConnectionPool advanced parameters (optional, for fine-tuning):
        "pool_max_lifetime",  # Connection max lifetime in seconds (default: 3600)
        "pool_max_idle",  # Connection max idle time in seconds (default: 600)
        "pool_timeout",  # Timeout to get connection from pool in seconds (default: 30)
        "pool_reconnect_timeout",  # Reconnect timeout in seconds (default: 300)
        "pool_max_waiting",  # Max waiting connections (default: 0 = unlimited)
        "pool_open",  # Open pool immediately (default: True)
        "pool_check",  # Health check function (default: ConnectionPool.check_connection)
    )

    # Preserve all valid keys from config
    for key in valid_keys:
        if key in config and config[key] is not None:
            normalized[key] = config[key]

    # Handle connection parameters according to priority:
    # 1. connection_pool (highest priority) - overrides everything
    if "connection_pool" in normalized:
        logger.debug("Using connection_pool (highest priority)")
        _remove_connection_params(normalized, also_remove_pool_params=True)
    # 2. connection_string (second priority) - create psycopg3 ConnectionPool
    elif "connection_string" in normalized and isinstance(
        normalized["connection_string"], str,
    ):
        _handle_connection_string(normalized)
    # 3. Individual parameters (lowest priority) - build connection_string and create pool
    else:
        result = _handle_individual_params(normalized, config)
        if result is not config:
            normalized = result
        else:
            return result

    # Set connection pool settings if not already provided (for backward compatibility)
    # These are only used if connection_pool was not created (mem0 will use them directly)
    if "minconn" not in normalized or normalized.get("minconn") is None:
        normalized["minconn"] = PGVECTOR_MIN_CONNECTIONS
        logger.debug("Setting pgvector minconn to: %d", PGVECTOR_MIN_CONNECTIONS)
    if "maxconn" not in normalized or normalized.get("maxconn") is None:
        normalized["maxconn"] = PGVECTOR_MAX_CONNECTIONS
        logger.debug("Setting pgvector maxconn to: %d", PGVECTOR_MAX_CONNECTIONS)

    return normalized
