"""Tests that send_input does NOT log the actual input text."""

import logging
from unittest.mock import MagicMock

from conductor.sessions.manager import SessionManager


class TestSendInputLogging:
    def test_send_input_does_not_log_text(self, caplog):
        """Verify that send_input logs char count but NOT the actual text."""
        mgr = SessionManager()
        session_id = "test-session"

        # Set up a mock pane
        mock_pane = MagicMock()
        mgr._panes[session_id] = mock_pane

        secret_text = "my-super-secret-password-123"

        with caplog.at_level(logging.DEBUG):
            result = mgr.send_input(session_id, secret_text)

        assert result is True
        # The secret text must NOT appear in any log record
        for record in caplog.records:
            assert secret_text not in record.message
        # But the char count should appear
        log_output = caplog.text
        assert f"{len(secret_text)} chars" in log_output

    def test_send_input_logs_session_id(self, caplog):
        """Verify that the session ID is still logged for debugging."""
        mgr = SessionManager()
        session_id = "test-session-42"

        mock_pane = MagicMock()
        mgr._panes[session_id] = mock_pane

        with caplog.at_level(logging.DEBUG):
            mgr.send_input(session_id, "anything")

        log_output = caplog.text
        assert session_id in log_output
