"""Tests for logger setup."""

import logging
from pathlib import Path
from unittest.mock import patch

from conductor.utils import logger as logger_mod
from conductor.utils.logger import setup_logging, get_logger


class TestLogger:
    @classmethod
    def setup_class(cls):
        # Reset the configured flag for testing
        logger_mod._configured = False

    def setup_method(self):
        logger_mod._configured = False
        # Clear handlers
        root = logging.getLogger("conductor")
        root.handlers.clear()

    def test_setup_logging_console(self):
        log = setup_logging(level="DEBUG", console=True)
        assert log.name == "conductor"
        assert log.level == logging.DEBUG
        assert len(log.handlers) >= 1

    def test_setup_logging_file(self, tmp_path):
        logger_mod._configured = False
        log_file = str(tmp_path / "test.log")
        log = setup_logging(level="INFO", log_file=log_file, console=False)
        assert any(
            isinstance(h, logging.handlers.RotatingFileHandler) for h in log.handlers
        )
        assert Path(log_file).exists()

    def test_setup_logging_idempotent(self):
        logger_mod._configured = False
        log1 = setup_logging(console=True)
        handler_count = len(log1.handlers)
        log2 = setup_logging(console=True)
        assert log1 is log2
        assert len(log2.handlers) == handler_count

    def test_get_logger(self):
        log = get_logger("conductor.test")
        assert log.name == "conductor.test"

    def test_get_logger_default(self):
        log = get_logger()
        assert log.name == "conductor"

    def test_setup_no_console(self):
        logger_mod._configured = False
        log = setup_logging(console=False)
        # Should have no RichHandler
        from rich.logging import RichHandler

        rich_handlers = [h for h in log.handlers if isinstance(h, RichHandler)]
        assert len(rich_handlers) == 0
