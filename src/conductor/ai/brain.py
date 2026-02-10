"""AI Brain — summarize, suggest, parse via Claude Haiku API."""

from __future__ import annotations

import asyncio
import json

import anthropic

from conductor.config import get_config
from conductor.ai.prompts import SUMMARIZE_PROMPT, SUGGEST_PROMPT, NLP_PARSE_PROMPT
from conductor.ai.fallback import get_raw_fallback
from conductor.utils.logger import get_logger

logger = get_logger("conductor.ai.brain")


class AIBrain:
    """Claude Haiku-powered intelligence layer."""

    def __init__(self) -> None:
        cfg = get_config()
        self._client = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)
        self._model = cfg.ai_model
        self._timeout = cfg.ai_timeout
        self._last_call_time: dict[str, float] = {}
        self._min_interval: float = 10.0

    async def _call(self, prompt: str, max_tokens: int = 200) -> str:
        """Make an API call to Claude Haiku with timeout.

        Args:
            prompt: User message to send.
            max_tokens: Maximum response length (default 200).

        Returns:
            The text content of the first response block.

        Raises:
            asyncio.TimeoutError: If the call exceeds ``ai_timeout`` seconds.
            Exception: On any Anthropic API error.
        """
        try:
            response = await asyncio.wait_for(
                self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=self._timeout,
            )
            if not response.content:
                raise ValueError("Empty response from Haiku API")
            return response.content[0].text
        except asyncio.TimeoutError:
            logger.warning("Haiku API timeout")
            raise
        except Exception as e:
            logger.warning(f"Haiku API error: {e}")
            raise

    def _rate_ok(self, key: str) -> bool:
        """Check if enough time has elapsed since the last call for this key."""
        import time

        now = time.monotonic()
        last = self._last_call_time.get(key, 0)
        if (now - last) < self._min_interval:
            return False
        self._last_call_time[key] = now
        return True

    async def summarize(self, terminal_output: str) -> str:
        """Summarize terminal output into 2-4 sentences.

        Falls back to raw last-N-lines output if the API call fails.

        Args:
            terminal_output: Raw terminal text (last 3000 chars are used).

        Returns:
            AI-generated summary, or raw fallback text on failure.
        """
        if not self._rate_ok("summarize"):
            return get_raw_fallback(terminal_output)
        cfg = get_config()
        prompt = SUMMARIZE_PROMPT.format(terminal_output=terminal_output[-3000:])
        try:
            return await self._call(
                prompt, max_tokens=cfg.ai_config.get("summary_max_tokens", 200)
            )
        except Exception:
            return get_raw_fallback(terminal_output)

    async def suggest(
        self,
        terminal_output: str,
        project_alias: str = "",
        session_type: str = "",
        working_dir: str = "",
    ) -> list[dict[str, str]]:
        """Suggest 1-3 next actions based on terminal output and session context.

        Args:
            terminal_output: Raw terminal text (last 2000 chars are used).
            project_alias: Human-readable project name.
            session_type: Session type (``'claude-code'`` or ``'shell'``).
            working_dir: Session working directory.

        Returns:
            List of dicts with ``'label'`` and ``'command'`` keys, or empty
            list on failure.
        """
        if not self._rate_ok("suggest"):
            return []
        cfg = get_config()
        prompt = SUGGEST_PROMPT.format(
            terminal_output=terminal_output[-2000:],
            project_alias=project_alias,
            session_type=session_type,
            working_dir=working_dir,
        )
        try:
            text = await self._call(
                prompt, max_tokens=cfg.ai_config.get("suggestion_max_tokens", 300)
            )
            return json.loads(text)
        except Exception as e:
            logger.warning(f"Suggestion parse error: {e}")
            return []

    async def parse_nlp(
        self,
        user_message: str,
        session_list_json: str = "[]",
        last_prompt_context: str = "None",
    ) -> dict:
        """Parse natural language into a structured command via AI.

        Args:
            user_message: Free-text message from the user.
            session_list_json: JSON string of active sessions for context.
            last_prompt_context: Description of the last pending prompt, or ``"None"``.

        Returns:
            Dict with ``'command'``, ``'session'``, ``'args'``, and ``'confidence'``
            keys. Returns ``{'command': 'unknown', 'confidence': 0.0}`` on failure.
        """
        cfg = get_config()
        prompt = NLP_PARSE_PROMPT.format(
            user_message=user_message,
            session_list_json=session_list_json,
            last_prompt_context=last_prompt_context,
        )
        try:
            text = await self._call(
                prompt, max_tokens=cfg.ai_config.get("nlp_max_tokens", 150)
            )
            result = json.loads(text)
            return result
        except Exception as e:
            logger.warning(f"NLP parse error: {e}")
            return {"command": "unknown", "confidence": 0.0}
