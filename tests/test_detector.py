"""Tests for pattern detection — Section 18.2."""

import pytest
from conductor.sessions.detector import PatternDetector, has_destructive_keyword

detector = PatternDetector()


class TestPermissionPrompts:
    """Test that all Claude Code permission prompt formats are detected."""

    @pytest.mark.parametrize(
        "text",
        [
            "Claude wants to run: rm -rf node_modules\nAllow? (y/n/a)",
            "Do you want to allow Claude to use Bash(npm install)?\n  Yes (y)  |  No (n)",
            "Claude wants to edit src/main.py\n  Allow? [y/n/a]",
            'Allow Claude to use the "Write" tool?\n  (y)es / (n)o / (a)lways allow',
            "Claude wants to delete old-config.json",
            "Do you want to proceed with this change?",
            "Would you like to continue with the operation?",
        ],
    )
    def test_detects_permission_prompts(self, text):
        result = detector.classify(text)
        assert result.type == "permission_prompt"

    @pytest.mark.parametrize(
        "text",
        [
            "Running npm install...\ninstalled 234 packages",
            "Tests passed: 42/42",
            "Building project...",
            "Downloading dependencies",
        ],
    )
    def test_does_not_false_positive(self, text):
        result = detector.classify(text)
        assert result.type != "permission_prompt"


class TestRateLimits:
    @pytest.mark.parametrize(
        "text",
        [
            "Rate limit exceeded. Please wait 30 seconds.",
            "You've reached your usage limit",
            "Error 429: Too many requests",
            "Usage limit reached. Limit will reset in 2 hours.",
            "Rate limited. Try again in 60 seconds.",
            "Quota exceeded for this billing period.",
        ],
    )
    def test_detects_rate_limits(self, text):
        result = detector.classify(text)
        assert result.type == "rate_limit"


class TestErrorPatterns:
    @pytest.mark.parametrize(
        "text",
        [
            "npm ERR! ENOENT: no such file",
            'Traceback (most recent call last):\n  File "main.py"',
            "FATAL: password authentication failed",
            "process exited with code 1",
            "ModuleNotFoundError: No module named 'foo'",
            "Connection refused to localhost:5432",
        ],
    )
    def test_detects_errors(self, text):
        result = detector.classify(text)
        assert result.type == "error"


class TestCompletionPatterns:
    @pytest.mark.parametrize(
        "text",
        [
            "✓ Build succeeded",
            "All 42 tests passed",
            "Successfully deployed to production",
            "Done in 34.2s",
            "Task completed successfully",
            "42 passing",
        ],
    )
    def test_detects_completions(self, text):
        result = detector.classify(text)
        assert result.type == "completion"


class TestDestructiveKeywords:
    @pytest.mark.parametrize(
        "text",
        [
            "Delete all data?",
            "rm -rf /tmp/stuff",
            "force push to main?",
            "Drop table users?",
            "Deploy to production?",
        ],
    )
    def test_detects_destructive(self, text):
        assert has_destructive_keyword(text) is True

    def test_normal_text_not_destructive(self):
        assert has_destructive_keyword("Run tests") is False
        assert has_destructive_keyword("Build succeeded") is False
