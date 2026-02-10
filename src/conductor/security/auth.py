"""Telegram user ID authentication middleware."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from conductor.config import get_config
from conductor.utils.logger import get_logger

logger = get_logger("conductor.security.auth")


class AuthMiddleware(BaseMiddleware):
    """Reject messages from unauthorized Telegram users."""

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        cfg = get_config()
        user_id = event.from_user.id if event.from_user else None

        if user_id != cfg.telegram_user_id:
            logger.warning(f"Unauthorized access attempt from user_id={user_id}")
            if isinstance(event, Message):
                await event.answer("⛔ Unauthorized. This bot is private.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Unauthorized.", show_alert=True)
            return

        return await handler(event, data)
