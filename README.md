# Conductor

Remote terminal command center via Telegram.

Monitor long-running terminal sessions, relay prompts to your phone, auto-respond to common patterns, and manage everything from a private Telegram chat — all from bed.

## How It Feels

You're in bed. Your phone buzzes:

```
🔔 [CountWize] Session waiting for input:
"Do you want to proceed with the migration? (y/n)"

    [ ✅ Yes ]  [ ❌ No ]  [ 👀 Show Context ]
```

You tap "Yes". Done. Session continues.

5 minutes later:

```
✅ [CountWize] Task completed: Database migration finished.
   📊 Tokens used: 72% of limit
   💡 Suggested next: Run test suite to verify migration

    [ ▶️ Run Tests ]  [ 📋 View Output ]  [ ⏭️ Next Task ]
```

## Features

- **Live Session Monitoring** — poll tmux panes for output changes, detect patterns in real time
- **Smart Notifications** — permission prompts, errors, completions, rate limits — each with contextual inline buttons
- **AI Summaries** — Claude Haiku condenses terminal output into 2-4 sentence digests
- **AI Suggestions** — actionable next-step buttons generated from session context
- **Natural Language** — type "what's happening in CountWize?" instead of remembering slash commands
- **Auto-Responder** — pattern-based auto-replies for `(Y/n)`, `Press Enter`, retries — with safety guards
- **Token Tracking** — message-count estimation against Pro/Max plan tier limits with threshold warnings
- **Security** — single-user auth, API key redaction, destructive action confirmation with 30s TTL
- **Session Recovery** — reconnect to existing tmux sessions after daemon restart
- **Quiet Hours** — suppress non-urgent notifications during sleep
- **Mac Sleep Detection** — health-check sessions after wake, recalculate timers
- **Daemon Mode** — launchd plist for auto-start on login with log rotation

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     YOUR MAC (Daemon)                     │
│                                                          │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────┐ │
│  │   Session    │    │   Output     │    │    AI        │ │
│  │   Manager    │◄──►│   Monitor    │───►│   Brain     │ │
│  │  (tmux ctl)  │    │  (watcher)   │    │  (Haiku)    │ │
│  └──────┬───────┘    └──────┬───────┘    └──────┬──────┘ │
│         │                   │                   │        │
│         └───────────┬───────┴───────────────────┘        │
│                     │                                    │
│              ┌──────▼───────┐     ┌──────────────┐       │
│              │  Command     │     │   SQLite DB   │       │
│              │  Router      │◄───►│  (state +     │       │
│              │  (core hub)  │     │   history)    │       │
│              └──────┬───────┘     └──────────────┘       │
│                     │                                    │
│              ┌──────▼───────┐                            │
│              │  Auto-       │                            │
│              │  Responder   │                            │
│              │  Engine      │                            │
│              └──────┬───────┘                            │
│                     │                                    │
└─────────────────────┼────────────────────────────────────┘
                      │ HTTPS (Telegram Bot API)
                      ▼
              ┌───────────────┐
              │   Telegram    │
              │   Bot API     │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │  Your Phone   │
              │  (Private DM) │
              └───────────────┘
```

## Prerequisites

- **macOS** (launchd daemon support; tmux + sleep detection are Mac-specific)
- **Python 3.11+**
- **tmux** — `brew install tmux`
- **Telegram Bot Token** — create via [@BotFather](https://t.me/BotFather)
- **Your Telegram User ID** — get from [@userinfobot](https://t.me/userinfobot)
- **Anthropic API Key** — for AI summaries and suggestions

## Quick Start

### 1. Clone and enter the project

```bash
git clone <repo-url> CTC && cd CTC
```

### 2. Create your secrets file

```bash
mkdir -p ~/.conductor
cat > ~/.conductor/.env << 'EOF'
TELEGRAM_BOT_TOKEN=your-bot-token-here
TELEGRAM_USER_ID=your-numeric-id
ANTHROPIC_API_KEY=sk-ant-...
LOG_LEVEL=INFO
EOF
```

### 3. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 4. Verify configuration

```bash
source .venv/bin/activate
python -c "from conductor.config import get_config; c = get_config(); print('Missing:', c.validate() or 'None')"
```

### 5. Run

```bash
python -m conductor
```

Then open your Telegram bot and send `/start`.

## Command Reference

| Command     | Usage                                    | Description                                           |
| ----------- | ---------------------------------------- | ----------------------------------------------------- |
| `/start`    | `/start`                                 | Welcome message and quick-start guide                 |
| `/help`     | `/help`                                  | Full command reference                                |
| `/status`   | `/status [name\|#]`                      | Dashboard of all sessions or one session              |
| `/new`      | `/new cc\|sh <dir>`                      | Create a Claude Code or shell session                 |
| `/kill`     | `/kill <name\|#>`                        | Terminate a session (with confirmation)               |
| `/restart`  | `/restart <name\|#>`                     | Kill and recreate a session (with confirmation)       |
| `/pause`    | `/pause <name\|#>`                       | Pause (SIGSTOP) a session                             |
| `/resume`   | `/resume <name\|#>`                      | Resume (SIGCONT) a paused session                     |
| `/input`    | `/input <name\|#> <text>`                | Send text input to a session                          |
| `/output`   | `/output [name\|#]`                      | AI-summarized recent output                           |
| `/log`      | `/log [name\|#]`                         | Download full session output as .txt file             |
| `/rename`   | `/rename <#> <name>`                     | Change session alias                                  |
| `/run`      | `/run <name\|#> <cmd>`                   | Execute a command inside a session                    |
| `/shell`    | `/shell <cmd>`                           | Run a one-off shell command on your Mac (30s timeout) |
| `/tokens`   | `/tokens`                                | Token usage per session and total                     |
| `/digest`   | `/digest`                                | AI digest of session status                           |
| `/auto`     | `/auto list\|add\|remove\|pause\|resume` | Manage auto-responder rules                           |
| `/quiet`    | `/quiet [HH:MM-HH:MM]`                   | View or set quiet hours                               |
| `/settings` | `/settings`                              | View current configuration                            |

**Natural language** also works — just type:

- "what's happening in CountWize?"
- "send yes to session 1"
- "show me the tokens"

## Configuration Reference

### Secrets (`~/.conductor/.env`)

| Variable             | Required | Description                                   |
| -------------------- | -------- | --------------------------------------------- |
| `TELEGRAM_BOT_TOKEN` | Yes      | Bot token from @BotFather                     |
| `TELEGRAM_USER_ID`   | Yes      | Your numeric Telegram user ID                 |
| `ANTHROPIC_API_KEY`  | Yes      | Anthropic API key for Claude Haiku            |
| `LOG_LEVEL`          | No       | `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |

### Preferences (`config.yaml`)

All settings have sensible defaults. Edit `config.yaml` in the project root to customize.

| Section                     | Key                           | Default                      | Description                                     |
| --------------------------- | ----------------------------- | ---------------------------- | ----------------------------------------------- |
| `sessions`                  | `max_concurrent`              | `5`                          | Maximum simultaneous tmux sessions              |
| `sessions`                  | `default_type`                | `claude-code`                | Default session type (`claude-code` or `shell`) |
| `sessions`                  | `default_dir`                 | `~/projects`                 | Default working directory for new sessions      |
| `sessions`                  | `aliases`                     | `{}`                         | Path-to-alias mappings                          |
| `tokens`                    | `plan_tier`                   | `pro`                        | Anthropic plan: `pro`, `max_5x`, `max_20x`      |
| `tokens`                    | `warning_pct`                 | `80`                         | Token warning threshold (%)                     |
| `tokens`                    | `danger_pct`                  | `90`                         | Token danger threshold (%)                      |
| `tokens`                    | `critical_pct`                | `95`                         | Token critical threshold (%)                    |
| `tokens`                    | `window_hours`                | `5`                          | Token tracking window in hours                  |
| `monitor`                   | `poll_interval_ms`            | `500`                        | Default polling interval                        |
| `monitor`                   | `active_poll_interval_ms`     | `300`                        | Polling interval during active output           |
| `monitor`                   | `idle_poll_interval_ms`       | `2000`                       | Polling interval when idle (>5min)              |
| `monitor`                   | `output_buffer_max_lines`     | `5000`                       | Max lines kept in rolling buffer                |
| `monitor`                   | `completion_idle_threshold_s` | `30`                         | Seconds of idle before checking completion      |
| `notifications`             | `batch_window_s`              | `5`                          | Seconds to batch non-urgent notifications       |
| `notifications`             | `confirmation_timeout_s`      | `30`                         | Confirmation TTL for destructive actions        |
| `notifications.quiet_hours` | `enabled`                     | `false`                      | Enable quiet hours                              |
| `notifications.quiet_hours` | `start`                       | `23:00`                      | Quiet hours start (HH:MM)                       |
| `notifications.quiet_hours` | `end`                         | `07:00`                      | Quiet hours end (HH:MM)                         |
| `notifications.quiet_hours` | `timezone`                    | `Asia/Makassar`              | Timezone for quiet hours                        |
| `auto_responder`            | `enabled`                     | `true`                       | Enable auto-responder                           |
| `auto_responder`            | `default_rules`               | _(4 rules)_                  | Default pattern-response pairs                  |
| `ai`                        | `model`                       | `claude-haiku-4-5-20251001`  | AI model for summaries/suggestions              |
| `ai`                        | `summary_max_tokens`          | `200`                        | Max tokens for summaries                        |
| `ai`                        | `suggestion_max_tokens`       | `300`                        | Max tokens for suggestions                      |
| `ai`                        | `nlp_max_tokens`              | `150`                        | Max tokens for NLP parsing                      |
| `ai`                        | `timeout_seconds`             | `10`                         | API call timeout                                |
| `ai`                        | `fallback_lines`              | `20`                         | Lines to show when AI is unavailable            |
| `security`                  | `redact_patterns`             | `true`                       | Redact API keys/tokens in output                |
| `security`                  | `confirm_destructive`         | `true`                       | Require confirmation for kill/restart           |
| `security`                  | `log_all_commands`            | `true`                       | Log every command to database                   |
| `logging`                   | `file`                        | `~/.conductor/conductor.log` | Log file path                                   |
| `logging`                   | `max_size_mb`                 | `50`                         | Max log file size before rotation               |
| `logging`                   | `backup_count`                | `3`                          | Number of rotated log files to keep             |
| `logging`                   | `console_output`              | `false`                      | Also log to console (stdout)                    |

## Running as Daemon

### Install (auto-start on login)

```bash
bash scripts/install.sh
```

### Check status

```bash
launchctl list | grep conductor
```

### View logs

```bash
tail -f ~/.conductor/conductor.log
```

### Stop

```bash
launchctl unload ~/Library/LaunchAgents/com.codexs.conductor.plist
```

### Uninstall

```bash
bash scripts/uninstall.sh
```

## Project Structure

```
src/conductor/
├── __main__.py              # Entry point: python -m conductor
├── main.py                  # Async startup, event loop, shutdown
├── config.py                # Singleton config from .env + config.yaml
│
├── sessions/
│   ├── manager.py           # tmux session CRUD via libtmux
│   ├── monitor.py           # Async polling loop for pane output
│   ├── detector.py          # Pattern detection engine (5 categories)
│   ├── output_buffer.py     # ANSI stripping + deduplication
│   └── recovery.py          # Reconnect sessions after restart
│
├── bot/
│   ├── bot.py               # Bot + Dispatcher + middleware setup
│   ├── notifier.py          # Batched notifications + offline queue
│   ├── formatter.py         # Telegram message formatting (HTML)
│   ├── keyboards.py         # Inline keyboard builders
│   └── handlers/
│       ├── commands.py      # 19 slash command handlers
│       ├── callbacks.py     # Inline button callback handlers
│       ├── natural.py       # NLP → AI Brain → command dispatch
│       └── fallback.py      # Unknown input handler
│
├── ai/
│   ├── brain.py             # Claude Haiku API (summarize, suggest, NLP)
│   ├── prompts.py           # System prompts for AI calls
│   └── fallback.py          # Raw output fallback when AI is down
│
├── auto/
│   ├── responder.py         # Auto-response engine with safety guards
│   └── rules.py             # Rule CRUD (DB wrapper)
│
├── db/
│   ├── database.py          # aiosqlite connection + WAL + schema
│   ├── models.py            # Session, Command, AutoRule, Event dataclasses
│   └── queries.py           # Async CRUD for all tables
│
├── security/
│   ├── auth.py              # Telegram user ID middleware
│   ├── redactor.py          # API key / token / secret scrubbing
│   └── confirm.py           # Destructive action confirmation + TTL
│
├── tokens/
│   └── estimator.py         # Message-count estimation vs plan limits
│
└── utils/
    ├── logger.py            # Rich console + rotating file handler
    ├── errors.py            # Global error handler with escalation
    └── sleep_handler.py     # Mac sleep/wake detection
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=conductor --cov-report=term-missing

# Run a specific test file
pytest tests/test_detector.py -v
```

**Coverage**: 96.14% on unit-testable code (195 tests). Handler files that require a live Telegram bot are excluded from coverage measurement — see `pyproject.toml` `[tool.coverage.run]` for the full omit list.

## Troubleshooting

**Q: Bot doesn't respond to messages**
Check that `TELEGRAM_USER_ID` in `~/.conductor/.env` matches your actual Telegram user ID (get it from @userinfobot). The bot only responds to the configured user.

**Q: "Missing required config" on startup**
Ensure `~/.conductor/.env` exists and contains all three required variables: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_USER_ID`, `ANTHROPIC_API_KEY`.

**Q: Sessions show as "exited" after restart**
Run the daemon — it automatically recovers `conductor-*` tmux sessions on startup. If processes died during sleep, they'll be marked exited correctly.

**Q: AI summaries return raw text instead**
The Haiku API call timed out or failed. Check your `ANTHROPIC_API_KEY` is valid and you have API credits. The fallback shows the last 20 raw lines.

**Q: Notifications are delayed**
Non-urgent notifications are batched in a 5-second window (configurable via `notifications.batch_window_s` in `config.yaml`). Permission prompts and errors always send immediately.
