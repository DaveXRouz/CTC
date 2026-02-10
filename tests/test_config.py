"""Tests for configuration loader."""

import os
import pytest
from unittest.mock import patch

from conductor.config import Config, _load_yaml, get_config


@pytest.fixture(autouse=True)
def reset_config_singleton():
    """Reset the Config singleton between tests."""
    Config._instance = None
    yield
    Config._instance = None


class TestLoadYaml:
    def test_load_existing_yaml(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("key: value\nnested:\n  a: 1\n")
        result = _load_yaml(f)
        assert result["key"] == "value"
        assert result["nested"]["a"] == 1

    def test_load_nonexistent_yaml(self, tmp_path):
        f = tmp_path / "nope.yaml"
        result = _load_yaml(f)
        assert result == {}

    def test_load_empty_yaml(self, tmp_path):
        f = tmp_path / "empty.yaml"
        f.write_text("")
        result = _load_yaml(f)
        assert result == {}


class TestConfig:
    def test_singleton(self):
        c1 = Config()
        c2 = Config()
        assert c1 is c2

    def test_load_sets_defaults(self):
        cfg = Config()
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_USER_ID": "12345",
                "ANTHROPIC_API_KEY": "test-key",
            },
        ):
            cfg.load()
        assert cfg.telegram_bot_token == "test-token"
        assert cfg.telegram_user_id == 12345
        assert cfg.anthropic_api_key == "test-key"

    def test_load_idempotent(self):
        cfg = Config()
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "first",
                "TELEGRAM_USER_ID": "1",
                "ANTHROPIC_API_KEY": "key",
            },
        ):
            cfg.load()
        # Change env and reload — should NOT change due to _loaded guard
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "second"}):
            cfg.load()
        assert cfg.telegram_bot_token == "first"

    def test_validate_missing_token(self):
        cfg = Config()
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "",
                "TELEGRAM_USER_ID": "0",
                "ANTHROPIC_API_KEY": "",
            },
            clear=False,
        ):
            cfg.load()
        missing = cfg.validate()
        assert "TELEGRAM_BOT_TOKEN" in missing
        assert "TELEGRAM_USER_ID" in missing
        assert "ANTHROPIC_API_KEY" in missing

    def test_validate_all_present(self):
        cfg = Config()
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "tok",
                "TELEGRAM_USER_ID": "123",
                "ANTHROPIC_API_KEY": "key",
            },
        ):
            cfg.load()
        assert cfg.validate() == []

    def test_yaml_properties_with_defaults(self):
        cfg = Config()
        cfg._loaded = True  # Skip real load
        cfg._yaml = {}
        cfg.telegram_bot_token = ""
        cfg.telegram_user_id = 0
        cfg.anthropic_api_key = ""
        assert cfg.max_concurrent_sessions == 5
        assert cfg.default_session_type == "claude-code"
        assert cfg.default_dir == "~/projects"
        assert cfg.aliases == {}
        assert cfg.plan_tier == "pro"
        assert cfg.ai_model == "claude-haiku-4-5-20251001"
        assert cfg.ai_timeout == 10
        assert cfg.batch_window_s == 5
        assert cfg.confirmation_timeout_s == 30
        assert cfg.quiet_hours == {}

    def test_yaml_properties_with_values(self):
        cfg = Config()
        cfg._loaded = True
        cfg._yaml = {
            "sessions": {"max_concurrent": 10, "default_type": "shell"},
            "tokens": {"plan_tier": "max_5x"},
            "ai": {"model": "custom-model", "timeout_seconds": 20},
            "notifications": {"batch_window_s": 10, "quiet_hours": {"start": "22:00"}},
        }
        cfg.telegram_bot_token = "tok"
        cfg.telegram_user_id = 1
        cfg.anthropic_api_key = "key"
        assert cfg.max_concurrent_sessions == 10
        assert cfg.default_session_type == "shell"
        assert cfg.plan_tier == "max_5x"
        assert cfg.ai_model == "custom-model"
        assert cfg.ai_timeout == 20
        assert cfg.batch_window_s == 10
        assert cfg.quiet_hours == {"start": "22:00"}

    def test_section_accessors(self):
        cfg = Config()
        cfg._loaded = True
        cfg._yaml = {
            "monitor": {"poll_ms": 300},
            "security": {"require_auth": True},
            "logging": {"level": "DEBUG"},
            "auto_responder": {"enabled": True},
        }
        assert cfg.monitor_config == {"poll_ms": 300}
        assert cfg.security_config == {"require_auth": True}
        assert cfg.logging_config == {"level": "DEBUG"}
        assert cfg.auto_responder_config == {"enabled": True}

    def test_get_config_loads(self):
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "tok",
                "TELEGRAM_USER_ID": "1",
                "ANTHROPIC_API_KEY": "key",
            },
        ):
            cfg = get_config()
        assert cfg.telegram_bot_token == "tok"
