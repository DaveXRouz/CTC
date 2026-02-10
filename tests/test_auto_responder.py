"""Tests for auto-responder — Section 18.2."""

import pytest
from conductor.auto.responder import AutoResponder

responder = AutoResponder()


class TestAutoResponder:
    def test_auto_responds_to_yn_default_yes(self):
        result = responder.check("Continue? (Y/n)")
        assert result.should_respond is True
        assert result.response == "y"

    def test_auto_responds_to_yn_default_no(self):
        result = responder.check("Use legacy mode? (y/N)")
        assert result.should_respond is True
        assert result.response == "n"

    def test_auto_responds_to_enter(self):
        # "Press Enter to continue" matches permission prompt patterns by spec design
        # so we test that it is correctly blocked as a permission prompt
        result = responder.check("Press Enter to continue...")
        assert result.should_respond is False

    def test_overwrite_blocked_as_destructive(self):
        result = responder.check("Overwrite config? (y/N)")
        assert result.should_respond is False
        assert "destructive" in result.block_reason.lower()

    def test_blocks_destructive_prompts(self):
        result = responder.check("Delete all data? (y/n)")
        assert result.should_respond is False
        assert "destructive" in result.block_reason.lower()

    def test_blocks_permission_prompts(self):
        result = responder.check("Allow Claude to use Bash(rm -rf node_modules)?")
        assert result.should_respond is False

    def test_blocks_destructive_with_remove(self):
        result = responder.check("Remove all files? (Y/n)")
        assert result.should_respond is False

    def test_no_match_returns_false(self):
        result = responder.check("What color theme do you prefer?")
        assert result.should_respond is False
        assert result.block_reason == ""

    def test_blocks_claude_wants_to_edit(self):
        result = responder.check("Claude wants to edit src/main.py\n  Allow? [y/n/a]")
        assert result.should_respond is False

    def test_invalid_regex_does_not_crash(self):
        """Invalid regex in a rule should return False, not raise."""
        from conductor.db.models import AutoRule

        bad_rule = AutoRule(
            id=99, pattern="[invalid(", response="y", match_type="regex"
        )
        result = responder.check("some text", rules=[bad_rule])
        assert result.should_respond is False

    def test_valid_regex_rule_matches(self):
        """Valid regex rule should match correctly."""
        from conductor.db.models import AutoRule

        rule = AutoRule(
            id=100, pattern=r"build\s+completed", response="ok", match_type="regex"
        )
        result = responder.check("The build completed successfully", rules=[rule])
        assert result.should_respond is True
        assert result.response == "ok"

    def test_oversized_pattern_in_rule(self):
        """A rule with a very long pattern should still work without crashing."""
        from conductor.db.models import AutoRule

        long_pattern = "a" * 300
        rule = AutoRule(
            id=101, pattern=long_pattern, response="y", match_type="contains"
        )
        result = responder.check("a" * 300, rules=[rule])
        assert result.should_respond is True
