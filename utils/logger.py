"""Unified logger configuration for Mem0 Dify Plugin.

This module provides a centralized logger configuration that ensures all logs
are properly output to the Dify plugin container using the official plugin logger handler.
"""

import logging
import os
import threading


def _is_dify_plugin_runtime() -> bool:
    return os.environ.get("DIFY_PLUGIN_RUNTIME") == "1"


if _is_dify_plugin_runtime():
    try:
        from dify_plugin.config.logger_format import plugin_logger_handler
    except (ImportError, ModuleNotFoundError, RecursionError, RuntimeError):
        plugin_logger_handler = logging.StreamHandler()
else:
    plugin_logger_handler = logging.StreamHandler()


class _LoggerConfig:
    """Thread-safe logger configuration manager."""

    def __init__(self) -> None:
        self._log_level = logging.INFO
        self._lock = threading.Lock()

    def set_log_level(self, level: str) -> None:
        """Set log level for all loggers.

        Args:
            level: Log level string (DEBUG, INFO, WARNING, ERROR)

        """
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
        }

        with self._lock:
            self._log_level = level_map.get(level.upper(), logging.INFO)
            # Update all existing loggers in tools and utils modules
            for logger_name in logging.Logger.manager.loggerDict:
                if logger_name.startswith(("tools.", "utils.")):
                    existing_logger = logging.getLogger(logger_name)
                    existing_logger.setLevel(self._log_level)

    def get_log_level(self) -> int:
        """Get current log level.

        Returns:
            Current log level constant

        """
        with self._lock:
            return self._log_level


# Singleton instance
_logger_config = _LoggerConfig()


def set_log_level(level: str) -> None:
    """Set global log level for all loggers.

    This function updates the log level for all existing loggers created by this module.
    It is thread-safe and can be called at runtime to dynamically adjust log verbosity.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR)

    """
    _logger_config.set_log_level(level)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with Dify plugin handler configured.

    Args:
        name: Logger name (typically __name__ of the calling module)

    Returns:
        Configured logger instance

    """
    logger = logging.getLogger(name)

    # Set to current global log level
    logger.setLevel(_logger_config.get_log_level())

    # Only add handler if not already added to avoid duplicate logs
    if not logger.handlers:
        logger.addHandler(plugin_logger_handler)

    # Avoid duplicate output via root logger in Dify runtime
    if _is_dify_plugin_runtime():
        logger.propagate = False

    return logger
