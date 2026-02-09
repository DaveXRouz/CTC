"""Configuration loader — .env secrets + config.yaml preferences."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Paths
CONDUCTOR_HOME = Path.home() / ".conductor"
ENV_PATH = CONDUCTOR_HOME / ".env"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_YAML_PATH = PROJECT_ROOT / "config.yaml"
DB_PATH = CONDUCTOR_HOME / "conductor.db"


def _load_yaml(path: Path) -> dict[str, Any]:
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


class Config:
    """Singleton configuration loaded from .env + config.yaml."""

    _instance: Config | None = None

    def __new__(cls) -> Config:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def load(self) -> None:
        if self._loaded:
            return
        # Load .env
        load_dotenv(ENV_PATH)

        # Secrets (required)
        self.telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_user_id: int = int(os.environ.get("TELEGRAM_USER_ID", "0"))
        self.anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
        self.log_level: str = os.environ.get("LOG_LEVEL", "INFO")

        # YAML preferences
        self._yaml = _load_yaml(CONFIG_YAML_PATH)

        self._loaded = True

    def validate(self) -> list[str]:
        """Return list of missing required config values."""
        missing = []
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.telegram_user_id:
            missing.append("TELEGRAM_USER_ID")
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        return missing

    # ── Typed accessors ──

    @property
    def sessions(self) -> dict[str, Any]:
        return self._yaml.get("sessions", {})

    @property
    def max_concurrent_sessions(self) -> int:
        return self.sessions.get("max_concurrent", 5)

    @property
    def default_session_type(self) -> str:
        return self.sessions.get("default_type", "claude-code")

    @property
    def default_dir(self) -> str:
        return self.sessions.get("default_dir", "~/projects")

    @property
    def aliases(self) -> dict[str, str]:
        return self.sessions.get("aliases", {})

    @property
    def tokens_config(self) -> dict[str, Any]:
        return self._yaml.get("tokens", {})

    @property
    def plan_tier(self) -> str:
        return self.tokens_config.get("plan_tier", "pro")

    @property
    def monitor_config(self) -> dict[str, Any]:
        return self._yaml.get("monitor", {})

    @property
    def notifications_config(self) -> dict[str, Any]:
        return self._yaml.get("notifications", {})

    @property
    def auto_responder_config(self) -> dict[str, Any]:
        return self._yaml.get("auto_responder", {})

    @property
    def ai_config(self) -> dict[str, Any]:
        return self._yaml.get("ai", {})

    @property
    def ai_model(self) -> str:
        return self.ai_config.get("model", "claude-haiku-4-5-20251001")

    @property
    def ai_timeout(self) -> int:
        return self.ai_config.get("timeout_seconds", 10)

    @property
    def security_config(self) -> dict[str, Any]:
        return self._yaml.get("security", {})

    @property
    def logging_config(self) -> dict[str, Any]:
        return self._yaml.get("logging", {})

    @property
    def quiet_hours(self) -> dict[str, Any]:
        return self.notifications_config.get("quiet_hours", {})

    @property
    def batch_window_s(self) -> int:
        return self.notifications_config.get("batch_window_s", 5)

    @property
    def confirmation_timeout_s(self) -> int:
        return self.notifications_config.get("confirmation_timeout_s", 30)


def get_config() -> Config:
    """Get the singleton config, loading it if needed."""
    cfg = Config()
    cfg.load()
    return cfg
