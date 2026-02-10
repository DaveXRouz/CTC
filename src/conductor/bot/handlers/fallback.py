"""Unknown input handler — friendly error message."""

from __future__ import annotations

from aiogram.types import Message


async def send_fallback(message: Message) -> None:
    """Handle unknown input with a helpful error response.

    Args:
        message: The unrecognized Telegram message.
    """
    await message.answer(
        "🤔 I didn't understand that.\n\n"
        "Try /help for commands, or just type naturally.",
        parse_mode="HTML",
    )
