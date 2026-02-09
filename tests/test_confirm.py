"""Tests for confirmation manager."""

import time
from conductor.security.confirm import ConfirmationManager, PendingConfirmation


class TestPendingConfirmation:
    def test_not_expired_initially(self):
        pc = PendingConfirmation(user_id=1, action_type="kill", session_id="s1")
        assert pc.is_expired is False

    def test_expired_after_ttl(self):
        pc = PendingConfirmation(
            user_id=1,
            action_type="kill",
            session_id="s1",
            created_at=time.time() - 60,
            ttl=30.0,
        )
        assert pc.is_expired is True


class TestConfirmationManager:
    def test_request_creates_pending(self):
        mgr = ConfirmationManager()
        conf = mgr.request(user_id=1, action_type="kill", session_id="s1")
        assert conf.user_id == 1
        assert conf.action_type == "kill"

    def test_confirm_valid(self):
        mgr = ConfirmationManager()
        mgr.request(user_id=1, action_type="kill", session_id="s1")
        assert mgr.confirm(1, "kill", "s1") is True

    def test_confirm_removes_pending(self):
        mgr = ConfirmationManager()
        mgr.request(user_id=1, action_type="kill", session_id="s1")
        mgr.confirm(1, "kill", "s1")
        # Second confirm should fail — already consumed
        assert mgr.confirm(1, "kill", "s1") is False

    def test_confirm_expired(self):
        mgr = ConfirmationManager(ttl=0.001)
        mgr.request(user_id=1, action_type="kill", session_id="s1")
        time.sleep(0.01)
        assert mgr.confirm(1, "kill", "s1") is False

    def test_confirm_nonexistent(self):
        mgr = ConfirmationManager()
        assert mgr.confirm(1, "kill", "nope") is False

    def test_cancel(self):
        mgr = ConfirmationManager()
        mgr.request(user_id=1, action_type="restart", session_id="s1")
        assert mgr.cancel(1, "restart", "s1") is True
        assert mgr.confirm(1, "restart", "s1") is False

    def test_cancel_nonexistent(self):
        mgr = ConfirmationManager()
        assert mgr.cancel(1, "kill", "nope") is False

    def test_cleanup_expired(self):
        mgr = ConfirmationManager(ttl=0.001)
        mgr.request(user_id=1, action_type="kill", session_id="s1")
        mgr.request(user_id=1, action_type="restart", session_id="s2")
        time.sleep(0.01)
        expired = mgr.cleanup_expired()
        assert len(expired) == 2

    def test_cleanup_keeps_valid(self):
        mgr = ConfirmationManager(ttl=300)
        mgr.request(user_id=1, action_type="kill", session_id="s1")
        expired = mgr.cleanup_expired()
        assert len(expired) == 0
        # Still confirmable
        assert mgr.confirm(1, "kill", "s1") is True

    def test_key_format(self):
        mgr = ConfirmationManager()
        key = mgr._key(123, "kill", "session-1")
        assert key == "123:kill:session-1"
