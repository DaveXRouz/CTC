"""Inline keyboard builders for Telegram bot."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from conductor.db.models import Session


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Build persistent reply keyboard for quick phone access.

    Returns:
        ReplyKeyboardMarkup with Menu, Status, New Session, Output, Tokens, Help buttons.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Menu"), KeyboardButton(text="Status")],
            [KeyboardButton(text="New Session"), KeyboardButton(text="Output")],
            [KeyboardButton(text="Tokens"), KeyboardButton(text="Help")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


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
    """Build inline keyboard for the status dashboard.

    Returns:
        InlineKeyboardMarkup with Refresh, Sessions, Actions, and New Session buttons.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Refresh", callback_data="status:refresh"),
                InlineKeyboardButton(text="📋 Sessions", callback_data="menu:sessions"),
            ],
            [
                InlineKeyboardButton(text="⚡ Actions", callback_data="menu:actions"),
                InlineKeyboardButton(text="➕ New Session", callback_data="menu:new"),
            ],
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


# ── Interactive menu keyboards ──


def main_action_menu() -> InlineKeyboardMarkup:
    """Build the main action menu hub.

    Returns:
        InlineKeyboardMarkup with navigation buttons for all major features.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Status", callback_data="menu:status"),
                InlineKeyboardButton(text="📋 Sessions", callback_data="menu:sessions"),
            ],
            [
                InlineKeyboardButton(text="⚡ Actions", callback_data="menu:actions"),
                InlineKeyboardButton(text="➕ New Session", callback_data="menu:new"),
            ],
            [
                InlineKeyboardButton(
                    text="🤖 Auto-Responder", callback_data="menu:auto"
                ),
                InlineKeyboardButton(text="📈 Tokens", callback_data="menu:tokens"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Settings", callback_data="menu:settings"),
            ],
        ]
    )


def session_list_keyboard(sessions: list[Session]) -> InlineKeyboardMarkup:
    """Build session list with status icons for the session-centric flow.

    Args:
        sessions: List of active Session objects.

    Returns:
        InlineKeyboardMarkup with one button per session plus New Session and Back.
    """
    _status_icons = {
        "running": "🟢",
        "paused": "⏸",
        "waiting": "❓",
        "error": "🔴",
        "exited": "⚪",
        "rate_limited": "🟡",
    }
    buttons = []
    for s in sessions:
        icon = _status_icons.get(s.status, "⚪")
        label = f"{s.color_emoji} #{s.number} {s.alias} {icon}"
        buttons.append(
            [InlineKeyboardButton(text=label, callback_data=f"sess:detail:{s.id}")]
        )
    buttons.append(
        [
            InlineKeyboardButton(text="➕ New Session", callback_data="menu:new"),
            InlineKeyboardButton(text="◀️ Back", callback_data="menu:main"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def session_action_keyboard(session: Session) -> InlineKeyboardMarkup:
    """Build context-aware action buttons for a single session.

    Args:
        session: The target Session object. Pause/Resume toggles based on status.

    Returns:
        InlineKeyboardMarkup with action buttons appropriate to the session state.
    """
    sid = session.id
    toggle_btn = (
        InlineKeyboardButton(text="▶️ Resume", callback_data=f"sess:resume:{sid}")
        if session.status == "paused"
        else InlineKeyboardButton(text="⏸ Pause", callback_data=f"sess:pause:{sid}")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Output", callback_data=f"sess:output:{sid}"
                ),
                InlineKeyboardButton(
                    text="📤 Send Input", callback_data=f"sess:input:{sid}"
                ),
            ],
            [
                toggle_btn,
                InlineKeyboardButton(
                    text="📋 Full Log", callback_data=f"sess:log:{sid}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Restart", callback_data=f"sess:restart:{sid}"
                ),
                InlineKeyboardButton(text="🗑️ Kill", callback_data=f"sess:kill:{sid}"),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Rename", callback_data=f"sess:rename:{sid}"
                ),
                InlineKeyboardButton(text="◀️ Back", callback_data="menu:sessions"),
            ],
        ]
    )


def action_list_keyboard() -> InlineKeyboardMarkup:
    """Build the action-centric menu listing all possible actions.

    Returns:
        InlineKeyboardMarkup with one button per action plus Back.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 View Output", callback_data="act:output"),
                InlineKeyboardButton(text="📤 Send Input", callback_data="act:input"),
            ],
            [
                InlineKeyboardButton(text="⏸ Pause", callback_data="act:pause"),
                InlineKeyboardButton(text="▶️ Resume", callback_data="act:resume"),
            ],
            [
                InlineKeyboardButton(text="🔄 Restart", callback_data="act:restart"),
                InlineKeyboardButton(text="🗑️ Kill", callback_data="act:kill"),
            ],
            [
                InlineKeyboardButton(text="📋 Full Log", callback_data="act:log"),
                InlineKeyboardButton(text="✏️ Rename", callback_data="act:rename"),
            ],
            [
                InlineKeyboardButton(text="◀️ Back", callback_data="menu:main"),
            ],
        ]
    )


def action_session_picker(sessions: list[Session], action: str) -> InlineKeyboardMarkup:
    """Build session picker for the action-centric flow.

    Args:
        sessions: List of active Session objects.
        action: Action name to embed in callback data.

    Returns:
        InlineKeyboardMarkup with one button per session plus Back.
    """
    buttons = []
    for s in sessions:
        label = f"{s.color_emoji} #{s.number} {s.alias}"
        buttons.append(
            [InlineKeyboardButton(text=label, callback_data=f"apick:{action}:{s.id}")]
        )
    buttons.append([InlineKeyboardButton(text="◀️ Back", callback_data="menu:actions")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def new_session_keyboard() -> InlineKeyboardMarkup:
    """Build session type picker for creating a new session.

    Returns:
        InlineKeyboardMarkup with Claude Code and Shell options plus Back.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🤖 Claude Code", callback_data="new:cc"),
                InlineKeyboardButton(text="🖥️ Shell", callback_data="new:sh"),
            ],
            [
                InlineKeyboardButton(text="◀️ Back", callback_data="menu:main"),
            ],
        ]
    )


def directory_picker(
    directories: list[tuple[int, str]],
) -> InlineKeyboardMarkup:
    """Inline keyboard with recent dirs, custom path option, and back.

    Args:
        directories: List of ``(index, display_label)`` tuples.

    Returns:
        InlineKeyboardMarkup with one button per directory, Custom path, and Back.
    """
    buttons = [
        [InlineKeyboardButton(text=f"\U0001f4c1 {label}", callback_data=f"dir:{idx}")]
        for idx, label in directories
    ]
    buttons.append(
        [InlineKeyboardButton(text="\U0001f50d Browse...", callback_data="dir:browse")]
    )
    buttons.append(
        [
            InlineKeyboardButton(
                text="\U0001f4dd Custom path...", callback_data="dir:custom"
            )
        ]
    )
    buttons.append(
        [InlineKeyboardButton(text="\u25c0\ufe0f Back", callback_data="menu:new")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def browse_keyboard(
    subdirs: list[str],
    generation: str,
    can_go_up: bool = True,
) -> InlineKeyboardMarkup:
    """Build Finder-style directory browser keyboard.

    Args:
        subdirs: Subdirectory names to display (max 8).
        generation: 4-char hex generation token for stale-button invalidation.
        can_go_up: Whether to show the "Parent Directory" button.

    Returns:
        InlineKeyboardMarkup with subdir buttons, parent, select, and cancel.
    """
    buttons: list[list[InlineKeyboardButton]] = []

    if subdirs:
        # 2 per row, max 8 items (4 rows)
        for i in range(0, len(subdirs[:8]), 2):
            row = [
                InlineKeyboardButton(
                    text=f"\U0001f4c1 {subdirs[i]}",
                    callback_data=f"br:{generation}:{i}",
                )
            ]
            if i + 1 < len(subdirs[:8]):
                row.append(
                    InlineKeyboardButton(
                        text=f"\U0001f4c1 {subdirs[i + 1]}",
                        callback_data=f"br:{generation}:{i + 1}",
                    )
                )
            buttons.append(row)
    else:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="(no subdirectories)",
                    callback_data=f"br:{generation}:noop",
                )
            ]
        )

    if can_go_up:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="\u2b06\ufe0f Parent Directory",
                    callback_data=f"br:{generation}:up",
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="\u2705 Select This Folder",
                callback_data=f"br:{generation}:sel",
            ),
            InlineKeyboardButton(
                text="\u274c Cancel",
                callback_data=f"br:{generation}:cancel",
            ),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def auto_responder_keyboard() -> InlineKeyboardMarkup:
    """Build auto-responder control panel.

    Returns:
        InlineKeyboardMarkup with List Rules, Pause All, Resume All, and Back.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 List Rules", callback_data="auto:list"),
            ],
            [
                InlineKeyboardButton(text="⏸ Pause All", callback_data="auto:pause"),
                InlineKeyboardButton(text="▶️ Resume All", callback_data="auto:resume"),
            ],
            [
                InlineKeyboardButton(text="◀️ Back", callback_data="menu:main"),
            ],
        ]
    )


def back_keyboard(target: str = "menu:main") -> InlineKeyboardMarkup:
    """Build a simple Back button keyboard.

    Args:
        target: Callback data for the Back button destination.

    Returns:
        InlineKeyboardMarkup with a single Back button.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Back", callback_data=target)],
        ]
    )
