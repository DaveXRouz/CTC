"""Message formatting — emoji labels, monospace blocks, HTML mode."""

from __future__ import annotations

from datetime import datetime

from conductor.db.models import Session


def session_label(session: Session) -> str:
    """Format a session label: emoji + alias."""
    return f"{session.color_emoji} {session.alias}"


def status_line(session: Session) -> str:
    """Single-line status for a session."""
    status_map = {
        "running": "🟢 Running",
        "paused": "⏸ Paused",
        "waiting": "⏸ WAITING FOR INPUT",
        "error": "🔴 Error",
        "exited": "⚪ Exited",
        "rate_limited": "🟡 Rate Limited",
    }
    return status_map.get(session.status, session.status)


def uptime_str(created_at: str) -> str:
    """Calculate uptime from created_at ISO string."""
    try:
        created = datetime.fromisoformat(created_at)
        delta = datetime.now() - created
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        return f"{hours}h {minutes:02d}m"
    except (ValueError, TypeError):
        return "unknown"


def token_bar(used: int, limit: int) -> str:
    """Format token usage with percentage."""
    if limit <= 0:
        return "N/A"
    pct = min(100, int((used / limit) * 100))
    warn = " ⚠️" if pct >= 80 else ""
    return f"{pct}% ({used} / {limit}){warn}"


def format_session_dashboard(session: Session) -> str:
    """Format a single session block for the status dashboard."""
    lines = [
        f"<b>{session.color_emoji} #{session.number} {session.alias}</b> ({session.type})",
        f"   ├ Status: {status_line(session)}",
        f"   ├ Tokens: {token_bar(session.token_used, session.token_limit)}",
        f"   ├ Uptime: {uptime_str(session.created_at)}",
    ]
    if session.last_summary:
        lines.append(f'   └ Last: "{session.last_summary}"')
    elif session.last_activity:
        lines.append(f"   └ Last activity: {session.last_activity}")
    else:
        lines.append("   └ Last: No activity yet")
    return "\n".join(lines)


def format_status_dashboard(sessions: list[Session]) -> str:
    """Format the full /status dashboard."""
    if not sessions:
        return "📊 <b>Conductor Status</b> — No active sessions\n\nUse /new to start a session."

    header = f"📊 <b>Conductor Status</b> — {len(sessions)} Active Session{'s' if len(sessions) != 1 else ''}\n"
    header += "─" * 35 + "\n\n"

    blocks = [format_session_dashboard(s) for s in sessions]
    return header + "\n\n".join(blocks)


def format_event(emoji: str, session: Session | None, text: str) -> str:
    """Format an event notification message."""
    if session:
        return f"{emoji} {session_label(session)}\n{text}"
    return f"{emoji} {text}"


def mono(text: str) -> str:
    """Wrap text in monospace HTML tags."""
    return f"<code>{text}</code>"


def bold(text: str) -> str:
    return f"<b>{text}</b>"
