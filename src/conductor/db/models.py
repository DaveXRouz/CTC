"""Data models — dataclasses for all DB entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Session:
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
    id: int | None = None
    session_id: str | None = None
    source: str = "user"  # 'user', 'auto', 'system'
    input: str = ""
    context: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AutoRule:
    id: int | None = None
    pattern: str = ""
    response: str = ""
    match_type: str = "contains"  # 'regex', 'contains', 'exact'
    enabled: bool = True
    hit_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Event:
    id: int | None = None
    session_id: str | None = None
    event_type: str = "system"
    message: str = ""
    acknowledged: bool = False
    telegram_message_id: int | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
