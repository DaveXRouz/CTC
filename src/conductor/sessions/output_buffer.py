"""Output buffer — ANSI stripping + deduplication for tmux pane capture."""

from __future__ import annotations

import re
import zlib
from collections import OrderedDict

_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class OutputBuffer:
    """Manages deduplicated output capture from a tmux pane."""

    def __init__(self, max_lines: int = 5000) -> None:
        self.seen_line_hashes: OrderedDict[int, None] = OrderedDict()
        self.last_capture_length: int = 0
        self.rolling_buffer: list[str] = []
        self.max_lines = max_lines

    def get_new_lines(self, pane) -> list[str]:
        """Capture and return only truly new, deduplicated lines from a tmux pane."""
        try:
            raw = pane.capture_pane(start="-1000", end="-0")
        except Exception:
            return []

        cleaned = [self._strip_ansi(line) for line in raw]

        if len(cleaned) < self.last_capture_length:
            self.last_capture_length = 0

        if len(cleaned) <= self.last_capture_length:
            return []

        new_lines = cleaned[self.last_capture_length :]
        self.last_capture_length = len(cleaned)

        truly_new = []
        for line in new_lines:
            line_hash = zlib.crc32(line.encode())
            if line_hash not in self.seen_line_hashes:
                self.seen_line_hashes[line_hash] = None
                truly_new.append(line)

        while len(self.seen_line_hashes) > 10000:
            self.seen_line_hashes.popitem(last=False)

        self.rolling_buffer.extend(truly_new)
        if len(self.rolling_buffer) > self.max_lines:
            self.rolling_buffer = self.rolling_buffer[-self.max_lines :]

        return truly_new

    def reset(self) -> None:
        """Reset buffer state, clearing all hashes and captured lines."""
        self.seen_line_hashes.clear()
        self.last_capture_length = 0
        self.rolling_buffer.clear()

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """Remove ANSI escape codes."""
        return _ANSI_RE.sub("", text)
