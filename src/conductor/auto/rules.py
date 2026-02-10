"""Auto-response rule management."""

from __future__ import annotations

from conductor.db import queries
from conductor.db.models import AutoRule


async def get_active_rules() -> list[AutoRule]:
    """Get all enabled auto-response rules from the database.

    Returns:
        List of enabled AutoRule dataclasses.
    """
    return await queries.get_all_rules(enabled_only=True)


async def get_all_rules() -> list[AutoRule]:
    """Get all auto-response rules from the database.

    Returns:
        List of all AutoRule dataclasses (enabled and disabled).
    """
    return await queries.get_all_rules()


async def add_rule(pattern: str, response: str, match_type: str = "contains") -> int:
    """Add a new auto-response rule to the database.

    Args:
        pattern: Text or regex pattern to match.
        response: Text to send when matched.
        match_type: Matching strategy — ``'contains'``, ``'regex'``, or ``'exact'``.

    Returns:
        The auto-generated rule ID.
    """
    rule = AutoRule(pattern=pattern, response=response, match_type=match_type)
    return await queries.add_rule(rule)


async def remove_rule(rule_id: int) -> bool:
    """Remove an auto-response rule from the database.

    Args:
        rule_id: Primary key of the rule to remove.

    Returns:
        True if the rule was found and removed.
    """
    return await queries.delete_rule(rule_id)


async def pause_all() -> None:
    """Disable all auto-response rules globally."""
    await queries.set_rules_enabled(False)


async def resume_all() -> None:
    """Enable all auto-response rules globally."""
    await queries.set_rules_enabled(True)


async def record_hit(rule_id: int) -> None:
    """Increment the hit count for a rule.

    Args:
        rule_id: Primary key of the rule that was triggered.
    """
    await queries.increment_rule_hit(rule_id)
