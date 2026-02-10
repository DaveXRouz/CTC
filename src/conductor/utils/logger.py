"""Structured logging — rich console + rotating file handler."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

_configured = False


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    max_bytes: int = 50 * 1024 * 1024,
    backup_count: int = 3,
    console: bool = True,
) -> logging.Logger:
    """Configure the conductor logger with Rich console + rotating file handler.

    Args:
        level: Log level string (``'DEBUG'``, ``'INFO'``, ``'WARNING'``, ``'ERROR'``).
        log_file: Path to the rotating log file. None to disable file logging.
        max_bytes: Max file size before rotation (default 50 MB).
        backup_count: Number of rotated files to keep (default 3).
        console: Whether to enable Rich console output (default True).

    Returns:
        The configured ``'conductor'`` root logger.
    """
    global _configured
    if _configured:
        return logging.getLogger("conductor")

    logger = logging.getLogger("conductor")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    fmt = "%(asctime)s | %(name)s | %(levelname)-8s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    if console:
        rich_handler = RichHandler(
            rich_tracebacks=True,
            show_time=False,
            show_path=False,
        )
        rich_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(rich_handler)

    if log_file:
        log_path = Path(log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        logger.addHandler(file_handler)

    _configured = True
    return logger


def get_logger(name: str = "conductor") -> logging.Logger:
    """Get a child logger under the ``'conductor'`` namespace.

    Args:
        name: Logger name (e.g. ``'conductor.bot.commands'``).

    Returns:
        A ``logging.Logger`` instance.
    """
    return logging.getLogger(name)
