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
        self._queue: asyncio.Queue[tuple[str, dict[str, Any], int]] = asyncio.Queue()
        self._max_retries = 5
        self._batch_buffer: list[tuple[str, dict[str, Any]]] = []
        self._batch_task: asyncio.Task | None = None
        self._running = False
        self.is_online = True

        cfg = get_config()
        self._batch_window = cfg.batch_window_s

    async def start(self) -> None:
        """Start the background batch flusher loop."""
        self._running = True
        self._batch_task = asyncio.create_task(self._batch_loop())

    async def stop(self) -> None:
        """Stop the batch flusher and flush any remaining buffered messages."""
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
        """Queue a notification for batched delivery.

        Messages are buffered and combined if multiple arrive within the batch
        window. If the batch window is 0, sends immediately.

        Args:
            text: Message text (HTML). Sensitive data is auto-redacted.
            reply_markup: Optional inline keyboard.
            disable_notification: If True, send silently.

        Returns:
            Message ID if sent immediately, or None if batched for later.
        """
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
        """Send a notification immediately, bypassing the batch queue.

        Use this for urgent notifications (permission prompts, errors).

        Args:
            text: Message text (HTML). Sensitive data is auto-redacted.
            reply_markup: Optional inline keyboard.
            disable_notification: If True, send silently.

        Returns:
            Message ID on success, or None if offline (message queued).
        """
        text = redact_sensitive(text)
        kwargs: dict[str, Any] = {"parse_mode": "HTML"}
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        if disable_notification:
            kwargs["disable_notification"] = True
        return await self._send_direct(text, kwargs)

    async def _send_direct(self, text: str, kwargs: dict) -> int | None:
        """Attempt direct send to Telegram with 429 backoff; queue if offline."""
        backoff = 1.0
        max_backoff = 30.0
        for attempt in range(4):
            try:
                msg = await self.bot.send_message(self.chat_id, text, **kwargs)
                self.is_online = True
                await self._flush_offline_queue()
                return msg.message_id
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Too Many Requests" in err_str:
                    logger.warning(
                        f"Telegram 429 — backoff {backoff}s (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)
                    continue
                self.is_online = False
                await self._queue.put((text, kwargs, 1))
                logger.warning(
                    f"Queued notification (offline): {e}. Queue: {self._queue.qsize()}"
                )
                return None
        # All retries exhausted
        await self._queue.put((text, kwargs, 1))
        return None

    async def _batch_loop(self) -> None:
        """Background loop that flushes the batch buffer at regular intervals."""
        while self._running:
            await asyncio.sleep(self._batch_window)
            await self._flush_batch()

    async def _flush_batch(self) -> None:
        """Flush all buffered messages.

        Single messages are sent as-is. Multiple messages are combined into
        one message prefixed with the update count.
        """
        if not self._batch_buffer:
            return

        items = self._batch_buffer[:]
        self._batch_buffer.clear()

        if len(items) == 1:
            text, kwargs = items[0]
            await self._send_direct(text, kwargs)
        else:
            # C4: Send messages with keyboards separately to preserve reply_markup
            keyboard_items = [(t, k) for t, k in items if "reply_markup" in k]
            plain_items = [(t, k) for t, k in items if "reply_markup" not in k]

            # Combine plain text messages into one
            if plain_items:
                if len(plain_items) == 1:
                    await self._send_direct(plain_items[0][0], plain_items[0][1])
                else:
                    combined = f"📬 {len(plain_items)} Updates:\n\n"
                    combined += "\n\n".join(text for text, _ in plain_items)
                    kwargs = plain_items[0][1].copy()
                    await self._send_direct(combined, kwargs)

            # Send keyboard messages individually
            for text, kwargs in keyboard_items:
                await self._send_direct(text, kwargs)

    async def _flush_offline_queue(self) -> None:
        """Send all queued messages accumulated during offline periods.

        Processes the queue sequentially with a 100ms delay between sends
        to respect Telegram rate limits. Stops on first failure.
        """
        while not self._queue.empty():
            text, kwargs, retries = await self._queue.get()
            try:
                await self.bot.send_message(self.chat_id, text, **kwargs)
                await asyncio.sleep(0.1)  # Respect rate limits
            except Exception:
                if retries < self._max_retries:
                    await self._queue.put((text, kwargs, retries + 1))
                else:
                    logger.warning(f"Discarding message after {retries} retries")
                break

    async def connectivity_check(self) -> None:
        """Background task that checks Telegram connectivity every 30 seconds.

        When the bot is offline, periodically calls ``get_me()`` to detect
        when connectivity returns, then flushes the offline queue.
        """
        while self._running:
            if not self.is_online:
                try:
                    await self.bot.get_me()
                    self.is_online = True
                    await self._flush_offline_queue()
                except Exception:
                    pass
            await asyncio.sleep(30)
