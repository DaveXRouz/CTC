"""Pattern detection engine — classify terminal output into event types."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class DetectionResult:
    """Result of classifying terminal output against known patterns.

    Attributes:
        type: Event category — one of ``'permission_prompt'``, ``'input_prompt'``,
            ``'rate_limit'``, ``'error'``, ``'completion'``, or ``'none'``.
        matched_text: The substring that triggered the match (empty if none).
        pattern: The regex pattern string that matched (empty if none).
        confidence: Match confidence, currently always ``1.0``.
    """

    type: str
    matched_text: str = ""
    pattern: str = ""
    confidence: float = 1.0


# ── Section 12.1: Permission prompts (NEVER auto-respond) ──

PERMISSION_PROMPT_PATTERNS = [
    r"Claude wants to (?:run|edit|use|write|read|delete)",
    r"Do you want to allow Claude to use",
    r"Allow Claude to use",
    r"Allow\?\s*\(?[yna]",
    r"\(y\)es\s*/\s*\(n\)o",
    r"\[y/n(?:/a)?\]",
    r"Yes \(y\)\s*\|\s*No \(n\)",
    r"Do you want to proceed",
    r"Would you like to continue",
    r"Press Enter to continue",
    r"Continue\?\s*\[",
]

# ── Section 12.2: User input prompts ──

INPUT_PROMPT_PATTERNS = [
    r"(?:Choose|Select|Pick)\s+(?:one|an option|from)",
    r"^\s*\d+[\.\)]\s+\w+",
    r"\(\d+\)\s+\w+",
    r"\?\s*$",
    r"(?:Enter|Type|Provide|Input|Specify)\s+(?:a|the|your)",
    r">\s*$",
    r"❯\s*$",
]

# ── Section 12.3: Rate limit patterns ──

RATE_LIMIT_PATTERNS = [
    r"(?i)rate\s*limit(?:ed)?",
    r"(?i)usage\s*limit\s*(?:reached|exceeded|hit)",
    r"(?i)too\s*many\s*requests",
    r"(?i)(?:please\s+)?wait\s+(?:\d+\s*(?:second|minute|hour)|\w+\s+before)",
    r"(?i)try\s*again\s*(?:in|after)\s*\d+",
    r"(?i)429\s*(?:error)?",
    r"(?i)capacity\s*(?:limit|exceeded)",
    r"(?i)cooldown",
    r"(?i)quota\s*(?:exceeded|reached)",
    r"(?i)you(?:'ve| have)\s+(?:reached|hit|exceeded)\s+(?:your|the)\s+(?:usage|message|token)\s+limit",
    r"(?i)limit\s+will\s+reset",
]

# ── Section 12.4: Error/crash patterns ──

ERROR_PATTERNS = [
    r"(?i)(?:error|err!|fatal|panic|exception|traceback|segfault)",
    r"(?i)process\s+exited\s+with\s+(?:code|status)\s+[^0]",
    r"(?i)command\s+(?:failed|not found)",
    r"(?i)killed|terminated|aborted",
    r"(?i)SIGTERM|SIGKILL|SIGSEGV",
    r"npm\s+ERR!",
    r"(?i)unhandled\s+(?:promise\s+)?rejection",
    r"(?i)cannot\s+find\s+module",
    r"Traceback \(most recent call last\)",
    r"(?:ModuleNotFoundError|ImportError|SyntaxError|TypeError|ValueError)",
    r"(?i)connection\s+(?:lost|reset|refused|timed?\s*out)",
    r"(?i)authentication\s+(?:failed|error|expired)",
    r"(?i)api\s+(?:error|unavailable)",
]

# ── Section 12.5: Completion patterns ──

COMPLETION_PATTERNS = [
    r"(?i)(?:task|job|build|test|deployment?)\s+(?:complete[d]?|finish(?:ed)?|done|success(?:ful)?)",
    r"(?i)all\s+(?:\d+\s+)?(?:tests?\s+)?pass(?:ed|ing)?",
    r"(?i)✓|✅|☑",
    r"(?i)successfully\s+(?:built|compiled|deployed|installed|created|updated)",
    r"(?i)compiled?\s+(?:successfully|with\s+\d+\s+warning)",
    r"(?i)build\s+succeeded",
    r"Done in \d+",
    r"\d+\s+passing",
]

# ── Section 12.6: Destructive keywords (never auto-respond) ──

DESTRUCTIVE_KEYWORDS = [
    "delete",
    "remove",
    "drop",
    "truncate",
    "destroy",
    "overwrite",
    "replace all",
    "reset",
    "wipe",
    "purge",
    "force push",
    "hard reset",
    "rm -rf",
    "uninstall",
    "migrate",
    "rollback",
    "production",
    "deploy",
]

# Pre-compile all patterns
_COMPILED: dict[str, list[re.Pattern]] = {}


def _compile(name: str, patterns: list[str]) -> list[re.Pattern]:
    """Compile and cache a named group of regex patterns.

    Args:
        name: Cache key for this pattern group.
        patterns: Raw regex strings to compile with ``re.MULTILINE``.

    Returns:
        List of compiled regex patterns (cached after first call).
    """
    if name not in _COMPILED:
        _COMPILED[name] = [re.compile(p, re.MULTILINE) for p in patterns]
    return _COMPILED[name]


def _match_any(text: str, name: str, patterns: list[str]) -> tuple[bool, str, str]:
    """Check if text matches any pattern in a named group.

    Args:
        text: Terminal output to test.
        name: Cache key for ``_compile()``.
        patterns: Raw regex strings.

    Returns:
        Tuple of ``(matched, matched_text, pattern_string)``. On no match,
        returns ``(False, "", "")``.
    """
    for compiled in _compile(name, patterns):
        m = compiled.search(text)
        if m:
            return True, m.group(0), compiled.pattern
    return False, "", ""


def has_destructive_keyword(text: str) -> bool:
    """Check if text contains any destructive keywords (case-insensitive).

    Args:
        text: Terminal output to scan.

    Returns:
        ``True`` if any keyword from ``DESTRUCTIVE_KEYWORDS`` appears in the text.
    """
    text_lower = text.lower()
    return any(kw in text_lower for kw in DESTRUCTIVE_KEYWORDS)


class PatternDetector:
    """Classify terminal output by pattern matching."""

    def classify(self, text: str) -> DetectionResult:
        """Classify terminal output into an event type.

        Tests ``text`` against five pattern groups in strict priority order:
        permission_prompt > input_prompt > rate_limit > error > completion.
        Returns on the first match. If nothing matches, returns type ``'none'``.

        Args:
            text: Raw terminal output (may be multi-line).

        Returns:
            A ``DetectionResult`` with the matched type, text, and pattern.
        """
        # Priority 1: Permission prompts
        matched, mtext, pattern = _match_any(text, "perm", PERMISSION_PROMPT_PATTERNS)
        if matched:
            return DetectionResult(
                type="permission_prompt", matched_text=mtext, pattern=pattern
            )

        # Priority 2: Input prompts
        matched, mtext, pattern = _match_any(text, "input", INPUT_PROMPT_PATTERNS)
        if matched:
            return DetectionResult(
                type="input_prompt", matched_text=mtext, pattern=pattern
            )

        # Priority 3: Rate limits
        matched, mtext, pattern = _match_any(text, "rate", RATE_LIMIT_PATTERNS)
        if matched:
            return DetectionResult(
                type="rate_limit", matched_text=mtext, pattern=pattern
            )

        # Priority 4: Errors
        matched, mtext, pattern = _match_any(text, "error", ERROR_PATTERNS)
        if matched:
            return DetectionResult(type="error", matched_text=mtext, pattern=pattern)

        # Priority 5: Completions
        matched, mtext, pattern = _match_any(text, "comp", COMPLETION_PATTERNS)
        if matched:
            return DetectionResult(
                type="completion", matched_text=mtext, pattern=pattern
            )

        return DetectionResult(type="none")
