"""Sensitive data redaction — scrub API keys, tokens, passwords before sending to Telegram."""

from __future__ import annotations

import re

REDACTION_PATTERNS: list[tuple[str, str]] = [
    # Anthropic API keys
    (r"sk-ant-api\S+", "[REDACTED:ANTHROPIC_KEY]"),
    # Generic API keys
    (r"sk-[a-zA-Z0-9]{20,}", "[REDACTED:API_KEY]"),
    (r"key-[a-zA-Z0-9]{20,}", "[REDACTED:API_KEY]"),
    # GitHub tokens
    (r"ghp_[a-zA-Z0-9]{36}", "[REDACTED:GITHUB_TOKEN]"),
    (r"gho_[a-zA-Z0-9]{36}", "[REDACTED:GITHUB_TOKEN]"),
    # NPM tokens
    (r"npm_[a-zA-Z0-9]{36}", "[REDACTED:NPM_TOKEN]"),
    # Generic secrets in env vars
    (r"(?i)(password|secret|token|api_key)\s*=\s*\S+", r"\1=[REDACTED]"),
    # OAuth tokens
    (r"Bearer\s+[a-zA-Z0-9\-._~+/]+=*", "Bearer [REDACTED]"),
    # .env file contents
    (r"^[A-Z_]+=(sk-|key-|ghp_|gho_|npm_)\S+$", "[REDACTED:ENV_LINE]"),
]

_compiled = [(re.compile(p, re.MULTILINE), r) for p, r in REDACTION_PATTERNS]


def redact_sensitive(text: str) -> str:
    """Redact sensitive data from text before sending to Telegram."""
    for pattern, replacement in _compiled:
        text = pattern.sub(replacement, text)
    return text
