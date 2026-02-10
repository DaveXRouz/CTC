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
    "status": "status",
    "new session": "new_session",
    "output": "output",
    "tokens": "tokens",
    "help": "help",
}


async def _dispatch_menu_command(message: Message, route: str) -> None:
    """Dispatch a menu button tap to the appropriate command handler."""
    if route == "status":
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
    0. Menu button taps (Status, Output, etc.)
    1. Quick prompt responses (short text -> last active session)
    2. AI NLP parsing via brain.parse_nlp()
    3. Single-session fallback (send text to the only active session)
    4. Fallback error message

    Args:
        message: Incoming Telegram message.
    """
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    # Menu button routing — check before anything else
    route = _MENU_ROUTES.get(text.lower())
    if route:
        await _dispatch_menu_command(message, route)
        return

    from conductor.bot.bot import get_app_data
    from conductor.bot.handlers.commands import _session_manager

    app_data = get_app_data()
    brain = app_data.get("brain")
    mgr = _session_manager

    if not mgr:
        await message.answer("⏳ Bot is still initializing. Try again shortly.")
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

            mgr.send_input(session.id, text)
            await message.answer(
                f"📤 Sent to {session_label(session)}: <code>{text}</code>",
                parse_mode="HTML",
            )
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

        mgr.send_input(session.id, text)
        await message.answer(
            f"📤 Sent to {session_label(session)}: <code>{text}</code>",
            parse_mode="HTML",
        )
        return

    # Give up
    from conductor.bot.handlers.fallback import send_fallback

    await send_fallback(message)


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
            message.text = f"/status {session_ref}"
        await cmd_status(message)
    elif command == "input":
        text = args.get("text", "")
        if session_ref and text:
            session = mgr.resolve_session(str(session_ref))
            if session:
                from conductor.bot.formatter import session_label

                mgr.send_input(session.id, text)
                await message.answer(
                    f"📤 Sent to {session_label(session)}: <code>{text}</code>",
                    parse_mode="HTML",
                )
    elif command == "output":
        from conductor.bot.handlers.commands import cmd_output

        if session_ref:
            message.text = f"/output {session_ref}"
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

            message.text = f"/kill {session_ref}"
            await cmd_kill(message)
    elif command == "pause":
        if session_ref:
            from conductor.bot.handlers.commands import cmd_pause

            message.text = f"/pause {session_ref}"
            await cmd_pause(message)
    elif command == "resume":
        if session_ref:
            from conductor.bot.handlers.commands import cmd_resume

            message.text = f"/resume {session_ref}"
            await cmd_resume(message)
    elif command == "digest":
        from conductor.bot.handlers.commands import cmd_digest

        await cmd_digest(message)
    else:
        from conductor.bot.handlers.fallback import send_fallback

        await send_fallback(message)
