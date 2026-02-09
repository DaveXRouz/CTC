"""Tests for global error handler."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from conductor.utils.errors import ErrorHandler


class TestErrorHandler:
    async def test_handle_logs_error(self):
        handler = ErrorHandler()
        err = ValueError("test error")
        await handler.handle(err, "test_context")
        assert handler.error_counts["ValueError"] == 1

    async def test_handle_increments_count(self):
        handler = ErrorHandler()
        for _ in range(3):
            await handler.handle(ValueError("err"), "ctx")
        assert handler.error_counts["ValueError"] == 3

    async def test_escalate_after_5(self):
        notifier = AsyncMock()
        handler = ErrorHandler(notifier=notifier)
        for i in range(5):
            await handler.handle(RuntimeError("boom"), "test")
        notifier.send_immediate.assert_called_once()
        call_args = notifier.send_immediate.call_args[0][0]
        assert "Repeated error" in call_args
        assert "RuntimeError" in call_args

    async def test_escalate_without_notifier(self):
        handler = ErrorHandler(notifier=None)
        for i in range(5):
            await handler.handle(RuntimeError("boom"), "test")
        # Should not raise — just logs

    async def test_escalate_notifier_failure(self):
        notifier = AsyncMock()
        notifier.send_immediate.side_effect = Exception("network error")
        handler = ErrorHandler(notifier=notifier)
        for i in range(5):
            await handler.handle(TypeError("boom"), "test")
        # Should not raise

    async def test_different_error_types_tracked_separately(self):
        handler = ErrorHandler()
        await handler.handle(ValueError("v"), "ctx")
        await handler.handle(TypeError("t"), "ctx")
        assert handler.error_counts["ValueError"] == 1
        assert handler.error_counts["TypeError"] == 1

    async def test_start_stop(self):
        handler = ErrorHandler()
        await handler.start()
        assert handler._reset_task is not None
        await handler.stop()
        # After cancel, the task is in cancelling state; give event loop a tick
        await asyncio.sleep(0.01)
        assert handler._reset_task.done()

    async def test_stop_no_task(self):
        handler = ErrorHandler()
        await handler.stop()  # Should not raise
