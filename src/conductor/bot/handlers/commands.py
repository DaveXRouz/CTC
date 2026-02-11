"""Slash command handlers for the Telegram bot."""

from __future__ import annotations

import io
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, BufferedInputFile

from conductor.bot.formatter import (
    format_status_dashboard,
    session_label,
    mono,
    bold,
)
from conductor.bot.keyboards import (
    status_keyboard,
    confirm_keyboard,
    main_menu_keyboard,
    main_action_menu,
)
from conductor.security.redactor import redact_sensitive
from conductor.sessions.manager import SessionManager
from conductor.bot.handlers.callbacks import confirmation_mgr
from conductor.utils.logger import get_logger

logger = get_logger("conductor.bot.commands")

router = Router()

# These get injected at bot startup
_session_manager: SessionManager | None = None


def set_session_manager(manager: SessionManager) -> None:
    """Inject the SessionManager instance for command handlers.

    Args:
        manager: The active SessionManager, set during startup in ``main.py``.
    """
    global _session_manager
    _session_manager = manager


def _mgr() -> SessionManager:
    if _session_manager is None:
        raise RuntimeError("Session manager not initialized")
    return _session_manager


# ── /start ──


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "🎛️ <b>Conductor</b>\n\n"
        "Remote terminal control from Telegram.\n"
        "Monitor sessions, relay prompts, manage everything.\n\n"
        "Conductor tracks sessions <b>it</b> creates — your existing\n"
        "terminals aren't monitored until you start one here.\n\n"
        "<b>Quick start</b>\n"
        "<code>/new cc ~/projects/myapp</code> — Claude Code\n"
        "<code>/new sh ~/projects/myapp</code> — Shell\n\n"
        "Tap the buttons below or type /help for all commands.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# ── /help ──


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📖 <b>Command Reference</b>\n\n"
        "<b>Navigation</b>\n"
        "/menu — interactive button menu\n\n"
        "<b>Sessions</b>\n"
        "/new cc|sh &lt;dir&gt; — create session\n"
        "/kill /restart /pause /resume &lt;name|#&gt;\n"
        "/rename &lt;#&gt; &lt;name&gt;\n\n"
        "<b>Monitor</b>\n"
        "/status — dashboard\n"
        "/output &lt;name|#&gt; — AI summary\n"
        "/log &lt;name|#&gt; — full log file\n"
        "/tokens — usage overview\n\n"
        "<b>Input</b>\n"
        "/input &lt;name|#&gt; &lt;text&gt;\n"
        "/run &lt;name|#&gt; &lt;cmd&gt;\n"
        "/shell &lt;cmd&gt; — one-off command\n\n"
        "<b>Auto-Responder</b>\n"
        "/auto list | add | remove | pause | resume\n\n"
        "<b>Settings</b>\n"
        "/quiet HH:MM-HH:MM — quiet hours\n"
        "/settings — view config\n\n"
        "💡 Tap <b>Menu</b> for a button-driven interface.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# ── /menu ──


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer(
        "🎛️ <b>Conductor Menu</b>",
        parse_mode="HTML",
        reply_markup=main_action_menu(),
    )


# ── /status ──


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    mgr = _mgr()
    args = (message.text or "").split(maxsplit=1)

    if len(args) > 1:
        session = mgr.resolve_session(args[1])
        if not session:
            await message.answer(f"❌ Session not found: {args[1]}")
            return
        from conductor.bot.formatter import format_session_dashboard

        await message.answer(
            format_session_dashboard(session),
            parse_mode="HTML",
            reply_markup=status_keyboard(),
        )
    else:
        sessions = await mgr.list_sessions()
        await message.answer(
            format_status_dashboard(sessions),
            parse_mode="HTML",
            reply_markup=status_keyboard(),
        )


# ── /new ──


@router.message(Command("new"))
async def cmd_new(message: Message) -> None:
    mgr = _mgr()
    args = (message.text or "").split()

    if len(args) < 3:
        await message.answer(
            "Usage: /new &lt;cc|sh&gt; &lt;directory&gt;\n"
            "Example: /new cc ~/projects/myapp",
            parse_mode="HTML",
        )
        return

    stype = "claude-code" if args[1] in ("cc", "claude-code") else "shell"
    working_dir = args[2]

    try:
        session = await mgr.create_session(session_type=stype, working_dir=working_dir)
        await message.answer(
            f"✅ Created {session_label(session)} (#{session.number})\n"
            f"Type: {session.type}\n"
            f"Dir: {mono(session.working_dir)}",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Failed to create session: {e}")


# ── /kill ──


@router.message(Command("kill"))
async def cmd_kill(message: Message) -> None:
    mgr = _mgr()
    args = (message.text or "").split(maxsplit=1)

    if len(args) < 2:
        await message.answer("Usage: /kill &lt;name|#&gt;", parse_mode="HTML")
        return

    session = mgr.resolve_session(args[1])
    if not session:
        await message.answer(f"❌ Session not found: {args[1]}")
        return

    confirmation_mgr.request(message.from_user.id, "kill", session.id)
    await message.answer(
        f"⚠️ Confirm: Kill session {session_label(session)}?\n"
        "This will terminate the process. Unsaved work may be lost.\n\n"
        "⏱️ Auto-cancels in 30 seconds.",
        parse_mode="HTML",
        reply_markup=confirm_keyboard("kill", session.id),
    )


# ── /pause ──


@router.message(Command("pause"))
async def cmd_pause(message: Message) -> None:
    mgr = _mgr()
    args = (message.text or "").split(maxsplit=1)

    if len(args) < 2:
        await message.answer("Usage: /pause &lt;name|#&gt;", parse_mode="HTML")
        return

    session = mgr.resolve_session(args[1])
    if not session:
        await message.answer(f"❌ Session not found: {args[1]}")
        return

    result = await mgr.pause_session(session.id)
    if result:
        await message.answer(f"⏸ Paused {session_label(result)}")
    else:
        await message.answer("❌ Could not pause session.")


# ── /resume ──


@router.message(Command("resume"))
async def cmd_resume(message: Message) -> None:
    mgr = _mgr()
    args = (message.text or "").split(maxsplit=1)

    if len(args) < 2:
        await message.answer("Usage: /resume &lt;name|#&gt;", parse_mode="HTML")
        return

    session = mgr.resolve_session(args[1])
    if not session:
        await message.answer(f"❌ Session not found: {args[1]}")
        return

    result = await mgr.resume_session(session.id)
    if result:
        await message.answer(f"▶️ Resumed {session_label(result)}")
    else:
        await message.answer("❌ Could not resume session.")


# ── /input ──


@router.message(Command("input"))
async def cmd_input(message: Message) -> None:
    mgr = _mgr()
    args = (message.text or "").split(maxsplit=2)

    if len(args) < 3:
        await message.answer(
            "Usage: /input &lt;name|#&gt; &lt;text&gt;",
            parse_mode="HTML",
        )
        return

    session = mgr.resolve_session(args[1])
    if not session:
        await message.answer(f"❌ Session not found: {args[1]}")
        return

    text = args[2]
    if mgr.send_input(session.id, text):
        await message.answer(
            f"📤 Sent to {session_label(session)}: {mono(text)}", parse_mode="HTML"
        )
    else:
        await message.answer("❌ Could not send input.")


# ── /output ──


@router.message(Command("output"))
async def cmd_output(message: Message) -> None:
    mgr = _mgr()
    args = (message.text or "").split(maxsplit=1)

    sessions = await mgr.list_sessions()
    if len(args) > 1:
        session = mgr.resolve_session(args[1])
    elif len(sessions) == 1:
        session = sessions[0]
    else:
        await message.answer("Usage: /output &lt;name|#&gt;", parse_mode="HTML")
        return

    if not session:
        await message.answer(
            f"❌ Session not found: {args[1] if len(args) > 1 else ''}"
        )
        return

    # Try to get output from the monitor's buffer
    from conductor.bot.bot import get_app_data

    app_data = get_app_data()
    monitors = app_data.get("monitors", {})
    monitor = monitors.get(session.id)

    if monitor and hasattr(monitor, "output_buffer"):
        lines = monitor.output_buffer.rolling_buffer[-30:]
        if lines:
            text = redact_sensitive("\n".join(lines))
            # Try AI summary if brain is available
            brain = app_data.get("brain")
            if brain:
                try:
                    summary = await brain.summarize(text)
                    await message.answer(
                        f"📊 {session_label(session)} — AI Summary:\n\n{summary}",
                        parse_mode="HTML",
                    )
                    return
                except Exception:
                    pass
            # Fallback: raw output
            await message.answer(
                f"📝 {session_label(session)} — Last 30 lines:\n\n{mono(text[:3500])}",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                f"📝 {session_label(session)} — No output captured yet."
            )
    else:
        await message.answer(f"📝 {session_label(session)} — No monitor active.")


# ── /log ──


@router.message(Command("log"))
async def cmd_log(message: Message) -> None:
    mgr = _mgr()
    args = (message.text or "").split(maxsplit=1)

    sessions = await mgr.list_sessions()
    if len(args) > 1:
        session = mgr.resolve_session(args[1])
    elif len(sessions) == 1:
        session = sessions[0]
    else:
        await message.answer("Usage: /log &lt;name|#&gt;", parse_mode="HTML")
        return

    if not session:
        identifier = args[1] if len(args) > 1 else ""
        await message.answer(
            f"❌ Session not found: {identifier}"
            if identifier
            else "❌ Session not found."
        )
        return

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
            await message.answer_document(
                doc, caption=f"📋 Full log for {session_label(session)}"
            )
        else:
            await message.answer(
                f"📋 {session_label(session)} — No output captured yet."
            )
    else:
        await message.answer(f"📋 {session_label(session)} — No monitor active.")


# ── /rename ──


@router.message(Command("rename"))
async def cmd_rename(message: Message) -> None:
    mgr = _mgr()
    args = (message.text or "").split(maxsplit=2)

    if len(args) < 3:
        await message.answer(
            "Usage: /rename &lt;#&gt; &lt;new_name&gt;",
            parse_mode="HTML",
        )
        return

    session = mgr.resolve_session(args[1])
    if not session:
        await message.answer(f"❌ Session not found: {args[1]}")
        return

    old_name = session.alias
    result = await mgr.rename_session(session.id, args[2])
    if result:
        await message.answer(
            f"✏️ Renamed {session.color_emoji} #{session.number}: "
            f"{old_name} → {bold(args[2])}",
            parse_mode="HTML",
        )


# ── /run ──


@router.message(Command("run"))
async def cmd_run(message: Message) -> None:
    mgr = _mgr()
    args = (message.text or "").split(maxsplit=2)

    if len(args) < 3:
        await message.answer(
            "Usage: /run &lt;name|#&gt; &lt;command&gt;",
            parse_mode="HTML",
        )
        return

    session = mgr.resolve_session(args[1])
    if not session:
        await message.answer(f"❌ Session not found: {args[1]}")
        return

    cmd = args[2]
    if mgr.send_input(session.id, cmd):
        await message.answer(
            f"▶️ Running in {session_label(session)}:\n{mono(cmd)}",
            parse_mode="HTML",
        )
    else:
        await message.answer("❌ Could not send command.")


# ── /shell ──


@router.message(Command("shell"))
async def cmd_shell(message: Message) -> None:
    args = (message.text or "").split(maxsplit=1)

    if len(args) < 2:
        await message.answer("Usage: /shell &lt;command&gt;", parse_mode="HTML")
        return

    cmd = args[1]

    # M8: Block dangerous shell commands
    _dangerous_commands = [
        "rm -rf /",
        "rm -rf /*",
        "mkfs",
        "dd if=",
        ":(){",
        "fork bomb",
    ]
    cmd_lower = cmd.lower().strip()
    for dangerous in _dangerous_commands:
        if dangerous in cmd_lower:
            await message.answer(f"🚫 Blocked: destructive command detected.")
            return

    try:
        import asyncio

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode("utf-8", errors="replace")
        if stderr:
            output += "\n" + stderr.decode("utf-8", errors="replace")
        output = output[:3500]
        await message.answer(
            (
                f"🖥️ Shell output:\n{mono(output)}"
                if output.strip()
                else "🖥️ Command completed (no output)."
            ),
            parse_mode="HTML",
        )
    except asyncio.TimeoutError:
        await message.answer("⏰ Command timed out after 30 seconds.")
    except Exception as e:
        await message.answer(f"❌ Shell error: {e}")


# ── /tokens ──


@router.message(Command("tokens"))
async def cmd_tokens(message: Message) -> None:
    mgr = _mgr()
    from conductor.bot.bot import get_app_data

    estimator = get_app_data().get("token_estimator")

    if not estimator:
        await message.answer("📊 Token tracking not available.")
        return

    sessions = await mgr.list_sessions()
    if not sessions:
        await message.answer("📊 No active sessions.\n\nUse /new to start one.")
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

    await message.answer("\n".join(lines), parse_mode="HTML")


# ── /digest ──


@router.message(Command("digest"))
async def cmd_digest(message: Message) -> None:
    # Same as /status for now — AI digest comes in Phase 3
    await cmd_status(message)


# ── /auto ──


@router.message(Command("auto"))
async def cmd_auto(message: Message) -> None:
    from conductor.auto import rules as auto_rules

    args = (message.text or "").split(maxsplit=2)
    subcmd = args[1] if len(args) > 1 else "list"

    if subcmd == "list":
        all_rules = await auto_rules.get_all_rules()
        if not all_rules:
            await message.answer(
                "📋 No auto-response rules.\n\nUse /auto add to create one."
            )
            return
        lines = ["📋 <b>Auto-Response Rules</b>\n"]
        for r in all_rules:
            status = "✅" if r.enabled else "⏸"
            lines.append(
                f"{status} #{r.id} — <code>{r.pattern}</code> → <code>{r.response or '(enter)'}</code> "
                f"({r.match_type}, {r.hit_count} hits)"
            )
        await message.answer("\n".join(lines), parse_mode="HTML")

    elif subcmd == "add":
        # Parse: /auto add "pattern" "response"
        rest = args[2] if len(args) > 2 else ""
        import re as _re

        parts = _re.findall(r'"([^"]*)"', rest)
        if len(parts) < 2:
            await message.answer(
                'Usage: /auto add "pattern" "response"',
                parse_mode="HTML",
            )
            return
        pattern = parts[0]
        if len(pattern) > 256:
            await message.answer("❌ Pattern too long (max 256 characters).")
            return
        # Validate regex syntax
        try:
            _re.compile(pattern)
        except _re.error as e:
            await message.answer(f"❌ Invalid regex pattern: {e}")
            return
        rule_id = await auto_rules.add_rule(pattern, parts[1])
        await message.answer(
            f"✅ Added rule #{rule_id}: <code>{parts[0]}</code> → <code>{parts[1]}</code>",
            parse_mode="HTML",
        )

    elif subcmd == "remove":
        try:
            rule_id = int(args[2])
        except (IndexError, ValueError):
            await message.answer("Usage: /auto remove &lt;#&gt;", parse_mode="HTML")
            return
        if await auto_rules.remove_rule(rule_id):
            await message.answer(f"🗑️ Removed rule #{rule_id}")
        else:
            await message.answer(f"❌ Rule #{rule_id} not found")

    elif subcmd == "pause":
        await auto_rules.pause_all()
        await message.answer("⏸ Auto-responder paused. All rules disabled.")

    elif subcmd == "resume":
        await auto_rules.resume_all()
        await message.answer("▶️ Auto-responder resumed. All rules enabled.")

    else:
        await message.answer(
            "Usage: /auto &lt;list|add|remove|pause|resume&gt;",
            parse_mode="HTML",
        )


# ── /restart ──


@router.message(Command("restart"))
async def cmd_restart(message: Message) -> None:
    mgr = _mgr()
    args = (message.text or "").split(maxsplit=1)

    if len(args) < 2:
        await message.answer("Usage: /restart &lt;name|#&gt;", parse_mode="HTML")
        return

    session = mgr.resolve_session(args[1])
    if not session:
        await message.answer(f"❌ Session not found: {args[1]}")
        return

    confirmation_mgr.request(message.from_user.id, "restart", session.id)
    await message.answer(
        f"⚠️ Confirm: Restart session {session_label(session)}?\n"
        "This will kill and recreate the session.\n\n"
        "⏱️ Auto-cancels in 30 seconds.",
        parse_mode="HTML",
        reply_markup=confirm_keyboard("restart", session.id),
    )


# ── /quiet ──


@router.message(Command("quiet"))
async def cmd_quiet(message: Message) -> None:
    args = (message.text or "").split(maxsplit=1)

    if len(args) < 2:
        from conductor.config import get_config

        cfg = get_config()
        qh = cfg.quiet_hours
        if qh.get("enabled"):
            tz = qh.get("timezone", "UTC")
            await message.answer(
                f"🌙 <b>Quiet Hours</b>\n"
                f"<code>{qh.get('start', '23:00')}</code> – <code>{qh.get('end', '07:00')}</code>  ({tz})",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                "🌙 Quiet hours are disabled.\nUse /quiet HH:MM-HH:MM to configure.",
                parse_mode="HTML",
            )
        return

    await message.answer(
        "🌙 Quiet hours updated. Note: changes require daemon restart to take effect.\n"
        "Edit config.yaml to persist.",
    )


# ── /settings ──


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
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
    await message.answer("\n".join(lines), parse_mode="HTML")
