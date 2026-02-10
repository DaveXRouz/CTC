"""SQLite database — async init, WAL mode, schema creation."""

from __future__ import annotations

import asyncio

import aiosqlite

from conductor.config import DB_PATH
from conductor.utils.logger import get_logger

logger = get_logger("conductor.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    number INTEGER NOT NULL,
    alias TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('claude-code', 'shell', 'one-off')),
    working_dir TEXT NOT NULL,
    tmux_session TEXT NOT NULL,
    tmux_pane_id TEXT,
    pid INTEGER,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK(status IN ('running', 'paused', 'waiting', 'error', 'exited', 'rate_limited')),
    color_emoji TEXT NOT NULL DEFAULT '🔵',
    token_used INTEGER DEFAULT 0,
    token_limit INTEGER DEFAULT 45,
    last_activity TEXT,
    last_summary TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK(source IN ('user', 'auto', 'system')),
    input TEXT NOT NULL,
    context TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS auto_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL,
    response TEXT NOT NULL,
    match_type TEXT NOT NULL DEFAULT 'contains'
        CHECK(match_type IN ('regex', 'contains', 'exact')),
    enabled INTEGER NOT NULL DEFAULT 1,
    hit_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL
        CHECK(event_type IN ('input_required', 'token_warning', 'error', 'completed',
                             'rate_limit', 'auto_response', 'system')),
    message TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    telegram_message_id INTEGER,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_commands_session ON commands(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type, acknowledged);
"""

_db: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()


async def init_database(db_path: str | None = None) -> aiosqlite.Connection:
    """Initialize SQLite with WAL mode and create tables.

    Args:
        db_path: Override path for the database file. Defaults to
            ``~/.conductor/conductor.db``.

    Returns:
        The opened ``aiosqlite.Connection`` with WAL mode enabled.
    """
    global _db
    path = db_path or str(DB_PATH)
    logger.info(f"Initializing database at {path}")

    db = await aiosqlite.connect(path)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.executescript(SCHEMA)
    await db.commit()

    _db = db
    logger.info("Database initialized successfully")
    return db


async def get_db() -> aiosqlite.Connection:
    """Get the database connection, initializing if needed.

    Returns:
        The shared ``aiosqlite.Connection`` singleton.
    """
    global _db
    if _db is not None:
        return _db
    async with _db_lock:
        if _db is None:
            _db = await init_database()
        return _db


async def close_database() -> None:
    """Close the database connection and reset the singleton."""
    global _db
    if _db:
        await _db.close()
        _db = None
        logger.info("Database closed")
