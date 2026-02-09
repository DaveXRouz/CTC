"""Auto-response rule management."""

from __future__ import annotations

from conductor.db import queries
from conductor.db.models import AutoRule


async def get_active_rules() -> list[AutoRule]:
    """Get all enabled auto-response rules."""
    return await queries.get_all_rules(enabled_only=True)


async def get_all_rules() -> list[AutoRule]:
    """Get all auto-response rules."""
    return await queries.get_all_rules()


async def add_rule(pattern: str, response: str, match_type: str = "contains") -> int:
    """Add a new auto-response rule."""
    rule = AutoRule(pattern=pattern, response=response, match_type=match_type)
    return await queries.add_rule(rule)


async def remove_rule(rule_id: int) -> bool:
    """Remove an auto-response rule."""
    return await queries.delete_rule(rule_id)


async def pause_all() -> None:
    """Disable all auto-response rules."""
    await queries.set_rules_enabled(False)


async def resume_all() -> None:
    """Enable all auto-response rules."""
    await queries.set_rules_enabled(True)


async def record_hit(rule_id: int) -> None:
    """Increment the hit count for a rule."""
    await queries.increment_rule_hit(rule_id)
