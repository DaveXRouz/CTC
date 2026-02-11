"""Tests for keyboard builders."""

from aiogram.types import ReplyKeyboardMarkup

from conductor.bot.keyboards import (
    main_menu_keyboard,
    permission_keyboard,
    completion_keyboard,
    rate_limit_keyboard,
    confirm_keyboard,
    undo_keyboard,
    status_keyboard,
    session_picker,
    suggestion_keyboard,
    main_action_menu,
    session_list_keyboard,
    session_action_keyboard,
    action_list_keyboard,
    action_session_picker,
    new_session_keyboard,
    directory_picker,
    browse_keyboard,
    auto_responder_keyboard,
    back_keyboard,
)
from conductor.db.models import Session


class TestMainMenuKeyboard:
    def test_returns_reply_keyboard(self):
        kb = main_menu_keyboard()
        assert isinstance(kb, ReplyKeyboardMarkup)

    def test_resize_and_persistent(self):
        kb = main_menu_keyboard()
        assert kb.resize_keyboard is True
        assert kb.is_persistent is True

    def test_layout(self):
        kb = main_menu_keyboard()
        rows = kb.keyboard
        assert len(rows) == 3
        assert [b.text for b in rows[0]] == ["Menu", "Status"]
        assert [b.text for b in rows[1]] == ["New Session", "Output"]
        assert [b.text for b in rows[2]] == ["Tokens", "Help"]


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
        assert len(buttons) == 2
        assert "status:refresh" in buttons[0][0].callback_data
        assert "menu:sessions" in buttons[0][1].callback_data
        assert "menu:actions" in buttons[1][0].callback_data
        assert "menu:new" in buttons[1][1].callback_data

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
        assert kb.inline_keyboard[0][0].text == "💡 Option 1"


def _make_session(
    id: str = "sess-1",
    number: int = 1,
    alias: str = "test-app",
    status: str = "running",
    color_emoji: str = "🔵",
) -> Session:
    return Session(
        id=id,
        number=number,
        alias=alias,
        type="claude-code",
        working_dir="/tmp",
        tmux_session="conductor-1",
        status=status,
        color_emoji=color_emoji,
    )


class TestMainActionMenu:
    def test_layout_4_rows(self):
        kb = main_action_menu()
        rows = kb.inline_keyboard
        assert len(rows) == 4

    def test_callback_data_prefixes(self):
        kb = main_action_menu()
        rows = kb.inline_keyboard
        # Row 0: Status, Sessions
        assert rows[0][0].callback_data == "menu:status"
        assert rows[0][1].callback_data == "menu:sessions"
        # Row 1: Actions, New Session
        assert rows[1][0].callback_data == "menu:actions"
        assert rows[1][1].callback_data == "menu:new"
        # Row 2: Auto-Responder, Tokens
        assert rows[2][0].callback_data == "menu:auto"
        assert rows[2][1].callback_data == "menu:tokens"
        # Row 3: Settings
        assert rows[3][0].callback_data == "menu:settings"


class TestSessionListKeyboard:
    def test_with_sessions(self):
        sessions = [_make_session("s1", 1, "app1"), _make_session("s2", 2, "app2")]
        kb = session_list_keyboard(sessions)
        rows = kb.inline_keyboard
        # 2 session rows + 1 footer row
        assert len(rows) == 3
        assert rows[0][0].callback_data == "sess:detail:s1"
        assert rows[1][0].callback_data == "sess:detail:s2"
        # Footer has New Session + Back
        assert rows[2][0].callback_data == "menu:new"
        assert rows[2][1].callback_data == "menu:main"

    def test_empty_list(self):
        kb = session_list_keyboard([])
        rows = kb.inline_keyboard
        # Only footer row
        assert len(rows) == 1
        assert rows[0][0].callback_data == "menu:new"

    def test_status_icons_in_label(self):
        session = _make_session(status="paused")
        kb = session_list_keyboard([session])
        label = kb.inline_keyboard[0][0].text
        assert "⏸" in label

    def test_running_status_icon(self):
        session = _make_session(status="running")
        kb = session_list_keyboard([session])
        label = kb.inline_keyboard[0][0].text
        assert "🟢" in label


class TestSessionActionKeyboard:
    def test_pause_button_when_running(self):
        session = _make_session(status="running")
        kb = session_action_keyboard(session)
        rows = kb.inline_keyboard
        # Row 1 has the toggle button
        toggle = rows[1][0]
        assert "Pause" in toggle.text
        assert toggle.callback_data == f"sess:pause:{session.id}"

    def test_resume_button_when_paused(self):
        session = _make_session(status="paused")
        kb = session_action_keyboard(session)
        rows = kb.inline_keyboard
        toggle = rows[1][0]
        assert "Resume" in toggle.text
        assert toggle.callback_data == f"sess:resume:{session.id}"

    def test_layout_4_rows(self):
        session = _make_session()
        kb = session_action_keyboard(session)
        assert len(kb.inline_keyboard) == 4

    def test_all_actions_present(self):
        session = _make_session()
        kb = session_action_keyboard(session)
        all_data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        sid = session.id
        assert f"sess:output:{sid}" in all_data
        assert f"sess:input:{sid}" in all_data
        assert f"sess:log:{sid}" in all_data
        assert f"sess:restart:{sid}" in all_data
        assert f"sess:kill:{sid}" in all_data
        assert f"sess:rename:{sid}" in all_data
        assert "menu:sessions" in all_data  # Back button


class TestActionListKeyboard:
    def test_layout_5_rows(self):
        kb = action_list_keyboard()
        assert len(kb.inline_keyboard) == 5

    def test_all_actions(self):
        kb = action_list_keyboard()
        all_data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        for action in (
            "output",
            "input",
            "pause",
            "resume",
            "restart",
            "kill",
            "log",
            "rename",
        ):
            assert f"act:{action}" in all_data

    def test_back_button(self):
        kb = action_list_keyboard()
        last_row = kb.inline_keyboard[-1]
        assert last_row[0].callback_data == "menu:main"


class TestActionSessionPicker:
    def test_callback_data_format(self):
        sessions = [_make_session("s1", 1, "app1"), _make_session("s2", 2, "app2")]
        kb = action_session_picker(sessions, "pause")
        rows = kb.inline_keyboard
        assert rows[0][0].callback_data == "apick:pause:s1"
        assert rows[1][0].callback_data == "apick:pause:s2"

    def test_back_button(self):
        kb = action_session_picker([_make_session()], "kill")
        last_row = kb.inline_keyboard[-1]
        assert last_row[0].callback_data == "menu:actions"

    def test_empty_sessions(self):
        kb = action_session_picker([], "output")
        # Only back button
        assert len(kb.inline_keyboard) == 1
        assert kb.inline_keyboard[0][0].callback_data == "menu:actions"

    def test_session_label_format(self):
        session = _make_session(color_emoji="🟣", number=3, alias="myapp")
        kb = action_session_picker([session], "input")
        label = kb.inline_keyboard[0][0].text
        assert "🟣" in label
        assert "#3" in label
        assert "myapp" in label


class TestNewSessionKeyboard:
    def test_layout(self):
        kb = new_session_keyboard()
        rows = kb.inline_keyboard
        assert len(rows) == 2

    def test_session_types(self):
        kb = new_session_keyboard()
        rows = kb.inline_keyboard
        assert rows[0][0].callback_data == "new:cc"
        assert rows[0][1].callback_data == "new:sh"

    def test_back_button(self):
        kb = new_session_keyboard()
        last_row = kb.inline_keyboard[-1]
        assert last_row[0].callback_data == "menu:main"


class TestAutoResponderKeyboard:
    def test_layout_3_rows(self):
        kb = auto_responder_keyboard()
        assert len(kb.inline_keyboard) == 3

    def test_buttons(self):
        kb = auto_responder_keyboard()
        rows = kb.inline_keyboard
        assert rows[0][0].callback_data == "auto:list"
        assert rows[1][0].callback_data == "auto:pause"
        assert rows[1][1].callback_data == "auto:resume"
        assert rows[2][0].callback_data == "menu:main"


class TestBackKeyboard:
    def test_default_target(self):
        kb = back_keyboard()
        assert len(kb.inline_keyboard) == 1
        assert kb.inline_keyboard[0][0].callback_data == "menu:main"

    def test_custom_target(self):
        kb = back_keyboard("sess:detail:abc-123")
        assert kb.inline_keyboard[0][0].callback_data == "sess:detail:abc-123"

    def test_button_text(self):
        kb = back_keyboard()
        assert "Back" in kb.inline_keyboard[0][0].text


class TestDirectoryPicker:
    def test_button_count_with_dirs(self):
        dirs = [(0, "myapp"), (1, "api"), (2, "frontend")]
        kb = directory_picker(dirs)
        rows = kb.inline_keyboard
        # 3 dir buttons + Browse + Custom + Back = 6
        assert len(rows) == 6

    def test_callback_data_format(self):
        dirs = [(0, "myapp"), (1, "api")]
        kb = directory_picker(dirs)
        rows = kb.inline_keyboard
        assert rows[0][0].callback_data == "dir:0"
        assert rows[1][0].callback_data == "dir:1"

    def test_labels_contain_dir_names(self):
        dirs = [(0, "myapp"), (1, "api")]
        kb = directory_picker(dirs)
        rows = kb.inline_keyboard
        assert "myapp" in rows[0][0].text
        assert "api" in rows[1][0].text

    def test_browse_button(self):
        dirs = [(0, "myapp")]
        kb = directory_picker(dirs)
        rows = kb.inline_keyboard
        browse_row = rows[-3]  # Third to last row
        assert browse_row[0].callback_data == "dir:browse"
        assert "Browse" in browse_row[0].text

    def test_custom_path_button(self):
        dirs = [(0, "myapp")]
        kb = directory_picker(dirs)
        rows = kb.inline_keyboard
        custom_row = rows[-2]  # Second to last row
        assert custom_row[0].callback_data == "dir:custom"
        assert "Custom" in custom_row[0].text

    def test_back_button(self):
        dirs = [(0, "myapp")]
        kb = directory_picker(dirs)
        rows = kb.inline_keyboard
        last_row = rows[-1]
        assert last_row[0].callback_data == "menu:new"
        assert "Back" in last_row[0].text

    def test_empty_dirs(self):
        kb = directory_picker([])
        rows = kb.inline_keyboard
        # Only Browse + Custom + Back = 3
        assert len(rows) == 3
        assert rows[0][0].callback_data == "dir:browse"
        assert rows[1][0].callback_data == "dir:custom"
        assert rows[2][0].callback_data == "menu:new"


class TestBrowseKeyboard:
    def test_subdirs_layout_2_per_row(self):
        kb = browse_keyboard(["dir1", "dir2", "dir3", "dir4"], "a1b2")
        rows = kb.inline_keyboard
        # 2 subdir rows + parent + action row = 4
        assert len(rows) == 4
        assert len(rows[0]) == 2  # dir1, dir2
        assert len(rows[1]) == 2  # dir3, dir4

    def test_odd_subdirs(self):
        kb = browse_keyboard(["dir1", "dir2", "dir3"], "a1b2")
        rows = kb.inline_keyboard
        # 2 subdir rows (2+1) + parent + action = 4
        assert len(rows) == 4
        assert len(rows[0]) == 2
        assert len(rows[1]) == 1  # dir3 alone

    def test_callback_data_format(self):
        kb = browse_keyboard(["alpha", "beta"], "f00d")
        rows = kb.inline_keyboard
        assert rows[0][0].callback_data == "br:f00d:0"
        assert rows[0][1].callback_data == "br:f00d:1"

    def test_parent_button(self):
        kb = browse_keyboard(["sub"], "abcd", can_go_up=True)
        rows = kb.inline_keyboard
        parent_row = rows[-2]  # Before action row
        assert parent_row[0].callback_data == "br:abcd:up"
        assert "Parent" in parent_row[0].text

    def test_no_parent_when_disabled(self):
        kb = browse_keyboard(["sub"], "abcd", can_go_up=False)
        rows = kb.inline_keyboard
        all_data = [btn.callback_data for row in rows for btn in row]
        assert "br:abcd:up" not in all_data

    def test_select_and_cancel_buttons(self):
        kb = browse_keyboard(["sub"], "abcd")
        rows = kb.inline_keyboard
        action_row = rows[-1]
        assert action_row[0].callback_data == "br:abcd:sel"
        assert action_row[1].callback_data == "br:abcd:cancel"
        assert "Select" in action_row[0].text
        assert "Cancel" in action_row[1].text

    def test_empty_subdirs_placeholder(self):
        kb = browse_keyboard([], "abcd")
        rows = kb.inline_keyboard
        assert rows[0][0].callback_data == "br:abcd:noop"
        assert "no subdirectories" in rows[0][0].text

    def test_max_8_subdirs(self):
        dirs = [f"d{i}" for i in range(12)]
        kb = browse_keyboard(dirs, "abcd")
        rows = kb.inline_keyboard
        # 4 subdir rows (8 items / 2) + parent + action = 6
        assert len(rows) == 6
        # Count subdir buttons
        subdir_buttons = [
            btn
            for row in rows[:-2]
            for btn in row
            if btn.callback_data.startswith("br:abcd:")
            and btn.callback_data.split(":")[-1].isdigit()
        ]
        assert len(subdir_buttons) == 8
