"""Tests for AI fallback — raw output when Haiku is down."""

import os
from unittest.mock import patch

from conductor.config import Config
from conductor.ai.fallback import get_raw_fallback


class TestFallback:
    @classmethod
    def setup_class(cls):
        Config._instance = None

    @classmethod
    def teardown_class(cls):
        Config._instance = None

    def test_raw_fallback_basic(self):
        Config._instance = None
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "t",
                "TELEGRAM_USER_ID": "1",
                "ANTHROPIC_API_KEY": "k",
            },
        ):
            output = "line1\nline2\nline3\nline4\nline5"
            result = get_raw_fallback(output)
            assert "Raw output" in result
            assert "AI unavailable" in result
            assert "line5" in result

    def test_raw_fallback_fewer_lines(self):
        Config._instance = None
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "t",
                "TELEGRAM_USER_ID": "1",
                "ANTHROPIC_API_KEY": "k",
            },
        ):
            output = "short output"
            result = get_raw_fallback(output)
            assert "short output" in result

    def test_raw_fallback_last_n_lines(self):
        Config._instance = None
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "t",
                "TELEGRAM_USER_ID": "1",
                "ANTHROPIC_API_KEY": "k",
            },
        ):
            lines = [f"line-{i}" for i in range(100)]
            output = "\n".join(lines)
            result = get_raw_fallback(output)
            # Default is 20 lines
            assert "line-99" in result
            assert "line-80" in result
            assert "line-50" not in result
