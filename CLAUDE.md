# Conductor — Project Instructions

## What This Is

A Telegram bot daemon that monitors and controls tmux terminal sessions.
See conductor-plan-v2.md for full architecture and plan.

## Tech Stack

- Python 3.11+, asyncio throughout
- aiogram 3.x for Telegram
- libtmux for tmux control
- aiosqlite for database (WAL mode)
- anthropic SDK for Haiku AI calls

## Key Patterns

- Everything is async (use `async def`, `await`)
- All external calls have timeout + fallback
- SQLite uses WAL mode (set on connection init)
- Config loaded once at startup from config.py
- Secrets in ~/.conductor/.env, preferences in config.yaml

## Running

```bash
source .venv/bin/activate
python -m conductor
```

## Testing

```bash
pytest tests/ -v
pytest tests/test_detector.py -v  # Unit tests only (fast)
```

## Important Files

- src/conductor/sessions/detector.py — Pattern matching (see plan Section 12)
- src/conductor/sessions/monitor.py — tmux polling (see plan Section 13)
- src/conductor/ai/prompts.py — AI system prompts (see plan Section 14)
- config.yaml — All configurable settings with comments
