"""Inline button callback handlers."""

from __future__ import annotations

import asyncio

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from conductor.bot.formatter import (
    session_label,
    format_status_dashboard,
    format_session_dashboard,
    mono,
)
from conductor.bot.keyboards import (
    status_keyboard,
    main_action_menu,
    session_list_keyboard,
    session_action_keyboard,
    action_list_keyboard,
    action_session_picker,
    new_session_keyboard,
    directory_picker,
    auto_responder_keyboard,
    back_keyboard,
    confirm_keyboard,
)
from conductor.security.confirm import ConfirmationManager
from conductor.security.redactor import redact_sensitive
from conductor.utils.logger import get_logger

logger = get_logger("conductor.bot.callbacks")

router = Router()

confirmation_mgr = ConfirmationManager()


def _get_mgr():
    from conductor.bot.bot import get_app_data

    return get_app_data().get("session_manager")


# ── Confirmation callbacks ──


@router.callback_query(F.data.startswith("confirm:"))
async def handle_confirm(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Invalid callback")
        return

    _, decision, action, session_id = parts[0], parts[1], parts[2], parts[3]
    mgr = _get_mgr()
    if not mgr:
        await callback.answer("Session manager unavailable")
        return

    if decision == "no":
        confirmation_mgr.cancel(callback.from_user.id, action, session_id)
        await callback.message.edit_text("↩️ Action cancelled.")
        await callback.answer()
        return

    # TTL check — reject expired confirmations
    if not confirmation_mgr.confirm(callback.from_user.id, action, session_id):
        await callback.message.edit_text(
            "⏰ Confirmation expired. Please re-issue the command."
        )
        await callback.answer()
        return

    session = mgr.get_session(session_id)
    if not session:
        await callback.message.edit_text("❌ Session no longer exists.")
        await callback.answer()
        return

    if action == "kill":
        result = await mgr.kill_session(session_id)
        if result:
            await callback.message.edit_text(f"🗑️ Killed {session_label(result)}")
        else:
            await callback.message.edit_text("❌ Could not kill session.")
    elif action == "restart":
        old_session = mgr.get_session(session_id)
        if old_session:
            await mgr.kill_session(session_id)
            new_session = await mgr.create_session(
                session_type=old_session.type,
                working_dir=old_session.working_dir,
                alias=old_session.alias,
            )
            await callback.message.edit_text(
                f"🔄 Restarted {session_label(new_session)} (#{new_session.number})"
            )

    await callback.answer()


# ── Permission prompt callbacks ──


@router.callback_query(F.data.startswith("perm:"))
async def handle_permission(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    _, decision, session_id = parts[0], parts[1], parts[2]
    mgr = _get_mgr()
    if not mgr:
        await callback.answer("Session manager unavailable")
        return

    session = mgr.get_session(session_id)
    if not session:
        await callback.message.edit_text("❌ Session no longer exists.")
        await callback.answer()
        return

    if decision == "yes":
        if mgr.send_input(session_id, "y"):
            await callback.message.edit_text(f"✅ Sent 'y' to {session_label(session)}")
        else:
            await callback.message.edit_text(
                f"⚠️ Failed to send to {session_label(session)} — pane not found"
            )
    elif decision == "no":
        if mgr.send_input(session_id, "n"):
            await callback.message.edit_text(f"❌ Sent 'n' to {session_label(session)}")
        else:
            await callback.message.edit_text(
                f"⚠️ Failed to send to {session_label(session)} — pane not found"
            )
    elif decision == "ctx":
        # Show last 20 lines of context
        from conductor.bot.bot import get_app_data

        monitors = get_app_data().get("monitors", {})
        monitor = monitors.get(session_id)
        if monitor and hasattr(monitor, "output_buffer"):
            lines = monitor.output_buffer.rolling_buffer[-20:]
            text = "\n".join(lines)[:3500]
            await callback.message.answer(
                f"👀 Context for {session_label(session)}:\n\n<code>{text}</code>",
                parse_mode="HTML",
            )
        else:
            await callback.message.answer("👀 No context available.")
    elif decision == "custom":
        await callback.message.answer(
            f"✏️ Type your response for {session_label(session)}:\n"
            f"(Use /input {session.number} &lt;text&gt;)",
            parse_mode="HTML",
        )

    await callback.answer()


# ── Rate limit callbacks ──


@router.callback_query(F.data.startswith("rate:"))
async def handle_rate_limit(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    _, action, session_id = parts[0], parts[1], parts[2]
    mgr = _get_mgr()
    if not mgr:
        await callback.answer("Session manager unavailable")
        return

    session = mgr.get_session(session_id)
    if not session:
        await callback.message.edit_text("❌ Session no longer exists.")
        await callback.answer()
        return

    if action == "resume":
        result = await mgr.resume_session(session_id)
        if result:
            await callback.message.edit_text(f"▶️ Resumed {session_label(result)}")
    elif action == "auto":
        await callback.message.edit_text(
            f"⏰ {session_label(session)} will auto-resume in 15 minutes."
        )
        # Schedule auto-resume (tracked to log exceptions)
        from conductor.bot.bot import get_app_data

        track_task = get_app_data().get("track_task")
        task = asyncio.create_task(_auto_resume(mgr, session_id, 15, callback))
        if track_task:
            track_task(task)
    elif action == "switch":
        await callback.message.answer("↪️ Use /new to start a different task.")

    await callback.answer()


async def _auto_resume(
    mgr, session_id: str, minutes: int, callback: CallbackQuery
) -> None:
    await asyncio.sleep(minutes * 60)
    session = mgr.get_session(session_id)
    if session and session.status == "paused":
        await mgr.resume_session(session_id)
        try:
            await callback.message.answer(
                f"▶️ {session_label(session)} auto-resumed after {minutes}m cooldown."
            )
        except Exception:
            pass


# ── Completion callbacks ──


@router.callback_query(F.data.startswith("comp:"))
async def handle_completion(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    _, action, session_id = parts[0], parts[1], parts[2]
    mgr = _get_mgr()
    if not mgr:
        await callback.answer("Session manager unavailable")
        return

    session = mgr.get_session(session_id)
    if not session:
        await callback.message.edit_text("❌ Session no longer exists.")
        await callback.answer()
        return

    if action == "test":
        if mgr.send_input(session_id, "npm test"):
            await callback.message.edit_text(
                f"▶️ Running tests in {session_label(session)}"
            )
        else:
            await callback.message.edit_text(
                f"⚠️ Failed to send to {session_label(session)} — pane not found"
            )
    elif action == "log":
        await callback.message.answer("📋 Use /log to view the full session log.")
    elif action == "new":
        await callback.message.answer(
            "⏭️ Type your next task instruction and I'll send it to the session."
        )

    await callback.answer()


# ── Status refresh ──


@router.callback_query(F.data == "status:refresh")
async def handle_status_refresh(callback: CallbackQuery) -> None:
    mgr = _get_mgr()
    if not mgr:
        await callback.answer("Session manager unavailable")
        return

    sessions = await mgr.list_sessions()
    try:
        await callback.message.edit_text(
            format_status_dashboard(sessions),
            parse_mode="HTML",
            reply_markup=status_keyboard(),
        )
        await callback.answer("Refreshed!")
    except TelegramBadRequest:
        await callback.answer("Already up to date")


# ── Suggestion callbacks ──


@router.callback_query(F.data.startswith("suggest:"))
async def handle_suggestion(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    _, idx, session_id = parts[0], parts[1], parts[2]
    mgr = _get_mgr()
    if not mgr:
        await callback.answer("Session manager unavailable")
        return

    from conductor.bot.bot import get_app_data

    suggestions = get_app_data().get("last_suggestions", {}).get(session_id, [])
    try:
        suggestion = suggestions[int(idx)]
        cmd = suggestion.get("command", "")
        if cmd:
            session = mgr.get_session(session_id)
            label = session_label(session) if session else session_id
            if mgr.send_input(session_id, cmd):
                await callback.message.edit_text(f"▶️ Running in {label}: {cmd}")
            else:
                await callback.message.edit_text(
                    f"⚠️ Failed to send to {label} — pane not found"
                )
    except (IndexError, ValueError):
        await callback.message.edit_text("❌ Suggestion no longer available.")

    await callback.answer()


# ── Undo callback ──


@router.callback_query(F.data.startswith("undo:"))
async def handle_undo(callback: CallbackQuery) -> None:
    _action_id = callback.data.split(":", 1)[1] if ":" in callback.data else ""
    await callback.message.edit_text(
        "🔙 Auto-response cancelled. Send a manual reply if needed."
    )
    await callback.answer()


# ── Session picker ──


@router.callback_query(F.data.startswith("pick:"))
async def handle_session_pick(callback: CallbackQuery) -> None:
    session_id = callback.data.split(":", 1)[1] if ":" in callback.data else ""
    # Store selected session in context for next message
    from conductor.bot.bot import set_app_data

    set_app_data("picked_session", session_id)
    mgr = _get_mgr()
    if mgr:
        session = mgr.get_session(session_id)
        if session:
            await callback.message.edit_text(
                f"👆 Selected {session_label(session)}. Now type your message."
            )
    await callback.answer()


# ── Interactive menu callbacks ──


def _clear_pending_input():
    """Clear any pending text-collection state."""
    from conductor.bot.bot import set_app_data

    set_app_data("pending_input_type", None)
    set_app_data("pending_input_session", None)
    set_app_data("pending_new_session_type", None)
    set_app_data("pending_dir_choices", None)


def _dir_display_label(path: str) -> str:
    """Return a short display label for a directory path.

    Uses config alias name if matched, otherwise the last path component.
    """
    from conductor.config import get_config

    cfg = get_config()
    # Check if path matches a configured alias
    import os

    normalized = os.path.expanduser(path)
    for alias_name, alias_path in cfg.aliases.items():
        if os.path.expanduser(alias_path) == normalized:
            return alias_name
    # Fall back to last path component
    return os.path.basename(normalized) or path


async def _build_directory_choices() -> list[tuple[int, str, str]]:
    """Build deduplicated directory choices from DB + config.

    Returns list of (index, display_label, full_path) tuples, capped at 5.
    """
    import os

    from conductor.config import get_config
    from conductor.db.queries import get_recent_working_dirs

    cfg = get_config()
    seen: set[str] = set()
    choices: list[tuple[str, str]] = []  # (full_path, label)

    # Recent dirs from DB (most recent first)
    recent = await get_recent_working_dirs(limit=5)
    for path in recent:
        normalized = os.path.expanduser(path)
        if normalized not in seen:
            seen.add(normalized)
            choices.append((path, _dir_display_label(path)))

    # Config default_dir as fallback
    default = cfg.default_dir
    if default:
        normalized = os.path.expanduser(default)
        if normalized not in seen:
            seen.add(normalized)
            choices.append((default, _dir_display_label(default)))

    # Config aliases
    for alias_name, alias_path in cfg.aliases.items():
        normalized = os.path.expanduser(alias_path)
        if normalized not in seen:
            seen.add(normalized)
            choices.append((alias_path, alias_name))

    # Cap at 5 and assign indices
    return [(i, label, path) for i, (path, label) in enumerate(choices[:5])]


@router.callback_query(F.data.startswith("menu:"))
async def handle_menu(callback: CallbackQuery) -> None:
    """Navigate between menu screens."""
    target = callback.data.split(":", 1)[1]
    _clear_pending_input()
    mgr = _get_mgr()

    try:
        if target == "main":
            await callback.message.edit_text(
                "🎛️ <b>Conductor Menu</b>",
                parse_mode="HTML",
                reply_markup=main_action_menu(),
            )

        elif target == "sessions":
            if not mgr:
                await callback.answer("Session manager unavailable")
                return
            sessions = await mgr.list_sessions()
            if sessions:
                await callback.message.edit_text(
                    "📋 <b>Active Sessions</b>\n\nTap a session for actions:",
                    parse_mode="HTML",
                    reply_markup=session_list_keyboard(sessions),
                )
            else:
                await callback.message.edit_text(
                    "📋 <b>No active sessions</b>\n\nCreate one to get started.",
                    parse_mode="HTML",
                    reply_markup=new_session_keyboard(),
                )

        elif target == "actions":
            await callback.message.edit_text(
                "⚡ <b>Actions</b>\n\nPick an action, then choose a session:",
                parse_mode="HTML",
                reply_markup=action_list_keyboard(),
            )

        elif target == "new":
            await callback.message.edit_text(
                "➕ <b>New Session</b>\n\nPick session type:",
                parse_mode="HTML",
                reply_markup=new_session_keyboard(),
            )

        elif target == "auto":
            await callback.message.edit_text(
                "🤖 <b>Auto-Responder</b>",
                parse_mode="HTML",
                reply_markup=auto_responder_keyboard(),
            )

        elif target == "tokens":
            await _show_tokens_inline(callback)

        elif target == "settings":
            await _show_settings_inline(callback)

        elif target == "status":
            if not mgr:
                await callback.answer("Session manager unavailable")
                return
            sessions = await mgr.list_sessions()
            await callback.message.edit_text(
                format_status_dashboard(sessions),
                parse_mode="HTML",
                reply_markup=status_keyboard(),
            )

    except TelegramBadRequest:
        pass  # Message content unchanged

    await callback.answer()


# ── Session action callbacks ──


async def _execute_session_action(
    callback: CallbackQuery, action: str, session_id: str
) -> None:
    """Execute a session action — shared logic for sess:, act:, and apick: flows."""
    mgr = _get_mgr()
    if not mgr:
        await callback.answer("Session manager unavailable")
        return

    session = mgr.get_session(session_id)
    if not session:
        try:
            await callback.message.edit_text(
                "❌ Session no longer exists.",
                reply_markup=back_keyboard("menu:sessions"),
            )
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    try:
        if action == "detail":
            await callback.message.edit_text(
                format_session_dashboard(session),
                parse_mode="HTML",
                reply_markup=session_action_keyboard(session),
            )

        elif action == "output":
            await _show_output_inline(callback, session, mgr)

        elif action == "input":
            from conductor.bot.bot import set_app_data

            set_app_data("pending_input_type", "input")
            set_app_data("pending_input_session", session_id)
            await callback.message.edit_text(
                f"📤 <b>Send Input to {session_label(session)}</b>\n\n"
                "Type your message below:",
                parse_mode="HTML",
                reply_markup=back_keyboard(f"sess:detail:{session_id}"),
            )

        elif action == "pause":
            result = await mgr.pause_session(session_id)
            if result:
                await callback.message.edit_text(
                    f"⏸ Paused {session_label(result)}",
                    parse_mode="HTML",
                    reply_markup=session_action_keyboard(result),
                )
            else:
                await callback.answer("Could not pause session")

        elif action == "resume":
            result = await mgr.resume_session(session_id)
            if result:
                await callback.message.edit_text(
                    f"▶️ Resumed {session_label(result)}",
                    parse_mode="HTML",
                    reply_markup=session_action_keyboard(result),
                )
            else:
                await callback.answer("Could not resume session")

        elif action == "kill":
            confirmation_mgr.request(callback.from_user.id, "kill", session_id)
            await callback.message.edit_text(
                f"⚠️ Confirm: Kill session {session_label(session)}?\n"
                "This will terminate the process.\n\n"
                "⏱️ Auto-cancels in 30 seconds.",
                parse_mode="HTML",
                reply_markup=confirm_keyboard("kill", session_id),
            )

        elif action == "restart":
            confirmation_mgr.request(callback.from_user.id, "restart", session_id)
            await callback.message.edit_text(
                f"⚠️ Confirm: Restart session {session_label(session)}?\n"
                "This will kill and recreate the session.\n\n"
                "⏱️ Auto-cancels in 30 seconds.",
                parse_mode="HTML",
                reply_markup=confirm_keyboard("restart", session_id),
            )

        elif action == "rename":
            from conductor.bot.bot import set_app_data

            set_app_data("pending_input_type", "rename")
            set_app_data("pending_input_session", session_id)
            await callback.message.edit_text(
                f"✏️ <b>Rename {session_label(session)}</b>\n\n"
                "Type the new name below:",
                parse_mode="HTML",
                reply_markup=back_keyboard(f"sess:detail:{session_id}"),
            )

        elif action == "log":
            await _send_log_inline(callback, session, mgr)

    except TelegramBadRequest:
        pass  # Message content unchanged

    await callback.answer()


@router.callback_query(F.data.startswith("sess:"))
async def handle_session_action(callback: CallbackQuery) -> None:
    """Handle per-session action buttons."""
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    action, session_id = parts[1], parts[2]
    await _execute_session_action(callback, action, session_id)


# ── Action-centric flow callbacks ──


@router.callback_query(F.data.startswith("act:"))
async def handle_action_pick(callback: CallbackQuery) -> None:
    """Show session picker for a chosen action (action-centric flow)."""
    action = callback.data.split(":", 1)[1]
    mgr = _get_mgr()
    if not mgr:
        await callback.answer("Session manager unavailable")
        return

    sessions = await mgr.list_sessions()
    if not sessions:
        try:
            await callback.message.edit_text(
                "📋 <b>No active sessions</b>\n\nCreate one first.",
                parse_mode="HTML",
                reply_markup=new_session_keyboard(),
            )
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    # Single-session shortcut — skip picker
    if len(sessions) == 1:
        s = sessions[0]
        await _execute_session_action(callback, action, s.id)
        return

    try:
        _action_labels = {
            "output": "📊 View Output",
            "input": "📤 Send Input",
            "pause": "⏸ Pause",
            "resume": "▶️ Resume",
            "restart": "🔄 Restart",
            "kill": "🗑️ Kill",
            "log": "📋 Full Log",
            "rename": "✏️ Rename",
        }
        label = _action_labels.get(action, action.title())
        await callback.message.edit_text(
            f"⚡ <b>{label}</b>\n\nPick a session:",
            parse_mode="HTML",
            reply_markup=action_session_picker(sessions, action),
        )
    except TelegramBadRequest:
        pass

    await callback.answer()


@router.callback_query(F.data.startswith("apick:"))
async def handle_action_session_pick(callback: CallbackQuery) -> None:
    """Complete the action-centric flow — session picked for pending action."""
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    action, session_id = parts[1], parts[2]
    await _execute_session_action(callback, action, session_id)


# ── New session callbacks ──


@router.callback_query(F.data.startswith("new:"))
async def handle_new_session(callback: CallbackQuery) -> None:
    """Start the new session creation flow with a directory picker."""
    session_type_code = callback.data.split(":", 1)[1]
    from conductor.bot.bot import set_app_data

    session_type = "claude-code" if session_type_code == "cc" else "shell"
    set_app_data("pending_new_session_type", session_type)

    type_label = "Claude Code" if session_type_code == "cc" else "Shell"

    # Build directory choices
    choices = await _build_directory_choices()

    if choices:
        # Store full paths indexed by position for the dir: callback
        path_map = {i: path for i, _label, path in choices}
        set_app_data("pending_dir_choices", path_map)

        picker_dirs = [(i, label) for i, label, _path in choices]
        try:
            await callback.message.edit_text(
                f"➕ <b>New {type_label} Session</b>\n\n" "Pick a working directory:",
                parse_mode="HTML",
                reply_markup=directory_picker(picker_dirs),
            )
        except TelegramBadRequest:
            pass
    else:
        # No dirs available — fall back to text input
        set_app_data("pending_input_type", "new_session")
        try:
            await callback.message.edit_text(
                f"➕ <b>New {type_label} Session</b>\n\n"
                "Type the working directory path below:\n"
                "<code>~/projects/myapp</code>",
                parse_mode="HTML",
                reply_markup=back_keyboard("menu:new"),
            )
        except TelegramBadRequest:
            pass

    await callback.answer()


@router.callback_query(F.data.startswith("dir:"))
async def handle_directory_pick(callback: CallbackQuery) -> None:
    """Handle directory picker button taps."""
    choice = callback.data.split(":", 1)[1]
    from conductor.bot.bot import get_app_data, set_app_data

    app_data = get_app_data()
    session_type = app_data.get("pending_new_session_type", "claude-code")

    if choice == "custom":
        # Fall back to text input
        set_app_data("pending_input_type", "new_session")
        set_app_data("pending_dir_choices", None)
        type_label = "Claude Code" if session_type == "claude-code" else "Shell"
        try:
            await callback.message.edit_text(
                f"➕ <b>New {type_label} Session</b>\n\n"
                "Type the working directory path below:\n"
                "<code>~/projects/myapp</code>",
                parse_mode="HTML",
                reply_markup=back_keyboard("menu:new"),
            )
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    # Numeric index — look up path
    path_map = app_data.get("pending_dir_choices", {})
    try:
        idx = int(choice)
        working_dir = path_map[idx]
    except (ValueError, KeyError):
        try:
            await callback.message.edit_text(
                "⏰ Directory picker expired. Please start again.",
                reply_markup=back_keyboard("menu:new"),
            )
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    # Clear state
    set_app_data("pending_dir_choices", None)
    set_app_data("pending_new_session_type", None)

    mgr = _get_mgr()
    if not mgr:
        await callback.answer("Session manager unavailable")
        return

    try:
        session = await mgr.create_session(
            session_type=session_type, working_dir=working_dir
        )
        # Start monitor
        from conductor.bot.handlers.natural import _start_monitor_for_session

        _start_monitor_for_session(session, mgr, app_data)

        from conductor.bot.formatter import session_label

        await callback.message.edit_text(
            f"✅ Created {session_label(session)} (#{session.number})\n"
            f"Type: {session.type}\n"
            f"Dir: {mono(session.working_dir)}",
            parse_mode="HTML",
        )
    except Exception as e:
        try:
            await callback.message.edit_text(f"❌ Failed to create session: {e}")
        except TelegramBadRequest:
            pass

    await callback.answer()


# ── Auto-responder callbacks ──


@router.callback_query(F.data.startswith("auto:"))
async def handle_auto(callback: CallbackQuery) -> None:
    """Handle auto-responder control buttons."""
    subcmd = callback.data.split(":", 1)[1]
    from conductor.auto import rules as auto_rules

    try:
        if subcmd == "list":
            all_rules = await auto_rules.get_all_rules()
            if not all_rules:
                await callback.message.edit_text(
                    "📋 <b>No auto-response rules</b>\n\n"
                    "Use /auto add to create one.",
                    parse_mode="HTML",
                    reply_markup=auto_responder_keyboard(),
                )
            else:
                lines = ["📋 <b>Auto-Response Rules</b>\n"]
                for r in all_rules:
                    status = "✅" if r.enabled else "⏸"
                    lines.append(
                        f"{status} #{r.id} — <code>{r.pattern}</code> → "
                        f"<code>{r.response or '(enter)'}</code> "
                        f"({r.match_type}, {r.hit_count} hits)"
                    )
                await callback.message.edit_text(
                    "\n".join(lines),
                    parse_mode="HTML",
                    reply_markup=auto_responder_keyboard(),
                )

        elif subcmd == "pause":
            await auto_rules.pause_all()
            await callback.message.edit_text(
                "⏸ Auto-responder paused. All rules disabled.",
                reply_markup=auto_responder_keyboard(),
            )

        elif subcmd == "resume":
            await auto_rules.resume_all()
            await callback.message.edit_text(
                "▶️ Auto-responder resumed. All rules enabled.",
                reply_markup=auto_responder_keyboard(),
            )

    except TelegramBadRequest:
        pass

    await callback.answer()


# ── Helper functions for inline display ──


async def _show_output_inline(callback: CallbackQuery, session, mgr) -> None:
    """Show session output inline with refresh and back buttons."""
    from conductor.bot.bot import get_app_data

    app_data = get_app_data()
    monitors = app_data.get("monitors", {})
    monitor = monitors.get(session.id)

    if monitor and hasattr(monitor, "output_buffer"):
        lines = monitor.output_buffer.rolling_buffer[-30:]
        if lines:
            text = redact_sensitive("\n".join(lines))
            # Try AI summary
            brain = app_data.get("brain")
            if brain:
                try:
                    summary = await brain.summarize(text)
                    await callback.message.edit_text(
                        f"📊 {session_label(session)} — AI Summary:\n\n{summary}",
                        parse_mode="HTML",
                        reply_markup=back_keyboard(f"sess:detail:{session.id}"),
                    )
                    return
                except Exception:
                    pass
            # Fallback: raw output
            await callback.message.edit_text(
                f"📝 {session_label(session)} — Last 30 lines:\n\n"
                f"{mono(text[:3500])}",
                parse_mode="HTML",
                reply_markup=back_keyboard(f"sess:detail:{session.id}"),
            )
        else:
            await callback.message.edit_text(
                f"📝 {session_label(session)} — No output captured yet.",
                reply_markup=back_keyboard(f"sess:detail:{session.id}"),
            )
    else:
        await callback.message.edit_text(
            f"📝 {session_label(session)} — No monitor active.",
            reply_markup=back_keyboard(f"sess:detail:{session.id}"),
        )


async def _send_log_inline(callback: CallbackQuery, session, mgr) -> None:
    """Send session log as a document file."""
    import io
    from datetime import datetime
    from aiogram.types import BufferedInputFile

    from conductor.bot.bot import get_app_data

    monitors = get_app_data().get("monitors", {})
    monitor = monitors.get(session.id)

    if monitor and hasattr(monitor, "output_buffer"):
        lines = monitor.output_buffer.rolling_buffer
        if lines:
            content = redact_sensitive("\n".join(lines))
            buf = io.BytesIO(content.encode("utf-8"))
            filename = f"{session.alias}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
            doc = BufferedInputFile(buf.read(), filename=filename)
            await callback.message.answer_document(
                doc, caption=f"📋 Full log for {session_label(session)}"
            )
            return

    await callback.message.answer(
        f"📋 {session_label(session)} — No output captured yet."
    )


async def _show_tokens_inline(callback: CallbackQuery) -> None:
    """Show token usage inline."""
    from conductor.bot.bot import get_app_data

    mgr = _get_mgr()
    app_data = get_app_data()
    estimator = app_data.get("token_estimator")

    if not estimator or not mgr:
        await callback.message.edit_text(
            "📊 Token tracking not available.",
            reply_markup=back_keyboard(),
        )
        return

    sessions = await mgr.list_sessions()
    if not sessions:
        await callback.message.edit_text(
            "📊 No active sessions.",
            reply_markup=back_keyboard(),
        )
        return

    lines = ["📊 <b>Token Usage</b>\n"]
    for s in sessions:
        usage = estimator.get_usage(s.id)
        pct = usage["percentage"]
        warn = " ⚠️" if pct >= 80 else ""
        lines.append(
            f"{s.color_emoji} {s.alias}  {pct}% ({usage['used']}/{usage['limit']}){warn}"
        )

    total = estimator.get_usage()
    lines.append(
        f"\n<b>Total</b>  {total['percentage']}% ({total['used']}/{total['limit']})"
    )
    lines.append(f"Tier  <code>{total['tier']}</code>")
    if total["reset_in_seconds"]:
        mins = int(total["reset_in_seconds"] / 60)
        lines.append(f"Resets in  <code>{mins}m</code>")

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )


async def _show_settings_inline(callback: CallbackQuery) -> None:
    """Show settings inline."""
    from conductor.config import get_config

    cfg = get_config()

    lines = [
        "⚙️ <b>Settings</b>\n",
        "<b>Sessions</b>",
        f"Plan tier  <code>{cfg.plan_tier}</code>",
        f"Max concurrent  <code>{cfg.max_concurrent_sessions}</code>",
        f"Poll interval  <code>{cfg.monitor_config.get('poll_interval_ms', 500)}ms</code>\n",
        "<b>Intelligence</b>",
        f"AI model  <code>{cfg.ai_model}</code>",
        f"Batch window  <code>{cfg.batch_window_s}s</code>",
        f"Auto-responder  <code>{'enabled' if cfg.auto_responder_config.get('enabled') else 'disabled'}</code>\n",
        "<b>Security</b>",
        f"Redaction  <code>{'enabled' if cfg.security_config.get('redact_patterns') else 'disabled'}</code>",
        f"Quiet hours  <code>{'enabled' if cfg.quiet_hours.get('enabled') else 'disabled'}</code>",
    ]
    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )
