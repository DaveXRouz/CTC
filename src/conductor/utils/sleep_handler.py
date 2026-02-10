"""Mac sleep/wake detection — recalculate timers + health check on wake."""

from __future__ import annotations

import asyncio
import time

from conductor.utils.logger import get_logger

logger = get_logger("conductor.utils.sleep")


class SleepHandler:
    """Detect Mac sleep/wake by monitoring time gaps."""

    def __init__(
        self,
        on_wake_callback=None,
        check_interval: float = 5.0,
        sleep_threshold: float = 15.0,
    ) -> None:
        self._on_wake = on_wake_callback
        self._check_interval = check_interval
        self._sleep_threshold = sleep_threshold
        self._task: asyncio.Task | None = None
        self._last_check: float = time.monotonic()

    async def start(self) -> None:
        """Start the background sleep detection loop."""
        self._last_check = time.monotonic()
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Sleep handler started")

    async def stop(self) -> None:
        """Stop the sleep detection loop and cancel the background task."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Sleep handler stopped")

    async def _monitor_loop(self) -> None:
        """Background loop that detects time gaps indicating macOS sleep.

        Compares elapsed real time against the expected check interval.
        A gap exceeding ``sleep_threshold`` triggers wake handling.
        """
        while True:
            await asyncio.sleep(self._check_interval)
            now = time.monotonic()
            elapsed = now - self._last_check

            if elapsed > self._sleep_threshold:
                sleep_duration = elapsed - self._check_interval
                logger.warning(
                    f"Mac wake detected — system was asleep for ~{sleep_duration:.0f}s"
                )
                await self._handle_wake(sleep_duration)

            self._last_check = now

    async def _handle_wake(self, sleep_duration: float) -> None:
        """Handle a detected wake event.

        Args:
            sleep_duration: Estimated seconds the system was asleep.
        """
        if self._on_wake:
            try:
                await self._on_wake(sleep_duration)
            except Exception as e:
                logger.error(f"Wake callback error: {e}")
