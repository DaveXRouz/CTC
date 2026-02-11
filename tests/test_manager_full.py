"""Comprehensive tests for SessionManager — covers create, kill, pause, resume,
send_input, resolve, rename, list, get, and helper functions."""

from __future__ import annotations

import logging
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conductor.db.models import Session
from conductor.sessions.manager import (
    SessionManager,
    guess_alias_from_dir,
    COLOR_PALETTE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    session_id: str = "sid-1",
    number: int = 1,
    alias: str = "TestProject",
    session_type: str = "claude-code",
    working_dir: str = "/tmp/project",
    tmux_session: str = "conductor-1",
    tmux_pane_id: str = "%0",
    pid: int | None = 12345,
    status: str = "running",
    color_emoji: str = "🔵",
) -> Session:
    return Session(
        id=session_id,
        number=number,
        alias=alias,
        type=session_type,
        working_dir=working_dir,
        tmux_session=tmux_session,
        tmux_pane_id=tmux_pane_id,
        pid=pid,
        status=status,
        color_emoji=color_emoji,
    )


def _make_manager_with_session(session: Session | None = None) -> SessionManager:
    """Return a SessionManager with one session pre-loaded."""
    mgr = SessionManager()
    s = session or _make_session()
    mgr._sessions[s.id] = s
    return mgr


def _make_mock_config(
    max_concurrent: int = 5,
    default_dir: str = "/tmp",
    aliases: dict | None = None,
):
    cfg = MagicMock()
    cfg.max_concurrent_sessions = max_concurrent
    cfg.default_dir = default_dir
    cfg.aliases = aliases or {}
    return cfg


def _make_mock_pane(pane_pid: str = "99999", pane_id: str = "%0"):
    pane = MagicMock()
    pane.get = MagicMock(
        side_effect=lambda key: {"pane_pid": pane_pid, "pane_id": pane_id}.get(key)
    )
    pane.send_keys = MagicMock()
    return pane


def _make_mock_tmux_session(pane: MagicMock | None = None):
    pane = pane or _make_mock_pane()
    tmux_session = MagicMock()
    tmux_session.active_window.active_pane = pane
    return tmux_session, pane


# ===========================================================================
# 1. guess_alias_from_dir
# ===========================================================================


class TestGuessAliasFromDir:
    def test_simple_directory(self):
        assert guess_alias_from_dir("/home/user/my-project") == "My-Project"

    def test_underscore_separator(self):
        assert guess_alias_from_dir("/home/user/hello_world") == "Hello-World"

    def test_mixed_separators(self):
        assert guess_alias_from_dir("/var/data/my_cool-app") == "My-Cool-App"

    def test_trailing_slash(self):
        assert guess_alias_from_dir("/home/user/project/") == "Project"

    def test_single_word(self):
        assert guess_alias_from_dir("/tmp/foobar") == "Foobar"

    def test_root_path(self):
        # basename of "/" after rstrip is "", so we get an empty capitalize
        result = guess_alias_from_dir("/")
        assert isinstance(result, str)


# ===========================================================================
# 2. create_session
# ===========================================================================


class TestCreateSession:
    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    @patch("conductor.sessions.manager.get_config")
    @patch("conductor.sessions.manager.uuid.uuid4", return_value="fake-uuid")
    async def test_create_session_happy_path(
        self, mock_uuid, mock_get_config, mock_queries
    ):
        cfg = _make_mock_config()
        mock_get_config.return_value = cfg

        mock_queries.get_next_session_number = AsyncMock(return_value=1)
        mock_queries.create_session = AsyncMock()

        tmux_session, pane = _make_mock_tmux_session()
        mock_server = MagicMock()
        mock_server.new_session.return_value = tmux_session
        mock_server.sessions = []

        mgr = SessionManager()
        mgr._server = mock_server

        session = await mgr.create_session(
            session_type="claude-code",
            working_dir="/tmp",
            alias="MyAlias",
        )

        assert session.id == "fake-uuid"
        assert session.number == 1
        assert session.alias == "MyAlias"
        assert session.type == "claude-code"
        assert session.status == "running"
        assert session.working_dir == "/tmp"
        assert session.tmux_session == "conductor-1"

        mock_server.new_session.assert_called_once_with(
            session_name="conductor-1",
            start_directory="/tmp",
            attach=False,
        )
        pane.send_keys.assert_called_once_with("claude", enter=True)
        mock_queries.create_session.assert_awaited_once()

        # Session stored in manager
        assert "fake-uuid" in mgr._sessions
        assert "fake-uuid" in mgr._panes

    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    @patch("conductor.sessions.manager.get_config")
    @patch("conductor.sessions.manager.uuid.uuid4", return_value="uuid-shell")
    async def test_create_shell_session_does_not_send_claude(
        self, mock_uuid, mock_get_config, mock_queries
    ):
        cfg = _make_mock_config()
        mock_get_config.return_value = cfg

        mock_queries.get_next_session_number = AsyncMock(return_value=2)
        mock_queries.create_session = AsyncMock()

        tmux_session, pane = _make_mock_tmux_session()
        mock_server = MagicMock()
        mock_server.new_session.return_value = tmux_session
        mock_server.sessions = []

        mgr = SessionManager()
        mgr._server = mock_server

        session = await mgr.create_session(
            session_type="shell",
            working_dir="/tmp",
            alias="ShellSession",
        )

        assert session.type == "shell"
        pane.send_keys.assert_not_called()

    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.get_config")
    async def test_create_session_max_limit(self, mock_get_config):
        cfg = _make_mock_config(max_concurrent=2)
        mock_get_config.return_value = cfg

        mgr = SessionManager()
        mgr._sessions["a"] = _make_session(session_id="a")
        mgr._sessions["b"] = _make_session(session_id="b")

        with pytest.raises(RuntimeError, match="Max 2 concurrent sessions reached"):
            await mgr.create_session(working_dir="/tmp")

    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.get_config")
    async def test_create_session_invalid_directory(self, mock_get_config):
        cfg = _make_mock_config()
        mock_get_config.return_value = cfg

        mgr = SessionManager()

        with pytest.raises(ValueError, match="Directory does not exist"):
            await mgr.create_session(working_dir="/nonexistent/dir/does/not/exist")

    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    @patch("conductor.sessions.manager.get_config")
    @patch("conductor.sessions.manager.uuid.uuid4", return_value="uuid-alias")
    async def test_create_session_alias_from_config(
        self, mock_uuid, mock_get_config, mock_queries
    ):
        cfg = _make_mock_config(aliases={"/tmp": "ConfigAlias"})
        mock_get_config.return_value = cfg

        mock_queries.get_next_session_number = AsyncMock(return_value=1)
        mock_queries.create_session = AsyncMock()

        tmux_session, pane = _make_mock_tmux_session()
        mock_server = MagicMock()
        mock_server.new_session.return_value = tmux_session
        mock_server.sessions = []

        mgr = SessionManager()
        mgr._server = mock_server

        session = await mgr.create_session(working_dir="/tmp")
        assert session.alias == "ConfigAlias"

    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    @patch("conductor.sessions.manager.get_config")
    @patch("conductor.sessions.manager.uuid.uuid4", return_value="uuid-guess")
    async def test_create_session_alias_guessed_from_dir(
        self, mock_uuid, mock_get_config, mock_queries
    ):
        cfg = _make_mock_config(aliases={})
        mock_get_config.return_value = cfg

        mock_queries.get_next_session_number = AsyncMock(return_value=1)
        mock_queries.create_session = AsyncMock()

        tmux_session, pane = _make_mock_tmux_session()
        mock_server = MagicMock()
        mock_server.new_session.return_value = tmux_session
        mock_server.sessions = []

        mgr = SessionManager()
        mgr._server = mock_server

        session = await mgr.create_session(working_dir="/tmp")
        assert session.alias == "Tmp"

    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    @patch("conductor.sessions.manager.get_config")
    @patch("conductor.sessions.manager.uuid.uuid4", return_value="uuid-collision")
    async def test_create_session_skips_orphaned_tmux_name(
        self, mock_uuid, mock_get_config, mock_queries
    ):
        cfg = _make_mock_config()
        mock_get_config.return_value = cfg

        mock_queries.get_next_session_number = AsyncMock(return_value=1)
        mock_queries.create_session = AsyncMock()

        tmux_session, pane = _make_mock_tmux_session()
        mock_server = MagicMock()
        mock_server.new_session.return_value = tmux_session

        # Simulate an orphaned tmux session named conductor-1
        orphan = MagicMock()
        orphan.name = "conductor-1"
        mock_server.sessions = [orphan]

        mgr = SessionManager()
        mgr._server = mock_server

        session = await mgr.create_session(working_dir="/tmp", alias="Skip")

        assert session.number == 2
        assert session.tmux_session == "conductor-2"
        mock_server.new_session.assert_called_once_with(
            session_name="conductor-2",
            start_directory="/tmp",
            attach=False,
        )


# ===========================================================================
# 3. kill_session
# ===========================================================================


class TestKillSession:
    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    async def test_kill_session_happy_path(self, mock_queries):
        mock_queries.update_session = AsyncMock()

        mgr = _make_manager_with_session()
        mock_pane = MagicMock()
        mgr._panes["sid-1"] = mock_pane

        mock_tmux_session_list = [MagicMock()]
        mock_server = MagicMock()
        mock_server.sessions.filter.return_value = mock_tmux_session_list
        mgr._server = mock_server

        result = await mgr.kill_session("sid-1")

        assert result is not None
        assert result.status == "exited"
        mock_tmux_session_list[0].kill.assert_called_once()
        mock_queries.update_session.assert_awaited_once_with("sid-1", status="exited")
        assert "sid-1" not in mgr._sessions
        assert "sid-1" not in mgr._panes

    @pytest.mark.asyncio
    async def test_kill_session_not_found(self):
        mgr = SessionManager()
        result = await mgr.kill_session("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    async def test_kill_session_tmux_error_still_marks_exited(self, mock_queries):
        mock_queries.update_session = AsyncMock()

        mgr = _make_manager_with_session()
        mock_server = MagicMock()
        mock_server.sessions.filter.side_effect = Exception("tmux gone")
        mgr._server = mock_server

        result = await mgr.kill_session("sid-1")

        assert result is not None
        assert result.status == "exited"
        assert "sid-1" not in mgr._sessions


# ===========================================================================
# 4. pause_session
# ===========================================================================


class TestPauseSession:
    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    @patch("os.kill")
    async def test_pause_session_happy_path(self, mock_kill, mock_queries):
        mock_queries.update_session = AsyncMock()

        mgr = _make_manager_with_session()
        result = await mgr.pause_session("sid-1")

        assert result is not None
        assert result.status == "paused"
        mock_kill.assert_called_once_with(12345, signal.SIGSTOP)
        mock_queries.update_session.assert_awaited_once_with("sid-1", status="paused")

    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    @patch("os.kill", side_effect=ProcessLookupError)
    async def test_pause_session_process_dead(self, mock_kill, mock_queries):
        mock_queries.update_session = AsyncMock()

        mgr = _make_manager_with_session()
        result = await mgr.pause_session("sid-1")

        assert result is not None
        assert result.status == "exited"
        mock_queries.update_session.assert_awaited_once_with("sid-1", status="exited")

    @pytest.mark.asyncio
    async def test_pause_session_not_found(self):
        mgr = SessionManager()
        result = await mgr.pause_session("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_pause_session_no_pid(self):
        session = _make_session(pid=None)
        mgr = _make_manager_with_session(session)
        result = await mgr.pause_session("sid-1")
        assert result is None


# ===========================================================================
# 5. resume_session
# ===========================================================================


class TestResumeSession:
    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    @patch("os.kill")
    async def test_resume_session_happy_path(self, mock_kill, mock_queries):
        mock_queries.update_session = AsyncMock()

        session = _make_session(status="paused")
        mgr = _make_manager_with_session(session)
        result = await mgr.resume_session("sid-1")

        assert result is not None
        assert result.status == "running"
        mock_kill.assert_called_once_with(12345, signal.SIGCONT)
        mock_queries.update_session.assert_awaited_once_with("sid-1", status="running")

    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    @patch("os.kill", side_effect=ProcessLookupError)
    async def test_resume_session_process_dead(self, mock_kill, mock_queries):
        mock_queries.update_session = AsyncMock()

        session = _make_session(status="paused")
        mgr = _make_manager_with_session(session)
        result = await mgr.resume_session("sid-1")

        assert result is not None
        assert result.status == "exited"
        mock_queries.update_session.assert_awaited_once_with("sid-1", status="exited")

    @pytest.mark.asyncio
    async def test_resume_session_not_found(self):
        mgr = SessionManager()
        result = await mgr.resume_session("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_resume_session_no_pid(self):
        session = _make_session(pid=None)
        mgr = _make_manager_with_session(session)
        result = await mgr.resume_session("sid-1")
        assert result is None


# ===========================================================================
# 6. send_input
# ===========================================================================


class TestSendInput:
    def test_send_input_happy_path(self):
        mgr = SessionManager()
        mock_pane = MagicMock()
        mgr._panes["sid-1"] = mock_pane

        result = mgr.send_input("sid-1", "hello world")

        assert result is True
        mock_pane.send_keys.assert_called_once_with("hello world", enter=True)

    def test_send_input_unknown_session(self):
        mgr = SessionManager()
        result = mgr.send_input("nonexistent", "hello")
        assert result is False

    def test_send_input_logs_char_count_not_text(self, caplog):
        mgr = SessionManager()
        mock_pane = MagicMock()
        mgr._panes["sid-1"] = mock_pane
        secret = "super-secret-api-key-12345"

        with caplog.at_level(logging.DEBUG):
            mgr.send_input("sid-1", secret)

        log_text = caplog.text
        assert secret not in log_text
        assert f"{len(secret)} chars" in log_text

    def test_send_input_logs_session_id(self, caplog):
        mgr = SessionManager()
        mock_pane = MagicMock()
        mgr._panes["my-session-id"] = mock_pane

        with caplog.at_level(logging.DEBUG):
            mgr.send_input("my-session-id", "data")

        assert "my-session-id" in caplog.text


# ===========================================================================
# 7. resolve_session
# ===========================================================================


class TestResolveSession:
    def test_resolve_by_number(self):
        mgr = _make_manager_with_session()
        result = mgr.resolve_session("1")
        assert result is not None
        assert result.number == 1

    def test_resolve_by_alias(self):
        mgr = _make_manager_with_session()
        result = mgr.resolve_session("TestProject")
        assert result is not None
        assert result.alias == "TestProject"

    def test_resolve_by_alias_case_insensitive(self):
        mgr = _make_manager_with_session()
        result = mgr.resolve_session("testproject")
        assert result is not None
        assert result.alias == "TestProject"

    def test_resolve_by_id(self):
        mgr = _make_manager_with_session()
        result = mgr.resolve_session("sid-1")
        assert result is not None
        assert result.id == "sid-1"

    def test_resolve_not_found(self):
        mgr = _make_manager_with_session()
        result = mgr.resolve_session("nonexistent")
        assert result is None

    def test_resolve_number_not_found_falls_through(self):
        """A numeric string that doesn't match any session number should
        still attempt alias and id lookups."""
        mgr = _make_manager_with_session()
        result = mgr.resolve_session("999")
        assert result is None


# ===========================================================================
# 8. rename_session
# ===========================================================================


class TestRenameSession:
    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    async def test_rename_happy_path(self, mock_queries):
        mock_queries.update_session = AsyncMock()

        mgr = _make_manager_with_session()
        result = await mgr.rename_session("sid-1", "NewName")

        assert result is not None
        assert result.alias == "NewName"
        mock_queries.update_session.assert_awaited_once_with("sid-1", alias="NewName")

    @pytest.mark.asyncio
    async def test_rename_empty_alias(self):
        mgr = _make_manager_with_session()
        with pytest.raises(ValueError, match="cannot be empty"):
            await mgr.rename_session("sid-1", "")

    @pytest.mark.asyncio
    async def test_rename_whitespace_alias(self):
        mgr = _make_manager_with_session()
        with pytest.raises(ValueError, match="cannot be empty"):
            await mgr.rename_session("sid-1", "   ")

    @pytest.mark.asyncio
    async def test_rename_alias_too_long(self):
        mgr = _make_manager_with_session()
        with pytest.raises(ValueError, match="too long"):
            await mgr.rename_session("sid-1", "x" * 51)

    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    async def test_rename_max_length_accepted(self, mock_queries):
        mock_queries.update_session = AsyncMock()
        mgr = _make_manager_with_session()
        result = await mgr.rename_session("sid-1", "a" * 50)
        assert result is not None
        assert result.alias == "a" * 50

    @pytest.mark.asyncio
    async def test_rename_not_found(self):
        mgr = SessionManager()
        # Validation passes first, then lookup returns None
        result = await mgr.rename_session("nonexistent", "ValidName")
        assert result is None


# ===========================================================================
# 9. list_sessions
# ===========================================================================


class TestListSessions:
    @pytest.mark.asyncio
    async def test_list_sessions_empty(self):
        mgr = SessionManager()
        result = await mgr.list_sessions()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_sessions_multiple(self):
        mgr = SessionManager()
        s1 = _make_session(session_id="a", number=1)
        s2 = _make_session(session_id="b", number=2)
        mgr._sessions["a"] = s1
        mgr._sessions["b"] = s2

        result = await mgr.list_sessions()
        assert len(result) == 2
        ids = {s.id for s in result}
        assert ids == {"a", "b"}


# ===========================================================================
# 10. get_pane / get_session
# ===========================================================================


class TestGetPaneAndSession:
    def test_get_pane_found(self):
        mgr = SessionManager()
        mock_pane = MagicMock()
        mgr._panes["sid-1"] = mock_pane
        assert mgr.get_pane("sid-1") is mock_pane

    def test_get_pane_not_found(self):
        mgr = SessionManager()
        assert mgr.get_pane("nonexistent") is None

    def test_get_session_found(self):
        mgr = _make_manager_with_session()
        result = mgr.get_session("sid-1")
        assert result is not None
        assert result.id == "sid-1"

    def test_get_session_not_found(self):
        mgr = SessionManager()
        assert mgr.get_session("nonexistent") is None

    def test_get_session_by_number_found(self):
        mgr = _make_manager_with_session()
        result = mgr.get_session_by_number(1)
        assert result is not None
        assert result.number == 1

    def test_get_session_by_number_not_found(self):
        mgr = _make_manager_with_session()
        assert mgr.get_session_by_number(999) is None

    def test_get_session_by_alias_found(self):
        mgr = _make_manager_with_session()
        result = mgr.get_session_by_alias("TestProject")
        assert result is not None

    def test_get_session_by_alias_case_insensitive(self):
        mgr = _make_manager_with_session()
        result = mgr.get_session_by_alias("TESTPROJECT")
        assert result is not None

    def test_get_session_by_alias_not_found(self):
        mgr = _make_manager_with_session()
        assert mgr.get_session_by_alias("NoSuchAlias") is None


# ===========================================================================
# 11. load_from_db
# ===========================================================================


class TestLoadFromDb:
    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    async def test_load_from_db(self, mock_queries):
        s1 = _make_session(session_id="db-1", number=1)
        s2 = _make_session(session_id="db-2", number=2)
        mock_queries.get_all_sessions = AsyncMock(return_value=[s1, s2])

        mgr = SessionManager()
        await mgr.load_from_db()

        assert len(mgr._sessions) == 2
        assert "db-1" in mgr._sessions
        assert "db-2" in mgr._sessions

    @pytest.mark.asyncio
    @patch("conductor.sessions.manager.queries")
    async def test_load_from_db_empty(self, mock_queries):
        mock_queries.get_all_sessions = AsyncMock(return_value=[])

        mgr = SessionManager()
        await mgr.load_from_db()

        assert len(mgr._sessions) == 0


# ===========================================================================
# 12. _next_color
# ===========================================================================


class TestNextColor:
    def test_first_color_when_empty(self):
        mgr = SessionManager()
        assert mgr._next_color() == COLOR_PALETTE[0]

    def test_skips_used_colors(self):
        mgr = SessionManager()
        mgr._sessions["a"] = _make_session(session_id="a", color_emoji=COLOR_PALETTE[0])
        assert mgr._next_color() == COLOR_PALETTE[1]

    def test_wraps_to_first_when_all_used(self):
        mgr = SessionManager()
        for i, color in enumerate(COLOR_PALETTE):
            mgr._sessions[str(i)] = _make_session(session_id=str(i), color_emoji=color)
        assert mgr._next_color() == COLOR_PALETTE[0]


# ===========================================================================
# 13. is_pid_alive
# ===========================================================================


class TestIsPidAlive:
    @patch("os.kill")
    def test_pid_alive(self, mock_kill):
        mock_kill.return_value = None
        mgr = SessionManager()
        assert mgr.is_pid_alive(12345) is True
        mock_kill.assert_called_once_with(12345, 0)

    @patch("os.kill", side_effect=ProcessLookupError)
    def test_pid_dead(self, mock_kill):
        mgr = SessionManager()
        assert mgr.is_pid_alive(12345) is False

    @patch("os.kill", side_effect=PermissionError)
    def test_pid_permission_error(self, mock_kill):
        mgr = SessionManager()
        assert mgr.is_pid_alive(12345) is False


# ===========================================================================
# 14. server property (lazy init)
# ===========================================================================


class TestServerProperty:
    @patch("conductor.sessions.manager.libtmux.Server")
    def test_server_lazy_init(self, mock_server_cls):
        mock_instance = MagicMock()
        mock_server_cls.return_value = mock_instance

        mgr = SessionManager()
        assert mgr._server is None

        server = mgr.server
        assert server is mock_instance
        mock_server_cls.assert_called_once()

    @patch("conductor.sessions.manager.libtmux.Server")
    def test_server_cached(self, mock_server_cls):
        mock_instance = MagicMock()
        mock_server_cls.return_value = mock_instance

        mgr = SessionManager()
        _ = mgr.server
        _ = mgr.server

        # Only one Server() call even after accessing .server twice
        mock_server_cls.assert_called_once()
