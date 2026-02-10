"""Session recovery — scan for existing conductor tmux sessions after daemon restart."""

from __future__ import annotations

import asyncio
import os
import uuid

import libtmux

from conductor.db.models import Session
from conductor.db import queries
from conductor.sessions.manager import (
    SessionManager,
    guess_alias_from_dir,
    COLOR_PALETTE,
)
from conductor.utils.logger import get_logger

logger = get_logger("conductor.sessions.recovery")


async def recover_sessions(
    session_manager: SessionManager,
    monitors: dict,
    on_event=None,
) -> list[Session]:
    """Scan for existing conductor-* tmux sessions and re-attach monitors.

    Finds tmux sessions matching the ``conductor-*`` naming pattern that
    aren't already tracked, creates DB records for them, and starts monitors.

    Args:
        session_manager: The active SessionManager instance.
        monitors: Dict of session_id -> OutputMonitor to populate.
        on_event: Async callback for monitor events.

    Returns:
        List of recovered Session dataclasses.
    """
    try:
        server = session_manager.server
    except Exception:
        logger.warning("tmux server not running, nothing to recover")
        return []

    recovered = []
    existing_numbers = {s.number for s in (await session_manager.list_sessions())}

    for tmux_session in server.sessions:
        if not tmux_session.name.startswith("conductor-"):
            continue

        try:
            number = int(tmux_session.name.split("-")[1])
        except (IndexError, ValueError):
            continue

        # Skip if we already have this session
        if number in existing_numbers:
            continue

        pane = tmux_session.attached_window.attached_pane
        pid_str = pane.get("pane_pid")
        pid = int(pid_str) if pid_str else None

        # Check if process is alive
        if pid and not _is_pid_alive(pid):
            logger.info(f"Session conductor-{number} process dead, marking as exited")
            continue

        # Get working directory
        pane_path = pane.get("pane_current_path") or "~"
        alias = guess_alias_from_dir(pane_path)

        # Determine available color
        used_colors = {s.color_emoji for s in (await session_manager.list_sessions())}
        color = "🔵"
        for c in COLOR_PALETTE:
            if c not in used_colors:
                color = c
                break

        session = Session(
            id=str(uuid.uuid4()),
            number=number,
            alias=alias,
            type="claude-code",  # Assume claude-code for recovered sessions
            working_dir=pane_path,
            tmux_session=tmux_session.name,
            tmux_pane_id=pane.get("pane_id"),
            pid=pid,
            status="running",
            color_emoji=color,
        )

        await queries.create_session(session)
        session_manager._sessions[session.id] = session
        session_manager._panes[session.id] = pane

        # Start monitor
        if on_event:
            from conductor.sessions.monitor import OutputMonitor

            monitor = OutputMonitor(pane, session, on_event=on_event)
            monitors[session.id] = monitor
            task = asyncio.create_task(monitor.start())
            # Store ref in monitors dict to prevent GC and silent exception loss
            if hasattr(monitors, "__setitem__"):
                from conductor.bot.bot import get_app_data

                track_task = get_app_data().get("track_task")
                if track_task:
                    track_task(task)

        recovered.append(session)
        logger.info(f"Recovered session {color} #{number} '{alias}'")

    return recovered


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
