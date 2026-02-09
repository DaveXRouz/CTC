"""Extended tests for formatter — cover remaining lines."""

from conductor.bot.formatter import (
    uptime_str,
    format_session_dashboard,
    format_event,
    token_bar,
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


class TestUptimeStr:
    def test_valid_datetime(self):
        from datetime import datetime, timedelta

        past = (datetime.now() - timedelta(hours=2, minutes=30)).isoformat()
        result = uptime_str(past)
        assert "2h 30m" in result

    def test_invalid_datetime(self):
        result = uptime_str("not-a-date")
        assert result == "unknown"

    def test_none_datetime(self):
        result = uptime_str(None)
        assert result == "unknown"


class TestFormatSessionDashboard:
    def test_with_last_summary(self):
        s = _make_session(last_summary="Build succeeded")
        result = format_session_dashboard(s)
        assert "Build succeeded" in result

    def test_with_last_activity_no_summary(self):
        s = _make_session(last_summary=None, last_activity="2024-01-01T12:00:00")
        result = format_session_dashboard(s)
        assert "Last activity" in result

    def test_no_activity(self):
        s = _make_session(last_summary=None, last_activity=None)
        result = format_session_dashboard(s)
        assert "No activity yet" in result


class TestFormatEvent:
    def test_with_session(self):
        s = _make_session()
        result = format_event("🔔", s, "Something happened")
        assert "🔵 TestApp" in result
        assert "Something happened" in result

    def test_without_session(self):
        result = format_event("🔔", None, "Global event")
        assert "🔔 Global event" in result


class TestTokenBarEdgeCases:
    def test_zero_limit(self):
        result = token_bar(10, 0)
        assert result == "N/A"

    def test_negative_limit(self):
        result = token_bar(10, -1)
        assert result == "N/A"

    def test_over_100_percent(self):
        result = token_bar(100, 45)
        assert "100%" in result  # Capped at 100
