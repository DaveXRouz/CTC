"""Global error handler — Section 17.2."""

from __future__ import annotations

import asyncio

from conductor.utils.logger import get_logger

logger = get_logger("conductor.utils.errors")


class ErrorHandler:
    """Global error handler — log, count, and escalate repeated errors."""

    def __init__(self, notifier=None) -> None:
        self.notifier = notifier
        self.error_counts: dict[str, int] = {}
        self._reset_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start periodic error count reset."""
        self._reset_task = asyncio.create_task(self._periodic_reset())

    async def stop(self) -> None:
        if self._reset_task:
            self._reset_task.cancel()

    async def handle(self, error: Exception, context: str) -> None:
        """Global error handler — log, count, and decide recovery."""
        error_type = type(error).__name__
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

        logger.error(f"[{context}] {error_type}: {error}")

        if self.error_counts[error_type] >= 5:
            await self._escalate(error_type, context)

    async def _escalate(self, error_type: str, context: str) -> None:
        """Alert user about repeated errors."""
        if self.notifier:
            try:
                await self.notifier.send_immediate(
                    f"🔴 Repeated error in {context}: {error_type} "
                    f"({self.error_counts[error_type]} times). "
                    f"Check daemon logs: ~/.conductor/conductor.log"
                )
            except Exception:
                logger.critical(f"Cannot notify user about {error_type}")

    async def _periodic_reset(self) -> None:
        """Reset error counts every 5 minutes."""
        while True:
            await asyncio.sleep(300)
            self.error_counts.clear()
