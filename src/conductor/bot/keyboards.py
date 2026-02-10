"""Inline keyboard builders for Telegram bot."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def permission_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard for permission prompts.

    Args:
        session_id: UUID of the session awaiting permission.

    Returns:
        InlineKeyboardMarkup with Yes, No, Context, and Custom buttons.
    """
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
    """Build inline keyboard for task completion events.

    Args:
        session_id: UUID of the completed session.

    Returns:
        InlineKeyboardMarkup with Run Tests, Full Log, and New Task buttons.
    """
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
                    text="⏭️ New Task", callback_data=f"comp:new:{session_id}"
                ),
            ],
        ]
    )


def rate_limit_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard for rate limit events.

    Args:
        session_id: UUID of the rate-limited session.

    Returns:
        InlineKeyboardMarkup with Resume Now, Auto-Resume 15m, and Switch Task buttons.
    """
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
                    text="↪️ Switch Task", callback_data=f"rate:switch:{session_id}"
                ),
            ],
        ]
    )


def confirm_keyboard(action: str, session_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard for destructive action confirmation.

    Args:
        action: Action type (e.g. ``'kill'``, ``'restart'``).
        session_id: UUID of the target session.

    Returns:
        InlineKeyboardMarkup with "Yes, Do It" and Cancel buttons.
    """
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
    """Build inline keyboard with an undo button for auto-responses.

    Args:
        action_id: Identifier for the auto-response action to undo.

    Returns:
        InlineKeyboardMarkup with a single Undo button.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Undo", callback_data=f"undo:{action_id}")],
        ]
    )


def status_keyboard() -> InlineKeyboardMarkup:
    """Build inline keyboard with a refresh button for the status dashboard.

    Returns:
        InlineKeyboardMarkup with a single Refresh button.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data="status:refresh")],
        ]
    )


def session_picker(sessions: list[tuple[str, str, str]]) -> InlineKeyboardMarkup:
    """Build inline keyboard for selecting a session.

    Args:
        sessions: List of ``(session_id, emoji, alias)`` tuples.

    Returns:
        InlineKeyboardMarkup with one button per session.
    """
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
    """Build inline keyboard from AI-generated suggestions.

    Args:
        suggestions: List of dicts with ``'label'`` keys (max 3 shown).
        session_id: UUID of the session the suggestions apply to.

    Returns:
        InlineKeyboardMarkup with one button per suggestion.
    """
    buttons = []
    for i, s in enumerate(suggestions[:3]):
        buttons.append(
            [
                InlineKeyboardButton(
                    text=s.get("label", f"💡 Option {i+1}"),
                    callback_data=f"suggest:{i}:{session_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
