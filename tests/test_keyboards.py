"""Tests for inline keyboard builders."""

from conductor.bot.keyboards import (
    permission_keyboard,
    completion_keyboard,
    rate_limit_keyboard,
    confirm_keyboard,
    undo_keyboard,
    status_keyboard,
    session_picker,
    suggestion_keyboard,
)


class TestKeyboards:
    def test_permission_keyboard(self):
        kb = permission_keyboard("sess-1")
        buttons = kb.inline_keyboard
        assert len(buttons) == 2  # 2 rows
        assert len(buttons[0]) == 2  # Yes, No
        assert len(buttons[1]) == 2  # Context, Custom
        assert "perm:yes:sess-1" in buttons[0][0].callback_data
        assert "perm:no:sess-1" in buttons[0][1].callback_data

    def test_completion_keyboard(self):
        kb = completion_keyboard("sess-1")
        buttons = kb.inline_keyboard
        assert len(buttons) == 2
        assert "comp:test:sess-1" in buttons[0][0].callback_data
        assert "comp:log:sess-1" in buttons[0][1].callback_data
        assert "comp:new:sess-1" in buttons[1][0].callback_data

    def test_rate_limit_keyboard(self):
        kb = rate_limit_keyboard("sess-1")
        buttons = kb.inline_keyboard
        assert len(buttons) == 2
        assert "rate:resume:sess-1" in buttons[0][0].callback_data
        assert "rate:auto:sess-1" in buttons[0][1].callback_data

    def test_confirm_keyboard(self):
        kb = confirm_keyboard("kill", "sess-1")
        buttons = kb.inline_keyboard
        assert len(buttons) == 1
        assert "confirm:yes:kill:sess-1" in buttons[0][0].callback_data
        assert "confirm:no:kill:sess-1" in buttons[0][1].callback_data

    def test_undo_keyboard(self):
        kb = undo_keyboard("action-123")
        buttons = kb.inline_keyboard
        assert len(buttons) == 1
        assert "undo:action-123" in buttons[0][0].callback_data

    def test_status_keyboard(self):
        kb = status_keyboard()
        buttons = kb.inline_keyboard
        assert len(buttons) == 1
        assert "status:refresh" in buttons[0][0].callback_data

    def test_session_picker(self):
        sessions = [
            ("id1", "🔵", "App1"),
            ("id2", "🟣", "App2"),
        ]
        kb = session_picker(sessions)
        buttons = kb.inline_keyboard
        assert len(buttons) == 2
        assert "pick:id1" in buttons[0][0].callback_data
        assert "🔵 App1" in buttons[0][0].text
        assert "pick:id2" in buttons[1][0].callback_data

    def test_session_picker_empty(self):
        kb = session_picker([])
        assert len(kb.inline_keyboard) == 0

    def test_suggestion_keyboard(self):
        suggestions = [
            {"label": "Run tests", "command": "pytest"},
            {"label": "Deploy", "command": "deploy.sh"},
        ]
        kb = suggestion_keyboard(suggestions, "sess-1")
        buttons = kb.inline_keyboard
        assert len(buttons) == 2
        assert "suggest:0:sess-1" in buttons[0][0].callback_data
        assert buttons[0][0].text == "Run tests"

    def test_suggestion_keyboard_max_3(self):
        suggestions = [
            {"label": f"Option {i}", "command": f"cmd-{i}"} for i in range(5)
        ]
        kb = suggestion_keyboard(suggestions, "sess-1")
        assert len(kb.inline_keyboard) == 3  # Max 3

    def test_suggestion_keyboard_missing_label(self):
        suggestions = [{"command": "test"}]
        kb = suggestion_keyboard(suggestions, "s1")
        assert kb.inline_keyboard[0][0].text == "Option 1"
