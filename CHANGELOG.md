# Changelog

All notable changes to Conductor will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.0] - 2026-02-10

Polish, documentation, and quality release.

### Added

- Comprehensive docstrings on all public functions and classes across 40 source files
- README.md with project overview, setup guide, and full command reference
- 9 new test files: brain, commands handlers, confirm integration, manager (full, logging, validation), monitor, natural, notifier
- Test count increased from 195 to 476

### Changed

- UX polish across 60 message templates — emoji additions, copy rewrites for clarity
- `.gitignore` hygiene — IDE state and worker artifacts excluded

### Fixed

- 36 lint issues resolved (unused imports, empty f-strings, unused variables)
- All modules pass clean import verification

---

## [1.0.0] - 2026-02-10

First complete release. 40 build tasks, 195 tests, 96.14% coverage.

### Core

- Async daemon startup with clean SIGINT/SIGTERM shutdown (`main.py`)
- Singleton configuration from `~/.conductor/.env` (secrets) and `config.yaml` (preferences) with validation (`config.py`)
- Async SQLite database with WAL mode, busy timeout, schema auto-creation, and 4-table schema: sessions, commands, auto_rules, events (`db/database.py`)
- Structured logging with Rich console handler and rotating file handler up to 50 MB with 3 backups (`utils/logger.py`)
- Global error handler that counts errors by type, logs them, and escalates to user after 5 repeated occurrences (`utils/errors.py`)
- Automatic pruning of events and commands older than 30 days on startup

### Session Management

- Create, kill, pause (SIGSTOP), resume (SIGCONT), rename, and list tmux sessions via libtmux (`sessions/manager.py`)
- Session resolution by number, alias (case-insensitive), or UUID
- Auto-generated aliases from directory names with configurable path-to-alias mappings
- Color-coded sessions from a 6-emoji palette for visual differentiation
- Configurable max concurrent sessions (default: 5)
- Session recovery on daemon restart — scans for existing `conductor-*` tmux sessions and re-attaches monitors (`sessions/recovery.py`)
- Output deduplication via MD5 hash tracking with 10,000-entry cap to prevent memory leak (`sessions/output_buffer.py`)
- ANSI escape code stripping for clean output capture
- Rolling output buffer up to 5,000 lines per session

### Pattern Detection

- 5-category priority-ordered pattern detection engine (`sessions/detector.py`):
  1. **Permission prompts** (highest priority) — Claude Code permission requests, y/n/a prompts
  2. **Input prompts** — choose/select, numbered options, question marks, input cursors
  3. **Rate limits** — API rate limit, quota exceeded, retry-after, 429 errors
  4. **Errors** — exceptions, tracebacks, fatal, process exit codes, connection failures
  5. **Completions** (lowest priority) — task complete, tests passing, build succeeded
- 17 destructive keywords that block auto-response ("delete", "drop", "rm -rf", "production", etc.)
- Regex pattern pre-compilation and caching for performance

### AI Intelligence

- Claude Haiku integration for terminal output summarization (2-4 sentences) (`ai/brain.py`)
- AI-generated next-step suggestions as `{label, command}` pairs rendered as inline buttons
- Natural language command parsing with confidence scoring — "what's happening in CountWize?" maps to `/status CountWize`
- System prompt templates with context injection (`ai/prompts.py`)
- Graceful fallback to raw last-N-lines output when AI is unavailable (`ai/fallback.py`)
- Configurable model, max tokens, and timeout per AI function

### Auto-Responder

- Pattern-based auto-reply engine with 3 match types: `contains`, `regex`, `exact` (`auto/responder.py`)
- Safety guards: permission prompts and destructive keywords **always** block auto-response
- 4 default rules: `(Y/n)` → y, `(y/N)` → n, `Press Enter to continue` → enter, `retry? (y/n)` → y
- Rule CRUD via `/auto add|remove|list|pause|resume` commands
- Hit count tracking per rule
- Undo button on auto-response notifications (30s TTL)
- Global pause/resume for all rules

### Telegram Bot

- 19 slash commands: `/start`, `/help`, `/status`, `/new`, `/kill`, `/restart`, `/pause`, `/resume`, `/input`, `/output`, `/log`, `/rename`, `/run`, `/shell`, `/tokens`, `/digest`, `/auto`, `/quiet`, `/settings`
- Natural language handler with AI NLP parsing and fallback to single-session input relay (`handlers/natural.py`)
- 9 inline keyboard types: permission, completion, rate limit, confirm, undo, status refresh, session picker, suggestion, and custom (`keyboards.py`)
- 8 callback handler groups: confirm, permission, rate limit, completion, status refresh, suggestion, undo, session pick (`handlers/callbacks.py`)
- Batched notification sender with configurable window (default: 5s) — combines multiple updates into one message (`notifier.py`)
- Offline message queue with automatic flush on connectivity recovery
- Background connectivity checker (30s polling)
- HTML message formatting with emoji status indicators (`formatter.py`)
- Friendly fallback for unrecognized input (`handlers/fallback.py`)

### Token Tracking

- Message-count estimation against Anthropic plan tier limits (`tokens/estimator.py`)
- Three tiers: Pro (~45/5h), Max 5x (~225/5h), Max 20x (~900/5h)
- Three warning thresholds: warning (80%), danger (90%), critical (95%)
- Per-session and aggregate usage tracking
- Rolling 5-hour window with automatic reset
- Response boundary detection based on idle time + line count

### Security

- Single-user authentication via Telegram user ID middleware — rejects all other users (`security/auth.py`)
- Automatic redaction of 12 sensitive data patterns before sending to Telegram: Anthropic keys, GitHub tokens, AWS keys, Slack tokens, NPM tokens, private key blocks, OAuth tokens, env var secrets (`security/redactor.py`)
- Destructive action confirmation with 30-second TTL for `/kill` and `/restart` — expired confirmations are rejected (`security/confirm.py`)
- Pending confirmation cleanup for expired entries

### DevOps

- launchd plist for macOS daemon auto-start on login (`scripts/com.codexs.conductor.plist`)
- Install script: creates `~/.conductor`, installs venv + dependencies, loads launchd plist (`scripts/install.sh`)
- Uninstall script: unloads plist, kills conductor tmux sessions, preserves user data (`scripts/uninstall.sh`)
- Mac sleep/wake detection via monotonic time gap monitoring — triggers session health checks on wake (`utils/sleep_handler.py`)
- Quiet hours: suppress non-urgent notifications during configurable time window
