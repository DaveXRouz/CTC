"""Telegram bot initialization — Bot + Dispatcher + handler registration."""

from __future__ import annotations

from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from conductor.config import get_config
from conductor.security.auth import AuthMiddleware
from conductor.bot.handlers import commands, callbacks, natural
from conductor.utils.logger import get_logger

logger = get_logger("conductor.bot")

# App-wide shared data (monitors, brain, etc.)
_app_data: dict[str, Any] = {}


def get_app_data() -> dict[str, Any]:
    """Get the shared application data dictionary.

    Returns:
        Dict of app-wide shared state (monitors, brain, notifier, etc.).
    """
    return _app_data


def set_app_data(key: str, value: Any) -> None:
    """Set a value in the shared application data dictionary.

    Args:
        key: State key name.
        value: Value to store.
    """
    _app_data[key] = value


async def create_bot() -> tuple[Bot, Dispatcher]:
    """Create and configure the Telegram bot and dispatcher.

    Registers auth middleware and includes routers in order:
    commands -> callbacks -> natural (natural must be last).

    Returns:
        Tuple of ``(Bot, Dispatcher)`` ready for polling.
    """
    cfg = get_config()

    bot = Bot(
        token=cfg.telegram_bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()

    # Register auth middleware
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Register routers
    dp.include_router(commands.router)
    dp.include_router(callbacks.router)
    dp.include_router(natural.router)  # Must be last — catches all non-command messages

    logger.info("Bot created and handlers registered")
    return bot, dp
