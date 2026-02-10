"""Tests for Notifier — batching, offline queue, retry, redaction, lifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch


from conductor.bot.notifier import Notifier


def _make_config(batch_window_s=0):
    """Create a mock config with controllable batch_window_s."""
    cfg = MagicMock()
    cfg.batch_window_s = batch_window_s
    return cfg


def _make_bot(message_id=42):
    """Create a mock aiogram.Bot whose send_message returns a message with message_id."""
    bot = AsyncMock()
    msg = MagicMock()
    msg.message_id = message_id
    bot.send_message.return_value = msg
    bot.get_me.return_value = MagicMock()
    return bot


CHAT_ID = 123456


class TestSendImmediate:
    """send_immediate bypasses batch buffer and sends directly."""

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=5)
    )
    async def test_send_immediate_bypasses_batch(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        result = await notifier.send_immediate("urgent message")
        assert result == 42
        bot.send_message.assert_awaited_once()
        # Buffer should be empty -- nothing was batched
        assert len(notifier._batch_buffer) == 0

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_send_immediate_with_reply_markup(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        markup = MagicMock()
        await notifier.send_immediate("prompt", reply_markup=markup)
        call_kwargs = bot.send_message.call_args
        assert (
            call_kwargs.kwargs.get("reply_markup") is markup
            or call_kwargs[1].get("reply_markup") is markup
        )

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_send_immediate_with_disable_notification(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        await notifier.send_immediate("silent", disable_notification=True)
        call_kwargs = bot.send_message.call_args
        assert (
            call_kwargs.kwargs.get("disable_notification") is True
            or call_kwargs[1].get("disable_notification") is True
        )


class TestSendWithZeroBatchWindow:
    """When batch_window_s == 0, send() should dispatch immediately."""

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_send_immediate_when_window_zero(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        result = await notifier.send("hello")
        assert result == 42
        bot.send_message.assert_awaited_once()

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_send_returns_message_id_when_window_zero(self, _mock_cfg):
        bot = _make_bot(message_id=99)
        notifier = Notifier(bot, CHAT_ID)
        result = await notifier.send("test")
        assert result == 99


class TestSendWithBatchWindow:
    """When batch_window_s > 0, send() should buffer messages."""

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=5)
    )
    async def test_send_buffers_when_window_positive(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        result = await notifier.send("buffered message")
        assert result is None
        bot.send_message.assert_not_awaited()
        assert len(notifier._batch_buffer) == 1

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=5)
    )
    async def test_send_buffers_multiple_messages(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        await notifier.send("msg1")
        await notifier.send("msg2")
        await notifier.send("msg3")
        assert len(notifier._batch_buffer) == 3
        bot.send_message.assert_not_awaited()


class TestRedaction:
    """send and send_immediate should redact sensitive data before sending."""

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_send_redacts_api_key(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        await notifier.send("key is sk-ant-api03-abcdefghijklmnopqrstuvwx")
        sent_text = bot.send_message.call_args[0][1]
        assert "sk-ant" not in sent_text
        assert "[REDACTED" in sent_text

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_send_immediate_redacts_api_key(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        await notifier.send_immediate("key is sk-ant-api03-abcdefghijklmnopqrstuvwx")
        sent_text = bot.send_message.call_args[0][1]
        assert "sk-ant" not in sent_text
        assert "[REDACTED" in sent_text

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=5)
    )
    async def test_send_redacts_before_buffering(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        await notifier.send("Bearer eyJhbGciOiJIUzI1NiJ9.secret")
        buffered_text = notifier._batch_buffer[0][0]
        assert "eyJ" not in buffered_text
        assert "Bearer [REDACTED]" in buffered_text


class TestFlushBatch:
    """_flush_batch combines plain messages and sends keyboard messages separately."""

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=5)
    )
    async def test_flush_single_message(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        notifier._batch_buffer.append(("single message", {"parse_mode": "HTML"}))
        await notifier._flush_batch()
        bot.send_message.assert_awaited_once()
        sent_text = bot.send_message.call_args[0][1]
        assert sent_text == "single message"

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=5)
    )
    async def test_flush_combines_plain_messages(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        notifier._batch_buffer.append(("msg1", {"parse_mode": "HTML"}))
        notifier._batch_buffer.append(("msg2", {"parse_mode": "HTML"}))
        notifier._batch_buffer.append(("msg3", {"parse_mode": "HTML"}))
        await notifier._flush_batch()
        # All plain messages combined into one send
        bot.send_message.assert_awaited_once()
        sent_text = bot.send_message.call_args[0][1]
        assert "3 Updates" in sent_text
        assert "msg1" in sent_text
        assert "msg2" in sent_text
        assert "msg3" in sent_text

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=5)
    )
    async def test_flush_keyboard_messages_sent_separately(self, _mock_cfg):
        """C4 fix: messages with reply_markup are not combined."""
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        markup1 = MagicMock()
        markup2 = MagicMock()
        notifier._batch_buffer.append(
            ("kb1", {"parse_mode": "HTML", "reply_markup": markup1})
        )
        notifier._batch_buffer.append(
            ("kb2", {"parse_mode": "HTML", "reply_markup": markup2})
        )
        await notifier._flush_batch()
        # Each keyboard message sent individually
        assert bot.send_message.await_count == 2

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=5)
    )
    async def test_flush_mixed_plain_and_keyboard(self, _mock_cfg):
        """C4 fix: plain messages combined, keyboard messages sent separately."""
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        markup = MagicMock()
        notifier._batch_buffer.append(("plain1", {"parse_mode": "HTML"}))
        notifier._batch_buffer.append(("plain2", {"parse_mode": "HTML"}))
        notifier._batch_buffer.append(
            ("kb1", {"parse_mode": "HTML", "reply_markup": markup})
        )
        await notifier._flush_batch()
        # 1 combined plain + 1 keyboard = 2 sends
        assert bot.send_message.await_count == 2
        # First call should be the combined plain message
        first_text = bot.send_message.call_args_list[0][0][1]
        assert "2 Updates" in first_text
        assert "plain1" in first_text
        assert "plain2" in first_text
        # Second call should be the keyboard message
        second_text = bot.send_message.call_args_list[1][0][1]
        assert second_text == "kb1"

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=5)
    )
    async def test_flush_clears_buffer(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        notifier._batch_buffer.append(("msg", {"parse_mode": "HTML"}))
        await notifier._flush_batch()
        assert len(notifier._batch_buffer) == 0

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=5)
    )
    async def test_flush_empty_buffer_is_noop(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        await notifier._flush_batch()
        bot.send_message.assert_not_awaited()

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=5)
    )
    async def test_flush_single_plain_among_keyboards(self, _mock_cfg):
        """A single plain message among keyboard messages is sent as-is (not combined)."""
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        markup = MagicMock()
        notifier._batch_buffer.append(("plain1", {"parse_mode": "HTML"}))
        notifier._batch_buffer.append(
            ("kb1", {"parse_mode": "HTML", "reply_markup": markup})
        )
        await notifier._flush_batch()
        assert bot.send_message.await_count == 2
        # The single plain message should be sent without "Updates" prefix
        first_text = bot.send_message.call_args_list[0][0][1]
        assert first_text == "plain1"


class TestOfflineQueueAndRetry:
    """Offline queueing with retry limit (C5 fix)."""

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_send_failure_queues_message(self, _mock_cfg):
        bot = _make_bot()
        bot.send_message.side_effect = Exception("Network error")
        notifier = Notifier(bot, CHAT_ID)
        result = await notifier.send("test")
        assert result is None
        assert notifier.is_online is False
        assert notifier._queue.qsize() == 1

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_send_failure_sets_offline(self, _mock_cfg):
        bot = _make_bot()
        bot.send_message.side_effect = Exception("Timeout")
        notifier = Notifier(bot, CHAT_ID)
        await notifier.send("msg")
        assert notifier.is_online is False

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_successful_send_sets_online(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        notifier.is_online = False
        await notifier.send("msg")
        assert notifier.is_online is True

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_offline_queue_flushed_on_success(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        # Manually enqueue an offline message
        await notifier._queue.put(("queued msg", {"parse_mode": "HTML"}, 1))
        # Successful send triggers flush
        await notifier.send("new msg")
        assert notifier._queue.qsize() == 0
        # 1 for direct send + 1 for queued message = 2
        assert bot.send_message.await_count == 2

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_message_discarded_after_max_retries(self, _mock_cfg):
        """C5 fix: messages are discarded after 5 retries."""
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        # Put a message at max retries (5) into the queue
        await notifier._queue.put(("doomed msg", {"parse_mode": "HTML"}, 5))
        # Flush will try to send, fail, and discard because retries == max_retries
        bot.send_message.side_effect = Exception("Still broken")
        await notifier._flush_offline_queue()
        # Message should be gone (discarded, not re-queued)
        assert notifier._queue.qsize() == 0

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_message_requeued_under_max_retries(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        await notifier._queue.put(("retry msg", {"parse_mode": "HTML"}, 3))
        bot.send_message.side_effect = Exception("Temporary failure")
        await notifier._flush_offline_queue()
        # Message should be re-queued with retries incremented
        assert notifier._queue.qsize() == 1
        text, kwargs, retries = await notifier._queue.get()
        assert retries == 4

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_flush_offline_stops_on_first_failure(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        await notifier._queue.put(("msg1", {"parse_mode": "HTML"}, 1))
        await notifier._queue.put(("msg2", {"parse_mode": "HTML"}, 1))
        # First call succeeds, second fails
        msg_mock = MagicMock()
        msg_mock.message_id = 1
        bot.send_message.side_effect = [msg_mock, Exception("Fail")]
        await notifier._flush_offline_queue()
        # msg2 should still be in the queue (re-queued with retries=2)
        assert notifier._queue.qsize() == 1


class TestConnectivityCheck:
    """connectivity_check polls get_me when offline."""

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_connectivity_check_calls_get_me_when_offline(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        notifier._running = True
        notifier.is_online = False

        # Run one iteration by patching sleep to stop the loop
        call_count = 0

        async def stop_after_one(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                notifier._running = False

        with patch("conductor.bot.notifier.asyncio.sleep", side_effect=stop_after_one):
            await notifier.connectivity_check()

        bot.get_me.assert_awaited_once()
        assert notifier.is_online is True

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_connectivity_check_skips_when_online(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        notifier._running = True
        notifier.is_online = True

        call_count = 0

        async def stop_after_one(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                notifier._running = False

        with patch("conductor.bot.notifier.asyncio.sleep", side_effect=stop_after_one):
            await notifier.connectivity_check()

        bot.get_me.assert_not_awaited()

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_connectivity_check_handles_get_me_failure(self, _mock_cfg):
        bot = _make_bot()
        bot.get_me.side_effect = Exception("Still offline")
        notifier = Notifier(bot, CHAT_ID)
        notifier._running = True
        notifier.is_online = False

        call_count = 0

        async def stop_after_one(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                notifier._running = False

        with patch("conductor.bot.notifier.asyncio.sleep", side_effect=stop_after_one):
            await notifier.connectivity_check()

        bot.get_me.assert_awaited_once()
        # Should remain offline after get_me failure
        assert notifier.is_online is False


class TestStartStopLifecycle:
    """start/stop manage the batch loop task."""

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=1)
    )
    async def test_start_sets_running_and_creates_task(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        assert notifier._running is False
        assert notifier._batch_task is None
        await notifier.start()
        assert notifier._running is True
        assert notifier._batch_task is not None
        # Clean up
        await notifier.stop()

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=1)
    )
    async def test_stop_cancels_task_and_flushes(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        await notifier.start()
        # Add a message to the buffer to verify flush on stop
        notifier._batch_buffer.append(("pending", {"parse_mode": "HTML"}))
        await notifier.stop()
        assert notifier._running is False
        # Buffer should be flushed
        assert len(notifier._batch_buffer) == 0
        # The pending message should have been sent
        bot.send_message.assert_awaited()

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=1)
    )
    async def test_stop_without_start_is_safe(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        # Should not raise even if never started
        await notifier.stop()
        assert notifier._running is False

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=1)
    )
    async def test_stop_flushes_empty_buffer_gracefully(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        await notifier.start()
        await notifier.stop()
        bot.send_message.assert_not_awaited()


class TestHTMLParseMode:
    """All sends should include parse_mode=HTML."""

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_send_includes_html_parse_mode(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        await notifier.send("test")
        call_kwargs = bot.send_message.call_args
        assert (
            call_kwargs.kwargs.get("parse_mode") == "HTML"
            or call_kwargs[1].get("parse_mode") == "HTML"
        )

    @patch(
        "conductor.bot.notifier.get_config", return_value=_make_config(batch_window_s=0)
    )
    async def test_send_immediate_includes_html_parse_mode(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        await notifier.send_immediate("test")
        call_kwargs = bot.send_message.call_args
        assert (
            call_kwargs.kwargs.get("parse_mode") == "HTML"
            or call_kwargs[1].get("parse_mode") == "HTML"
        )


class TestInitialization:
    """Constructor reads batch_window_s from config."""

    @patch(
        "conductor.bot.notifier.get_config",
        return_value=_make_config(batch_window_s=10),
    )
    def test_init_reads_batch_window_from_config(self, _mock_cfg):
        bot = _make_bot()
        notifier = Notifier(bot, CHAT_ID)
        assert notifier._batch_window == 10
        assert notifier.chat_id == CHAT_ID
        assert notifier.bot is bot
        assert notifier.is_online is True
        assert notifier._running is False
        assert notifier._max_retries == 5
