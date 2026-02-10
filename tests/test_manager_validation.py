"""Tests for session manager input validation."""

import pytest
from unittest.mock import AsyncMock, patch

from conductor.sessions.manager import SessionManager


class TestRenameValidation:
    def _make_mgr_with_session(self):
        """Create a SessionManager with a fake session for testing."""
        from conductor.db.models import Session

        mgr = SessionManager()
        session = Session(
            id="test-1",
            number=1,
            alias="OldName",
            type="shell",
            working_dir="/tmp",
            tmux_session="conductor-1",
            color_emoji="🔵",
            status="running",
        )
        mgr._sessions["test-1"] = session
        return mgr

    @pytest.mark.asyncio
    async def test_alias_too_long_rejected(self):
        mgr = self._make_mgr_with_session()
        with pytest.raises(ValueError, match="too long"):
            await mgr.rename_session("test-1", "a" * 51)

    @pytest.mark.asyncio
    async def test_alias_empty_rejected(self):
        mgr = self._make_mgr_with_session()
        with pytest.raises(ValueError, match="cannot be empty"):
            await mgr.rename_session("test-1", "")

    @pytest.mark.asyncio
    async def test_alias_whitespace_only_rejected(self):
        mgr = self._make_mgr_with_session()
        with pytest.raises(ValueError, match="cannot be empty"):
            await mgr.rename_session("test-1", "   ")

    @pytest.mark.asyncio
    async def test_alias_max_length_accepted(self):
        mgr = self._make_mgr_with_session()
        with patch("conductor.sessions.manager.queries") as mock_queries:
            mock_queries.update_session = AsyncMock()
            result = await mgr.rename_session("test-1", "a" * 50)
            assert result is not None
            assert result.alias == "a" * 50

    @pytest.mark.asyncio
    async def test_alias_normal_accepted(self):
        mgr = self._make_mgr_with_session()
        with patch("conductor.sessions.manager.queries") as mock_queries:
            mock_queries.update_session = AsyncMock()
            result = await mgr.rename_session("test-1", "MyProject")
            assert result is not None
            assert result.alias == "MyProject"
