"""Push notification sender — batching queue + offline resilience."""

from __future__ import annotations

import asyncio
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from conductor.config import get_config
from conductor.security.redactor import redact_sensitive
from conductor.utils.logger import get_logger

logger = get_logger("conductor.bot.notifier")


class Notifier:
    """Notification sender with batching and offline resilience."""

    def __init__(self, bot: Bot, chat_id: int) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._batch_buffer: list[tuple[str, dict[str, Any]]] = []
        self._batch_task: asyncio.Task | None = None
        self._running = False
        self.is_online = True

        cfg = get_config()
        self._batch_window = cfg.batch_window_s

    async def start(self) -> None:
        """Start the batch flusher."""
        self._running = True
        self._batch_task = asyncio.create_task(self._batch_loop())

    async def stop(self) -> None:
        """Stop and flush remaining."""
        self._running = False
        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass
        await self._flush_batch()

    async def send(
        self,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        disable_notification: bool = False,
    ) -> int | None:
        """Send a notification. Returns message_id on success."""
        text = redact_sensitive(text)
        kwargs: dict[str, Any] = {"parse_mode": "HTML"}
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        if disable_notification:
            kwargs["disable_notification"] = True

        # If batch window is 0 or only one message, send immediately
        if self._batch_window <= 0:
            return await self._send_direct(text, kwargs)

        self._batch_buffer.append((text, kwargs))
        return None

    async def send_immediate(
        self,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        disable_notification: bool = False,
    ) -> int | None:
        """Send immediately, bypassing batch queue."""
        text = redact_sensitive(text)
        kwargs: dict[str, Any] = {"parse_mode": "HTML"}
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        if disable_notification:
            kwargs["disable_notification"] = True
        return await self._send_direct(text, kwargs)

    async def _send_direct(self, text: str, kwargs: dict) -> int | None:
        """Try to send; queue if offline."""
        try:
            msg = await self.bot.send_message(self.chat_id, text, **kwargs)
            self.is_online = True
            await self._flush_offline_queue()
            return msg.message_id
        except Exception as e:
            self.is_online = False
            await self._queue.put((text, kwargs))
            logger.warning(
                f"Queued notification (offline): {e}. Queue: {self._queue.qsize()}"
            )
            return None

    async def _batch_loop(self) -> None:
        """Flush batch buffer every batch_window seconds."""
        while self._running:
            await asyncio.sleep(self._batch_window)
            await self._flush_batch()

    async def _flush_batch(self) -> None:
        """Send all buffered messages."""
        if not self._batch_buffer:
            return

        items = self._batch_buffer[:]
        self._batch_buffer.clear()

        if len(items) == 1:
            text, kwargs = items[0]
            await self._send_direct(text, kwargs)
        else:
            # Combine into one message
            combined = f"📬 {len(items)} Updates:\n\n"
            combined += "\n\n".join(text for text, _ in items)
            # Use kwargs from the first item as base
            kwargs = items[0][1].copy()
            kwargs.pop("reply_markup", None)
            await self._send_direct(combined, kwargs)

    async def _flush_offline_queue(self) -> None:
        """Send all queued messages from offline period."""
        while not self._queue.empty():
            text, kwargs = await self._queue.get()
            try:
                await self.bot.send_message(self.chat_id, text, **kwargs)
                await asyncio.sleep(0.1)  # Respect rate limits
            except Exception:
                await self._queue.put((text, kwargs))
                break

    async def connectivity_check(self) -> None:
        """Background task to check if Telegram is reachable."""
        while self._running:
            if not self.is_online:
                try:
                    await self.bot.get_me()
                    self.is_online = True
                    await self._flush_offline_queue()
                except Exception:
                    pass
            await asyncio.sleep(30)
