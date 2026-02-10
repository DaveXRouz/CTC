# Conductor — Project Instructions

## Project Purpose

Conductor is a Telegram bot daemon that monitors and controls tmux terminal sessions on macOS. It solves the problem of babysitting long-running CLI processes (Claude Code sessions, builds, tests, deployments) by forwarding prompts to your phone and letting you respond with a tap. It also auto-responds to common patterns, summarizes output via AI, and tracks token usage.

## Architecture Map

```
main.py (startup orchestrator)
  ├── config.py ─────────────── singleton Config from .env + config.yaml
  ├── db/database.py ────────── aiosqlite init (WAL mode)
  ├── sessions/manager.py ───── tmux CRUD via libtmux
  ├── sessions/recovery.py ──── reconnect conductor-* sessions on restart
  ├── bot/bot.py ────────────── aiogram Bot + Dispatcher + auth middleware
  │     ├── handlers/commands.py ── 19 slash commands
  │     ├── handlers/callbacks.py ─ inline button handlers
  │     ├── handlers/natural.py ─── NLP → AI → command dispatch (last router)
  │     └── handlers/fallback.py ── unknown input fallback
  ├── bot/notifier.py ───────── batch queue + offline resilience
  ├── ai/brain.py ───────────── Claude Haiku (summarize, suggest, NLP)
  ├── auto/responder.py ─────── pattern match → safe auto-reply
  ├── tokens/estimator.py ───── message-count vs plan tier limits
  └── utils/sleep_handler.py ── Mac sleep/wake detection
```

Data flows **event-driven**: `monitor` polls pane → `detector` classifies → `on_monitor_event()` in `main.py` dispatches → `notifier`/`auto_responder`/`brain` handle.

## Tech Stack

| Dependency    | Version  | Purpose                                       |
| ------------- | -------- | --------------------------------------------- |
| Python        | >=3.11   | Async (match statement, `X \| Y` union types) |
| aiogram       | >=3.4.0  | Telegram Bot API (async, router-based)        |
| libtmux       | >=0.37.0 | tmux session/pane control                     |
| aiosqlite     | >=0.20.0 | Async SQLite (WAL mode)                       |
| anthropic     | >=0.40.0 | Claude Haiku API calls                        |
| pyyaml        | >=6.0    | config.yaml parsing                           |
| python-dotenv | >=1.0.0  | .env loading                                  |
| rich          | >=13.0   | Console log formatting                        |
| aiofiles      | >=24.0   | Async file I/O                                |

Dev: `pytest>=8.0`, `pytest-asyncio>=0.23`, `aioresponses>=0.7`, `pytest-cov`

## Key Patterns

### Async everywhere

Every I/O function is `async def` with `await`. The event loop is started via `asyncio.run(run())` in `__main__.py`. All database calls, API calls, and Telegram sends are awaited.

### Timeout + fallback on all external calls

- AI calls: `asyncio.wait_for(..., timeout=cfg.ai_timeout)` in `brain.py`
- Shell commands: `asyncio.wait_for(proc.communicate(), timeout=30)` in `commands.py`
- On AI failure: `ai/fallback.py` returns raw last-N-lines instead

### SQLite WAL mode

Set in `db/database.py:init_database()` via `PRAGMA journal_mode=WAL`. Also sets `busy_timeout=5000` and `synchronous=NORMAL`. This allows concurrent reads during writes.

### Singleton config

`config.py:Config` uses `__new__` for singleton. Call `get_config()` from anywhere — it loads once, returns the same instance. To reset in tests, set `Config._instance = None`.

### Event-driven monitoring

`monitor.py:OutputMonitor` polls a tmux pane on a configurable interval. New lines go through `detector.py:PatternDetector.classify()` which returns a `DetectionResult` with a type. The `on_monitor_event()` callback in `main.py` dispatches based on `result.type`.

### Router registration order

In `bot/bot.py`, routers register in order: `commands` → `callbacks` → `natural`. The `natural` router uses a bare `@router.message()` with no filter, so it catches all non-command messages. **It must be registered last** or it will swallow commands.

### Destructive keyword safety boundary

`detector.py:DESTRUCTIVE_KEYWORDS` is a list of 17 keywords ("delete", "drop", "rm -rf", "production", etc.). The auto-responder checks `has_destructive_keyword()` **before** matching rules. If any keyword is present, auto-response is blocked regardless of matching rules. This is a hard safety boundary — never bypass it.

## File-by-File Guide

### Root

- `main.py` — Async startup: init config, DB, session manager, bot, notifier, brain, auto-responder, token estimator, monitors, sleep handler. Contains `on_monitor_event()` which is the central event dispatcher. Also handles SIGINT/SIGTERM for clean shutdown.
- `config.py` — Singleton `Config` class. Loads `~/.conductor/.env` (secrets) and `config.yaml` (preferences). Properties provide typed access to all config sections.
- `__main__.py` — Entry point: `asyncio.run(run())`.

### `sessions/`

- `manager.py` — `SessionManager` class: create/kill/pause/resume/list/rename tmux sessions via libtmux. Maps session IDs to `Session` dataclasses and `libtmux.Pane` objects. `resolve_session()` finds by number, alias, or UUID.
- `monitor.py` — `OutputMonitor`: async polling loop. Adaptive poll interval (300ms active, 500ms default, 2s idle, 5s paused). Calls `detector.classify()` on new lines. Fires `on_event` callback when patterns match.
- `detector.py` — `PatternDetector.classify()`: tests text against 5 pattern groups in priority order: permission_prompt > input_prompt > rate_limit > error > completion. Returns `DetectionResult(type, matched_text, pattern, confidence)`. `has_destructive_keyword()` is a separate safety check.
- `output_buffer.py` — `OutputBuffer`: captures pane output via `pane.capture_pane()`, strips ANSI codes, deduplicates via MD5 hashes (capped at 10,000 entries to prevent memory leak), maintains rolling buffer up to `max_lines`.
- `recovery.py` — `recover_sessions()`: scans for `conductor-*` tmux sessions not in the DB, re-creates `Session` records, and starts monitors for them.

### `bot/`

- `bot.py` — `create_bot()`: creates aiogram `Bot` + `Dispatcher`, registers `AuthMiddleware` on both message and callback_query, includes routers in order. `_app_data` dict provides global shared state.
- `notifier.py` — `Notifier`: batches non-urgent notifications into a configurable window. `send()` goes through batch; `send_immediate()` bypasses it. On send failure, messages are queued offline and flushed when connectivity returns.
- `formatter.py` — HTML formatting helpers: `session_label()`, `status_line()`, `uptime_str()`, `token_bar()`, `format_session_dashboard()`, `format_status_dashboard()`, `format_event()`, `mono()`, `bold()`.
- `keyboards.py` — Inline keyboard builders for each event type: `permission_keyboard`, `completion_keyboard`, `rate_limit_keyboard`, `confirm_keyboard`, `undo_keyboard`, `status_keyboard`, `session_picker`, `suggestion_keyboard`.

### `bot/handlers/`

- `commands.py` — 19 slash command handlers. Uses a module-level `_session_manager` injected at startup via `set_session_manager()`.
- `callbacks.py` — Inline button handlers for: `confirm:`, `perm:`, `rate:`, `comp:`, `status:refresh`, `suggest:`, `undo:`, `pick:`. Manages `confirmation_mgr` (ConfirmationManager instance).
- `natural.py` — Catches all non-command messages. Checks for quick prompt responses (short text → last_prompt_session), then tries AI NLP parsing via `brain.parse_nlp()`, then falls back to sending text to the only session, then gives up.
- `fallback.py` — `send_fallback()`: friendly "I didn't understand" with /help hint.

### `ai/`

- `brain.py` — `AIBrain`: wraps the Anthropic async client. `summarize()` condenses output to 2-4 sentences. `suggest()` returns 1-3 `{label, command}` actions as JSON. `parse_nlp()` converts natural language to `{command, session, args, confidence}`.
- `prompts.py` — System prompt templates: `SUMMARIZE_PROMPT`, `SUGGEST_PROMPT`, `NLP_PARSE_PROMPT`. Each uses `.format()` to inject context.
- `fallback.py` — `get_raw_fallback()`: returns last N lines when AI is unavailable.

### `auto/`

- `responder.py` — `AutoResponder`: `check()` (sync, for tests) and `check_and_respond()` (async, for production) both enforce safety guards (permission prompts blocked, destructive keywords blocked) before matching rules. `_matches()` supports `exact`, `regex`, `contains`.
- `rules.py` — Thin async wrapper around `db/queries.py` rule functions: `get_active_rules()`, `add_rule()`, `remove_rule()`, `pause_all()`, `resume_all()`, `record_hit()`.

### `db/`

- `database.py` — `init_database()`: connects aiosqlite, sets WAL + busy_timeout + synchronous, executes schema DDL. `get_db()` returns the singleton connection. `close_database()` for shutdown.
- `models.py` — Four dataclasses: `Session` (16 fields), `Command` (6 fields), `AutoRule` (7 fields), `Event` (7 fields). All use `datetime.now().isoformat()` defaults.
- `queries.py` — All async CRUD: sessions (create, get, get_by_number, get_by_alias, get_all, update, delete, next_number), commands (log, get), auto_rules (get_all, add, delete, increment_hit, set_enabled), events (log, get, acknowledge), plus `seed_default_rules()` and `prune_old_records()`.

### `security/`

- `auth.py` — `AuthMiddleware`: aiogram middleware that checks `event.from_user.id == cfg.telegram_user_id`. Rejects unauthorized users with "Unauthorized" message.
- `redactor.py` — `redact_sensitive()`: regex-based scrubbing of Anthropic keys, GitHub tokens, AWS keys, Slack tokens, private key blocks, OAuth tokens, env var secrets. Applied automatically by notifier before sending.
- `confirm.py` — `ConfirmationManager`: stores `PendingConfirmation` objects keyed by `user:action:session`. `request()` creates, `confirm()` validates + checks TTL expiry, `cancel()` removes. 30s default TTL.

### `tokens/`

- `estimator.py` — `TokenEstimator`: counts Claude Code message exchanges per session. `get_usage()` returns `{used, limit, percentage, reset_in_seconds, tier}`. `check_thresholds()` returns `"warning"`, `"danger"`, `"critical"`, or `None`. Limits defined per tier: pro=45, max_5x=225, max_20x=900 messages per 5h window.

### `utils/`

- `logger.py` — `setup_logging()`: configures Rich console handler + rotating file handler. `get_logger()`: returns child logger. Global `_configured` flag prevents double-init.
- `errors.py` — `ErrorHandler`: counts errors by type, logs them, escalates to user (via notifier) after 5 occurrences. Resets counts every 5 minutes.
- `sleep_handler.py` — `SleepHandler`: monitors `time.monotonic()` gaps. If elapsed > threshold (15s), assumes Mac slept and fires wake callback.

## Testing

### 3-Layer Approach

1. **Unit tests** (fast, no I/O): `test_detector.py`, `test_database.py`, `test_redactor.py`, `test_auto_responder.py`
2. **Integration tests**: `test_confirm_integration.py`, `test_manager_logging.py`
3. **Handler tests are excluded from coverage** — they require a live Telegram bot connection

### Running

```bash
pytest tests/ -v                          # all tests
pytest tests/test_detector.py -v          # single file
pytest tests/ --cov=conductor --cov-report=term-missing  # with coverage
```

### Coverage Omissions

Files omitted from coverage (see `pyproject.toml`): `commands.py`, `callbacks.py`, `natural.py`, `fallback.py`, `bot.py`, `notifier.py`, `manager.py`, `monitor.py`, `recovery.py`, `auth.py`, `brain.py`, `__main__.py`, `main.py`. These require live tmux/Telegram connections.

## Common Tasks

### Adding a new slash command

1. Add handler in `bot/handlers/commands.py`:
   ```python
   @router.message(Command("mycommand"))
   async def cmd_mycommand(message: Message) -> None:
       ...
   ```
2. Update `/help` text in `cmd_help()` to include the new command.
3. If the command needs NLP support, add a branch in `natural.py:_dispatch_nlp_command()`.
4. Update the `NLP_PARSE_PROMPT` in `ai/prompts.py` to list the new command.

### Adding a detection pattern

1. Add regex patterns to the appropriate list in `sessions/detector.py` (e.g., `ERROR_PATTERNS`).
2. If it's a new category, add a new pattern list, a new priority block in `PatternDetector.classify()`, and handle the new `result.type` in `main.py:on_monitor_event()`.
3. Add tests in `tests/test_detector.py`.

### Adding an auto-response rule

Via Telegram: `/auto add "pattern" "response"`

Via code: Add to `config.yaml` under `auto_responder.default_rules`.

### Adding a callback button

1. Define the keyboard in `bot/keyboards.py`.
2. Add a handler in `bot/handlers/callbacks.py` with `@router.callback_query(F.data.startswith("prefix:"))`.
3. Wire the keyboard to a notification in `main.py:on_monitor_event()` or a command handler.

## Gotchas

### WAL mode must be set before any reads

`init_database()` sets `PRAGMA journal_mode=WAL` immediately after connecting. Don't query before init completes.

### Singleton reset in tests

`Config` is a singleton. Tests that need fresh config must do `Config._instance = None` in setup. Same for `db/database.py:_db = None`.

### Router order matters

`natural.py`'s router has a bare `@router.message()` filter. It **must** be the last included router in `bot.py`, or it catches slash commands before `commands.py` can handle them.

### Destructive keywords block auto-response

The auto-responder's safety guard (`has_destructive_keyword()`) is checked **before** rule matching. Even if a rule matches, auto-response is blocked if any of the 17 destructive keywords appear in the prompt text. This is intentional — never add a rule override.

### Circular imports

`commands.py` and `callbacks.py` share state (e.g., `confirmation_mgr`). `callbacks.py` imports from `commands.py` via a function-level import (`_get_mgr()`). Similarly, `natural.py` imports handlers lazily inside `_dispatch_nlp_command()`. Don't move these to module-level or you'll get circular imports.

### Output buffer hash cap

`output_buffer.py` caps the dedup hash dict at 10,000 entries. If you increase `output_buffer_max_lines` significantly, you may also need to raise this cap.

## Running

```bash
source .venv/bin/activate
python -m conductor
```

## Important Files

- `src/conductor/sessions/detector.py` — Pattern matching engine
- `src/conductor/sessions/monitor.py` — tmux output polling
- `src/conductor/ai/prompts.py` — AI system prompts
- `src/conductor/main.py` — Startup orchestrator + event dispatcher
- `config.yaml` — All configurable settings with comments
