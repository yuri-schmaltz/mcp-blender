"""Logging configuration helpers for Blender MCP."""

from __future__ import annotations

import logging
import os

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_HANDLER = "console"
# Alias to keep CLI defaults descriptive without changing legacy name
DEFAULT_LOG_HANDLER = DEFAULT_HANDLER


def _create_handler(handler_type: str, log_format: str, log_level: int) -> logging.Handler:
    if handler_type == "console":
        handler: logging.Handler = logging.StreamHandler()
    elif handler_type == "file":
        log_file = os.getenv("BLENDER_MCP_LOG_FILE", "blender_mcp.log")
        handler = logging.FileHandler(log_file)
    else:
        raise ValueError(f"Unsupported handler type: {handler_type}")

    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter(log_format))
    return handler


def configure_logging(
    *,
    level: str | None = None,
    log_format: str | None = None,
    handler_type: str | None = None,
) -> None:
    """Configure root logging for the MCP server.

    The configuration is idempotent and can be overridden via environment variables:

    - ``BLENDER_MCP_LOG_LEVEL``: logging level (e.g. ``DEBUG``, ``INFO``)
    - ``BLENDER_MCP_LOG_FORMAT``: logging format string
    - ``BLENDER_MCP_LOG_HANDLER``: handler type (``console`` or ``file``)
    - ``BLENDER_MCP_LOG_FILE``: file path when using the ``file`` handler
    """

    resolved_level = (level or os.getenv("BLENDER_MCP_LOG_LEVEL", DEFAULT_LOG_LEVEL)).upper()
    resolved_format = log_format or os.getenv("BLENDER_MCP_LOG_FORMAT", DEFAULT_LOG_FORMAT)
    resolved_handler = (
        handler_type or os.getenv("BLENDER_MCP_LOG_HANDLER", DEFAULT_HANDLER)
    ).lower()

    numeric_level = logging.getLevelName(resolved_level)
    if isinstance(numeric_level, str):
        # getLevelName returns a string for unknown names; fallback to INFO
        numeric_level = logging.INFO

    logger = logging.getLogger()
    logger.setLevel(numeric_level)

    # Clear existing handlers to avoid duplicate logs when reconfiguring
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    handler = _create_handler(resolved_handler, resolved_format, numeric_level)
    logger.addHandler(handler)

    logger.debug(
        "Logging configured",  # type: ignore[arg-type]
        extra={
            "config": {
                "level": resolved_level,
                "format": resolved_format,
                "handler": resolved_handler,
            }
        },
    )
