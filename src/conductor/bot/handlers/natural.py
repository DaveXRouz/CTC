"""Natural language → AI brain NLP parser → command dispatch."""

from __future__ import annotations

import json

from aiogram import Router
from aiogram.types import Message

from conductor.utils.logger import get_logger

logger = get_logger("conductor.bot.natural")

router = Router()

# Menu button text → command mapping
_MENU_ROUTES = {
    "menu": "menu",
    "status": "status",
    "new session": "new_session",
    "output": "output",
    "tokens": "tokens",
    "help": "help",
}


async def _dispatch_menu_command(message: Message, route: str) -> None:
    """Dispatch a menu button tap to the appropriate command handler."""
    if route == "menu":
        from conductor.bot.handlers.commands import cmd_menu

        await cmd_menu(message)
    elif route == "status":
        from conductor.bot.handlers.commands import cmd_status

        await cmd_status(message)
    elif route == "output":
        from conductor.bot.handlers.commands import cmd_output

        await cmd_output(message)
    elif route == "tokens":
        from conductor.bot.handlers.commands import cmd_tokens

        await cmd_tokens(message)
    elif route == "help":
        from conductor.bot.handlers.commands import cmd_help

        await cmd_help(message)
    elif route == "new_session":
        from conductor.bot.keyboards import main_menu_keyboard

        await message.answer(
            "📦 <b>Create a Session</b>\n\n"
            "Usage: /new &lt;type&gt; &lt;directory&gt;\n\n"
            "<b>Examples:</b>\n"
            "<code>/new cc ~/projects/myapp</code> — Claude Code\n"
            "<code>/new sh ~/projects/myapp</code> — Shell\n",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )


@router.message()
async def handle_natural_language(message: Message) -> None:
    """Handle non-command messages via NLP parsing.

    Processing order:
    0. Pending input from button flow (input/rename/new_session)
    1. Menu button taps (Status, Output, etc.)
    2. Picked session (inline keyboard one-shot)
    3. Quick prompt responses (short text -> last active session)
    4. AI NLP parsing via brain.parse_nlp()
    5. Single-session fallback (send text to the only active session)
    6. Fallback error message

    Args:
        message: Incoming Telegram message.
    """
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    from conductor.bot.bot import get_app_data, set_app_data
    from conductor.bot.handlers.commands import _session_manager

    app_data = get_app_data()
    brain = app_data.get("brain")
    mgr = _session_manager

    # Pending input from button flow (input/rename/new_session) — check first
    # so that typing "Status" as a rename value doesn't trigger menu dispatch.
    pending_type = app_data.get("pending_input_type")
    if pending_type:
        if not mgr:
            await message.answer("⏳ Bot is still initializing. Try again shortly.")
            return
        await _handle_pending_input(message, text, pending_type, app_data, mgr)
        return

    # Menu button routing
    route = _MENU_ROUTES.get(text.lower())
    if route:
        await _dispatch_menu_command(message, route)
        return

    if not mgr:
        await message.answer("⏳ Bot is still initializing. Try again shortly.")
        return

    # Check if a session was picked via inline keyboard (one-time use)
    picked_session = app_data.get("picked_session")
    if picked_session:
        set_app_data("picked_session", None)
        session = mgr.get_session(picked_session)
        if session:
            from conductor.bot.formatter import session_label

            if mgr.send_input(session.id, text):
                await message.answer(
                    f"📤 Sent to {session_label(session)}: <code>{text}</code>",
                    parse_mode="HTML",
                )
            else:
                await message.answer("⚠️ Failed to send — session pane not found")
            return

    # Quick check: if only one session and text looks like a response (short, y/n, number)
    sessions = await mgr.list_sessions()
    last_prompt_session = app_data.get("last_prompt_session")

    if last_prompt_session and len(text) <= 10:
        # Likely a response to a pending prompt
        session = mgr.get_session(last_prompt_session)
        if session and session.status == "waiting":
            from conductor.sessions.detector import has_destructive_keyword

            if has_destructive_keyword(text):
                await message.answer(
                    "⚠️ Blocked: destructive keyword detected. "
                    "Use /input to send explicitly."
                )
                return
            from conductor.bot.formatter import session_label

            if mgr.send_input(session.id, text):
                await message.answer(
                    f"📤 Sent to {session_label(session)}: <code>{text}</code>",
                    parse_mode="HTML",
                )
            else:
                await message.answer("⚠️ Failed to send — session pane not found")
            return

    # Try AI brain NLP if available
    if brain:
        session_list = [
            {"number": s.number, "alias": s.alias, "status": s.status} for s in sessions
        ]
        try:
            result = await brain.parse_nlp(
                user_message=text,
                session_list_json=json.dumps(session_list),
                last_prompt_context=str(app_data.get("last_prompt_context", "None")),
            )

            confidence = result.get("confidence", 0)
            command = result.get("command", "unknown")

            if confidence >= 0.8 and command != "unknown":
                await _dispatch_nlp_command(message, result, mgr)
                return
        except Exception as e:
            logger.warning(f"NLP parse failed: {e}")

    # Fallback: if only one session, send input to it
    if len(sessions) == 1:
        session = sessions[0]
        from conductor.bot.formatter import session_label

        if mgr.send_input(session.id, text):
            await message.answer(
                f"📤 Sent to {session_label(session)}: <code>{text}</code>",
                parse_mode="HTML",
            )
        else:
            await message.answer("⚠️ Failed to send — session pane not found")
        return

    # Give up
    from conductor.bot.handlers.fallback import send_fallback

    await send_fallback(message)


async def _handle_pending_input(
    message: Message, text: str, pending_type: str, app_data: dict, mgr
) -> None:
    """Handle text input collected after a button tap (input/rename/new_session)."""
    from conductor.bot.bot import set_app_data
    from conductor.bot.formatter import session_label, mono
    from conductor.bot.keyboards import main_menu_keyboard

    # Clear pending state
    set_app_data("pending_input_type", None)
    session_id = app_data.get("pending_input_session")

    if pending_type == "input":
        if not session_id:
            await message.answer("⚠️ No session selected.")
            return
        session = mgr.get_session(session_id)
        if not session:
            await message.answer("❌ Session no longer exists.")
            return
        # Safety: check destructive keywords
        from conductor.sessions.detector import has_destructive_keyword

        if has_destructive_keyword(text):
            await message.answer(
                "⚠️ Blocked: destructive keyword detected. "
                "Use /input to send explicitly."
            )
            return
        if mgr.send_input(session.id, text):
            await message.answer(
                f"📤 Sent to {session_label(session)}: <code>{text}</code>",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await message.answer("⚠️ Failed to send — session pane not found")

    elif pending_type == "rename":
        if not session_id:
            await message.answer("⚠️ No session selected.")
            return
        session = mgr.get_session(session_id)
        if not session:
            await message.answer("❌ Session no longer exists.")
            return
        old_name = session.alias
        try:
            result = await mgr.rename_session(session.id, text)
            if result:
                await message.answer(
                    f"✏️ Renamed {session.color_emoji} #{session.number}: "
                    f"{old_name} → <b>{text}</b>",
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
        except ValueError as e:
            await message.answer(f"❌ {e}")

    elif pending_type == "new_session":
        session_type = app_data.get("pending_new_session_type", "claude-code")
        set_app_data("pending_new_session_type", None)
        try:
            session = await mgr.create_session(
                session_type=session_type, working_dir=text
            )
            # Start monitor for the new session
            _start_monitor_for_session(session, mgr, app_data)
            await message.answer(
                f"✅ Created {session_label(session)} (#{session.number})\n"
                f"Type: {session.type}\n"
                f"Dir: {mono(session.working_dir)}",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
        except Exception as e:
            await message.answer(f"❌ Failed to create session: {e}")

    set_app_data("pending_input_session", None)


def _start_monitor_for_session(session, mgr, app_data: dict) -> None:
    """Start an OutputMonitor for a newly created session (from button flow)."""
    import asyncio
    from conductor.sessions.monitor import OutputMonitor

    monitors = app_data.get("monitors", {})
    monitor_tasks = app_data.get("monitor_tasks", {})
    on_monitor_event = app_data.get("on_monitor_event")

    pane = mgr.get_pane(session.id)
    if pane and on_monitor_event:
        monitor = OutputMonitor(pane, session, on_event=on_monitor_event)
        monitors[session.id] = monitor
        monitor_tasks[session.id] = asyncio.create_task(monitor.start())


async def _dispatch_nlp_command(message: Message, result: dict, mgr) -> None:
    """Dispatch a parsed NLP command to the appropriate slash command handler.

    Args:
        message: Original Telegram message (text may be overwritten for dispatch).
        result: Parsed NLP result dict with 'command', 'session', 'args' keys.
        mgr: The active SessionManager instance.
    """
    command = result.get("command", "")
    session_ref = result.get("session")
    args = result.get("args", {})

    # Map to slash commands
    if command == "status":
        from conductor.bot.handlers.commands import cmd_status

        if session_ref:
            message.__dict__["text"] = f"/status {session_ref}"
        await cmd_status(message)
    elif command == "input":
        text = args.get("text", "")
        if session_ref and text:
            session = mgr.resolve_session(str(session_ref))
            if session:
                from conductor.bot.formatter import session_label

                if mgr.send_input(session.id, text):
                    await message.answer(
                        f"📤 Sent to {session_label(session)}: <code>{text}</code>",
                        parse_mode="HTML",
                    )
                else:
                    await message.answer("⚠️ Failed to send — session pane not found")
    elif command == "output":
        from conductor.bot.handlers.commands import cmd_output

        if session_ref:
            message.__dict__["text"] = f"/output {session_ref}"
        await cmd_output(message)
    elif command == "tokens":
        from conductor.bot.handlers.commands import cmd_tokens

        await cmd_tokens(message)
    elif command == "help":
        from conductor.bot.handlers.commands import cmd_help

        await cmd_help(message)
    elif command == "kill":
        if session_ref:
            from conductor.bot.handlers.commands import cmd_kill

            message.__dict__["text"] = f"/kill {session_ref}"
            await cmd_kill(message)
    elif command == "pause":
        if session_ref:
            from conductor.bot.handlers.commands import cmd_pause

            message.__dict__["text"] = f"/pause {session_ref}"
            await cmd_pause(message)
    elif command == "resume":
        if session_ref:
            from conductor.bot.handlers.commands import cmd_resume

            message.__dict__["text"] = f"/resume {session_ref}"
            await cmd_resume(message)
    elif command == "digest":
        from conductor.bot.handlers.commands import cmd_digest

        await cmd_digest(message)
    else:
        from conductor.bot.handlers.fallback import send_fallback

        await send_fallback(message)
