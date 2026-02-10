"""Message formatting — emoji labels, monospace blocks, HTML mode."""

from __future__ import annotations

import html
from datetime import datetime

from conductor.db.models import Session


def session_label(session: Session) -> str:
    """Format a session label as emoji + alias.

    Args:
        session: Session dataclass.

    Returns:
        String like ``'🔵 MyProject'``.
    """
    return f"{session.color_emoji} {html.escape(session.alias)}"


def status_line(session: Session) -> str:
    """Format a single-line status indicator for a session.

    Args:
        session: Session dataclass.

    Returns:
        Status string like ``'🟢 Running'`` or ``'⏸ Paused'``.
    """
    status_map = {
        "running": "🟢 Running",
        "paused": "⏸ Paused",
        "waiting": "❓ Waiting for Input",
        "error": "🔴 Error",
        "exited": "⚪ Exited",
        "rate_limited": "🟡 Rate Limited",
    }
    return status_map.get(session.status, session.status)


def uptime_str(created_at: str) -> str:
    """Calculate human-readable uptime from an ISO timestamp.

    Args:
        created_at: ISO 8601 timestamp string.

    Returns:
        Uptime string like ``'2h 15m'``, or ``'unknown'`` on parse failure.
    """
    try:
        created = datetime.fromisoformat(created_at)
        delta = datetime.now() - created
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        return f"{hours}h {minutes:02d}m"
    except (ValueError, TypeError):
        return "unknown"


def token_bar(used: int, limit: int) -> str:
    """Format token usage as a percentage with warning indicator.

    Args:
        used: Number of tokens/messages used.
        limit: Maximum allowed tokens/messages.

    Returns:
        String like ``'72% (32 / 45)'`` or ``'90% (40 / 45) ⚠️'``.
    """
    if limit <= 0:
        return "N/A"
    pct = min(100, int((used / limit) * 100))
    warn = " ⚠️" if pct >= 80 else ""
    return f"{pct}% ({used} / {limit}){warn}"


def format_session_dashboard(session: Session) -> str:
    """Format a single session block for the status dashboard.

    Args:
        session: Session dataclass.

    Returns:
        Multi-line HTML string with status, tokens, uptime, and last activity.
    """
    alias = html.escape(session.alias)
    lines = [
        f"<b>{session.color_emoji} #{session.number} {alias}</b> ({session.type})",
        f"   ├ Status: {status_line(session)}",
        f"   ├ Tokens: {token_bar(session.token_used, session.token_limit)}",
        f"   ├ Uptime: {uptime_str(session.created_at)}",
    ]
    if session.last_summary:
        lines.append(f'   └ Last: "{html.escape(session.last_summary)}"')
    elif session.last_activity:
        lines.append(f"   └ Last activity: {session.last_activity}")
    else:
        lines.append("   └ Last: No activity yet")
    return "\n".join(lines)


def format_status_dashboard(sessions: list[Session]) -> str:
    """Format the full /status dashboard for all sessions.

    Args:
        sessions: List of active Session dataclasses.

    Returns:
        HTML string with header and one block per session, or a "no sessions" message.
    """
    if not sessions:
        return "📊 <b>Conductor Status</b> — No active sessions\n\nUse /new to start a session."

    header = f"📊 <b>Conductor Status</b> — {len(sessions)} Active Session{'s' if len(sessions) != 1 else ''}\n"
    header += "─" * 35 + "\n\n"

    blocks = [format_session_dashboard(s) for s in sessions]
    return header + "\n\n".join(blocks)


def format_event(emoji: str, session: Session | None, text: str) -> str:
    """Format an event notification message.

    Args:
        emoji: Leading emoji for the notification.
        session: Related session (or None for global events).
        text: Event description text.

    Returns:
        Formatted notification string.
    """
    if session:
        return f"{emoji} {session_label(session)}\n{text}"
    return f"{emoji} {html.escape(text)}"


def mono(text: str) -> str:
    """Wrap text in ``<code>`` HTML tags for monospace display.

    Args:
        text: Text to wrap.

    Returns:
        HTML string with ``<code>`` tags.
    """
    return f"<code>{html.escape(text)}</code>"


def bold(text: str) -> str:
    """Wrap text in ``<b>`` HTML tags for bold display.

    Args:
        text: Text to wrap.

    Returns:
        HTML string with ``<b>`` tags.
    """
    return f"<b>{text}</b>"
