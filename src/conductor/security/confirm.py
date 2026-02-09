"""Destructive action confirmation with TTL — Section 9.2."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class PendingConfirmation:
    user_id: int
    action_type: str  # 'kill', 'restart'
    session_id: str
    created_at: float = field(default_factory=time.time)
    ttl: float = 30.0  # seconds

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl


class ConfirmationManager:
    """Manage pending confirmations for destructive actions."""

    def __init__(self, ttl: float = 30.0) -> None:
        self._pending: dict[str, PendingConfirmation] = {}
        self._ttl = ttl

    def _key(self, user_id: int, action_type: str, session_id: str) -> str:
        return f"{user_id}:{action_type}:{session_id}"

    def request(
        self, user_id: int, action_type: str, session_id: str
    ) -> PendingConfirmation:
        """Create a pending confirmation request."""
        key = self._key(user_id, action_type, session_id)
        conf = PendingConfirmation(
            user_id=user_id,
            action_type=action_type,
            session_id=session_id,
            ttl=self._ttl,
        )
        self._pending[key] = conf
        return conf

    def confirm(self, user_id: int, action_type: str, session_id: str) -> bool:
        """Confirm a pending action. Returns True if valid and not expired."""
        key = self._key(user_id, action_type, session_id)
        conf = self._pending.pop(key, None)
        if conf is None:
            return False
        return not conf.is_expired

    def cancel(self, user_id: int, action_type: str, session_id: str) -> bool:
        """Cancel a pending confirmation."""
        key = self._key(user_id, action_type, session_id)
        return self._pending.pop(key, None) is not None

    def cleanup_expired(self) -> list[PendingConfirmation]:
        """Remove and return expired confirmations."""
        expired = []
        for key in list(self._pending.keys()):
            if self._pending[key].is_expired:
                expired.append(self._pending.pop(key))
        return expired
