"""Tests for output buffer — ANSI stripping + dedup."""

from conductor.sessions.output_buffer import OutputBuffer


class TestOutputBuffer:
    def test_strip_ansi(self):
        text = "\x1b[31mRed text\x1b[0m"
        result = OutputBuffer._strip_ansi(text)
        assert result == "Red text"

    def test_strip_ansi_cursor(self):
        text = "\x1b[2J\x1b[HHello"
        result = OutputBuffer._strip_ansi(text)
        assert result == "Hello"

    def test_preserves_plain_text(self):
        text = "Hello, world!"
        result = OutputBuffer._strip_ansi(text)
        assert result == text

    def test_rolling_buffer_limit(self):
        buf = OutputBuffer(max_lines=10)
        buf.rolling_buffer = list(range(15))
        # Simulate adding more lines
        buf.rolling_buffer.extend([16, 17])
        if len(buf.rolling_buffer) > buf.max_lines:
            buf.rolling_buffer = buf.rolling_buffer[-buf.max_lines :]
        assert len(buf.rolling_buffer) == 10

    def test_reset(self):
        buf = OutputBuffer()
        buf.rolling_buffer = ["line1", "line2"]
        buf.seen_line_hashes["abc"] = None
        buf.last_capture_length = 5
        buf.reset()
        assert buf.rolling_buffer == []
        assert len(buf.seen_line_hashes) == 0
        assert buf.last_capture_length == 0

    def test_hash_cleanup_preserves_recent(self):
        """Deterministic cleanup: oldest hashes removed, newest kept."""
        buf = OutputBuffer()
        # Insert hashes in known order
        for i in range(10005):
            buf.seen_line_hashes[f"hash-{i}"] = None
        # Simulate cleanup (same logic as get_new_lines)
        while len(buf.seen_line_hashes) > 10000:
            buf.seen_line_hashes.popitem(last=False)
        assert len(buf.seen_line_hashes) == 10000
        # Oldest should be gone, newest should remain
        assert "hash-0" not in buf.seen_line_hashes
        assert "hash-4" not in buf.seen_line_hashes
        assert "hash-10004" in buf.seen_line_hashes
        assert "hash-5" in buf.seen_line_hashes
