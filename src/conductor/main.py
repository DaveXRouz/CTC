"""Async startup — init config, DB, session manager, bot; run event loop; clean shutdown."""

from __future__ import annotations

import asyncio
import signal
import sys

from conductor.config import get_config, CONDUCTOR_HOME
from conductor.utils.logger import setup_logging, get_logger
from conductor.db.database import init_database, close_database
from conductor.db.queries import seed_default_rules
from conductor.sessions.manager import SessionManager
from conductor.sessions.monitor import OutputMonitor
from conductor.sessions.recovery import recover_sessions
from conductor.bot.bot import create_bot, set_app_data
from conductor.bot.notifier import Notifier
from conductor.bot.formatter import format_event, session_label
from conductor.bot.keyboards import (
    permission_keyboard,
    completion_keyboard,
    rate_limit_keyboard,
    undo_keyboard,
    suggestion_keyboard,
)
from conductor.bot.handlers.commands import set_session_manager
from conductor.ai.brain import AIBrain
from conductor.auto.responder import AutoResponder
from conductor.tokens.estimator import TokenEstimator
from conductor.utils.sleep_handler import SleepHandler
from conductor.db.models import Event
from conductor.db import queries as db_queries


async def run() -> None:
    """Main async entry point."""
    CONDUCTOR_HOME.mkdir(parents=True, exist_ok=True)

    # Load config
    cfg = get_config()
    missing = cfg.validate()
    if missing:
        print(f"❌ Missing required config: {', '.join(missing)}")
        print(f"   Set them in {CONDUCTOR_HOME / '.env'}")
        sys.exit(1)

    # Setup logging
    log_cfg = cfg.logging_config
    logger = setup_logging(
        level=cfg.log_level,
        log_file=log_cfg.get("file", "~/.conductor/conductor.log"),
        max_bytes=log_cfg.get("max_size_mb", 50) * 1024 * 1024,
        backup_count=log_cfg.get("backup_count", 3),
        console=log_cfg.get("console_output", True),
    )
    logger.info("🎛️ Conductor starting up...")

    # Init database
    await init_database()
    logger.info("Database initialized")

    # Seed default auto-response rules
    auto_rules = cfg.auto_responder_config.get("default_rules", [])
    if auto_rules:
        await seed_default_rules(auto_rules)

    # Init session manager
    session_manager = SessionManager()
    await session_manager.load_from_db()
    set_session_manager(session_manager)
    set_app_data("session_manager", session_manager)

    # Create bot
    bot, dp = await create_bot()
    set_app_data("bot", bot)

    # Init notifier
    notifier = Notifier(bot, cfg.telegram_user_id)
    await notifier.start()
    set_app_data("notifier", notifier)

    # Init AI brain
    brain = AIBrain()
    set_app_data("brain", brain)

    # Init auto-responder
    auto_responder = AutoResponder()
    set_app_data("auto_responder", auto_responder)

    # Init token estimator
    token_estimator = TokenEstimator()
    set_app_data("token_estimator", token_estimator)

    # Monitor store
    monitors: dict[str, OutputMonitor] = {}
    set_app_data("monitors", monitors)

    # Event handler for monitors
    async def on_monitor_event(session, result, lines):
        """Handle detected events from monitors."""
        text = "\n".join(lines[-10:])

        if result.type == "permission_prompt":
            msg = format_event(
                "❓", session, f"Waiting for input:\n<code>{text[:500]}</code>"
            )
            msg_id = await notifier.send_immediate(
                msg, reply_markup=permission_keyboard(session.id)
            )
            await db_queries.update_session(session.id, status="waiting")
            session.status = "waiting"
            set_app_data("last_prompt_session", session.id)
            set_app_data("last_prompt_context", text)
            await db_queries.log_event(
                Event(
                    session_id=session.id,
                    event_type="input_required",
                    message=text,
                    telegram_message_id=msg_id,
                )
            )

        elif result.type == "input_prompt":
            # Check auto-responder first
            auto_result = await auto_responder.check_and_respond(text)
            if auto_result.should_respond:
                session_manager.send_input(session.id, auto_result.response)
                undo_id = f"{session.id}:{auto_result.rule_id}"
                msg = format_event(
                    "🤖",
                    session,
                    f"Auto-responded: <code>{auto_result.response or '(enter)'}</code>",
                )
                await notifier.send(
                    msg, reply_markup=undo_keyboard(undo_id), disable_notification=True
                )
                await db_queries.log_event(
                    Event(
                        session_id=session.id,
                        event_type="auto_response",
                        message=f"Auto: {auto_result.response}",
                    )
                )
            else:
                msg = format_event(
                    "❓", session, f"Waiting for input:\n<code>{text[:500]}</code>"
                )
                await notifier.send_immediate(
                    msg, reply_markup=permission_keyboard(session.id)
                )
                await db_queries.update_session(session.id, status="waiting")
                session.status = "waiting"
                set_app_data("last_prompt_session", session.id)

        elif result.type == "rate_limit":
            await session_manager.pause_session(session.id)
            msg = format_event(
                "⚠️",
                session,
                f"Rate Limited\nPaused automatically.\n\n<code>{result.matched_text}</code>",
            )
            await notifier.send_immediate(
                msg, reply_markup=rate_limit_keyboard(session.id)
            )
            await db_queries.log_event(
                Event(
                    session_id=session.id,
                    event_type="rate_limit",
                    message=result.matched_text,
                )
            )

        elif result.type == "error":
            msg = format_event(
                "🔴", session, f"Error detected:\n<code>{text[:500]}</code>"
            )
            await notifier.send_immediate(msg)
            await db_queries.update_session(session.id, status="error")
            session.status = "error"
            await db_queries.log_event(
                Event(session_id=session.id, event_type="error", message=text[:500])
            )

        elif result.type == "completion":
            summary = await brain.summarize("\n".join(lines[-50:]))
            suggestions = await brain.suggest(
                "\n".join(lines[-50:]),
                project_alias=session.alias,
                session_type=session.type,
                working_dir=session.working_dir,
            )
            set_app_data("last_suggestions", {session.id: suggestions})
            await db_queries.update_session(session.id, last_summary=summary)
            session.last_summary = summary

            kb = (
                suggestion_keyboard(suggestions, session.id)
                if suggestions
                else completion_keyboard(session.id)
            )
            msg = format_event("✅", session, f"Task Complete\n{summary}")
            if suggestions:
                labels = ", ".join(s.get("label", "") for s in suggestions)
                msg += f"\n\n💡 Suggested: {labels}"
            await notifier.send(msg, reply_markup=kb, disable_notification=True)
            await db_queries.log_event(
                Event(session_id=session.id, event_type="completed", message=summary)
            )

        # Track token usage on response completion
        token_estimator.on_claude_response(session.id)
        threshold = token_estimator.check_thresholds()
        if threshold:
            usage = token_estimator.get_usage(session.id)
            warn_msg = format_event(
                "⚠️", session, f"Token usage at {usage['percentage']}%"
            )
            await notifier.send(warn_msg, disable_notification=(threshold == "warning"))
            await db_queries.log_event(
                Event(
                    session_id=session.id,
                    event_type="token_warning",
                    message=f"{usage['percentage']}%",
                )
            )

    # Start monitors for existing sessions
    for session in await session_manager.list_sessions():
        pane = session_manager.get_pane(session.id)
        if pane:
            monitor = OutputMonitor(pane, session, on_event=on_monitor_event)
            monitors[session.id] = monitor
            asyncio.create_task(monitor.start())

    # Recover sessions from previous run
    try:
        recovered = await recover_sessions(session_manager, monitors, on_monitor_event)
        if recovered:
            await notifier.send_immediate(
                f"🔄 Conductor restarted. Recovered {len(recovered)} session(s)."
            )
    except Exception as e:
        logger.warning(f"Session recovery failed: {e}")

    existing = await session_manager.list_sessions()
    logger.info(f"Session manager ready ({len(existing)} sessions)")

    # Mac sleep/wake handler
    async def on_mac_wake(sleep_duration: float):
        mins = int(sleep_duration // 60)
        secs = int(sleep_duration % 60)
        logger.info(f"Mac woke up after {mins}m {secs}s sleep")
        # Health check all sessions
        for sid, monitor in monitors.items():
            pane = session_manager.get_pane(sid)
            if pane is None:
                await monitor.stop()
        await notifier.send_immediate(
            f"💤 Mac slept for {mins}m {secs}s — session health check done."
        )

    sleep_handler = SleepHandler(on_wake_callback=on_mac_wake)
    await sleep_handler.start()

    # Setup shutdown handler
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("🚀 Conductor is online! Polling for Telegram messages...")

    try:
        polling_task = asyncio.create_task(dp.start_polling(bot))
        connectivity_task = asyncio.create_task(notifier.connectivity_check())

        await shutdown_event.wait()

        logger.info("Shutting down...")
        await dp.stop_polling()
        polling_task.cancel()
        connectivity_task.cancel()
        await sleep_handler.stop()
        for m in monitors.values():
            await m.stop()
        await notifier.stop()

        try:
            await polling_task
        except asyncio.CancelledError:
            pass

    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await bot.session.close()
        await close_database()
        logger.info("🎛️ Conductor stopped.")
