"""Unknown input handler — friendly error message."""

from __future__ import annotations

from aiogram.types import Message


async def send_fallback(message: Message) -> None:
    """Handle unknown input with a helpful response."""
    await message.answer(
        "🤔 I didn't understand that.\n\n"
        "Try:\n"
        "• A /command (see /help for the list)\n"
        '• A natural language request like "what\'s happening?"\n'
        "• A direct response if a session is waiting for input",
        parse_mode="HTML",
    )
