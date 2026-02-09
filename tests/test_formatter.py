"""Tests for message formatting."""

from conductor.bot.formatter import (
    session_label,
    status_line,
    token_bar,
    format_status_dashboard,
    mono,
    bold,
)
from conductor.db.models import Session


def _make_session(**kwargs) -> Session:
    defaults = dict(
        id="test-id",
        number=1,
        alias="TestApp",
        type="claude-code",
        working_dir="/tmp/test",
        tmux_session="conductor-1",
        color_emoji="🔵",
        status="running",
        token_used=10,
        token_limit=45,
    )
    defaults.update(kwargs)
    return Session(**defaults)


class TestFormatter:
    def test_session_label(self):
        s = _make_session()
        assert session_label(s) == "🔵 TestApp"

    def test_status_line_running(self):
        s = _make_session(status="running")
        assert "Running" in status_line(s)

    def test_status_line_paused(self):
        s = _make_session(status="paused")
        assert "Paused" in status_line(s)

    def test_token_bar(self):
        result = token_bar(36, 45)
        assert "80%" in result
        assert "⚠️" in result

    def test_token_bar_low(self):
        result = token_bar(10, 45)
        assert "⚠️" not in result

    def test_format_empty_dashboard(self):
        result = format_status_dashboard([])
        assert "No active sessions" in result

    def test_format_dashboard_with_sessions(self):
        s = _make_session()
        result = format_status_dashboard([s])
        assert "TestApp" in result
        assert "#1" in result

    def test_mono(self):
        assert mono("test") == "<code>test</code>"

    def test_bold(self):
        assert bold("test") == "<b>test</b>"
