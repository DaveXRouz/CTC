"""Tests for AIBrain — summarize, suggest, parse_nlp via Claude Haiku API."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_config():
    """Return a mock Config object with sensible defaults."""
    cfg = MagicMock()
    cfg.anthropic_api_key = "test-key"
    cfg.ai_model = "haiku"
    cfg.ai_timeout = 10
    cfg.ai_config = {}
    return cfg


def _mock_response(text: str):
    """Build a fake Anthropic Messages response with a single text block."""
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def _mock_empty_response():
    """Build a fake Anthropic Messages response with empty content list."""
    resp = MagicMock()
    resp.content = []
    return resp


# ---------------------------------------------------------------------------
# Fixture: patched AIBrain that never touches real config / network
# ---------------------------------------------------------------------------


@pytest.fixture()
def brain():
    """Create an AIBrain with mocked config and mocked Anthropic client."""
    with (
        patch("conductor.ai.brain.get_config", return_value=_mock_config()),
        patch("conductor.ai.brain.anthropic") as mock_anthropic_mod,
    ):
        # Build a mock async client whose messages.create is an AsyncMock
        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock()
        mock_anthropic_mod.AsyncAnthropic.return_value = mock_client

        from conductor.ai.brain import AIBrain

        instance = AIBrain()

        # Expose the mock so tests can configure return values
        instance._mock_create = mock_client.messages.create
        yield instance


# ===================================================================
# 1. _call tests
# ===================================================================


class TestCall:
    """Tests for AIBrain._call (low-level API wrapper)."""

    async def test_call_successful_response(self, brain):
        """_call returns the text from the first content block."""
        brain._mock_create.return_value = _mock_response("hello world")
        result = await brain._call("some prompt")
        assert result == "hello world"

    async def test_call_passes_model_and_max_tokens(self, brain):
        """_call forwards model, max_tokens, and messages to the client."""
        brain._mock_create.return_value = _mock_response("ok")
        await brain._call("my prompt", max_tokens=500)
        brain._mock_create.assert_awaited_once()
        call_kwargs = brain._mock_create.call_args.kwargs
        assert call_kwargs["model"] == "haiku"
        assert call_kwargs["max_tokens"] == 500
        assert call_kwargs["messages"] == [{"role": "user", "content": "my prompt"}]

    async def test_call_empty_content_raises_value_error(self, brain):
        """B8 fix: empty response.content must raise ValueError."""
        brain._mock_create.return_value = _mock_empty_response()
        with pytest.raises(ValueError, match="Empty response"):
            await brain._call("prompt")

    async def test_call_timeout_raises(self, brain):
        """_call re-raises asyncio.TimeoutError on timeout."""
        brain._mock_create.side_effect = asyncio.TimeoutError()
        with pytest.raises(asyncio.TimeoutError):
            await brain._call("prompt")

    async def test_call_api_error_raises(self, brain):
        """_call re-raises generic exceptions from the API."""
        brain._mock_create.side_effect = RuntimeError("API down")
        with pytest.raises(RuntimeError, match="API down"):
            await brain._call("prompt")

    async def test_call_default_max_tokens(self, brain):
        """_call uses 200 as the default max_tokens."""
        brain._mock_create.return_value = _mock_response("ok")
        await brain._call("prompt")
        call_kwargs = brain._mock_create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 200


# ===================================================================
# 2. summarize tests
# ===================================================================


class TestSummarize:
    """Tests for AIBrain.summarize."""

    async def test_summarize_success(self, brain):
        """summarize returns the AI-generated summary text."""
        brain._mock_create.return_value = _mock_response("Tests passed. 42 OK.")
        result = await brain.summarize("...long terminal output...")
        assert result == "Tests passed. 42 OK."

    async def test_summarize_falls_back_on_failure(self, brain):
        """When _call raises, summarize returns raw fallback text."""
        brain._mock_create.side_effect = RuntimeError("API down")
        with (
            patch("conductor.ai.brain.get_config", return_value=_mock_config()),
            patch(
                "conductor.ai.brain.get_raw_fallback", return_value="fallback text"
            ) as mock_fb,
        ):
            result = await brain.summarize("terminal stuff")
            assert result == "fallback text"
            mock_fb.assert_called_once_with("terminal stuff")

    async def test_summarize_truncates_to_3000(self, brain):
        """summarize passes only last 3000 chars of terminal output to the prompt."""
        long_output = "X" * 5000
        brain._mock_create.return_value = _mock_response("summary")

        with (
            patch("conductor.ai.brain.get_config", return_value=_mock_config()),
            patch("conductor.ai.brain.SUMMARIZE_PROMPT", "{terminal_output}"),
        ):
            await brain.summarize(long_output)

        # The prompt sent should contain only the last 3000 characters
        call_kwargs = brain._mock_create.call_args.kwargs
        prompt_sent = call_kwargs["messages"][0]["content"]
        assert len(prompt_sent) <= 3000

    async def test_summarize_uses_summary_max_tokens_config(self, brain):
        """summarize reads summary_max_tokens from ai_config if available."""
        cfg = _mock_config()
        cfg.ai_config = {"summary_max_tokens": 400}
        brain._mock_create.return_value = _mock_response("summary")

        with patch("conductor.ai.brain.get_config", return_value=cfg):
            await brain.summarize("output")

        call_kwargs = brain._mock_create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 400


# ===================================================================
# 3. suggest tests
# ===================================================================


class TestSuggest:
    """Tests for AIBrain.suggest."""

    async def test_suggest_success_parses_json(self, brain):
        """suggest returns parsed JSON list on success."""
        suggestions = [{"label": "Run tests", "command": "pytest"}]
        brain._mock_create.return_value = _mock_response(json.dumps(suggestions))

        with patch("conductor.ai.brain.get_config", return_value=_mock_config()):
            result = await brain.suggest("test output")
        assert result == suggestions

    async def test_suggest_json_parse_error_returns_empty(self, brain):
        """When the AI returns invalid JSON, suggest returns []."""
        brain._mock_create.return_value = _mock_response("not valid json {{{")

        with patch("conductor.ai.brain.get_config", return_value=_mock_config()):
            result = await brain.suggest("output")
        assert result == []

    async def test_suggest_timeout_returns_empty(self, brain):
        """When _call times out, suggest returns []."""
        brain._mock_create.side_effect = asyncio.TimeoutError()

        with patch("conductor.ai.brain.get_config", return_value=_mock_config()):
            result = await brain.suggest("output")
        assert result == []

    async def test_suggest_api_error_returns_empty(self, brain):
        """When _call raises a generic error, suggest returns []."""
        brain._mock_create.side_effect = RuntimeError("fail")

        with patch("conductor.ai.brain.get_config", return_value=_mock_config()):
            result = await brain.suggest("output")
        assert result == []

    async def test_suggest_passes_context_params(self, brain):
        """suggest includes project_alias, session_type, working_dir in the prompt."""
        suggestions = [{"label": "Deploy", "command": "deploy.sh"}]
        brain._mock_create.return_value = _mock_response(json.dumps(suggestions))

        with patch("conductor.ai.brain.get_config", return_value=_mock_config()):
            await brain.suggest(
                "output",
                project_alias="myapp",
                session_type="shell",
                working_dir="/home/user",
            )

        call_kwargs = brain._mock_create.call_args.kwargs
        prompt = call_kwargs["messages"][0]["content"]
        assert "myapp" in prompt
        assert "shell" in prompt
        assert "/home/user" in prompt

    async def test_suggest_uses_suggestion_max_tokens_config(self, brain):
        """suggest reads suggestion_max_tokens from ai_config if available."""
        cfg = _mock_config()
        cfg.ai_config = {"suggestion_max_tokens": 600}
        brain._mock_create.return_value = _mock_response("[]")

        with patch("conductor.ai.brain.get_config", return_value=cfg):
            await brain.suggest("output")

        call_kwargs = brain._mock_create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 600


# ===================================================================
# 4. parse_nlp tests
# ===================================================================


class TestParseNlp:
    """Tests for AIBrain.parse_nlp."""

    async def test_parse_nlp_success(self, brain):
        """parse_nlp returns the parsed dict on success."""
        nlp_result = {"command": "status", "session": None, "confidence": 0.95}
        brain._mock_create.return_value = _mock_response(json.dumps(nlp_result))

        with patch("conductor.ai.brain.get_config", return_value=_mock_config()):
            result = await brain.parse_nlp("show me status")
        assert result == nlp_result

    async def test_parse_nlp_json_error_returns_default(self, brain):
        """When AI returns invalid JSON, parse_nlp returns default dict."""
        brain._mock_create.return_value = _mock_response("broken json")

        with patch("conductor.ai.brain.get_config", return_value=_mock_config()):
            result = await brain.parse_nlp("do something")
        assert result == {"command": "unknown", "confidence": 0.0}

    async def test_parse_nlp_exception_returns_default(self, brain):
        """When _call raises, parse_nlp returns default dict."""
        brain._mock_create.side_effect = RuntimeError("kaboom")

        with patch("conductor.ai.brain.get_config", return_value=_mock_config()):
            result = await brain.parse_nlp("help me")
        assert result == {"command": "unknown", "confidence": 0.0}

    async def test_parse_nlp_timeout_returns_default(self, brain):
        """When _call times out, parse_nlp returns default dict."""
        brain._mock_create.side_effect = asyncio.TimeoutError()

        with patch("conductor.ai.brain.get_config", return_value=_mock_config()):
            result = await brain.parse_nlp("kill session 1")
        assert result == {"command": "unknown", "confidence": 0.0}

    async def test_parse_nlp_passes_session_list_and_context(self, brain):
        """parse_nlp includes session_list_json and last_prompt_context in the prompt."""
        nlp_result = {"command": "input", "confidence": 0.9}
        brain._mock_create.return_value = _mock_response(json.dumps(nlp_result))

        sessions = '[{"name": "main", "id": 1}]'
        context = "Last prompt was: confirm?"

        with patch("conductor.ai.brain.get_config", return_value=_mock_config()):
            await brain.parse_nlp(
                "type yes", session_list_json=sessions, last_prompt_context=context
            )

        call_kwargs = brain._mock_create.call_args.kwargs
        prompt = call_kwargs["messages"][0]["content"]
        assert "main" in prompt
        assert "confirm?" in prompt

    async def test_parse_nlp_uses_nlp_max_tokens_config(self, brain):
        """parse_nlp reads nlp_max_tokens from ai_config if available."""
        cfg = _mock_config()
        cfg.ai_config = {"nlp_max_tokens": 250}
        brain._mock_create.return_value = _mock_response(
            '{"command":"help","confidence":1.0}'
        )

        with patch("conductor.ai.brain.get_config", return_value=cfg):
            await brain.parse_nlp("help")

        call_kwargs = brain._mock_create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 250


# ===================================================================
# 5. B8 fix verification — redundant except simplified
# ===================================================================


class TestB8Fix:
    """Verify the B8 fix: empty content raises ValueError and
    the except clause properly re-raises all exceptions."""

    async def test_empty_content_is_value_error_not_silent(self, brain):
        """Empty content must raise ValueError, never return empty string."""
        brain._mock_create.return_value = _mock_empty_response()
        with pytest.raises(ValueError, match="Empty response from Haiku API"):
            await brain._call("test")

    async def test_value_error_propagates_through_summarize_fallback(self, brain):
        """Empty API response in summarize triggers fallback, not a crash."""
        brain._mock_create.return_value = _mock_empty_response()
        with (
            patch("conductor.ai.brain.get_config", return_value=_mock_config()),
            patch("conductor.ai.brain.get_raw_fallback", return_value="raw lines"),
        ):
            result = await brain.summarize("output")
        assert result == "raw lines"

    async def test_value_error_propagates_through_suggest(self, brain):
        """Empty API response in suggest returns [] via except branch."""
        brain._mock_create.return_value = _mock_empty_response()
        with patch("conductor.ai.brain.get_config", return_value=_mock_config()):
            result = await brain.suggest("output")
        assert result == []

    async def test_value_error_propagates_through_parse_nlp(self, brain):
        """Empty API response in parse_nlp returns default dict via except branch."""
        brain._mock_create.return_value = _mock_empty_response()
        with patch("conductor.ai.brain.get_config", return_value=_mock_config()):
            result = await brain.parse_nlp("hello")
        assert result == {"command": "unknown", "confidence": 0.0}
