"""Tests for Mac sleep/wake detection handler."""

import asyncio
import pytest
from unittest.mock import AsyncMock

from conductor.utils.sleep_handler import SleepHandler


class TestSleepHandler:
    async def test_start_stop(self):
        handler = SleepHandler()
        await handler.start()
        assert handler._task is not None
        await handler.stop()
        assert handler._task.done()

    async def test_stop_without_start(self):
        handler = SleepHandler()
        await handler.stop()  # Should not raise

    async def test_wake_callback_called(self):
        callback = AsyncMock()
        handler = SleepHandler(
            on_wake_callback=callback,
            check_interval=0.05,
            sleep_threshold=0.1,
        )
        # Simulate a time gap by setting last_check far in the past
        await handler.start()
        # Manually trigger wake detection
        handler._last_check -= 10  # Simulate 10 second gap
        await asyncio.sleep(0.15)
        await handler.stop()
        callback.assert_called_once()
        # sleep_duration should be approximately 10 seconds minus check interval
        args = callback.call_args[0]
        assert args[0] > 5  # At least 5 seconds

    async def test_no_callback_on_normal_interval(self):
        callback = AsyncMock()
        handler = SleepHandler(
            on_wake_callback=callback,
            check_interval=0.05,
            sleep_threshold=10.0,  # High threshold
        )
        await handler.start()
        await asyncio.sleep(0.15)
        await handler.stop()
        callback.assert_not_called()

    async def test_wake_callback_error_handled(self):
        async def bad_callback(duration):
            raise RuntimeError("callback failed")

        handler = SleepHandler(
            on_wake_callback=bad_callback,
            check_interval=0.05,
            sleep_threshold=0.1,
        )
        await handler.start()
        handler._last_check -= 10
        await asyncio.sleep(0.15)
        await handler.stop()
        # Should not raise

    async def test_no_callback_configured(self):
        handler = SleepHandler(
            on_wake_callback=None,
            check_interval=0.05,
            sleep_threshold=0.1,
        )
        await handler.start()
        handler._last_check -= 10
        await asyncio.sleep(0.15)
        await handler.stop()
        # Should not raise
