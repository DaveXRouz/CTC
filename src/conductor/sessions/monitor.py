"""Output monitor — async polling loop for tmux pane output."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime

import libtmux

from conductor.config import get_config
from conductor.sessions.output_buffer import OutputBuffer
from conductor.sessions.detector import PatternDetector
from conductor.db.models import Session
from conductor.utils.logger import get_logger

logger = get_logger("conductor.sessions.monitor")


class OutputMonitor:
    """Watch a tmux pane for output and detect patterns."""

    def __init__(
        self,
        pane: libtmux.Pane,
        session: Session,
        on_event=None,
    ) -> None:
        self.pane = pane
        self.session = session
        self.on_event = on_event  # async callback(session, detection_result, lines)

        self.output_buffer = OutputBuffer()
        self.detector = PatternDetector()

        self.idle_seconds: float = 0
        self.active_output: bool = False
        self._stop_event = asyncio.Event()
        self._last_poll_time: float = 0.0

        cfg = get_config().monitor_config
        self._poll_default = cfg.get("poll_interval_ms", 500) / 1000
        self._poll_active = cfg.get("active_poll_interval_ms", 300) / 1000
        self._poll_idle = cfg.get("idle_poll_interval_ms", 2000) / 1000
        self._completion_threshold = cfg.get("completion_idle_threshold_s", 30)

    @property
    def poll_interval(self) -> float:
        if self.session.status == "paused":
            return 5.0
        elif self.idle_seconds > 300:
            return self._poll_idle
        elif self.active_output:
            return self._poll_active
        return self._poll_default

    async def start(self) -> None:
        """Start the async monitoring loop.

        Polls the tmux pane at adaptive intervals and fires ``on_event``
        when patterns are detected in new output.
        """
        self._stop_event.clear()
        logger.info(
            f"Monitor started for session #{self.session.number} '{self.session.alias}'"
        )

        while not self._stop_event.is_set():
            self._last_poll_time = time.monotonic()
            try:
                new_lines = self.output_buffer.get_new_lines(self.pane)

                if new_lines:
                    self.idle_seconds = 0
                    self.active_output = True
                    await self._process_output(new_lines)
                else:
                    # C14: Use monotonic time delta for accurate idle tracking
                    self.idle_seconds += (
                        time.monotonic() - self._last_poll_time + self.poll_interval
                    )

                    if (
                        self.active_output
                        and self.idle_seconds >= self._completion_threshold
                    ):
                        self.active_output = False
                        await self._check_completion()

            except Exception as e:
                logger.error(f"Monitor error for {self.session.alias}: {e}")

            # C1: Use event wait so stop() can interrupt sleep immediately
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.poll_interval
                )
            except asyncio.TimeoutError:
                pass

    async def stop(self) -> None:
        """Stop the monitoring loop (interrupts sleep immediately)."""
        self._stop_event.set()
        logger.info(f"Monitor stopped for session #{self.session.number}")

    async def _process_output(self, lines: list[str]) -> None:
        """Analyze new output lines for patterns and fire event callback.

        Args:
            lines: New lines captured from the pane.
        """
        text = "\n".join(lines)
        result = self.detector.classify(text)

        if result.type != "none" and self.on_event:
            self.session.last_activity = datetime.now().isoformat()
            await self.on_event(self.session, result, lines)

    async def _check_completion(self) -> None:
        """Check recent output for completion patterns after an idle period.

        Called when the monitor transitions from active to idle state.
        """
        recent = self.output_buffer.rolling_buffer[-10:]
        if not recent:
            return

        text = "\n".join(recent)
        result = self.detector.classify(text)
        if result.type == "completion" and self.on_event:
            await self.on_event(self.session, result, recent)
