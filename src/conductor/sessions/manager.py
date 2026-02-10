"""Session Manager — create/kill/list/pause/resume tmux sessions via libtmux."""

from __future__ import annotations

import os
import re
import signal
import uuid

import libtmux

from conductor.config import get_config
from conductor.db.models import Session
from conductor.db import queries
from conductor.utils.logger import get_logger

logger = get_logger("conductor.sessions.manager")

COLOR_PALETTE = ["🔵", "🟣", "🟠", "🟢", "🔴", "🟤"]


def guess_alias_from_dir(working_dir: str) -> str:
    """Convert directory path to a readable alias.

    Args:
        working_dir: Absolute or relative directory path.

    Returns:
        Capitalized folder name with hyphens and underscores as word separators.
    """
    folder_name = os.path.basename(working_dir.rstrip("/"))
    parts = re.split(r"[-_]", folder_name)
    return "-".join(part.capitalize() for part in parts)


class SessionManager:
    """Manage tmux sessions for Conductor."""

    def __init__(self) -> None:
        self._server: libtmux.Server | None = None
        self._sessions: dict[str, Session] = {}  # id -> Session
        self._panes: dict[str, libtmux.Pane] = {}  # id -> Pane

    @property
    def server(self) -> libtmux.Server:
        if self._server is None:
            self._server = libtmux.Server()
        return self._server

    async def load_from_db(self) -> None:
        """Load existing active sessions from database on startup.

        Populates the in-memory session dict from the DB. Called once
        during ``main.py:run()`` initialization.
        """
        sessions = await queries.get_all_sessions(active_only=True)
        for s in sessions:
            self._sessions[s.id] = s

    def _next_color(self) -> str:
        used = {s.color_emoji for s in self._sessions.values()}
        for color in COLOR_PALETTE:
            if color not in used:
                return color
        return COLOR_PALETTE[0]

    async def create_session(
        self,
        session_type: str = "claude-code",
        working_dir: str | None = None,
        alias: str | None = None,
    ) -> Session:
        """Create a new tmux session and persist it to the database.

        Args:
            session_type: Session type — ``'claude-code'`` or ``'shell'``.
            working_dir: Absolute working directory. Defaults to ``config.default_dir``.
            alias: Human-readable name. Auto-generated from directory if not provided.

        Returns:
            The newly created ``Session`` dataclass.

        Raises:
            RuntimeError: If ``max_concurrent_sessions`` limit is reached.
            ValueError: If ``working_dir`` does not exist.
        """
        cfg = get_config()
        if len(self._sessions) >= cfg.max_concurrent_sessions:
            raise RuntimeError(
                f"Max {cfg.max_concurrent_sessions} concurrent sessions reached"
            )

        working_dir = working_dir or os.path.expanduser(cfg.default_dir)
        working_dir = os.path.expanduser(working_dir)

        if not os.path.isdir(working_dir):
            raise ValueError(f"Directory does not exist: {working_dir}")

        # Check alias mappings from config
        if not alias:
            for path_pattern, mapped_alias in cfg.aliases.items():
                expanded = os.path.expanduser(path_pattern)
                if os.path.abspath(working_dir) == os.path.abspath(expanded):
                    alias = mapped_alias
                    break
        if not alias:
            alias = guess_alias_from_dir(working_dir)

        number = await queries.get_next_session_number()
        session_name = f"conductor-{number}"
        session_id = str(uuid.uuid4())
        color = self._next_color()

        # Create tmux session
        tmux_session = self.server.new_session(
            session_name=session_name,
            start_directory=working_dir,
            attach=False,
        )
        pane = tmux_session.attached_window.attached_pane

        # Start Claude Code if needed
        if session_type == "claude-code":
            pane.send_keys("claude", enter=True)

        pid = pane.get("pane_pid")

        session = Session(
            id=session_id,
            number=number,
            alias=alias,
            type=session_type,
            working_dir=working_dir,
            tmux_session=session_name,
            tmux_pane_id=pane.get("pane_id"),
            pid=int(pid) if pid else None,
            status="running",
            color_emoji=color,
        )

        await queries.create_session(session)
        self._sessions[session_id] = session
        self._panes[session_id] = pane

        logger.info(
            f"Created session {color} #{number} '{alias}' ({session_type}) in {working_dir}"
        )
        return session

    async def kill_session(self, session_id: str) -> Session | None:
        """Kill a tmux session and mark it as exited.

        Args:
            session_id: UUID of the session to kill.

        Returns:
            The killed ``Session`` with status ``'exited'``, or ``None`` if not found.
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        try:
            tmux_session = self.server.sessions.filter(
                session_name=session.tmux_session
            )
            if tmux_session:
                tmux_session[0].kill()
        except Exception as e:
            logger.warning(f"Error killing tmux session: {e}")

        session.status = "exited"
        await queries.update_session(session_id, status="exited")
        self._sessions.pop(session_id, None)
        self._panes.pop(session_id, None)

        logger.info(f"Killed session #{session.number} '{session.alias}'")
        return session

    async def pause_session(self, session_id: str) -> Session | None:
        """Pause a session by sending SIGSTOP to its process.

        Args:
            session_id: UUID of the session to pause.

        Returns:
            The paused ``Session``, or ``None`` if not found or has no PID.
        """
        session = self._sessions.get(session_id)
        if not session or not session.pid:
            return None

        try:
            os.kill(session.pid, signal.SIGSTOP)
            session.status = "paused"
            await queries.update_session(session_id, status="paused")
            logger.info(f"Paused session #{session.number}")
        except ProcessLookupError:
            session.status = "exited"
            await queries.update_session(session_id, status="exited")

        return session

    async def resume_session(self, session_id: str) -> Session | None:
        """Resume a paused session by sending SIGCONT to its process.

        Args:
            session_id: UUID of the session to resume.

        Returns:
            The resumed ``Session``, or ``None`` if not found or has no PID.
        """
        session = self._sessions.get(session_id)
        if not session or not session.pid:
            return None

        try:
            os.kill(session.pid, signal.SIGCONT)
            session.status = "running"
            await queries.update_session(session_id, status="running")
            logger.info(f"Resumed session #{session.number}")
        except ProcessLookupError:
            session.status = "exited"
            await queries.update_session(session_id, status="exited")

        return session

    async def list_sessions(self) -> list[Session]:
        """List all active sessions in memory.

        Returns:
            List of ``Session`` dataclasses for all tracked sessions.
        """
        return list(self._sessions.values())

    async def rename_session(self, session_id: str, new_alias: str) -> Session | None:
        """Rename a session's alias.

        Args:
            session_id: UUID of the session.
            new_alias: New alias string (1-50 chars, non-empty).

        Returns:
            The updated ``Session``, or ``None`` if not found.

        Raises:
            ValueError: If alias is empty or exceeds 50 characters.
        """
        if not new_alias.strip():
            raise ValueError("Alias cannot be empty")
        if len(new_alias) > 50:
            raise ValueError("Alias too long (max 50 chars)")
        session = self._sessions.get(session_id)
        if not session:
            return None
        session.alias = new_alias
        await queries.update_session(session_id, alias=new_alias)
        return session

    def get_pane(self, session_id: str) -> libtmux.Pane | None:
        """Get the tmux pane for a session.

        Args:
            session_id: UUID of the session.

        Returns:
            The ``libtmux.Pane`` object, or ``None`` if not found.
        """
        return self._panes.get(session_id)

    def get_session(self, session_id: str) -> Session | None:
        """Get session by UUID.

        Args:
            session_id: UUID of the session.

        Returns:
            The ``Session`` dataclass, or ``None`` if not found.
        """
        return self._sessions.get(session_id)

    def get_session_by_number(self, number: int) -> Session | None:
        """Get session by its numeric identifier.

        Args:
            number: Session number (assigned sequentially at creation).

        Returns:
            The ``Session`` dataclass, or ``None`` if not found.
        """
        for s in self._sessions.values():
            if s.number == number:
                return s
        return None

    def get_session_by_alias(self, alias: str) -> Session | None:
        """Get session by alias (case-insensitive match).

        Args:
            alias: Session alias to search for.

        Returns:
            The ``Session`` dataclass, or ``None`` if not found.
        """
        alias_lower = alias.lower()
        for s in self._sessions.values():
            if s.alias.lower() == alias_lower:
                return s
        return None

    def resolve_session(self, identifier: str) -> Session | None:
        """Resolve a session by number, alias, or UUID.

        Tries parsing as int (number) first, then alias (case-insensitive),
        then UUID lookup.

        Args:
            identifier: Number string, alias, or UUID.

        Returns:
            The ``Session`` dataclass, or ``None`` if no match.
        """
        # Try number
        try:
            num = int(identifier)
            s = self.get_session_by_number(num)
            if s:
                return s
        except ValueError:
            pass

        # Try alias
        s = self.get_session_by_alias(identifier)
        if s:
            return s

        # Try ID
        return self._sessions.get(identifier)

    def send_input(self, session_id: str, text: str) -> bool:
        """Send text input to a session's tmux pane.

        Args:
            session_id: UUID of the target session.
            text: Text to send (followed by Enter).

        Returns:
            ``True`` if input was sent, ``False`` if pane not found.
        """
        pane = self._panes.get(session_id)
        if not pane:
            return False
        pane.send_keys(text, enter=True)
        logger.info(f"Sent input to session {session_id} ({len(text)} chars)")
        return True

    def is_pid_alive(self, pid: int) -> bool:
        """Check if a process is still running.

        Args:
            pid: Process ID to check.

        Returns:
            ``True`` if the process exists and is accessible.
        """
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False
