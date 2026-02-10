"""Pattern detection engine — classify terminal output into event types."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass


@dataclass
class DetectionResult:
    """Result of classifying terminal output."""

    type: str
    matched_text: str = ""
    pattern: str = ""
    confidence: float = 1.0


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
]

INPUT_PROMPT_PATTERNS = [
    r"(?:Choose|Select|Pick)\s+(?:one|an option|from)",
    r"\(\d+\)\s+\w+.*\n\(\d+\)\s+\w+",
    r"(?:Enter|Type|Provide|Input|Specify)\s+(?:a|the|your)\s+\w+",
    r"❯\s*$",
]

RATE_LIMIT_PATTERNS = [
    r"(?i)rate\s*limit(?:ed)?",
    r"(?i)usage\s*limit\s*(?:reached|exceeded|hit)",
    r"(?i)too\s*many\s*requests",
    r"(?i)(?:please\s+)?wait\s+(?:\d+\s*(?:second|minute|hour)|before\s+\w+ing)",
    r"(?i)try\s*again\s*(?:in|after)\s*\d+",
    r"(?i)429\s*(?:error)?",
    r"(?i)capacity\s*(?:limit|exceeded)",
    r"(?i)quota\s*(?:exceeded|reached)",
    r"(?i)you(?:'ve| have)\s+(?:reached|hit|exceeded)\s+(?:your|the)\s+(?:usage|message|token)\s+limit",
    r"(?i)limit\s+will\s+reset",
]

ERROR_PATTERNS = [
    r"(?i)(?:fatal|panic|segfault)\s*(?:error|:)",
    r"(?i)(?:^|\s)ERR!(?:\s|$)",
    r"(?i)process\s+exited\s+with\s+(?:code|status)\s+[^0]",
    r"(?i)command\s+(?:failed|not found)",
    r"(?i)(?:^|\s)(?:killed|terminated|aborted)(?:\s|$)",
    r"(?i)SIGTERM|SIGKILL|SIGSEGV",
    r"npm\s+ERR!",
    r"(?i)unhandled\s+(?:promise\s+)?rejection",
    r"(?i)cannot\s+find\s+module",
    r"Traceback \(most recent call last\)",
    r"(?:ModuleNotFoundError|ImportError|SyntaxError|TypeError|ValueError|KeyError|AttributeError):",
    r"(?i)connection\s+(?:lost|reset|refused|timed?\s*out)",
    r"(?i)authentication\s+(?:failed|error|expired)",
    r"(?i)api\s+(?:error|unavailable)",
]

COMPLETION_PATTERNS = [
    r"(?i)(?:task|job|build|test|deployment?)\s+(?:complete[d]?|finish(?:ed)?|done|success(?:ful)?)",
    r"(?i)all\s+(?:\d+\s+)?(?:tests?\s+)?pass(?:ed|ing)?",
    r"✓|✅|☑",
    r"(?i)successfully\s+(?:built|compiled|deployed|installed|created|updated)",
    r"(?i)compiled?\s+(?:successfully|with\s+\d+\s+warning)",
    r"(?i)build\s+succeeded",
    r"Done in \d+",
    r"\d+\s+passing",
]

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

_COMPILED: dict[str, list[re.Pattern]] = {}


def _compile(name: str, patterns: list[str]) -> list[re.Pattern]:
    if name not in _COMPILED:
        _COMPILED[name] = [re.compile(p, re.MULTILINE) for p in patterns]
    return _COMPILED[name]


def _match_any(text: str, name: str, patterns: list[str]) -> tuple[bool, str, str]:
    for compiled in _compile(name, patterns):
        m = compiled.search(text)
        if m:
            return True, m.group(0), compiled.pattern
    return False, "", ""


def has_destructive_keyword(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in DESTRUCTIVE_KEYWORDS)


class PatternDetector:
    """Classify terminal output with debounce."""

    def __init__(self) -> None:
        self._last_event_time: dict[str, float] = {}
        self._cooldown_seconds: float = 10.0

    def classify(self, text: str) -> DetectionResult:
        matched, mtext, pattern = _match_any(text, "perm", PERMISSION_PROMPT_PATTERNS)
        if matched:
            self._last_event_time["permission_prompt"] = time.monotonic()
            return DetectionResult(
                type="permission_prompt", matched_text=mtext, pattern=pattern
            )

        matched, mtext, pattern = _match_any(text, "input", INPUT_PROMPT_PATTERNS)
        if matched and self._not_in_cooldown("input_prompt"):
            self._last_event_time["input_prompt"] = time.monotonic()
            return DetectionResult(
                type="input_prompt", matched_text=mtext, pattern=pattern
            )

        matched, mtext, pattern = _match_any(text, "rate", RATE_LIMIT_PATTERNS)
        if matched:
            self._last_event_time["rate_limit"] = time.monotonic()
            return DetectionResult(
                type="rate_limit", matched_text=mtext, pattern=pattern
            )

        matched, mtext, pattern = _match_any(text, "error", ERROR_PATTERNS)
        if matched and self._not_in_cooldown("error"):
            self._last_event_time["error"] = time.monotonic()
            return DetectionResult(type="error", matched_text=mtext, pattern=pattern)

        matched, mtext, pattern = _match_any(text, "comp", COMPLETION_PATTERNS)
        if matched and self._not_in_cooldown("completion"):
            self._last_event_time["completion"] = time.monotonic()
            return DetectionResult(
                type="completion", matched_text=mtext, pattern=pattern
            )

        return DetectionResult(type="none")

    def _not_in_cooldown(self, event_type: str) -> bool:
        last = self._last_event_time.get(event_type, 0)
        return (time.monotonic() - last) > self._cooldown_seconds
