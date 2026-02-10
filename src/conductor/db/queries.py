"""Async CRUD functions for all database tables."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


from conductor.db.database import get_db
from conductor.db.models import AutoRule, Command, Event, Session

# ── Sessions ──


async def create_session(session: Session) -> None:
    """Persist a new session to the database.

    Args:
        session: Session dataclass with all fields populated.
    """
    db = await get_db()
    await db.execute(
        """INSERT INTO sessions (id, number, alias, type, working_dir, tmux_session,
           tmux_pane_id, pid, status, color_emoji, token_used, token_limit,
           last_activity, last_summary, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session.id,
            session.number,
            session.alias,
            session.type,
            session.working_dir,
            session.tmux_session,
            session.tmux_pane_id,
            session.pid,
            session.status,
            session.color_emoji,
            session.token_used,
            session.token_limit,
            session.last_activity,
            session.last_summary,
            session.created_at,
            session.updated_at,
        ),
    )
    await db.commit()


async def get_session(session_id: str) -> Session | None:
    """Fetch a session by its UUID.

    Args:
        session_id: UUID string.

    Returns:
        Session dataclass, or None if not found.
    """
    db = await get_db()
    async with db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)) as cur:
        row = await cur.fetchone()
        if row:
            return _row_to_session(row)
    return None


async def get_session_by_number(number: int) -> Session | None:
    """Fetch a session by its numeric identifier.

    Args:
        number: Sequential session number.

    Returns:
        Session dataclass, or None if not found.
    """
    db = await get_db()
    async with db.execute("SELECT * FROM sessions WHERE number = ?", (number,)) as cur:
        row = await cur.fetchone()
        if row:
            return _row_to_session(row)
    return None


async def get_session_by_alias(alias: str) -> Session | None:
    """Fetch a session by alias (case-insensitive).

    Args:
        alias: Session alias to search for.

    Returns:
        Session dataclass, or None if not found.
    """
    db = await get_db()
    async with db.execute(
        "SELECT * FROM sessions WHERE LOWER(alias) = LOWER(?)", (alias,)
    ) as cur:
        row = await cur.fetchone()
        if row:
            return _row_to_session(row)
    return None


async def get_all_sessions(active_only: bool = False) -> list[Session]:
    """Fetch all sessions, optionally filtering to active only.

    Args:
        active_only: If True, excludes sessions with status 'exited'.

    Returns:
        List of Session dataclasses ordered by number.
    """
    db = await get_db()
    if active_only:
        sql = "SELECT * FROM sessions WHERE status NOT IN ('exited') ORDER BY number"
    else:
        sql = "SELECT * FROM sessions ORDER BY number"
    async with db.execute(sql) as cur:
        rows = await cur.fetchall()
        return [_row_to_session(r) for r in rows]


ALLOWED_SESSION_COLUMNS = {
    "alias",
    "status",
    "last_activity",
    "last_summary",
    "token_used",
    "token_limit",
    "updated_at",
}


async def update_session(session_id: str, **kwargs: Any) -> None:
    """Update allowed columns on a session record.

    Args:
        session_id: UUID of the session to update.
        **kwargs: Column-value pairs. Allowed columns: alias, status,
            last_activity, last_summary, token_used, token_limit, updated_at.

    Raises:
        ValueError: If any column name is not in the allowed set.
    """
    invalid = set(kwargs.keys()) - ALLOWED_SESSION_COLUMNS
    if invalid:
        raise ValueError(f"Invalid column(s): {invalid}")
    db = await get_db()
    kwargs["updated_at"] = datetime.now().isoformat()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [session_id]
    await db.execute(f"UPDATE sessions SET {sets} WHERE id = ?", vals)
    await db.commit()


async def delete_session(session_id: str) -> None:
    """Delete a session record from the database.

    Args:
        session_id: UUID of the session to delete.
    """
    db = await get_db()
    await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    await db.commit()


async def get_next_session_number() -> int:
    """Get the next available session number.

    Returns:
        One greater than the current maximum session number, or 1 if no sessions exist.
    """
    db = await get_db()
    async with db.execute("SELECT COALESCE(MAX(number), 0) + 1 FROM sessions") as cur:
        row = await cur.fetchone()
        return row[0] if row else 1


def _row_to_session(row: tuple) -> Session:
    """Convert a raw SQLite row tuple to a Session dataclass.

    Args:
        row: Tuple of column values in schema order.

    Returns:
        Populated Session dataclass.
    """
    return Session(
        id=row[0],
        number=row[1],
        alias=row[2],
        type=row[3],
        working_dir=row[4],
        tmux_session=row[5],
        tmux_pane_id=row[6],
        pid=row[7],
        status=row[8],
        color_emoji=row[9],
        token_used=row[10],
        token_limit=row[11],
        last_activity=row[12],
        last_summary=row[13],
        created_at=row[14],
        updated_at=row[15],
    )


# ── Commands ──


async def log_command(cmd: Command) -> None:
    """Insert a command record into the database.

    Args:
        cmd: Command dataclass with session_id, source, input, and context.
    """
    db = await get_db()
    await db.execute(
        "INSERT INTO commands (session_id, source, input, context) VALUES (?, ?, ?, ?)",
        (cmd.session_id, cmd.source, cmd.input, cmd.context),
    )
    await db.commit()


async def get_commands(session_id: str, limit: int = 50) -> list[Command]:
    """Fetch recent commands for a session.

    Args:
        session_id: UUID of the session.
        limit: Maximum number of commands to return (default 50).

    Returns:
        List of Command dataclasses, newest first.
    """
    db = await get_db()
    async with db.execute(
        "SELECT * FROM commands WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
        (session_id, limit),
    ) as cur:
        rows = await cur.fetchall()
        return [
            Command(
                id=r[0],
                session_id=r[1],
                source=r[2],
                input=r[3],
                context=r[4],
                timestamp=r[5],
            )
            for r in rows
        ]


# ── Auto Rules ──


async def get_all_rules(enabled_only: bool = False) -> list[AutoRule]:
    """Fetch auto-response rules.

    Args:
        enabled_only: If True, only returns enabled rules.

    Returns:
        List of AutoRule dataclasses ordered by ID.
    """
    db = await get_db()
    sql = "SELECT * FROM auto_rules"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY id"
    async with db.execute(sql) as cur:
        rows = await cur.fetchall()
        return [
            AutoRule(
                id=r[0],
                pattern=r[1],
                response=r[2],
                match_type=r[3],
                enabled=bool(r[4]),
                hit_count=r[5],
                created_at=r[6],
            )
            for r in rows
        ]


async def add_rule(rule: AutoRule) -> int:
    """Insert a new auto-response rule.

    Args:
        rule: AutoRule dataclass with pattern, response, and match_type.

    Returns:
        The auto-generated row ID of the new rule.
    """
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO auto_rules (pattern, response, match_type) VALUES (?, ?, ?)",
        (rule.pattern, rule.response, rule.match_type),
    )
    await db.commit()
    return cur.lastrowid or 0


async def delete_rule(rule_id: int) -> bool:
    """Delete an auto-response rule by ID.

    Args:
        rule_id: Primary key of the rule to delete.

    Returns:
        True if a rule was deleted, False if not found.
    """
    db = await get_db()
    cur = await db.execute("DELETE FROM auto_rules WHERE id = ?", (rule_id,))
    await db.commit()
    return cur.rowcount > 0


async def increment_rule_hit(rule_id: int) -> None:
    """Increment the hit count for an auto-response rule.

    Args:
        rule_id: Primary key of the rule.
    """
    db = await get_db()
    await db.execute(
        "UPDATE auto_rules SET hit_count = hit_count + 1 WHERE id = ?", (rule_id,)
    )
    await db.commit()


async def set_rules_enabled(enabled: bool) -> None:
    """Enable or disable all auto-response rules at once.

    Args:
        enabled: True to enable all rules, False to disable.
    """
    db = await get_db()
    await db.execute("UPDATE auto_rules SET enabled = ?", (int(enabled),))
    await db.commit()


# ── Events ──


async def log_event(event: Event) -> int:
    """Insert an event record into the database.

    Args:
        event: Event dataclass with session_id, event_type, message, and
            optional telegram_message_id.

    Returns:
        The auto-generated row ID of the new event.
    """
    db = await get_db()
    cur = await db.execute(
        """INSERT INTO events (session_id, event_type, message, telegram_message_id)
           VALUES (?, ?, ?, ?)""",
        (event.session_id, event.event_type, event.message, event.telegram_message_id),
    )
    await db.commit()
    return cur.lastrowid or 0


async def get_events(session_id: str | None = None, limit: int = 50) -> list[Event]:
    """Fetch recent events, optionally filtered by session.

    Args:
        session_id: If provided, only returns events for this session.
        limit: Maximum number of events to return (default 50).

    Returns:
        List of Event dataclasses, newest first.
    """
    db = await get_db()
    if session_id:
        sql = (
            "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?"
        )
        params: tuple = (session_id, limit)
    else:
        sql = "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?"
        params = (limit,)
    async with db.execute(sql, params) as cur:
        rows = await cur.fetchall()
        return [
            Event(
                id=r[0],
                session_id=r[1],
                event_type=r[2],
                message=r[3],
                acknowledged=bool(r[4]),
                telegram_message_id=r[5],
                timestamp=r[6],
            )
            for r in rows
        ]


async def acknowledge_event(event_id: int) -> None:
    """Mark an event as acknowledged.

    Args:
        event_id: Primary key of the event.
    """
    db = await get_db()
    await db.execute("UPDATE events SET acknowledged = 1 WHERE id = ?", (event_id,))
    await db.commit()


# ── Seed default auto-rules ──


async def seed_default_rules(rules: list[dict]) -> None:
    """Insert default auto-response rules if the table is empty.

    Args:
        rules: List of dicts with 'pattern', 'response', and optional 'match_type' keys.
    """
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM auto_rules") as cur:
        row = await cur.fetchone()
        if row and row[0] > 0:
            return
    for r in rules:
        await db.execute(
            "INSERT INTO auto_rules (pattern, response, match_type) VALUES (?, ?, ?)",
            (r["pattern"], r["response"], r.get("match_type", "contains")),
        )
    await db.commit()


# ── Pruning ──


async def prune_old_records(max_age_days: int = 30) -> int:
    """Delete events and commands older than max_age_days.

    Args:
        max_age_days: Records older than this many days are deleted (default 30).

    Returns:
        Total number of deleted records across both tables.
    """
    db = await get_db()
    cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
    cur = await db.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
    deleted = cur.rowcount
    cur2 = await db.execute("DELETE FROM commands WHERE timestamp < ?", (cutoff,))
    deleted += cur2.rowcount
    await db.commit()
    return deleted
