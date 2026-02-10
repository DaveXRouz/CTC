"""Data models — dataclasses for all DB entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Session:
    """A monitored tmux session.

    Attributes:
        id: UUID primary key.
        number: Sequential session number for user-facing references.
        alias: Human-readable name (auto-generated or user-set).
        type: Session type — ``'claude-code'``, ``'shell'``, or ``'one-off'``.
        working_dir: Absolute path to the session's working directory.
        tmux_session: tmux session name (e.g. ``'conductor-1'``).
        tmux_pane_id: tmux pane identifier.
        pid: Process ID of the session's main process.
        status: One of ``'running'``, ``'paused'``, ``'waiting'``, ``'error'``,
            ``'exited'``, ``'rate_limited'``.
        color_emoji: Visual identifier from the 6-emoji palette.
        token_used: Estimated messages used in current window.
        token_limit: Message limit for the configured plan tier.
        last_activity: ISO timestamp of last detected activity.
        last_summary: Most recent AI summary of session output.
        created_at: ISO timestamp of session creation.
        updated_at: ISO timestamp of last update.
    """

    id: str
    number: int
    alias: str
    type: str  # 'claude-code', 'shell', 'one-off'
    working_dir: str
    tmux_session: str
    tmux_pane_id: str | None = None
    pid: int | None = None
    status: str = "running"
    color_emoji: str = "🔵"
    token_used: int = 0
    token_limit: int = 45
    last_activity: str | None = None
    last_summary: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Command:
    """A command sent to a session.

    Attributes:
        id: Auto-incremented primary key.
        session_id: UUID of the target session.
        source: Origin — ``'user'``, ``'auto'``, or ``'system'``.
        input: The command text that was sent.
        context: Optional context about why the command was sent.
        timestamp: ISO timestamp of when the command was sent.
    """

    id: int | None = None
    session_id: str | None = None
    source: str = "user"  # 'user', 'auto', 'system'
    input: str = ""
    context: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AutoRule:
    """An auto-response rule for terminal prompt matching.

    Attributes:
        id: Auto-incremented primary key.
        pattern: Text or regex pattern to match against.
        response: Text to send when the pattern matches.
        match_type: Matching strategy — ``'regex'``, ``'contains'``, or ``'exact'``.
        enabled: Whether this rule is active.
        hit_count: Number of times this rule has triggered.
        created_at: ISO timestamp of rule creation.
    """

    id: int | None = None
    pattern: str = ""
    response: str = ""
    match_type: str = "contains"  # 'regex', 'contains', 'exact'
    enabled: bool = True
    hit_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Event:
    """A system event for logging and notification tracking.

    Attributes:
        id: Auto-incremented primary key.
        session_id: UUID of the related session (if any).
        event_type: Category — ``'input_required'``, ``'token_warning'``, ``'error'``,
            ``'completed'``, ``'rate_limit'``, ``'auto_response'``, or ``'system'``.
        message: Human-readable event description.
        acknowledged: Whether the user has seen/acknowledged this event.
        telegram_message_id: ID of the Telegram message sent for this event.
        timestamp: ISO timestamp of the event.
    """

    id: int | None = None
    session_id: str | None = None
    event_type: str = "system"
    message: str = ""
    acknowledged: bool = False
    telegram_message_id: int | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
