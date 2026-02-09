"""Output buffer — ANSI stripping + deduplication for tmux pane capture."""

from __future__ import annotations

import hashlib
import re


class OutputBuffer:
    """Manages deduplicated output capture from a tmux pane."""

    def __init__(self, max_lines: int = 5000) -> None:
        self.seen_line_hashes: set[str] = set()
        self.last_capture_length: int = 0
        self.rolling_buffer: list[str] = []
        self.max_lines = max_lines

    def get_new_lines(self, pane) -> list[str]:
        """Get only truly new, complete lines from the pane."""
        try:
            raw = pane.capture_pane(start="-1000", end="-0")
        except Exception:
            return []

        cleaned = [self._strip_ansi(line) for line in raw]

        if len(cleaned) <= self.last_capture_length:
            return []

        new_lines = cleaned[self.last_capture_length :]
        self.last_capture_length = len(cleaned)

        # Deduplicate using hashes
        truly_new = []
        for line in new_lines:
            line_hash = hashlib.md5(line.encode()).hexdigest()
            if line_hash not in self.seen_line_hashes:
                self.seen_line_hashes.add(line_hash)
                truly_new.append(line)

        # Prevent hash set from growing forever
        if len(self.seen_line_hashes) > 10000:
            self.seen_line_hashes = set(list(self.seen_line_hashes)[-5000:])

        self.rolling_buffer.extend(truly_new)
        if len(self.rolling_buffer) > self.max_lines:
            self.rolling_buffer = self.rolling_buffer[-self.max_lines :]

        return truly_new

    def reset(self) -> None:
        """Reset buffer state (e.g., after session restart)."""
        self.seen_line_hashes.clear()
        self.last_capture_length = 0
        self.rolling_buffer.clear()

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """Remove ANSI escape codes (colors, cursor movement, etc.)."""
        ansi_pattern = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        return ansi_pattern.sub("", text)
