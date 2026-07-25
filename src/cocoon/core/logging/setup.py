"""Logging setup. Authoritative source: DOCUMENT.md §3 (NFR Auditability),
§8.3 (logging config), §18 (naming/env rules).

structlog is used because stdlib `logging` requires manual structuring
to produce JSON records; NFR auditability requires every order, signal,
and effective config value to be reconstructable from logs alone, which
demands structured (not free-text) records by default.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

import structlog

from cocoon.core.config.schema import LoggingConfig, LogLevel

_LEVEL_MAP: dict[LogLevel, int] = {
    LogLevel.DEBUG: logging.DEBUG,
    LogLevel.INFO: logging.INFO,
    LogLevel.WARN: logging.WARNING,
    LogLevel.ERROR: logging.ERROR,
}


def configure_logging(logging_config: LoggingConfig, *, log_level: LogLevel) -> None:
    """Idempotent: safe to call more than once (e.g. re-invoked on
    profile reload) — always fully resets stdlib logging handlers
    rather than accumulating duplicate handlers across calls."""

    level = _LEVEL_MAP[log_level]

    app_log_path = Path(logging_config.app_log_path)
    app_log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(app_log_path),
        maxBytes=logging_config.rotate_max_mb * 1024 * 1024,
        backupCount=logging_config.rotate_backups,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    root_logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(stream=sys.stderr)
    stream_handler.setLevel(level)
    root_logger.addHandler(stream_handler)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if logging_config.format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)


def quiet_console_logging() -> None:
    """Drop the stderr handler so records go to the rotating file only —
    used while a rich Live display owns the terminal. The file handler
    (a StreamHandler subclass) is kept, so nothing is lost."""
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if type(handler) is logging.StreamHandler:
            root_logger.removeHandler(handler)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
