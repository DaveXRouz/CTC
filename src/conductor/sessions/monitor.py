"""Output monitor — async polling loop for tmux pane output."""

from __future__ import annotations

import asyncio
from datetime import datetime

import libtmux

from conductor.config import get_config
from conductor.sessions.output_buffer import OutputBuffer
from conductor.sessions.detector import PatternDetector, DetectionResult
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
        self._running: bool = False

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
        """Start the monitoring loop."""
        self._running = True
        logger.info(
            f"Monitor started for session #{self.session.number} '{self.session.alias}'"
        )

        while self._running:
            try:
                new_lines = self.output_buffer.get_new_lines(self.pane)

                if new_lines:
                    self.idle_seconds = 0
                    self.active_output = True
                    await self._process_output(new_lines)
                else:
                    self.idle_seconds += self.poll_interval

                    if (
                        self.active_output
                        and self.idle_seconds >= self._completion_threshold
                    ):
                        self.active_output = False
                        await self._check_completion()

            except Exception as e:
                logger.error(f"Monitor error for {self.session.alias}: {e}")

            await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        """Stop the monitoring loop."""
        self._running = False
        logger.info(f"Monitor stopped for session #{self.session.number}")

    async def _process_output(self, lines: list[str]) -> None:
        """Analyze new output lines for patterns."""
        text = "\n".join(lines)
        result = self.detector.classify(text)

        if result.type != "none" and self.on_event:
            self.session.last_activity = datetime.now().isoformat()
            await self.on_event(self.session, result, lines)

    async def _check_completion(self) -> None:
        """Check if a task has completed (idle after active output)."""
        recent = self.output_buffer.rolling_buffer[-10:]
        if not recent:
            return

        text = "\n".join(recent)
        result = self.detector.classify(text)
        if result.type == "completion" and self.on_event:
            await self.on_event(self.session, result, recent)
