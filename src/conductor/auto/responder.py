"""Auto-responder engine — pattern match + auto-reply for simple prompts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from conductor.config import get_config
from conductor.sessions.detector import (
    PERMISSION_PROMPT_PATTERNS,
    DESTRUCTIVE_KEYWORDS,
    has_destructive_keyword,
)
from conductor.auto.rules import get_active_rules, record_hit
from conductor.db.models import AutoRule
from conductor.utils.logger import get_logger

logger = get_logger("conductor.auto.responder")


@dataclass
class AutoResponse:
    should_respond: bool
    response: str = ""
    rule_id: int | None = None
    block_reason: str = ""


class AutoResponder:
    """Match prompts against rules and auto-respond if safe."""

    def check(self, text: str, rules: list[AutoRule] | None = None) -> AutoResponse:
        """Check if text matches an auto-response rule (synchronous).

        Enforces safety guards before rule matching: blocks permission prompts
        and text containing destructive keywords.

        Args:
            text: Terminal output to check.
            rules: Rules to match against. If None, uses default rules from config.

        Returns:
            ``AutoResponse`` with ``should_respond=True`` and the response text
            if a rule matched, or ``should_respond=False`` with an optional
            ``block_reason``.
        """
        # Safety: never auto-respond to permission prompts
        for pattern in PERMISSION_PROMPT_PATTERNS:
            if re.search(pattern, text, re.MULTILINE):
                return AutoResponse(
                    should_respond=False,
                    block_reason="Permission prompt — requires manual approval",
                )

        # Safety: never auto-respond if destructive keywords present
        if has_destructive_keyword(text):
            return AutoResponse(
                should_respond=False,
                block_reason=f"Destructive keyword detected",
            )

        # Check against rules
        if rules is None:
            # Use default rules from config for sync checks (testing)
            cfg = get_config()
            default_rules = cfg.auto_responder_config.get("default_rules", [])
            rules = [
                AutoRule(
                    id=i,
                    pattern=r["pattern"],
                    response=r["response"],
                    match_type=r.get("match_type", "contains"),
                )
                for i, r in enumerate(default_rules)
            ]

        for rule in rules:
            if not rule.enabled:
                continue
            if self._matches(text, rule):
                return AutoResponse(
                    should_respond=True,
                    response=rule.response,
                    rule_id=rule.id,
                )

        return AutoResponse(should_respond=False)

    async def check_and_respond(self, text: str) -> AutoResponse:
        """Check text against database rules and record hits (async).

        Same safety guards as ``check()``, but loads rules from the database
        and increments hit counts on match.

        Args:
            text: Terminal output to check.

        Returns:
            ``AutoResponse`` with match result and rule details.
        """
        # Safety checks first (same as sync)
        for pattern in PERMISSION_PROMPT_PATTERNS:
            if re.search(pattern, text, re.MULTILINE):
                return AutoResponse(
                    should_respond=False,
                    block_reason="Permission prompt — requires manual approval",
                )

        if has_destructive_keyword(text):
            return AutoResponse(
                should_respond=False,
                block_reason="Destructive keyword detected",
            )

        rules = await get_active_rules()
        for rule in rules:
            if self._matches(text, rule):
                await record_hit(rule.id)
                logger.info(
                    f"Auto-responding to rule #{rule.id}: '{rule.pattern}' → '{rule.response}'"
                )
                return AutoResponse(
                    should_respond=True,
                    response=rule.response,
                    rule_id=rule.id,
                )

        return AutoResponse(should_respond=False)

    @staticmethod
    def _matches(text: str, rule: AutoRule) -> bool:
        """Check if text matches a single auto-response rule.

        Args:
            text: Terminal output to test.
            rule: AutoRule with pattern and match_type.

        Returns:
            True if the rule's pattern matches the text.
        """
        if rule.match_type == "exact":
            return text.strip() == rule.pattern
        elif rule.match_type == "regex":
            try:
                return bool(re.search(rule.pattern, text))
            except re.error:
                logger.warning(f"Invalid regex in rule #{rule.id}: {rule.pattern!r}")
                return False
        else:  # contains
            return rule.pattern in text
