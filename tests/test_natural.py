"""Tests for natural language handler — NLP dispatch, short message routing, fallbacks."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


from conductor.bot.handlers.natural import (
    handle_natural_language,
    _dispatch_nlp_command,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

# Patch targets: these are imported INSIDE the function body via
#   from conductor.bot.bot import get_app_data
#   from conductor.bot.handlers.commands import _session_manager
# so we patch them at their origin modules.
_PATCH_APP_DATA = "conductor.bot.bot.get_app_data"
_PATCH_MGR = "conductor.bot.handlers.commands._session_manager"


def _make_session(
    *,
    id: str = "sess-1",
    number: int = 1,
    alias: str = "claude",
    type: str = "claude-code",
    working_dir: str = "/tmp",
    tmux_session: str = "tmux-1",
    status: str = "running",
    color_emoji: str = "🔵",
) -> MagicMock:
    """Create a mock Session with all required fields."""
    s = MagicMock()
    s.id = id
    s.number = number
    s.alias = alias
    s.type = type
    s.working_dir = working_dir
    s.tmux_session = tmux_session
    s.status = status
    s.color_emoji = color_emoji
    s.token_used = 0
    s.token_limit = 45
    s.last_activity = None
    s.last_summary = None
    s.created_at = datetime.now().isoformat()
    s.updated_at = datetime.now().isoformat()
    return s


def _make_message(text: str = "hello") -> AsyncMock:
    """Create a mock aiogram Message."""
    msg = AsyncMock()
    msg.text = text
    msg.answer = AsyncMock()
    msg.from_user = MagicMock()
    msg.from_user.id = 12345
    return msg


def _make_manager(sessions: list | None = None) -> MagicMock:
    """Create a mock SessionManager."""
    mgr = MagicMock()
    mgr.list_sessions = AsyncMock(return_value=sessions or [])
    mgr.get_session = MagicMock(return_value=None)
    mgr.send_input = MagicMock()
    mgr.resolve_session = MagicMock(return_value=None)
    return mgr


# ── Tests: early returns ─────────────────────────────────────────────────────


class TestEarlyReturns:
    """Test cases where handle_natural_language returns without processing."""

    async def test_empty_text_returns_early(self):
        """Empty string should return without answering."""
        msg = _make_message("")
        await handle_natural_language(msg)
        msg.answer.assert_not_called()

    async def test_none_text_returns_early(self):
        """None .text attribute should return without answering."""
        msg = _make_message("hello")
        msg.text = None
        await handle_natural_language(msg)
        msg.answer.assert_not_called()

    async def test_whitespace_only_returns_early(self):
        """Whitespace-only text should return without answering."""
        msg = _make_message("   ")
        await handle_natural_language(msg)
        msg.answer.assert_not_called()

    async def test_slash_command_returns_early(self):
        """Messages starting with / should be ignored (handled by command router)."""
        msg = _make_message("/status")
        await handle_natural_language(msg)
        msg.answer.assert_not_called()

    async def test_slash_command_with_args_returns_early(self):
        """Commands with arguments should also be ignored."""
        msg = _make_message("/input 1 hello")
        await handle_natural_language(msg)
        msg.answer.assert_not_called()


# ── Tests: no manager (bot initializing) ─────────────────────────────────────


class TestNoManager:
    """When _session_manager is None the bot is still initializing."""

    async def test_no_manager_sends_initializing_message(self):
        """With no manager, user gets an initializing message."""
        msg = _make_message("check session 1")
        with patch(_PATCH_APP_DATA, return_value={}):
            with patch(_PATCH_MGR, None):
                await handle_natural_language(msg)

        msg.answer.assert_called_once()
        call_text = msg.answer.call_args[0][0]
        assert "initializing" in call_text.lower()


# ── Tests: short message to waiting session ──────────────────────────────────


class TestShortMessageWaiting:
    """Short messages (<=10 chars) with a last_prompt_session that is waiting."""

    async def test_short_message_sent_to_waiting_session(self):
        """A short 'yes' to a waiting session should send input."""
        session = _make_session(id="sess-1", status="waiting", alias="builder")
        mgr = _make_manager()
        mgr.get_session.return_value = session

        app_data = {"last_prompt_session": "sess-1", "brain": None}

        msg = _make_message("yes")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        mgr.send_input.assert_called_once_with("sess-1", "yes")
        msg.answer.assert_called_once()
        call_text = msg.answer.call_args[0][0]
        assert "Sent to" in call_text
        assert "builder" in call_text

    async def test_short_numeric_input_sent(self):
        """A short numeric response like '2' should be sent to waiting session."""
        session = _make_session(id="sess-2", status="waiting", alias="setup")
        mgr = _make_manager()
        mgr.get_session.return_value = session

        app_data = {"last_prompt_session": "sess-2", "brain": None}

        msg = _make_message("2")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        mgr.send_input.assert_called_once_with("sess-2", "2")


# ── Tests: B4 fix — destructive keyword blocking on short messages ───────────


class TestDestructiveKeywordBlocking:
    """B4 fix: short messages with destructive keywords are blocked."""

    async def test_delete_blocked_for_waiting_session(self):
        """'delete' as a short response should be blocked with warning."""
        session = _make_session(id="sess-1", status="waiting")
        mgr = _make_manager()
        mgr.get_session.return_value = session

        app_data = {"last_prompt_session": "sess-1", "brain": None}

        msg = _make_message("delete")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        mgr.send_input.assert_not_called()
        msg.answer.assert_called_once()
        call_text = msg.answer.call_args[0][0]
        assert "destructive" in call_text.lower()
        assert "Blocked" in call_text

    async def test_remove_blocked_for_waiting_session(self):
        """'remove' should also be blocked."""
        session = _make_session(id="sess-1", status="waiting")
        mgr = _make_manager()
        mgr.get_session.return_value = session

        app_data = {"last_prompt_session": "sess-1", "brain": None}

        msg = _make_message("remove")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        mgr.send_input.assert_not_called()
        call_text = msg.answer.call_args[0][0]
        assert "destructive" in call_text.lower()

    async def test_reset_blocked_for_waiting_session(self):
        """'reset' should also be blocked."""
        session = _make_session(id="sess-1", status="waiting")
        mgr = _make_manager()
        mgr.get_session.return_value = session

        app_data = {"last_prompt_session": "sess-1", "brain": None}

        msg = _make_message("reset")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        mgr.send_input.assert_not_called()
        call_text = msg.answer.call_args[0][0]
        assert "Blocked" in call_text


# ── Tests: B4 fix — short message to non-waiting session falls through ───────


class TestShortMessageNonWaiting:
    """B4 fix: short messages when session is not waiting should fall through."""

    async def test_short_msg_non_waiting_session_falls_through(self):
        """Short message to a 'running' session should not send input via short path."""
        session = _make_session(id="sess-1", status="running")
        mgr = _make_manager(sessions=[session])
        mgr.get_session.return_value = session

        app_data = {"last_prompt_session": "sess-1", "brain": None}

        msg = _make_message("yes")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        # Should fall through to single-session fallback, not the short-message path
        # It still sends input, but via the single-session fallback (len(sessions)==1)
        mgr.send_input.assert_called_once_with("sess-1", "yes")

    async def test_short_msg_no_session_found_falls_through(self):
        """Short message when get_session returns None should fall through."""
        mgr = _make_manager(sessions=[])
        mgr.get_session.return_value = None

        app_data = {"last_prompt_session": "sess-1", "brain": None}

        msg = _make_message("y")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        # No sessions, should reach the fallback path
        mgr.send_input.assert_not_called()
        # Fallback answer should have been called
        msg.answer.assert_called_once()


# ── Tests: NLP dispatch — high confidence ────────────────────────────────────


class TestNlpDispatchHighConfidence:
    """NLP brain returns high confidence -- routes to the correct handler."""

    async def test_nlp_status_command_dispatched(self):
        """High-confidence 'status' command from brain should dispatch."""
        session = _make_session()
        mgr = _make_manager(sessions=[session])

        brain = AsyncMock()
        brain.parse_nlp = AsyncMock(
            return_value={
                "confidence": 0.95,
                "command": "status",
                "session": None,
                "args": {},
            }
        )

        app_data = {
            "brain": brain,
            "last_prompt_session": None,
            "last_prompt_context": None,
        }

        msg = _make_message("show me the status")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                with patch(
                    "conductor.bot.handlers.natural._dispatch_nlp_command",
                    new_callable=AsyncMock,
                ) as mock_dispatch:
                    await handle_natural_language(msg)

        mock_dispatch.assert_called_once()
        result_arg = mock_dispatch.call_args[0][1]
        assert result_arg["command"] == "status"

    async def test_nlp_input_command_dispatched(self):
        """High-confidence 'input' command should dispatch with session ref."""
        session = _make_session()
        mgr = _make_manager(sessions=[session])

        brain = AsyncMock()
        brain.parse_nlp = AsyncMock(
            return_value={
                "confidence": 0.9,
                "command": "input",
                "session": "1",
                "args": {"text": "npm install"},
            }
        )

        app_data = {
            "brain": brain,
            "last_prompt_session": None,
            "last_prompt_context": None,
        }

        msg = _make_message("send npm install to session 1")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                with patch(
                    "conductor.bot.handlers.natural._dispatch_nlp_command",
                    new_callable=AsyncMock,
                ) as mock_dispatch:
                    await handle_natural_language(msg)

        mock_dispatch.assert_called_once()
        result_arg = mock_dispatch.call_args[0][1]
        assert result_arg["command"] == "input"
        assert result_arg["args"]["text"] == "npm install"


# ── Tests: NLP dispatch — low confidence falls through ───────────────────────


class TestNlpDispatchLowConfidence:
    """NLP brain returns low confidence -- should NOT dispatch, falls through."""

    async def test_low_confidence_falls_through_to_single_session(self):
        """Confidence < 0.8 should not dispatch; falls to single-session fallback."""
        session = _make_session(id="sess-1", alias="builder")
        mgr = _make_manager(sessions=[session])

        brain = AsyncMock()
        brain.parse_nlp = AsyncMock(
            return_value={
                "confidence": 0.5,
                "command": "status",
                "session": None,
                "args": {},
            }
        )

        app_data = {
            "brain": brain,
            "last_prompt_session": None,
            "last_prompt_context": None,
        }

        msg = _make_message("maybe check something")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        # Should have fallen through to single-session send
        mgr.send_input.assert_called_once_with("sess-1", "maybe check something")

    async def test_unknown_command_falls_through(self):
        """Command 'unknown' even with high confidence should fall through."""
        session = _make_session(id="sess-1")
        mgr = _make_manager(sessions=[session])

        brain = AsyncMock()
        brain.parse_nlp = AsyncMock(
            return_value={
                "confidence": 0.95,
                "command": "unknown",
                "session": None,
                "args": {},
            }
        )

        app_data = {
            "brain": brain,
            "last_prompt_session": None,
            "last_prompt_context": None,
        }

        msg = _make_message("do something weird")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        # 'unknown' at any confidence should not dispatch
        mgr.send_input.assert_called_once_with("sess-1", "do something weird")

    async def test_nlp_parse_exception_falls_through(self):
        """If brain.parse_nlp raises, should fall through gracefully."""
        session = _make_session(id="sess-1")
        mgr = _make_manager(sessions=[session])

        brain = AsyncMock()
        brain.parse_nlp = AsyncMock(side_effect=RuntimeError("API timeout"))

        app_data = {
            "brain": brain,
            "last_prompt_session": None,
            "last_prompt_context": None,
        }

        msg = _make_message("check status")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        # Exception caught, falls through to single-session
        mgr.send_input.assert_called_once_with("sess-1", "check status")


# ── Tests: single session fallback ───────────────────────────────────────────


class TestSingleSessionFallback:
    """When there is exactly one session and no NLP match, send input to it."""

    async def test_single_session_receives_input(self):
        """With one session and no brain, text goes to that session."""
        session = _make_session(id="sess-only", alias="main")
        mgr = _make_manager(sessions=[session])

        app_data = {"brain": None, "last_prompt_session": None}

        msg = _make_message("run the tests")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        mgr.send_input.assert_called_once_with("sess-only", "run the tests")
        msg.answer.assert_called_once()
        call_text = msg.answer.call_args[0][0]
        assert "Sent to" in call_text
        assert "main" in call_text

    async def test_single_session_html_mode(self):
        """Response should use HTML parse_mode."""
        session = _make_session(id="sess-1")
        mgr = _make_manager(sessions=[session])

        app_data = {"brain": None, "last_prompt_session": None}

        msg = _make_message("hello")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        _, kwargs = msg.answer.call_args
        assert kwargs.get("parse_mode") == "HTML"


# ── Tests: no sessions — fallback message ────────────────────────────────────


class TestNoSessions:
    """When there are zero sessions, send the fallback message."""

    async def test_no_sessions_sends_fallback(self):
        """With no sessions and no brain, fallback handler is called."""
        mgr = _make_manager(sessions=[])

        app_data = {"brain": None, "last_prompt_session": None}

        msg = _make_message("hello there")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        msg.answer.assert_called_once()
        call_text = msg.answer.call_args[0][0]
        assert "didn't understand" in call_text.lower() or "help" in call_text.lower()

    async def test_multiple_sessions_no_brain_sends_fallback(self):
        """With 2+ sessions and no brain, should send fallback (ambiguous)."""
        s1 = _make_session(id="s1", number=1, alias="first")
        s2 = _make_session(id="s2", number=2, alias="second")
        mgr = _make_manager(sessions=[s1, s2])

        app_data = {"brain": None, "last_prompt_session": None}

        msg = _make_message("do something")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        # Should NOT send input (ambiguous), should fallback
        mgr.send_input.assert_not_called()
        msg.answer.assert_called_once()


# ── Tests: _dispatch_nlp_command ─────────────────────────────────────────────


class TestDispatchNlpCommand:
    """Test the internal _dispatch_nlp_command function for each command type."""

    async def test_dispatch_input_sends_to_session(self):
        """'input' command should resolve session and send text."""
        session = _make_session(id="sess-1", alias="worker")
        mgr = _make_manager()
        mgr.resolve_session.return_value = session

        result = {"command": "input", "session": "1", "args": {"text": "npm test"}}
        msg = _make_message()
        await _dispatch_nlp_command(msg, result, mgr)

        mgr.resolve_session.assert_called_once_with("1")
        mgr.send_input.assert_called_once_with("sess-1", "npm test")
        msg.answer.assert_called_once()
        call_text = msg.answer.call_args[0][0]
        assert "npm test" in call_text

    async def test_dispatch_input_no_session_ref_no_send(self):
        """'input' with no session ref should not send."""
        mgr = _make_manager()
        result = {"command": "input", "session": None, "args": {"text": "hello"}}
        msg = _make_message()
        await _dispatch_nlp_command(msg, result, mgr)
        mgr.send_input.assert_not_called()

    async def test_dispatch_input_no_text_no_send(self):
        """'input' with no text should not send."""
        session = _make_session()
        mgr = _make_manager()
        mgr.resolve_session.return_value = session
        result = {"command": "input", "session": "1", "args": {}}
        msg = _make_message()
        await _dispatch_nlp_command(msg, result, mgr)
        mgr.send_input.assert_not_called()

    async def test_dispatch_status_calls_cmd_status(self):
        """'status' command should call cmd_status."""
        mgr = _make_manager()
        result = {"command": "status", "session": None, "args": {}}
        msg = _make_message()
        with patch(
            "conductor.bot.handlers.commands.cmd_status",
            new_callable=AsyncMock,
        ) as mock_cmd:
            await _dispatch_nlp_command(msg, result, mgr)
        mock_cmd.assert_called_once_with(msg)

    async def test_dispatch_status_with_session_sets_text(self):
        """'status' with session ref should modify message.text."""
        mgr = _make_manager()
        result = {"command": "status", "session": "2", "args": {}}
        msg = _make_message()
        with patch(
            "conductor.bot.handlers.commands.cmd_status",
            new_callable=AsyncMock,
        ) as mock_cmd:
            await _dispatch_nlp_command(msg, result, mgr)
        assert msg.text == "/status 2"
        mock_cmd.assert_called_once()

    async def test_dispatch_help_calls_cmd_help(self):
        """'help' command should call cmd_help."""
        mgr = _make_manager()
        result = {"command": "help", "session": None, "args": {}}
        msg = _make_message()
        with patch(
            "conductor.bot.handlers.commands.cmd_help",
            new_callable=AsyncMock,
        ) as mock_cmd:
            await _dispatch_nlp_command(msg, result, mgr)
        mock_cmd.assert_called_once()

    async def test_dispatch_tokens_calls_cmd_tokens(self):
        """'tokens' command should call cmd_tokens."""
        mgr = _make_manager()
        result = {"command": "tokens", "session": None, "args": {}}
        msg = _make_message()
        with patch(
            "conductor.bot.handlers.commands.cmd_tokens",
            new_callable=AsyncMock,
        ) as mock_cmd:
            await _dispatch_nlp_command(msg, result, mgr)
        mock_cmd.assert_called_once()

    async def test_dispatch_kill_with_session(self):
        """'kill' command with session ref should call cmd_kill."""
        mgr = _make_manager()
        result = {"command": "kill", "session": "3", "args": {}}
        msg = _make_message()
        with patch(
            "conductor.bot.handlers.commands.cmd_kill",
            new_callable=AsyncMock,
        ) as mock_cmd:
            await _dispatch_nlp_command(msg, result, mgr)
        assert msg.text == "/kill 3"
        mock_cmd.assert_called_once()

    async def test_dispatch_kill_without_session_no_call(self):
        """'kill' command without session ref should not call cmd_kill."""
        mgr = _make_manager()
        result = {"command": "kill", "session": None, "args": {}}
        msg = _make_message()
        with patch(
            "conductor.bot.handlers.commands.cmd_kill",
            new_callable=AsyncMock,
        ) as mock_cmd:
            await _dispatch_nlp_command(msg, result, mgr)
        mock_cmd.assert_not_called()

    async def test_dispatch_pause_with_session(self):
        """'pause' command with session ref should call cmd_pause."""
        mgr = _make_manager()
        result = {"command": "pause", "session": "1", "args": {}}
        msg = _make_message()
        with patch(
            "conductor.bot.handlers.commands.cmd_pause",
            new_callable=AsyncMock,
        ) as mock_cmd:
            await _dispatch_nlp_command(msg, result, mgr)
        assert msg.text == "/pause 1"
        mock_cmd.assert_called_once()

    async def test_dispatch_resume_with_session(self):
        """'resume' command with session ref should call cmd_resume."""
        mgr = _make_manager()
        result = {"command": "resume", "session": "2", "args": {}}
        msg = _make_message()
        with patch(
            "conductor.bot.handlers.commands.cmd_resume",
            new_callable=AsyncMock,
        ) as mock_cmd:
            await _dispatch_nlp_command(msg, result, mgr)
        assert msg.text == "/resume 2"
        mock_cmd.assert_called_once()

    async def test_dispatch_output_with_session(self):
        """'output' command with session ref should call cmd_output."""
        mgr = _make_manager()
        result = {"command": "output", "session": "1", "args": {}}
        msg = _make_message()
        with patch(
            "conductor.bot.handlers.commands.cmd_output",
            new_callable=AsyncMock,
        ) as mock_cmd:
            await _dispatch_nlp_command(msg, result, mgr)
        assert msg.text == "/output 1"
        mock_cmd.assert_called_once()

    async def test_dispatch_digest_calls_cmd_digest(self):
        """'digest' command should call cmd_digest."""
        mgr = _make_manager()
        result = {"command": "digest", "session": None, "args": {}}
        msg = _make_message()
        with patch(
            "conductor.bot.handlers.commands.cmd_digest",
            new_callable=AsyncMock,
        ) as mock_cmd:
            await _dispatch_nlp_command(msg, result, mgr)
        mock_cmd.assert_called_once()

    async def test_dispatch_unknown_command_sends_fallback(self):
        """Unrecognized command string should call send_fallback."""
        mgr = _make_manager()
        result = {"command": "nonexistent_cmd", "session": None, "args": {}}
        msg = _make_message()
        with patch(
            "conductor.bot.handlers.fallback.send_fallback",
            new_callable=AsyncMock,
        ) as mock_fallback:
            await _dispatch_nlp_command(msg, result, mgr)
        mock_fallback.assert_called_once_with(msg)


# ── Tests: edge cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    """Miscellaneous edge cases."""

    async def test_message_exactly_10_chars_is_short(self):
        """A message of exactly 10 characters should be treated as short."""
        session = _make_session(id="sess-1", status="waiting")
        mgr = _make_manager()
        mgr.get_session.return_value = session

        text_10 = "0123456789"  # exactly 10 chars
        assert len(text_10) == 10

        app_data = {"last_prompt_session": "sess-1", "brain": None}

        msg = _make_message(text_10)
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        mgr.send_input.assert_called_once_with("sess-1", text_10)

    async def test_message_11_chars_not_short(self):
        """A message of 11 characters should NOT take the short-message path."""
        session = _make_session(id="sess-1", status="waiting")
        mgr = _make_manager(sessions=[session])
        mgr.get_session.return_value = session

        text_11 = "01234567890"  # 11 chars
        assert len(text_11) == 11

        app_data = {"last_prompt_session": "sess-1", "brain": None}

        msg = _make_message(text_11)
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        # Should NOT go through short-message path, falls to single-session fallback
        mgr.send_input.assert_called_once_with("sess-1", text_11)
        # The key distinction: get_session was called but the short path was not used
        # This test verifies len(text) <= 10 boundary

    async def test_no_last_prompt_session_skips_short_path(self):
        """Without last_prompt_session, short messages skip the short-message path."""
        session = _make_session(id="sess-1")
        mgr = _make_manager(sessions=[session])

        app_data = {"last_prompt_session": None, "brain": None}

        msg = _make_message("y")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        # Goes through single-session fallback, not short-message path
        mgr.get_session.assert_not_called()
        mgr.send_input.assert_called_once_with("sess-1", "y")

    async def test_brain_result_missing_fields_handled(self):
        """Brain returning partial result (missing keys) should not crash."""
        session = _make_session(id="sess-1")
        mgr = _make_manager(sessions=[session])

        brain = AsyncMock()
        # Return result with missing 'confidence' and 'command' keys
        brain.parse_nlp = AsyncMock(return_value={})

        app_data = {
            "brain": brain,
            "last_prompt_session": None,
            "last_prompt_context": None,
        }

        msg = _make_message("do something")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        # confidence defaults to 0, command defaults to "unknown"
        # Neither passes the threshold, falls through to single-session
        mgr.send_input.assert_called_once_with("sess-1", "do something")

    async def test_nlp_builds_session_list_json(self):
        """Verify brain.parse_nlp receives correct session_list_json."""
        s1 = _make_session(id="s1", number=1, alias="alpha", status="running")
        s2 = _make_session(id="s2", number=2, alias="beta", status="waiting")
        mgr = _make_manager(sessions=[s1, s2])

        brain = AsyncMock()
        brain.parse_nlp = AsyncMock(
            return_value={"confidence": 0.3, "command": "unknown"}
        )

        app_data = {
            "brain": brain,
            "last_prompt_session": None,
            "last_prompt_context": "some ctx",
        }

        msg = _make_message("check sessions")
        with patch(_PATCH_APP_DATA, return_value=app_data):
            with patch(_PATCH_MGR, mgr):
                await handle_natural_language(msg)

        brain.parse_nlp.assert_called_once()
        call_kwargs = brain.parse_nlp.call_args[1]
        session_list = json.loads(call_kwargs["session_list_json"])
        assert len(session_list) == 2
        assert session_list[0]["number"] == 1
        assert session_list[0]["alias"] == "alpha"
        assert session_list[1]["status"] == "waiting"
        assert call_kwargs["last_prompt_context"] == "some ctx"
