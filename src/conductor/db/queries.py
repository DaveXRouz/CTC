"""Async CRUD functions for all database tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import aiosqlite

from conductor.db.database import get_db
from conductor.db.models import AutoRule, Command, Event, Session

# ── Sessions ──


async def create_session(session: Session) -> None:
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
    db = await get_db()
    async with db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)) as cur:
        row = await cur.fetchone()
        if row:
            return _row_to_session(row)
    return None


async def get_session_by_number(number: int) -> Session | None:
    db = await get_db()
    async with db.execute("SELECT * FROM sessions WHERE number = ?", (number,)) as cur:
        row = await cur.fetchone()
        if row:
            return _row_to_session(row)
    return None


async def get_session_by_alias(alias: str) -> Session | None:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM sessions WHERE LOWER(alias) = LOWER(?)", (alias,)
    ) as cur:
        row = await cur.fetchone()
        if row:
            return _row_to_session(row)
    return None


async def get_all_sessions(active_only: bool = False) -> list[Session]:
    db = await get_db()
    if active_only:
        sql = "SELECT * FROM sessions WHERE status NOT IN ('exited') ORDER BY number"
    else:
        sql = "SELECT * FROM sessions ORDER BY number"
    async with db.execute(sql) as cur:
        rows = await cur.fetchall()
        return [_row_to_session(r) for r in rows]


async def update_session(session_id: str, **kwargs: Any) -> None:
    db = await get_db()
    kwargs["updated_at"] = datetime.now().isoformat()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [session_id]
    await db.execute(f"UPDATE sessions SET {sets} WHERE id = ?", vals)
    await db.commit()


async def delete_session(session_id: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    await db.commit()


async def get_next_session_number() -> int:
    db = await get_db()
    async with db.execute("SELECT COALESCE(MAX(number), 0) + 1 FROM sessions") as cur:
        row = await cur.fetchone()
        return row[0] if row else 1


def _row_to_session(row: tuple) -> Session:
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
    db = await get_db()
    await db.execute(
        "INSERT INTO commands (session_id, source, input, context) VALUES (?, ?, ?, ?)",
        (cmd.session_id, cmd.source, cmd.input, cmd.context),
    )
    await db.commit()


async def get_commands(session_id: str, limit: int = 50) -> list[Command]:
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
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO auto_rules (pattern, response, match_type) VALUES (?, ?, ?)",
        (rule.pattern, rule.response, rule.match_type),
    )
    await db.commit()
    return cur.lastrowid or 0


async def delete_rule(rule_id: int) -> bool:
    db = await get_db()
    cur = await db.execute("DELETE FROM auto_rules WHERE id = ?", (rule_id,))
    await db.commit()
    return cur.rowcount > 0


async def increment_rule_hit(rule_id: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE auto_rules SET hit_count = hit_count + 1 WHERE id = ?", (rule_id,)
    )
    await db.commit()


async def set_rules_enabled(enabled: bool) -> None:
    db = await get_db()
    await db.execute("UPDATE auto_rules SET enabled = ?", (int(enabled),))
    await db.commit()


# ── Events ──


async def log_event(event: Event) -> int:
    db = await get_db()
    cur = await db.execute(
        """INSERT INTO events (session_id, event_type, message, telegram_message_id)
           VALUES (?, ?, ?, ?)""",
        (event.session_id, event.event_type, event.message, event.telegram_message_id),
    )
    await db.commit()
    return cur.lastrowid or 0


async def get_events(session_id: str | None = None, limit: int = 50) -> list[Event]:
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
    db = await get_db()
    await db.execute("UPDATE events SET acknowledged = 1 WHERE id = ?", (event_id,))
    await db.commit()


# ── Seed default auto-rules ──


async def seed_default_rules(rules: list[dict]) -> None:
    """Insert default auto-response rules if table is empty."""
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
