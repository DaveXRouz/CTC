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
        """Check if text should be auto-responded to (synchronous for tests)."""
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
        """Check against DB rules (async version)."""
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
        """Check if text matches a rule."""
        if rule.match_type == "exact":
            return text.strip() == rule.pattern
        elif rule.match_type == "regex":
            return bool(re.search(rule.pattern, text))
        else:  # contains
            return rule.pattern in text
