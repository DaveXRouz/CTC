"""Tests for auto-responder matching logic — covers _matches and all match types."""

from conductor.auto.responder import AutoResponder
from conductor.db.models import AutoRule


class TestResponderMatching:
    def setup_method(self):
        self.responder = AutoResponder()

    def test_exact_match(self):
        rule = AutoRule(id=1, pattern="Continue?", response="y", match_type="exact")
        assert self.responder._matches("Continue?", rule) is True
        assert (
            self.responder._matches("  Continue?  ", rule) is True
        )  # strip() trims whitespace
        assert self.responder._matches("Continue? yes", rule) is False

    def test_contains_match(self):
        rule = AutoRule(id=2, pattern="(Y/n)", response="y", match_type="contains")
        assert self.responder._matches("Continue? (Y/n)", rule) is True
        assert self.responder._matches("Just some text", rule) is False

    def test_regex_match(self):
        rule = AutoRule(id=3, pattern=r"\(Y/n\)", response="y", match_type="regex")
        assert self.responder._matches("Proceed? (Y/n)", rule) is True
        assert self.responder._matches("Proceed? (y/N)", rule) is False

    def test_disabled_rule_skipped(self):
        rules = [
            AutoRule(id=1, pattern="(Y/n)", response="y", enabled=False),
            AutoRule(id=2, pattern="(y/N)", response="n", enabled=True),
        ]
        # Text matches first rule but it's disabled
        result = self.responder.check("Continue? (Y/n)", rules=rules)
        assert result.should_respond is False

    def test_first_matching_rule_wins(self):
        rules = [
            AutoRule(id=1, pattern="(Y/n)", response="yes"),
            AutoRule(id=2, pattern="Y/n", response="also-yes"),
        ]
        result = self.responder.check("Continue? (Y/n)", rules=rules)
        assert result.should_respond is True
        assert result.response == "yes"
        assert result.rule_id == 1

    def test_check_with_explicit_rules(self):
        rules = [
            AutoRule(id=10, pattern="Save?", response="y", match_type="contains"),
        ]
        result = self.responder.check("Save? (Y/n)", rules=rules)
        assert result.should_respond is True
        assert result.response == "y"

    def test_no_rules_returns_false(self):
        result = self.responder.check("Some text", rules=[])
        assert result.should_respond is False
        assert result.response == ""
