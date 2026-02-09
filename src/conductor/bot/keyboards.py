"""Inline keyboard builders for Telegram bot."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def permission_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Buttons for permission prompts: Yes / No / Context / Custom."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Yes", callback_data=f"perm:yes:{session_id}"
                ),
                InlineKeyboardButton(
                    text="❌ No", callback_data=f"perm:no:{session_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="👀 Context", callback_data=f"perm:ctx:{session_id}"
                ),
                InlineKeyboardButton(
                    text="✏️ Custom", callback_data=f"perm:custom:{session_id}"
                ),
            ],
        ]
    )


def completion_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Buttons for task completion: Run Tests / Full Log / New Task."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ Run Tests", callback_data=f"comp:test:{session_id}"
                ),
                InlineKeyboardButton(
                    text="📋 Full Log", callback_data=f"comp:log:{session_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 New Task", callback_data=f"comp:new:{session_id}"
                ),
            ],
        ]
    )


def rate_limit_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Buttons for rate limit: Resume / Auto-Resume / Switch."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ Resume Now", callback_data=f"rate:resume:{session_id}"
                ),
                InlineKeyboardButton(
                    text="⏰ Auto-Resume 15m", callback_data=f"rate:auto:{session_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Switch Task", callback_data=f"rate:switch:{session_id}"
                ),
            ],
        ]
    )


def confirm_keyboard(action: str, session_id: str) -> InlineKeyboardMarkup:
    """Confirmation buttons for destructive actions."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑️ Yes, Do It",
                    callback_data=f"confirm:yes:{action}:{session_id}",
                ),
                InlineKeyboardButton(
                    text="↩️ Cancel", callback_data=f"confirm:no:{action}:{session_id}"
                ),
            ],
        ]
    )


def undo_keyboard(action_id: str) -> InlineKeyboardMarkup:
    """Undo button for auto-responses (30s TTL)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Undo", callback_data=f"undo:{action_id}")],
        ]
    )


def status_keyboard() -> InlineKeyboardMarkup:
    """Refresh button for status dashboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data="status:refresh")],
        ]
    )


def session_picker(sessions: list[tuple[str, str, str]]) -> InlineKeyboardMarkup:
    """Session picker keyboard. sessions = [(id, emoji, alias)]."""
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{emoji} {alias}",
                callback_data=f"pick:{sid}",
            )
        ]
        for sid, emoji, alias in sessions
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def suggestion_keyboard(
    suggestions: list[dict[str, str]], session_id: str
) -> InlineKeyboardMarkup:
    """Build keyboard from AI suggestions."""
    buttons = []
    for i, s in enumerate(suggestions[:3]):
        buttons.append(
            [
                InlineKeyboardButton(
                    text=s.get("label", f"Option {i+1}"),
                    callback_data=f"suggest:{i}:{session_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
