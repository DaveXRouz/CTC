"""Token usage estimation — Section 15."""

from __future__ import annotations

from datetime import datetime

from conductor.config import get_config
from conductor.utils.logger import get_logger

logger = get_logger("conductor.tokens.estimator")


class TokenEstimator:
    """Estimate token usage based on observable message exchanges."""

    LIMITS = {
        "pro": {"messages": 45, "description": "~45 messages per 5h"},
        "max_5x": {"messages": 225, "description": "~225 messages per 5h"},
        "max_20x": {"messages": 900, "description": "~900 messages per 5h"},
    }

    def __init__(self) -> None:
        cfg = get_config()
        self.tier = cfg.plan_tier
        self.message_counts: dict[str, int] = {}
        self.window_start: datetime | None = None

    def on_claude_response(self, session_id: str) -> None:
        """Record a message exchange (response from Claude)."""
        if session_id not in self.message_counts:
            self.message_counts[session_id] = 0
        self.message_counts[session_id] += 1

        if self.window_start is None:
            self.window_start = datetime.now()

    def get_usage(self, session_id: str | None = None) -> dict:
        """Get estimated usage for a session or all sessions."""
        limit = self.LIMITS.get(self.tier, self.LIMITS["pro"])["messages"]

        if session_id:
            used = self.message_counts.get(session_id, 0)
        else:
            used = sum(self.message_counts.values())

        pct = min(100, int((used / limit) * 100)) if limit > 0 else 0

        reset_seconds = None
        if self.window_start:
            elapsed = (datetime.now() - self.window_start).total_seconds()
            reset_seconds = max(0, (5 * 3600) - elapsed)

        return {
            "used": used,
            "limit": limit,
            "percentage": pct,
            "reset_in_seconds": reset_seconds,
            "tier": self.tier,
        }

    def check_thresholds(self) -> str | None:
        """Check if any warning threshold is crossed."""
        cfg = get_config()
        usage = self.get_usage()
        pct = usage["percentage"]

        critical = cfg.tokens_config.get("critical_pct", 95)
        danger = cfg.tokens_config.get("danger_pct", 90)
        warning = cfg.tokens_config.get("warning_pct", 80)

        if pct >= critical:
            return "critical"
        elif pct >= danger:
            return "danger"
        elif pct >= warning:
            return "warning"
        return None

    def detect_message_boundary(self, idle_seconds: float, new_line_count: int) -> bool:
        """Detect when Claude Code has completed a response."""
        return idle_seconds > 3 and new_line_count > 5

    def reset_window(self) -> None:
        """Reset the tracking window."""
        self.message_counts.clear()
        self.window_start = None
