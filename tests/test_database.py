"""Tests for database init + async CRUD queries."""

import pytest

from conductor.db.database import init_database, close_database, get_db
from conductor.db import database as db_module
from conductor.db.models import Session, Command, AutoRule, Event
from conductor.db import queries


@pytest.fixture
async def db(tmp_path):
    """Create a fresh in-memory database for each test."""
    db_path = str(tmp_path / "test.db")
    # Reset global
    db_module._db = None
    conn = await init_database(db_path)
    yield conn
    await close_database()
    db_module._db = None


def _make_session(number: int = 1, alias: str = "TestApp", **kwargs) -> Session:
    defaults = dict(
        id=f"test-{number}",
        number=number,
        alias=alias,
        type="claude-code",
        working_dir="/tmp/test",
        tmux_session=f"conductor-{number}",
        color_emoji="🔵",
        status="running",
        token_used=0,
        token_limit=45,
    )
    defaults.update(kwargs)
    return Session(**defaults)


class TestDatabaseInit:
    async def test_init_creates_tables(self, db):
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cur:
            rows = await cur.fetchall()
            tables = {r[0] for r in rows}
        assert "sessions" in tables
        assert "commands" in tables
        assert "auto_rules" in tables
        assert "events" in tables

    async def test_wal_mode(self, db):
        async with db.execute("PRAGMA journal_mode") as cur:
            row = await cur.fetchone()
        assert row[0] == "wal"

    async def test_get_db_returns_connection(self, db):
        conn = await get_db()
        assert conn is not None
        assert conn is db

    async def test_close_database(self, tmp_path):
        db_path = str(tmp_path / "close_test.db")
        db_module._db = None
        await init_database(db_path)
        assert db_module._db is not None
        await close_database()
        assert db_module._db is None


class TestSessionCRUD:
    async def test_create_and_get_session(self, db):
        s = _make_session()
        await queries.create_session(s)
        result = await queries.get_session("test-1")
        assert result is not None
        assert result.alias == "TestApp"
        assert result.number == 1

    async def test_get_session_not_found(self, db):
        result = await queries.get_session("nonexistent")
        assert result is None

    async def test_get_session_by_number(self, db):
        s = _make_session(number=3)
        await queries.create_session(s)
        result = await queries.get_session_by_number(3)
        assert result is not None
        assert result.id == "test-3"

    async def test_get_session_by_alias(self, db):
        s = _make_session(alias="MyProject")
        await queries.create_session(s)
        # Case-insensitive lookup
        result = await queries.get_session_by_alias("myproject")
        assert result is not None
        assert result.alias == "MyProject"

    async def test_get_all_sessions(self, db):
        await queries.create_session(_make_session(1, "App1"))
        await queries.create_session(_make_session(2, "App2"))
        result = await queries.get_all_sessions()
        assert len(result) == 2

    async def test_get_all_sessions_active_only(self, db):
        await queries.create_session(_make_session(1, "App1", status="running"))
        await queries.create_session(_make_session(2, "App2", status="exited"))
        result = await queries.get_all_sessions(active_only=True)
        assert len(result) == 1
        assert result[0].alias == "App1"

    async def test_update_session(self, db):
        s = _make_session()
        await queries.create_session(s)
        await queries.update_session("test-1", status="paused", token_used=10)
        updated = await queries.get_session("test-1")
        assert updated.status == "paused"
        assert updated.token_used == 10

    async def test_update_session_rejects_invalid_columns(self, db):
        s = _make_session()
        await queries.create_session(s)
        with pytest.raises(ValueError, match="Invalid column"):
            await queries.update_session("test-1", status="paused", evil_col="pwned")

    async def test_update_session_rejects_sql_injection_column(self, db):
        s = _make_session()
        await queries.create_session(s)
        with pytest.raises(ValueError, match="Invalid column"):
            await queries.update_session(
                "test-1", **{"1=1; DROP TABLE sessions--": "x"}
            )

    async def test_delete_session(self, db):
        s = _make_session()
        await queries.create_session(s)
        await queries.delete_session("test-1")
        result = await queries.get_session("test-1")
        assert result is None

    async def test_get_next_session_number(self, db):
        num = await queries.get_next_session_number()
        assert num == 1
        await queries.create_session(_make_session(1))
        num = await queries.get_next_session_number()
        assert num == 2


class TestCommandsCRUD:
    async def test_log_and_get_commands(self, db):
        s = _make_session()
        await queries.create_session(s)
        cmd = Command(session_id="test-1", source="user", input="ls -la")
        await queries.log_command(cmd)
        results = await queries.get_commands("test-1")
        assert len(results) == 1
        assert results[0].input == "ls -la"

    async def test_commands_limit(self, db):
        s = _make_session()
        await queries.create_session(s)
        for i in range(5):
            await queries.log_command(
                Command(session_id="test-1", source="user", input=f"cmd-{i}")
            )
        results = await queries.get_commands("test-1", limit=3)
        assert len(results) == 3


class TestAutoRulesCRUD:
    async def test_add_and_get_rules(self, db):
        rule = AutoRule(pattern="(y/N)", response="n", match_type="contains")
        rule_id = await queries.add_rule(rule)
        assert rule_id > 0
        rules = await queries.get_all_rules()
        assert len(rules) == 1
        assert rules[0].pattern == "(y/N)"

    async def test_get_enabled_only(self, db):
        await queries.add_rule(AutoRule(pattern="a", response="b"))
        await queries.add_rule(AutoRule(pattern="c", response="d"))
        await queries.set_rules_enabled(False)
        enabled = await queries.get_all_rules(enabled_only=True)
        assert len(enabled) == 0
        all_rules = await queries.get_all_rules()
        assert len(all_rules) == 2

    async def test_delete_rule(self, db):
        rule_id = await queries.add_rule(AutoRule(pattern="x", response="y"))
        result = await queries.delete_rule(rule_id)
        assert result is True
        # Delete non-existent
        result2 = await queries.delete_rule(9999)
        assert result2 is False

    async def test_increment_hit(self, db):
        rule_id = await queries.add_rule(AutoRule(pattern="p", response="r"))
        await queries.increment_rule_hit(rule_id)
        await queries.increment_rule_hit(rule_id)
        rules = await queries.get_all_rules()
        assert rules[0].hit_count == 2

    async def test_seed_default_rules(self, db):
        defaults = [
            {"pattern": "(Y/n)", "response": "y"},
            {"pattern": "(y/N)", "response": "n"},
        ]
        await queries.seed_default_rules(defaults)
        rules = await queries.get_all_rules()
        assert len(rules) == 2
        # Seeding again should not duplicate
        await queries.seed_default_rules(defaults)
        rules2 = await queries.get_all_rules()
        assert len(rules2) == 2

    async def test_set_rules_enabled(self, db):
        await queries.add_rule(AutoRule(pattern="a", response="b"))
        await queries.set_rules_enabled(False)
        enabled = await queries.get_all_rules(enabled_only=True)
        assert len(enabled) == 0
        await queries.set_rules_enabled(True)
        enabled2 = await queries.get_all_rules(enabled_only=True)
        assert len(enabled2) == 1


class TestPruning:
    async def test_prune_old_records(self, db):
        """Old events and commands are pruned; recent ones are kept."""
        s = _make_session()
        await queries.create_session(s)

        # Insert an old event (45 days ago)
        old_ts = (
            __import__("datetime").datetime.now()
            - __import__("datetime").timedelta(days=45)
        ).isoformat()
        await db.execute(
            "INSERT INTO events (session_id, event_type, message, timestamp) VALUES (?, ?, ?, ?)",
            ("test-1", "system", "old msg", old_ts),
        )
        # Insert a recent event
        await queries.log_event(
            Event(session_id="test-1", event_type="system", message="new msg")
        )
        # Insert an old command
        await db.execute(
            "INSERT INTO commands (session_id, source, input, timestamp) VALUES (?, ?, ?, ?)",
            ("test-1", "user", "old cmd", old_ts),
        )
        # Insert a recent command
        await queries.log_command(
            Command(session_id="test-1", source="user", input="new cmd")
        )
        await db.commit()

        deleted = await queries.prune_old_records(max_age_days=30)
        assert deleted == 2  # 1 old event + 1 old command

        events = await queries.get_events("test-1")
        assert len(events) == 1
        assert events[0].message == "new msg"

        cmds = await queries.get_commands("test-1")
        assert len(cmds) == 1
        assert cmds[0].input == "new cmd"

    async def test_prune_nothing_to_prune(self, db):
        """Pruning with no old records returns 0."""
        deleted = await queries.prune_old_records(max_age_days=30)
        assert deleted == 0


class TestEventsCRUD:
    async def test_log_and_get_events(self, db):
        s = _make_session()
        await queries.create_session(s)
        event = Event(
            session_id="test-1",
            event_type="input_required",
            message="Permission prompt detected",
        )
        event_id = await queries.log_event(event)
        assert event_id > 0
        events = await queries.get_events("test-1")
        assert len(events) == 1
        assert events[0].event_type == "input_required"

    async def test_get_events_all(self, db):
        s = _make_session()
        await queries.create_session(s)
        await queries.log_event(
            Event(session_id="test-1", event_type="error", message="Err")
        )
        events = await queries.get_events()
        assert len(events) == 1

    async def test_acknowledge_event(self, db):
        s = _make_session()
        await queries.create_session(s)
        eid = await queries.log_event(
            Event(session_id="test-1", event_type="system", message="test")
        )
        await queries.acknowledge_event(eid)
        events = await queries.get_events("test-1")
        assert events[0].acknowledged is True
