"""Integration tests for ConfirmationManager TTL enforcement in callbacks."""

import time

from conductor.security.confirm import ConfirmationManager


class TestConfirmationIntegration:
    """Test that confirmations are properly enforced end-to-end."""

    def test_valid_confirmation_flow(self):
        """Normal flow: request -> confirm within TTL -> succeeds."""
        mgr = ConfirmationManager(ttl=30.0)
        mgr.request(user_id=123, action_type="kill", session_id="sess-1")
        assert mgr.confirm(123, "kill", "sess-1") is True

    def test_expired_confirmation_rejected(self):
        """Expired flow: request -> wait past TTL -> confirm fails."""
        mgr = ConfirmationManager(ttl=0.001)
        mgr.request(user_id=123, action_type="kill", session_id="sess-1")
        time.sleep(0.01)
        assert mgr.confirm(123, "kill", "sess-1") is False

    def test_cancel_then_confirm_rejected(self):
        """Cancel flow: request -> cancel -> confirm fails."""
        mgr = ConfirmationManager()
        mgr.request(user_id=123, action_type="restart", session_id="sess-1")
        mgr.cancel(123, "restart", "sess-1")
        assert mgr.confirm(123, "restart", "sess-1") is False

    def test_double_confirm_rejected(self):
        """Replay protection: confirm consumes the token, second attempt fails."""
        mgr = ConfirmationManager()
        mgr.request(user_id=123, action_type="kill", session_id="sess-1")
        assert mgr.confirm(123, "kill", "sess-1") is True
        assert mgr.confirm(123, "kill", "sess-1") is False

    def test_wrong_user_rejected(self):
        """Different user cannot confirm another user's action."""
        mgr = ConfirmationManager()
        mgr.request(user_id=123, action_type="kill", session_id="sess-1")
        assert mgr.confirm(999, "kill", "sess-1") is False

    def test_wrong_action_rejected(self):
        """Confirm with wrong action type fails."""
        mgr = ConfirmationManager()
        mgr.request(user_id=123, action_type="kill", session_id="sess-1")
        assert mgr.confirm(123, "restart", "sess-1") is False

    def test_restart_confirmation_flow(self):
        """Restart action uses same TTL enforcement."""
        mgr = ConfirmationManager(ttl=30.0)
        mgr.request(user_id=456, action_type="restart", session_id="sess-2")
        assert mgr.confirm(456, "restart", "sess-2") is True

    def test_multiple_pending_independent(self):
        """Multiple pending confirmations for different sessions are independent."""
        mgr = ConfirmationManager()
        mgr.request(user_id=123, action_type="kill", session_id="sess-1")
        mgr.request(user_id=123, action_type="kill", session_id="sess-2")
        assert mgr.confirm(123, "kill", "sess-1") is True
        assert mgr.confirm(123, "kill", "sess-2") is True
