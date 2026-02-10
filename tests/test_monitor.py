"""Tests for OutputMonitor — async polling loop for tmux pane output."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conductor.db.models import Session
from conductor.sessions.detector import DetectionResult
from conductor.sessions.monitor import OutputMonitor


def _make_session(**overrides) -> Session:
    """Create a Session with sensible defaults, overriding any field."""
    defaults = dict(
        id="sess-1",
        number=1,
        alias="test-session",
        type="claude-code",
        working_dir="/tmp",
        tmux_session="conductor",
        tmux_pane_id="%0",
        status="running",
    )
    defaults.update(overrides)
    return Session(**defaults)


def _make_monitor(session=None, on_event=None, monitor_cfg=None):
    """Build an OutputMonitor with a mock pane and patched config."""
    if session is None:
        session = _make_session()
    if monitor_cfg is None:
        monitor_cfg = {
            "poll_interval_ms": 500,
            "active_poll_interval_ms": 300,
            "idle_poll_interval_ms": 2000,
            "completion_idle_threshold_s": 30,
        }

    mock_config = MagicMock()
    mock_config.monitor_config = monitor_cfg

    mock_pane = MagicMock()

    with patch("conductor.sessions.monitor.get_config", return_value=mock_config):
        monitor = OutputMonitor(pane=mock_pane, session=session, on_event=on_event)

    return monitor


# ---------------------------------------------------------------------------
# 1. poll_interval property
# ---------------------------------------------------------------------------


class TestPollInterval:
    def test_paused_returns_5(self):
        """Paused session always gets the slow 5-second poll interval."""
        monitor = _make_monitor(session=_make_session(status="paused"))
        assert monitor.poll_interval == 5.0

    def test_idle_over_300_returns_idle_interval(self):
        """When idle_seconds exceeds 300, use the configured idle interval."""
        monitor = _make_monitor()
        monitor.idle_seconds = 301
        assert monitor.poll_interval == 2.0  # 2000ms / 1000

    def test_active_output_returns_active_interval(self):
        """While actively receiving output, poll at the faster active rate."""
        monitor = _make_monitor()
        monitor.active_output = True
        monitor.idle_seconds = 0
        assert monitor.poll_interval == 0.3  # 300ms / 1000

    def test_default_returns_default_interval(self):
        """With no special conditions, poll at the default rate."""
        monitor = _make_monitor()
        monitor.active_output = False
        monitor.idle_seconds = 0
        assert monitor.poll_interval == 0.5  # 500ms / 1000

    def test_paused_takes_priority_over_active(self):
        """Paused status takes priority even when active_output is True."""
        monitor = _make_monitor(session=_make_session(status="paused"))
        monitor.active_output = True
        monitor.idle_seconds = 0
        assert monitor.poll_interval == 5.0

    def test_idle_over_300_takes_priority_over_active(self):
        """High idle_seconds takes priority over active_output flag."""
        monitor = _make_monitor()
        monitor.idle_seconds = 400
        monitor.active_output = True
        # idle_seconds > 300 is checked before active_output
        assert monitor.poll_interval == 2.0

    def test_custom_config_values(self):
        """Monitor respects non-default config values for poll intervals."""
        cfg = {
            "poll_interval_ms": 1000,
            "active_poll_interval_ms": 100,
            "idle_poll_interval_ms": 5000,
            "completion_idle_threshold_s": 60,
        }
        monitor = _make_monitor(monitor_cfg=cfg)
        assert monitor._poll_default == 1.0
        assert monitor._poll_active == 0.1
        assert monitor._poll_idle == 5.0
        assert monitor._completion_threshold == 60


# ---------------------------------------------------------------------------
# 2. start / stop loop
# ---------------------------------------------------------------------------


class TestStartStop:
    async def test_stop_event_interrupts_sleep(self):
        """Calling stop() should interrupt the wait_for sleep immediately (C1 fix)."""
        monitor = _make_monitor()
        monitor.output_buffer.get_new_lines = MagicMock(return_value=[])

        async def stop_after_short_delay():
            await asyncio.sleep(0.05)
            await monitor.stop()

        start_time = time.monotonic()
        # Run start() and stop concurrently; stop should interrupt quickly
        await asyncio.gather(monitor.start(), stop_after_short_delay())
        elapsed = time.monotonic() - start_time

        # Should complete well under 1 second (poll_interval is 0.5s)
        assert elapsed < 0.5

    async def test_stop_sets_event(self):
        """stop() sets the internal _stop_event."""
        monitor = _make_monitor()
        assert not monitor._stop_event.is_set()
        await monitor.stop()
        assert monitor._stop_event.is_set()

    async def test_start_clears_stop_event(self):
        """start() clears _stop_event so the loop can run again."""
        monitor = _make_monitor()
        monitor._stop_event.set()
        monitor.output_buffer.get_new_lines = MagicMock(return_value=[])

        async def stop_soon():
            await asyncio.sleep(0.05)
            await monitor.stop()

        # start() should clear the event and loop at least once
        await asyncio.gather(monitor.start(), stop_soon())
        # get_new_lines must have been called at least once
        assert monitor.output_buffer.get_new_lines.call_count >= 1

    async def test_loop_polls_multiple_times(self):
        """The loop should poll get_new_lines repeatedly until stopped."""
        cfg = {
            "poll_interval_ms": 20,
            "active_poll_interval_ms": 20,
            "idle_poll_interval_ms": 20,
            "completion_idle_threshold_s": 30,
        }
        monitor = _make_monitor(monitor_cfg=cfg)
        monitor.output_buffer.get_new_lines = MagicMock(return_value=[])

        async def stop_after_polls():
            await asyncio.sleep(0.15)
            await monitor.stop()

        await asyncio.gather(monitor.start(), stop_after_polls())
        # With 20ms interval and 150ms runtime, expect several polls
        assert monitor.output_buffer.get_new_lines.call_count >= 3


# ---------------------------------------------------------------------------
# 3. Idle time tracking (C14 fix)
# ---------------------------------------------------------------------------


class TestIdleTracking:
    async def test_idle_seconds_resets_on_new_output(self):
        """When new lines arrive, idle_seconds must reset to 0."""
        monitor = _make_monitor()
        monitor.idle_seconds = 100
        monitor.detector = MagicMock()
        monitor.detector.classify.return_value = DetectionResult(type="none")
        monitor.output_buffer.get_new_lines = MagicMock(side_effect=[["line1"], []])

        async def stop_after():
            await asyncio.sleep(0.05)
            await monitor.stop()

        await asyncio.gather(monitor.start(), stop_after())
        # After receiving output, idle_seconds should have been reset to 0
        # (it may have accumulated a tiny bit from the second empty poll)
        # but must not still be 100
        assert monitor.idle_seconds < 10

    async def test_idle_seconds_accumulates_when_no_output(self):
        """idle_seconds should grow when no new lines arrive."""
        cfg = {
            "poll_interval_ms": 20,
            "active_poll_interval_ms": 20,
            "idle_poll_interval_ms": 20,
            "completion_idle_threshold_s": 9999,
        }
        monitor = _make_monitor(monitor_cfg=cfg)
        monitor.output_buffer.get_new_lines = MagicMock(return_value=[])

        async def stop_after():
            await asyncio.sleep(0.12)
            await monitor.stop()

        await asyncio.gather(monitor.start(), stop_after())
        # idle_seconds should have accumulated some positive amount
        assert monitor.idle_seconds > 0

    async def test_active_output_cleared_after_threshold(self):
        """active_output should flip False once idle exceeds completion_threshold."""
        cfg = {
            "poll_interval_ms": 10,
            "active_poll_interval_ms": 10,
            "idle_poll_interval_ms": 10,
            "completion_idle_threshold_s": 0.01,  # very low for fast test
        }
        monitor = _make_monitor(monitor_cfg=cfg)
        monitor.active_output = True
        monitor.idle_seconds = 0
        # No rolling buffer content, so _check_completion will return early
        monitor.output_buffer.get_new_lines = MagicMock(return_value=[])
        monitor.output_buffer.rolling_buffer = []

        async def stop_after():
            await asyncio.sleep(0.08)
            await monitor.stop()

        await asyncio.gather(monitor.start(), stop_after())
        assert monitor.active_output is False


# ---------------------------------------------------------------------------
# 4. _process_output
# ---------------------------------------------------------------------------


class TestProcessOutput:
    async def test_calls_detector_classify(self):
        """_process_output should pass joined lines to detector.classify."""
        monitor = _make_monitor()
        monitor.detector = MagicMock()
        monitor.detector.classify.return_value = DetectionResult(type="none")

        await monitor._process_output(["line1", "line2"])
        monitor.detector.classify.assert_called_once_with("line1\nline2")

    async def test_triggers_on_event_for_non_none(self):
        """When detector returns a non-'none' type, on_event is called."""
        callback = AsyncMock()
        monitor = _make_monitor(on_event=callback)
        detection = DetectionResult(type="error", matched_text="Error", pattern="err")
        monitor.detector = MagicMock()
        monitor.detector.classify.return_value = detection

        lines = ["Something failed", "Error: crash"]
        await monitor._process_output(lines)

        callback.assert_awaited_once_with(monitor.session, detection, lines)

    async def test_does_not_trigger_on_event_for_none(self):
        """When detector returns 'none', on_event should NOT be called."""
        callback = AsyncMock()
        monitor = _make_monitor(on_event=callback)
        monitor.detector = MagicMock()
        monitor.detector.classify.return_value = DetectionResult(type="none")

        await monitor._process_output(["some normal output"])
        callback.assert_not_awaited()

    async def test_no_callback_does_not_crash(self):
        """If on_event is None, _process_output should not raise."""
        monitor = _make_monitor(on_event=None)
        monitor.detector = MagicMock()
        monitor.detector.classify.return_value = DetectionResult(
            type="error", matched_text="err", pattern="err"
        )
        # Should complete without exception
        await monitor._process_output(["Error line"])

    async def test_sets_last_activity_on_event(self):
        """on_event trigger should update session.last_activity."""
        callback = AsyncMock()
        monitor = _make_monitor(on_event=callback)
        monitor.session.last_activity = None
        monitor.detector = MagicMock()
        monitor.detector.classify.return_value = DetectionResult(
            type="error", matched_text="err", pattern="err"
        )

        await monitor._process_output(["Error happened"])
        assert monitor.session.last_activity is not None


# ---------------------------------------------------------------------------
# 5. _check_completion
# ---------------------------------------------------------------------------


class TestCheckCompletion:
    async def test_triggers_on_completion_detected(self):
        """When rolling buffer contains a completion pattern, fire on_event."""
        callback = AsyncMock()
        monitor = _make_monitor(on_event=callback)
        completion_result = DetectionResult(
            type="completion", matched_text="all tests passed", pattern=".*"
        )
        monitor.detector = MagicMock()
        monitor.detector.classify.return_value = completion_result
        monitor.output_buffer.rolling_buffer = [
            "Running tests...",
            "all 42 tests passed",
        ]

        await monitor._check_completion()

        callback.assert_awaited_once()
        args = callback.call_args[0]
        assert args[0] is monitor.session
        assert args[1].type == "completion"

    async def test_no_trigger_for_non_completion(self):
        """If rolling buffer pattern is not 'completion', skip the event."""
        callback = AsyncMock()
        monitor = _make_monitor(on_event=callback)
        monitor.detector = MagicMock()
        monitor.detector.classify.return_value = DetectionResult(type="error")
        monitor.output_buffer.rolling_buffer = ["Some error output"]

        await monitor._check_completion()
        callback.assert_not_awaited()

    async def test_empty_rolling_buffer_returns_early(self):
        """If rolling_buffer is empty, _check_completion returns without calling classify."""
        monitor = _make_monitor()
        monitor.detector = MagicMock()
        monitor.output_buffer.rolling_buffer = []

        await monitor._check_completion()
        monitor.detector.classify.assert_not_called()

    async def test_uses_last_10_lines(self):
        """_check_completion should only look at the last 10 lines of the buffer."""
        callback = AsyncMock()
        monitor = _make_monitor(on_event=callback)
        monitor.detector = MagicMock()
        monitor.detector.classify.return_value = DetectionResult(type="none")
        monitor.output_buffer.rolling_buffer = [f"line-{i}" for i in range(20)]

        await monitor._check_completion()

        # classify should be called with only lines 10-19
        expected_text = "\n".join([f"line-{i}" for i in range(10, 20)])
        monitor.detector.classify.assert_called_once_with(expected_text)

    async def test_fewer_than_10_lines_uses_all(self):
        """If buffer has fewer than 10 lines, all are used."""
        monitor = _make_monitor()
        monitor.detector = MagicMock()
        monitor.detector.classify.return_value = DetectionResult(type="none")
        monitor.output_buffer.rolling_buffer = ["a", "b", "c"]

        await monitor._check_completion()

        monitor.detector.classify.assert_called_once_with("a\nb\nc")

    async def test_no_callback_does_not_crash(self):
        """If on_event is None, _check_completion should not raise even on match."""
        monitor = _make_monitor(on_event=None)
        monitor.detector = MagicMock()
        monitor.detector.classify.return_value = DetectionResult(type="completion")
        monitor.output_buffer.rolling_buffer = ["task complete"]

        # Should not raise
        await monitor._check_completion()


# ---------------------------------------------------------------------------
# 6. Integration-style: start loop with output detection
# ---------------------------------------------------------------------------


class TestStartLoopIntegration:
    async def test_new_output_triggers_process_and_resets_idle(self):
        """Full loop: new lines trigger _process_output and reset idle."""
        callback = AsyncMock()
        cfg = {
            "poll_interval_ms": 10,
            "active_poll_interval_ms": 10,
            "idle_poll_interval_ms": 10,
            "completion_idle_threshold_s": 9999,
        }
        monitor = _make_monitor(on_event=callback, monitor_cfg=cfg)
        error_result = DetectionResult(type="error", matched_text="err", pattern="err")
        monitor.detector = MagicMock()
        monitor.detector.classify.return_value = error_result
        # Return output on first call, then empty
        monitor.output_buffer.get_new_lines = MagicMock(
            side_effect=[["Error: failure"], [], []]
        )

        async def stop_after():
            await asyncio.sleep(0.06)
            await monitor.stop()

        await asyncio.gather(monitor.start(), stop_after())

        callback.assert_awaited_once()
        assert monitor.active_output is True or monitor.idle_seconds > 0

    async def test_exception_in_loop_does_not_crash(self):
        """An exception during polling should be caught and not stop the loop."""
        cfg = {
            "poll_interval_ms": 10,
            "active_poll_interval_ms": 10,
            "idle_poll_interval_ms": 10,
            "completion_idle_threshold_s": 9999,
        }
        monitor = _make_monitor(monitor_cfg=cfg)
        call_count = 0

        def side_effect_fn(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("tmux pane gone")
            return []

        monitor.output_buffer.get_new_lines = MagicMock(side_effect=side_effect_fn)

        async def stop_after():
            await asyncio.sleep(0.08)
            await monitor.stop()

        # Should not raise despite the error on first call
        await asyncio.gather(monitor.start(), stop_after())
        # Loop should have continued after the exception
        assert call_count >= 2

    async def test_completion_check_fires_after_idle_threshold(self):
        """After active output followed by idle exceeding threshold, _check_completion runs."""
        callback = AsyncMock()
        cfg = {
            "poll_interval_ms": 10,
            "active_poll_interval_ms": 10,
            "idle_poll_interval_ms": 10,
            "completion_idle_threshold_s": 0.01,
        }
        monitor = _make_monitor(on_event=callback, monitor_cfg=cfg)
        completion_result = DetectionResult(type="completion", matched_text="done")
        monitor.detector = MagicMock()
        monitor.detector.classify.return_value = completion_result
        # First call returns output to set active_output = True,
        # then empty calls to accumulate idle time.
        monitor.output_buffer.get_new_lines = MagicMock(
            side_effect=[["task done"], [], [], [], [], [], []]
        )
        monitor.output_buffer.rolling_buffer = ["task done"]

        async def stop_after():
            await asyncio.sleep(0.12)
            await monitor.stop()

        await asyncio.gather(monitor.start(), stop_after())

        # on_event should have been called at least once from _process_output
        # and possibly again from _check_completion
        assert callback.await_count >= 1


# ---------------------------------------------------------------------------
# 7. Config defaults (missing keys)
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    def test_empty_config_uses_defaults(self):
        """An empty monitor_config dict should fall back to hardcoded defaults."""
        monitor = _make_monitor(monitor_cfg={})
        assert monitor._poll_default == 0.5
        assert monitor._poll_active == 0.3
        assert monitor._poll_idle == 2.0
        assert monitor._completion_threshold == 30
