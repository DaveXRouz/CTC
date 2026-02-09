"""Tests for sensitive data redaction — Section 18.2."""

import pytest
from conductor.security.redactor import redact_sensitive


class TestRedaction:
    def test_redacts_anthropic_key(self):
        text = "export ANTHROPIC_API_KEY=sk-ant-api03-abcdef123456"
        result = redact_sensitive(text)
        assert "sk-ant" not in result
        assert "[REDACTED" in result

    def test_redacts_generic_api_key(self):
        text = "api_key=sk-1234567890abcdefghijklmnop"
        result = redact_sensitive(text)
        assert "sk-1234" not in result

    def test_redacts_github_token(self):
        text = "Token: ghp_ABC123DEF456GHI789JKL012MNO345PQR678"
        result = redact_sensitive(text)
        assert "ghp_" not in result

    def test_redacts_npm_token(self):
        text = "NPM_TOKEN=npm_ABC123DEF456GHI789JKL012MNO345PQR678"
        result = redact_sensitive(text)
        assert "npm_" not in result

    def test_preserves_normal_text(self):
        text = "Running npm test... 42 tests passed"
        result = redact_sensitive(text)
        assert result == text

    def test_redacts_bearer_token(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
        result = redact_sensitive(text)
        assert "eyJ" not in result
        assert "Bearer [REDACTED]" in result

    def test_redacts_password_env(self):
        text = "PASSWORD=mysecretpassword123"
        result = redact_sensitive(text)
        assert "mysecretpassword" not in result

    def test_redacts_env_line(self):
        text = "GITHUB_TOKEN=ghp_ABC123DEF456GHI789JKL012MNO345PQR678"
        result = redact_sensitive(text)
        assert "ghp_" not in result
