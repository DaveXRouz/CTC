"""Inline button callback handlers."""

from __future__ import annotations

import asyncio

from aiogram import Router, F
from aiogram.types import CallbackQuery

from conductor.bot.formatter import session_label, format_status_dashboard
from conductor.bot.keyboards import status_keyboard
from conductor.security.confirm import ConfirmationManager
from conductor.utils.logger import get_logger

logger = get_logger("conductor.bot.callbacks")

router = Router()

confirmation_mgr = ConfirmationManager()


def _get_mgr():
    from conductor.bot.handlers.commands import _session_manager

    return _session_manager


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
        mgr.send_input(session_id, "y")
        await callback.message.edit_text(f"✅ Sent 'y' to {session_label(session)}")
    elif decision == "no":
        mgr.send_input(session_id, "n")
        await callback.message.edit_text(f"❌ Sent 'n' to {session_label(session)}")
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
        mgr.send_input(session_id, "npm test")
        await callback.message.edit_text(
            f"▶️ Running tests in {session_label(session)}"
        )
    elif action == "log":
        from conductor.bot.handlers.commands import cmd_log

        await cmd_log(callback.message)
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
    await callback.message.edit_text(
        format_status_dashboard(sessions),
        parse_mode="HTML",
        reply_markup=status_keyboard(),
    )
    await callback.answer("Refreshed!")


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
            mgr.send_input(session_id, cmd)
            session = mgr.get_session(session_id)
            label = session_label(session) if session else session_id
            await callback.message.edit_text(f"▶️ Running in {label}: {cmd}")
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
