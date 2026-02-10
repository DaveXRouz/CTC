"""Tests for command handlers — covers all /slash commands in commands.py."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from conductor.db.models import Session, AutoRule
from conductor.bot.handlers.commands import (
    set_session_manager,
    _mgr,
    cmd_start,
    cmd_help,
    cmd_status,
    cmd_new,
    cmd_kill,
    cmd_pause,
    cmd_resume,
    cmd_input,
    cmd_output,
    cmd_log,
    cmd_rename,
    cmd_run,
    cmd_auto,
    cmd_restart,
)

# ── Helpers ──


def _make_session(
    id: str = "sess-1",
    number: int = 1,
    alias: str = "MyApp",
    stype: str = "claude-code",
    working_dir: str = "/home/user/myapp",
    tmux_session: str = "conductor-1",
    status: str = "running",
    color_emoji: str = "🔵",
    token_used: int = 10,
    token_limit: int = 45,
) -> Session:
    return Session(
        id=id,
        number=number,
        alias=alias,
        type=stype,
        working_dir=working_dir,
        tmux_session=tmux_session,
        status=status,
        color_emoji=color_emoji,
        token_used=token_used,
        token_limit=token_limit,
    )


def _make_message(text: str = "", user_id: int = 12345) -> MagicMock:
    """Build a mock aiogram Message with AsyncMock answer methods."""
    msg = MagicMock()
    msg.text = text
    msg.answer = AsyncMock()
    msg.answer_document = AsyncMock()
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    return msg


def _make_manager(**overrides) -> MagicMock:
    """Build a mock SessionManager with sensible defaults."""
    mgr = MagicMock()
    mgr.list_sessions = AsyncMock(return_value=[])
    mgr.create_session = AsyncMock(return_value=_make_session())
    mgr.kill_session = AsyncMock(return_value=_make_session(status="exited"))
    mgr.pause_session = AsyncMock(return_value=_make_session(status="paused"))
    mgr.resume_session = AsyncMock(return_value=_make_session(status="running"))
    mgr.rename_session = AsyncMock(return_value=_make_session())
    mgr.resolve_session = MagicMock(return_value=None)
    mgr.send_input = MagicMock(return_value=True)
    mgr.get_session = MagicMock(return_value=None)
    for k, v in overrides.items():
        setattr(mgr, k, v)
    return mgr


@pytest.fixture(autouse=True)
def _reset_session_manager():
    """Ensure module-level _session_manager is reset after every test."""
    yield
    set_session_manager(None)


# ── 1. _mgr() raises RuntimeError when not initialized (C12 fix) ──


class TestMgrGuard:
    def test_mgr_raises_when_not_initialized(self):
        set_session_manager(None)
        with pytest.raises(RuntimeError, match="Session manager not initialized"):
            _mgr()

    def test_mgr_returns_manager_when_set(self):
        mgr = _make_manager()
        set_session_manager(mgr)
        assert _mgr() is mgr


# ── 2. /start and /help ──


class TestStartHelp:
    async def test_cmd_start_sends_welcome(self):
        msg = _make_message("/start")
        await cmd_start(msg)
        msg.answer.assert_awaited_once()
        text = msg.answer.call_args[0][0]
        assert "Conductor" in text
        assert "/status" in text

    async def test_cmd_help_sends_reference(self):
        msg = _make_message("/help")
        await cmd_help(msg)
        msg.answer.assert_awaited_once()
        text = msg.answer.call_args[0][0]
        assert "Command Reference" in text
        assert "/new" in text


# ── 3. /status — no sessions, single session detail, multiple sessions ──


class TestCmdStatus:
    async def test_status_no_sessions(self):
        mgr = _make_manager()
        set_session_manager(mgr)
        msg = _make_message("/status")
        await cmd_status(msg)
        msg.answer.assert_awaited_once()
        text = msg.answer.call_args[0][0]
        assert "No active sessions" in text

    async def test_status_with_sessions(self):
        s1 = _make_session(id="s1", number=1, alias="App1")
        s2 = _make_session(id="s2", number=2, alias="App2", color_emoji="🟣")
        mgr = _make_manager()
        mgr.list_sessions = AsyncMock(return_value=[s1, s2])
        set_session_manager(mgr)
        msg = _make_message("/status")
        await cmd_status(msg)
        msg.answer.assert_awaited_once()
        text = msg.answer.call_args[0][0]
        assert "2 Active Sessions" in text
        assert "App1" in text
        assert "App2" in text

    async def test_status_single_session_detail(self):
        s1 = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=s1)
        set_session_manager(mgr)
        msg = _make_message("/status 1")
        await cmd_status(msg)
        msg.answer.assert_awaited_once()
        text = msg.answer.call_args[0][0]
        assert "MyApp" in text
        mgr.resolve_session.assert_called_once_with("1")

    async def test_status_session_not_found(self):
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=None)
        set_session_manager(mgr)
        msg = _make_message("/status bogus")
        await cmd_status(msg)
        msg.answer.assert_awaited_once()
        text = msg.answer.call_args[0][0]
        assert "Session not found" in text


# ── 4. /new — missing args, success, exception ──


class TestCmdNew:
    async def test_new_missing_args(self):
        mgr = _make_manager()
        set_session_manager(mgr)
        msg = _make_message("/new")
        await cmd_new(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    async def test_new_missing_directory(self):
        mgr = _make_manager()
        set_session_manager(mgr)
        msg = _make_message("/new cc")
        await cmd_new(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    async def test_new_success(self):
        session = _make_session()
        mgr = _make_manager()
        mgr.create_session = AsyncMock(return_value=session)
        set_session_manager(mgr)
        msg = _make_message("/new cc ~/projects/myapp")
        await cmd_new(msg)
        mgr.create_session.assert_awaited_once_with(
            session_type="claude-code", working_dir="~/projects/myapp"
        )
        text = msg.answer.call_args[0][0]
        assert "Created" in text

    async def test_new_shell_type(self):
        session = _make_session(stype="shell")
        mgr = _make_manager()
        mgr.create_session = AsyncMock(return_value=session)
        set_session_manager(mgr)
        msg = _make_message("/new sh ~/projects/myapp")
        await cmd_new(msg)
        mgr.create_session.assert_awaited_once_with(
            session_type="shell", working_dir="~/projects/myapp"
        )

    async def test_new_invalid_dir_exception(self):
        mgr = _make_manager()
        mgr.create_session = AsyncMock(
            side_effect=ValueError("Directory does not exist: /nonexistent")
        )
        set_session_manager(mgr)
        msg = _make_message("/new cc /nonexistent")
        await cmd_new(msg)
        text = msg.answer.call_args[0][0]
        assert "Failed to create session" in text


# ── 5. /kill — confirmation flow ──


class TestCmdKill:
    async def test_kill_missing_args(self):
        mgr = _make_manager()
        set_session_manager(mgr)
        msg = _make_message("/kill")
        await cmd_kill(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    async def test_kill_session_not_found(self):
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=None)
        set_session_manager(mgr)
        msg = _make_message("/kill bogus")
        await cmd_kill(msg)
        text = msg.answer.call_args[0][0]
        assert "Session not found" in text

    @patch("conductor.bot.handlers.commands.confirmation_mgr")
    async def test_kill_requests_confirmation(self, mock_confirm_mgr):
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        set_session_manager(mgr)
        msg = _make_message("/kill 1")
        await cmd_kill(msg)
        mock_confirm_mgr.request.assert_called_once_with(
            msg.from_user.id, "kill", session.id
        )
        text = msg.answer.call_args[0][0]
        assert "Confirm" in text
        assert "Kill" in text
        # Verify reply_markup was passed (confirm keyboard)
        assert msg.answer.call_args[1].get("reply_markup") is not None


# ── 6. /pause and /resume — happy path, not found ──


class TestCmdPause:
    async def test_pause_missing_args(self):
        mgr = _make_manager()
        set_session_manager(mgr)
        msg = _make_message("/pause")
        await cmd_pause(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    async def test_pause_session_not_found(self):
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=None)
        set_session_manager(mgr)
        msg = _make_message("/pause bogus")
        await cmd_pause(msg)
        text = msg.answer.call_args[0][0]
        assert "Session not found" in text

    async def test_pause_success(self):
        session = _make_session()
        paused = _make_session(status="paused")
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.pause_session = AsyncMock(return_value=paused)
        set_session_manager(mgr)
        msg = _make_message("/pause 1")
        await cmd_pause(msg)
        mgr.pause_session.assert_awaited_once_with(session.id)
        text = msg.answer.call_args[0][0]
        assert "Paused" in text

    async def test_pause_returns_none(self):
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.pause_session = AsyncMock(return_value=None)
        set_session_manager(mgr)
        msg = _make_message("/pause 1")
        await cmd_pause(msg)
        text = msg.answer.call_args[0][0]
        assert "Could not pause" in text


class TestCmdResume:
    async def test_resume_missing_args(self):
        mgr = _make_manager()
        set_session_manager(mgr)
        msg = _make_message("/resume")
        await cmd_resume(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    async def test_resume_session_not_found(self):
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=None)
        set_session_manager(mgr)
        msg = _make_message("/resume bogus")
        await cmd_resume(msg)
        text = msg.answer.call_args[0][0]
        assert "Session not found" in text

    async def test_resume_success(self):
        session = _make_session(status="paused")
        resumed = _make_session(status="running")
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.resume_session = AsyncMock(return_value=resumed)
        set_session_manager(mgr)
        msg = _make_message("/resume 1")
        await cmd_resume(msg)
        mgr.resume_session.assert_awaited_once_with(session.id)
        text = msg.answer.call_args[0][0]
        assert "Resumed" in text

    async def test_resume_returns_none(self):
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.resume_session = AsyncMock(return_value=None)
        set_session_manager(mgr)
        msg = _make_message("/resume 1")
        await cmd_resume(msg)
        text = msg.answer.call_args[0][0]
        assert "Could not resume" in text


# ── 7. /input — missing args, success ──


class TestCmdInput:
    async def test_input_missing_args(self):
        mgr = _make_manager()
        set_session_manager(mgr)
        msg = _make_message("/input")
        await cmd_input(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    async def test_input_missing_text(self):
        mgr = _make_manager()
        set_session_manager(mgr)
        msg = _make_message("/input 1")
        await cmd_input(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    async def test_input_session_not_found(self):
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=None)
        set_session_manager(mgr)
        msg = _make_message("/input bogus hello")
        await cmd_input(msg)
        text = msg.answer.call_args[0][0]
        assert "Session not found" in text

    async def test_input_success(self):
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.send_input = MagicMock(return_value=True)
        set_session_manager(mgr)
        msg = _make_message("/input 1 hello world")
        await cmd_input(msg)
        mgr.send_input.assert_called_once_with(session.id, "hello world")
        text = msg.answer.call_args[0][0]
        assert "Sent to" in text
        assert "hello world" in text

    async def test_input_send_fails(self):
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.send_input = MagicMock(return_value=False)
        set_session_manager(mgr)
        msg = _make_message("/input 1 hello")
        await cmd_input(msg)
        text = msg.answer.call_args[0][0]
        assert "Could not send input" in text


# ── 8. /output — redaction applied (C13 fix) ──


class TestCmdOutput:
    async def test_output_no_monitor(self):
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.list_sessions = AsyncMock(return_value=[session])
        set_session_manager(mgr)
        with patch(
            "conductor.bot.handlers.commands.get_app_data",
            return_value={"monitors": {}},
            create=True,
        ):
            # Need to mock the import inside the function
            with patch.dict("sys.modules", {"conductor.bot.bot": MagicMock()}):
                import sys

                mock_bot_module = MagicMock()
                mock_bot_module.get_app_data = MagicMock(return_value={"monitors": {}})
                sys.modules["conductor.bot.bot"] = mock_bot_module
                try:
                    msg = _make_message("/output 1")
                    await cmd_output(msg)
                    text = msg.answer.call_args[0][0]
                    assert "No monitor active" in text
                finally:
                    sys.modules.pop("conductor.bot.bot", None)

    async def test_output_with_buffer_applies_redaction(self):
        """C13 fix: output must pass through redact_sensitive before display."""
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.list_sessions = AsyncMock(return_value=[session])
        set_session_manager(mgr)

        mock_buffer = MagicMock()
        mock_buffer.rolling_buffer = [
            "Normal line",
            "API key: sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXX",
        ]
        mock_monitor = MagicMock()
        mock_monitor.output_buffer = mock_buffer

        import sys

        mock_bot_module = MagicMock()
        mock_bot_module.get_app_data = MagicMock(
            return_value={"monitors": {session.id: mock_monitor}}
        )
        sys.modules["conductor.bot.bot"] = mock_bot_module
        try:
            msg = _make_message("/output 1")
            await cmd_output(msg)
            text = msg.answer.call_args[0][0]
            # The Anthropic key should be redacted
            assert "sk-ant-api03" not in text
            assert "REDACTED" in text
            assert "Last 30 lines" in text
        finally:
            sys.modules.pop("conductor.bot.bot", None)

    async def test_output_empty_buffer(self):
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.list_sessions = AsyncMock(return_value=[session])
        set_session_manager(mgr)

        mock_buffer = MagicMock()
        mock_buffer.rolling_buffer = []
        mock_monitor = MagicMock()
        mock_monitor.output_buffer = mock_buffer

        import sys

        mock_bot_module = MagicMock()
        mock_bot_module.get_app_data = MagicMock(
            return_value={"monitors": {session.id: mock_monitor}}
        )
        sys.modules["conductor.bot.bot"] = mock_bot_module
        try:
            msg = _make_message("/output 1")
            await cmd_output(msg)
            text = msg.answer.call_args[0][0]
            assert "No output captured" in text
        finally:
            sys.modules.pop("conductor.bot.bot", None)

    async def test_output_usage_when_multiple_sessions_no_arg(self):
        s1 = _make_session(id="s1")
        s2 = _make_session(id="s2", number=2, alias="App2")
        mgr = _make_manager()
        mgr.list_sessions = AsyncMock(return_value=[s1, s2])
        set_session_manager(mgr)
        msg = _make_message("/output")
        await cmd_output(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    async def test_output_single_session_auto_selects(self):
        session = _make_session()
        mgr = _make_manager()
        mgr.list_sessions = AsyncMock(return_value=[session])
        set_session_manager(mgr)

        import sys

        mock_bot_module = MagicMock()
        mock_bot_module.get_app_data = MagicMock(return_value={"monitors": {}})
        sys.modules["conductor.bot.bot"] = mock_bot_module
        try:
            msg = _make_message("/output")
            await cmd_output(msg)
            text = msg.answer.call_args[0][0]
            assert "No monitor active" in text
            assert "MyApp" in text
        finally:
            sys.modules.pop("conductor.bot.bot", None)


# ── 9. /log — redaction applied (C13 fix) ──


class TestCmdLog:
    async def test_log_with_buffer_applies_redaction(self):
        """C13 fix: log file must pass through redact_sensitive."""
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.list_sessions = AsyncMock(return_value=[session])
        set_session_manager(mgr)

        mock_buffer = MagicMock()
        mock_buffer.rolling_buffer = [
            "Normal line",
            "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        ]
        mock_monitor = MagicMock()
        mock_monitor.output_buffer = mock_buffer

        import sys

        mock_bot_module = MagicMock()
        mock_bot_module.get_app_data = MagicMock(
            return_value={"monitors": {session.id: mock_monitor}}
        )
        sys.modules["conductor.bot.bot"] = mock_bot_module
        try:
            msg = _make_message("/log 1")
            await cmd_log(msg)
            msg.answer_document.assert_awaited_once()
            # Extract the file content from the BufferedInputFile
            doc_call = msg.answer_document.call_args
            buffered_file = doc_call[1].get("document") or doc_call[0][0]
            # The file data should have the token redacted
            file_bytes = buffered_file.data
            file_content = file_bytes.decode("utf-8")
            assert "ghp_" not in file_content
            assert "REDACTED" in file_content
        finally:
            sys.modules.pop("conductor.bot.bot", None)

    async def test_log_no_monitor(self):
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.list_sessions = AsyncMock(return_value=[session])
        set_session_manager(mgr)

        import sys

        mock_bot_module = MagicMock()
        mock_bot_module.get_app_data = MagicMock(return_value={"monitors": {}})
        sys.modules["conductor.bot.bot"] = mock_bot_module
        try:
            msg = _make_message("/log 1")
            await cmd_log(msg)
            text = msg.answer.call_args[0][0]
            assert "No monitor active" in text
        finally:
            sys.modules.pop("conductor.bot.bot", None)

    async def test_log_empty_buffer(self):
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.list_sessions = AsyncMock(return_value=[session])
        set_session_manager(mgr)

        mock_buffer = MagicMock()
        mock_buffer.rolling_buffer = []
        mock_monitor = MagicMock()
        mock_monitor.output_buffer = mock_buffer

        import sys

        mock_bot_module = MagicMock()
        mock_bot_module.get_app_data = MagicMock(
            return_value={"monitors": {session.id: mock_monitor}}
        )
        sys.modules["conductor.bot.bot"] = mock_bot_module
        try:
            msg = _make_message("/log 1")
            await cmd_log(msg)
            text = msg.answer.call_args[0][0]
            assert "No output captured" in text
        finally:
            sys.modules.pop("conductor.bot.bot", None)

    async def test_log_session_not_found(self):
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=None)
        mgr.list_sessions = AsyncMock(return_value=[])
        set_session_manager(mgr)
        msg = _make_message("/log bogus")
        await cmd_log(msg)
        text = msg.answer.call_args[0][0]
        assert "Session not found" in text


# ── 10. /auto — list, add with regex validation, remove ──


class TestCmdAuto:
    @patch("conductor.auto.rules.get_all_rules", new_callable=AsyncMock)
    async def test_auto_list_empty(self, mock_get_rules):
        mock_get_rules.return_value = []
        msg = _make_message("/auto list")
        await cmd_auto(msg)
        text = msg.answer.call_args[0][0]
        assert "No auto-response rules" in text

    @patch("conductor.auto.rules.get_all_rules", new_callable=AsyncMock)
    async def test_auto_list_with_rules(self, mock_get_rules):
        rule = AutoRule(
            id=1,
            pattern="continue",
            response="y",
            match_type="contains",
            enabled=True,
            hit_count=5,
        )
        mock_get_rules.return_value = [rule]
        msg = _make_message("/auto list")
        await cmd_auto(msg)
        text = msg.answer.call_args[0][0]
        assert "Auto-Response Rules" in text
        assert "continue" in text
        assert "5 hits" in text

    @patch("conductor.auto.rules.get_all_rules", new_callable=AsyncMock)
    async def test_auto_list_default_subcmd(self, mock_get_rules):
        """When /auto is invoked with no subcommand, default to 'list'."""
        mock_get_rules.return_value = []
        msg = _make_message("/auto")
        await cmd_auto(msg)
        text = msg.answer.call_args[0][0]
        assert "No auto-response rules" in text

    @patch("conductor.auto.rules.add_rule", new_callable=AsyncMock)
    async def test_auto_add_success(self, mock_add):
        mock_add.return_value = 42
        msg = _make_message('/auto add "error.*timeout" "retry"')
        await cmd_auto(msg)
        mock_add.assert_awaited_once_with("error.*timeout", "retry")
        text = msg.answer.call_args[0][0]
        assert "Added rule #42" in text

    async def test_auto_add_missing_args(self):
        msg = _make_message("/auto add")
        await cmd_auto(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    async def test_auto_add_invalid_regex(self):
        msg = _make_message('/auto add "[invalid(" "response"')
        await cmd_auto(msg)
        text = msg.answer.call_args[0][0]
        assert "Invalid regex" in text

    async def test_auto_add_pattern_too_long(self):
        long_pattern = "a" * 300
        msg = _make_message(f'/auto add "{long_pattern}" "response"')
        await cmd_auto(msg)
        text = msg.answer.call_args[0][0]
        assert "too long" in text

    @patch("conductor.auto.rules.remove_rule", new_callable=AsyncMock)
    async def test_auto_remove_success(self, mock_remove):
        mock_remove.return_value = True
        msg = _make_message("/auto remove 1")
        await cmd_auto(msg)
        text = msg.answer.call_args[0][0]
        assert "Removed rule #1" in text

    @patch("conductor.auto.rules.remove_rule", new_callable=AsyncMock)
    async def test_auto_remove_not_found(self, mock_remove):
        mock_remove.return_value = False
        msg = _make_message("/auto remove 999")
        await cmd_auto(msg)
        text = msg.answer.call_args[0][0]
        assert "not found" in text

    async def test_auto_remove_missing_id(self):
        msg = _make_message("/auto remove")
        await cmd_auto(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    async def test_auto_remove_non_numeric_id(self):
        msg = _make_message("/auto remove abc")
        await cmd_auto(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    @patch("conductor.auto.rules.pause_all", new_callable=AsyncMock)
    async def test_auto_pause(self, mock_pause):
        msg = _make_message("/auto pause")
        await cmd_auto(msg)
        mock_pause.assert_awaited_once()
        text = msg.answer.call_args[0][0]
        assert "paused" in text

    @patch("conductor.auto.rules.resume_all", new_callable=AsyncMock)
    async def test_auto_resume(self, mock_resume):
        msg = _make_message("/auto resume")
        await cmd_auto(msg)
        mock_resume.assert_awaited_once()
        text = msg.answer.call_args[0][0]
        assert "resumed" in text

    async def test_auto_unknown_subcmd(self):
        msg = _make_message("/auto bogus")
        await cmd_auto(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text


# ── 11. /rename — success, empty alias ──


class TestCmdRename:
    async def test_rename_missing_args(self):
        mgr = _make_manager()
        set_session_manager(mgr)
        msg = _make_message("/rename")
        await cmd_rename(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    async def test_rename_missing_new_name(self):
        mgr = _make_manager()
        set_session_manager(mgr)
        msg = _make_message("/rename 1")
        await cmd_rename(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    async def test_rename_session_not_found(self):
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=None)
        set_session_manager(mgr)
        msg = _make_message("/rename 1 NewName")
        await cmd_rename(msg)
        text = msg.answer.call_args[0][0]
        assert "Session not found" in text

    async def test_rename_success(self):
        session = _make_session(alias="OldName")
        renamed = _make_session(alias="NewName")
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.rename_session = AsyncMock(return_value=renamed)
        set_session_manager(mgr)
        msg = _make_message("/rename 1 NewName")
        await cmd_rename(msg)
        mgr.rename_session.assert_awaited_once_with(session.id, "NewName")
        text = msg.answer.call_args[0][0]
        assert "Renamed" in text
        assert "OldName" in text
        assert "NewName" in text


# ── 12. /run ──


class TestCmdRun:
    async def test_run_missing_args(self):
        mgr = _make_manager()
        set_session_manager(mgr)
        msg = _make_message("/run")
        await cmd_run(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    async def test_run_session_not_found(self):
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=None)
        set_session_manager(mgr)
        msg = _make_message("/run bogus ls -la")
        await cmd_run(msg)
        text = msg.answer.call_args[0][0]
        assert "Session not found" in text

    async def test_run_success(self):
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.send_input = MagicMock(return_value=True)
        set_session_manager(mgr)
        msg = _make_message("/run 1 npm test")
        await cmd_run(msg)
        mgr.send_input.assert_called_once_with(session.id, "npm test")
        text = msg.answer.call_args[0][0]
        assert "Running" in text
        assert "npm test" in text

    async def test_run_send_fails(self):
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        mgr.send_input = MagicMock(return_value=False)
        set_session_manager(mgr)
        msg = _make_message("/run 1 npm test")
        await cmd_run(msg)
        text = msg.answer.call_args[0][0]
        assert "Could not send command" in text


# ── 13. /restart — confirmation flow ──


class TestCmdRestart:
    async def test_restart_missing_args(self):
        mgr = _make_manager()
        set_session_manager(mgr)
        msg = _make_message("/restart")
        await cmd_restart(msg)
        text = msg.answer.call_args[0][0]
        assert "Usage" in text

    async def test_restart_session_not_found(self):
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=None)
        set_session_manager(mgr)
        msg = _make_message("/restart bogus")
        await cmd_restart(msg)
        text = msg.answer.call_args[0][0]
        assert "Session not found" in text

    @patch("conductor.bot.handlers.commands.confirmation_mgr")
    async def test_restart_requests_confirmation(self, mock_confirm_mgr):
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session = MagicMock(return_value=session)
        set_session_manager(mgr)
        msg = _make_message("/restart 1")
        await cmd_restart(msg)
        mock_confirm_mgr.request.assert_called_once_with(
            msg.from_user.id, "restart", session.id
        )
        text = msg.answer.call_args[0][0]
        assert "Confirm" in text
        assert "Restart" in text
        assert msg.answer.call_args[1].get("reply_markup") is not None
