"""Fallback when AI (Haiku) is unavailable — raw output summary."""

from __future__ import annotations

from conductor.config import get_config


def get_raw_fallback(terminal_output: str) -> str:
    """Return last N lines as plain text when the AI API is unavailable.

    Args:
        terminal_output: Raw terminal text.

    Returns:
        Formatted string with a "Raw output" header and the last N lines
        (N configured via ``ai.fallback_lines``, default 20).
    """
    cfg = get_config()
    n = cfg.ai_config.get("fallback_lines", 20)
    lines = terminal_output.strip().split("\n")
    last_n = lines[-n:]
    return "📝 Raw output (AI unavailable):\n" + "\n".join(last_n)
