"""Tests for data models."""

from conductor.db.models import Session, Command, AutoRule, Event


class TestModels:
    def test_session_defaults(self):
        s = Session(
            id="s1",
            number=1,
            alias="App",
            type="claude-code",
            working_dir="/tmp",
            tmux_session="conductor-1",
        )
        assert s.status == "running"
        assert s.color_emoji == "🔵"
        assert s.token_used == 0
        assert s.token_limit == 45
        assert s.tmux_pane_id is None
        assert s.pid is None
        assert s.last_activity is None
        assert s.last_summary is None
        assert s.created_at is not None
        assert s.updated_at is not None

    def test_command_defaults(self):
        c = Command()
        assert c.id is None
        assert c.source == "user"
        assert c.input == ""
        assert c.context is None
        assert c.timestamp is not None

    def test_autorule_defaults(self):
        r = AutoRule()
        assert r.id is None
        assert r.match_type == "contains"
        assert r.enabled is True
        assert r.hit_count == 0

    def test_event_defaults(self):
        e = Event()
        assert e.event_type == "system"
        assert e.acknowledged is False
        assert e.telegram_message_id is None

    def test_session_all_fields(self):
        s = Session(
            id="x",
            number=5,
            alias="Full",
            type="shell",
            working_dir="/home",
            tmux_session="t-5",
            tmux_pane_id="%1",
            pid=1234,
            status="paused",
            color_emoji="🟣",
            token_used=20,
            token_limit=100,
            last_activity="now",
            last_summary="done",
        )
        assert s.pid == 1234
        assert s.tmux_pane_id == "%1"
        assert s.status == "paused"
