"""Extended tests for output buffer — full coverage including get_new_lines."""

from unittest.mock import MagicMock

from conductor.sessions.output_buffer import OutputBuffer


class TestOutputBufferGetNewLines:
    def test_get_new_lines_basic(self):
        buf = OutputBuffer()
        pane = MagicMock()
        pane.capture_pane.return_value = ["Line 1", "Line 2", "Line 3"]
        result = buf.get_new_lines(pane)
        assert result == ["Line 1", "Line 2", "Line 3"]
        assert buf.last_capture_length == 3

    def test_get_new_lines_incremental(self):
        buf = OutputBuffer()
        pane = MagicMock()
        # First capture
        pane.capture_pane.return_value = ["Line 1", "Line 2"]
        buf.get_new_lines(pane)
        # Second capture with new lines
        pane.capture_pane.return_value = ["Line 1", "Line 2", "Line 3", "Line 4"]
        result = buf.get_new_lines(pane)
        assert result == ["Line 3", "Line 4"]

    def test_get_new_lines_dedup(self):
        buf = OutputBuffer()
        pane = MagicMock()
        # First capture
        pane.capture_pane.return_value = ["Line 1", "Line 2"]
        buf.get_new_lines(pane)
        # Second capture repeats "Line 2" as new
        pane.capture_pane.return_value = ["Line 1", "Line 2", "Line 2", "Line 3"]
        result = buf.get_new_lines(pane)
        # "Line 2" already seen, should be deduped
        assert "Line 3" in result
        assert result.count("Line 2") == 0

    def test_get_new_lines_strips_ansi(self):
        buf = OutputBuffer()
        pane = MagicMock()
        pane.capture_pane.return_value = ["\x1b[31mRed text\x1b[0m"]
        result = buf.get_new_lines(pane)
        assert result == ["Red text"]

    def test_get_new_lines_exception(self):
        buf = OutputBuffer()
        pane = MagicMock()
        pane.capture_pane.side_effect = Exception("tmux error")
        result = buf.get_new_lines(pane)
        assert result == []

    def test_get_new_lines_no_growth(self):
        buf = OutputBuffer()
        pane = MagicMock()
        pane.capture_pane.return_value = ["Line 1", "Line 2"]
        buf.get_new_lines(pane)
        # Same length capture — no new lines
        pane.capture_pane.return_value = ["Line 1", "Line 2"]
        result = buf.get_new_lines(pane)
        assert result == []

    def test_rolling_buffer_trimmed(self):
        buf = OutputBuffer(max_lines=5)
        pane = MagicMock()
        pane.capture_pane.return_value = [f"Line {i}" for i in range(10)]
        buf.get_new_lines(pane)
        assert len(buf.rolling_buffer) == 5

    def test_hash_set_pruning(self):
        buf = OutputBuffer()
        # Fill seen_line_hashes past threshold using OrderedDict
        from collections import OrderedDict

        buf.seen_line_hashes = OrderedDict((f"hash-{i}", None) for i in range(10001))
        pane = MagicMock()
        pane.capture_pane.return_value = ["new line"]
        buf.get_new_lines(pane)
        # Hash dict should be pruned to 10000 (after removing oldest, then adding new)
        assert len(buf.seen_line_hashes) <= 10001

    def test_reset_clears_all(self):
        buf = OutputBuffer()
        buf.rolling_buffer = ["a", "b"]
        buf.seen_line_hashes["h1"] = None
        buf.seen_line_hashes["h2"] = None
        buf.last_capture_length = 5
        buf.reset()
        assert buf.rolling_buffer == []
        assert len(buf.seen_line_hashes) == 0
        assert buf.last_capture_length == 0
