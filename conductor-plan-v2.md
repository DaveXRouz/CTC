# 🎛️ Conductor — Remote Terminal Command Center via Telegram

> *"Orchestra-level control of your Mac terminals, from your bed."*

---

## TL;DR

- **What**: A Telegram bot running as a daemon on your Mac that gives you full remote control of Claude Code sessions + terminal commands
- **Why**: Never miss a blocking prompt, never wonder about token limits, never lose a session while AFK
- **How**: Python daemon → monitors tmux sessions → relays via Telegram bot → AI-summarized outputs → smart auto-responses
- **Sessions**: Supports 3–5 concurrent sessions, auto-detected by project name
- **Intelligence**: Medium AI brain (Claude Haiku) for summaries + suggested next actions
- **Automation**: Auto-answers simple y/n prompts, auto-pauses on rate limits, confirms destructive actions
- **Timeline**: Solid v1 in ~1 week across 5 phases (Phase 0 = setup prerequisites)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Phase 0 — Prerequisites & Setup](#3-phase-0--prerequisites--setup)
4. [Core Features](#4-core-features)
5. [Telegram UX Design](#5-telegram-ux-design)
6. [Notification System](#6-notification-system)
7. [AI Intelligence Layer](#7-ai-intelligence-layer)
8. [Auto-Responder Engine](#8-auto-responder-engine)
9. [Security Model](#9-security-model)
10. [Session Management](#10-session-management)
11. [Rate Limit Handling](#11-rate-limit-handling)
12. [Implementation Specs — Pattern Detection](#12-implementation-specs--pattern-detection)
13. [Implementation Specs — tmux Monitoring Algorithm](#13-implementation-specs--tmux-monitoring-algorithm)
14. [Implementation Specs — AI System Prompts](#14-implementation-specs--ai-system-prompts)
15. [Implementation Specs — Token Estimation](#15-implementation-specs--token-estimation)
16. [Implementation Specs — Output Deduplication & Streaming](#16-implementation-specs--output-deduplication--streaming)
17. [Implementation Specs — Error Handling Strategy](#17-implementation-specs--error-handling-strategy)
18. [Implementation Specs — Testing Strategy](#18-implementation-specs--testing-strategy)
19. [Command Reference](#19-command-reference)
20. [Tech Stack](#20-tech-stack)
21. [Config File Examples](#21-config-file-examples)
22. [File & Folder Structure](#22-file--folder-structure)
23. [Database Schema](#23-database-schema)
24. [Build Phases](#24-build-phases)
25. [Verification Checklist](#25-verification-checklist)

---

## 1. Project Overview

### The Problem

When you step away from your Mac, your Claude Code sessions keep running — but they get **stuck**. They hit prompts asking for confirmation (`Press 1 or 2`), run into rate limits, crash silently, or complete without you knowing. Every minute blocked = wasted time and tokens.

### The Solution

**Conductor** is a lightweight Python daemon that runs on your Mac. It wraps all your terminal sessions inside `tmux` (a terminal multiplexer = a tool that keeps terminal sessions alive in the background), monitors their output in real-time, and bridges everything to a Telegram bot you control from your phone.

### How It Feels

```
You're in bed. Your phone buzzes:

🔔 [CountWize] Session waiting for input:
"Do you want to proceed with the migration? (y/n)"

    [ ✅ Yes ]  [ ❌ No ]  [ 👀 Show Context ]

You tap "Yes". Done. Session continues.

5 minutes later:

✅ [CountWize] Task completed: Database migration finished.
   📊 Tokens used: 72% of limit
   💡 Suggested next: Run test suite to verify migration

    [ ▶️ Run Tests ]  [ 📋 View Output ]  [ ⏭️ Next Task ]
```

---

## 2. Architecture

### High-Level Diagram

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
              │  📱 Your      │
              │  Telegram     │
              │  (Private DM) │
              └───────────────┘
```

### Component Breakdown

| Component | Role | Technology |
|-----------|------|------------|
| **Session Manager** | Create, kill, restart tmux sessions; attach Claude Code or shell | `libtmux` (Python tmux API) |
| **Output Monitor** | Watch session output buffers in real-time; detect patterns | `asyncio` polling of tmux capture-pane |
| **AI Brain** | Summarize long outputs; suggest next actions | Claude Haiku API (cheap + fast) |
| **Command Router** | Parse user input (slash, natural language, buttons); dispatch | Custom parser + regex + AI fallback |
| **Auto-Responder** | Match known prompts; auto-reply simple confirmations | Pattern matching engine |
| **Telegram Bot** | Handle messages, callbacks, send notifications | `aiogram 3.x` (async Telegram framework) |
| **SQLite DB** | Store session state, command history, auto-response rules | `aiosqlite` |

---

## 3. Phase 0 — Prerequisites & Setup

**IMPORTANT**: These steps must be done BEFORE any code is written. The build phases assume all of this is already in place.

### 3.1 Install tmux on Mac

```bash
# Install via Homebrew
brew install tmux

# Verify version (need 3.0+)
tmux -V
# Expected: tmux 3.4 (or similar)
```

### 3.2 Create a Telegram Bot

Step-by-step (takes ~2 minutes):

1. Open Telegram on your phone
2. Search for `@BotFather` (the official bot that creates other bots)
3. Send `/newbot`
4. BotFather asks: "What name for your bot?" → Type: `Conductor Terminal Bot`
5. BotFather asks: "Choose a username" → Type: `conductor_term_bot` (must end in `bot`, must be unique; try variations if taken)
6. BotFather gives you a **bot token** — looks like: `7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
7. **Save this token** — it goes in the `.env` file

### 3.3 Get Your Telegram User ID

1. Search for `@userinfobot` in Telegram
2. Send it any message
3. It replies with your **numeric user ID** — looks like: `123456789`
4. **Save this ID** — it goes in the `.env` file (this is how the bot knows only YOU can control it)

### 3.4 Get an Anthropic API Key (for AI Brain)

1. Go to `https://console.anthropic.com/`
2. Sign in or create account
3. Go to API Keys → Create Key
4. Copy the key — looks like: `sk-ant-api03-xxxxxxxxxxxx`
5. **Save this key** — it goes in the `.env` file

### 3.5 Python Environment

```bash
# Verify Python 3.11+
python3 --version
# Expected: Python 3.11.x or higher

# If not installed:
brew install python@3.12
```

### 3.6 Create Project Directory

```bash
mkdir -p ~/.conductor
mkdir -p ~/projects/conductor
cd ~/projects/conductor

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Verify
which python
# Expected: /Users/dave/projects/conductor/.venv/bin/python
```

---

## 4. Core Features

### 4.1 Session Lifecycle Control

Full remote control of terminal sessions:

| Action | Description | Destructive? |
|--------|-------------|:------------:|
| **Create** | Start a new tmux session with Claude Code or shell | No |
| **Pause** | Freeze session (SIGSTOP) | No |
| **Resume** | Unfreeze paused session (SIGCONT) | No |
| **Restart** | Kill + recreate with same config | ⚠️ Confirm |
| **Kill** | Terminate session entirely | ⚠️ Confirm |
| **List** | Show all active sessions with status | No |
| **Rename** | Change session alias/project name | No |

### 4.2 Input Relay

When a session is waiting for input (detected by the Output Monitor), the bot:

1. Sends you the prompt text with surrounding context
2. Shows inline action buttons if choices are detected (e.g., `[1]` `[2]`)
3. Accepts your typed response and sends it to the terminal
4. Confirms the input was delivered

### 4.3 Output Viewing

| Request | Response |
|---------|----------|
| "What's happening in CountWize?" | AI-summarized status (2–4 sentences) |
| "Show me the last output" | Last 30 lines as text in chat |
| "Full log please" | Sent as `.txt` file attachment |
| "Screenshot" | Terminal screenshot (captured via tmux) |

### 4.4 Remote Command Execution

Run any shell command in a specific session or in a new one-off shell:

```
/run CountWize git status
/run CountWize npm test
/shell ls -la ~/projects/
```

### 4.5 Status Dashboard (On-Demand)

When you type `/status` or "what's going on?":

```
📊 Conductor Status — 3 Active Sessions
─────────────────────────────────

🟢 #1 CountWize (Claude Code)
   ├ Status: Running
   ├ Tokens: 58% used (12,400 / 21,000)
   ├ Uptime: 2h 34m
   └ Last: "Implementing edge function for fraud detection"

🟡 #2 NPS-Solver (Claude Code)
   ├ Status: ⏸ WAITING FOR INPUT
   ├ Tokens: 81% used ⚠️
   ├ Uptime: 1h 12m
   └ Prompt: "Which encoding format? (1) FC60 (2) Base58"

🔴 #3 Codexs-Site (Shell)
   ├ Status: Exited (error)
   ├ Exit code: 1
   ├ Uptime: 0h 04m
   └ Last error: "npm ERR! ENOENT package.json"

   [ 🔄 Refresh ]  [ ▶️ Answer #2 ]  [ 🔧 Fix #3 ]
```

---

## 5. Telegram UX Design

### 5.1 Chat Structure

**Single private chat** with the bot. Sessions are separated by **labels** (emoji + project name prefix on every message).

```
🏷️ Session Labels:

  🔵 CountWize     — Claude Code session
  🟣 NPS-Solver    — Claude Code session
  🟠 Codexs-Site   — Shell session
  🟢 Quick-Shell   — One-off command
```

Color assignment: Colors are assigned in order from a fixed palette: 🔵 🟣 🟠 🟢 🔴 🟤. When a session ends, its color becomes available for reuse.

### 5.2 Message Types

**Alert messages** (text, no buttons):
```
⚠️ 🟣 NPS-Solver
Token usage at 82%. Consider wrapping up current task.
```

**Action messages** (text + inline buttons):
```
❓ 🔵 CountWize is waiting:
"Apply these changes to 3 files? (y/n)"

  [ ✅ Yes ]  [ ❌ No ]  [ 👀 Context ]  [ ✏️ Custom ]
```

**Completion messages** (text + suggested actions):
```
✅ 🔵 CountWize — Task Complete
"Successfully deployed edge function auth-verify"

💡 Suggested: Run integration tests

  [ ▶️ Run Tests ]  [ 📋 Full Log ]  [ 🔄 New Task ]
```

### 5.3 Input Methods (Hybrid)

All three methods work interchangeably:

| Method | Example | Best For |
|--------|---------|----------|
| **Slash commands** | `/status`, `/kill 2`, `/run NPS git log` | Power users, precision |
| **Natural language** | "what's CountWize doing?", "restart the NPS session" | Lazy in bed, conversational |
| **Inline buttons** | Tap `[ ✅ Yes ]` on a prompt notification | Quick responses, one-tap |

### 5.4 Session Auto-Detection

When you type a message, the bot figures out which session you mean:

| Your Message | Bot Resolves To |
|-------------|-----------------|
| "yes" (after a prompt from CountWize) | → CountWize (last prompt context) |
| "what's happening in NPS?" | → NPS-Solver (keyword match) |
| "run npm test" (only one shell session) | → That shell session |
| "kill session 2" | → Session #2 by number |
| Ambiguous message | Bot asks: "Which session?" with buttons |

**Resolution priority**: Last active prompt > keyword match > session number > ask user.

### 5.5 Auto-Detection Algorithm (Pseudocode)

```python
def resolve_session(user_message: str, context: SessionContext) -> Session | AskUser:
    # Priority 1: If a session just prompted and user replies within 60s
    if context.last_prompt and context.last_prompt.age_seconds < 60:
        if is_likely_response(user_message):  # short text, y/n, number, etc.
            return context.last_prompt.session

    # Priority 2: Explicit session reference
    match = re.search(r'(?:session\s*)?#?(\d+)', user_message)
    if match:
        return get_session_by_number(int(match.group(1)))

    # Priority 3: Project name keyword match
    for session in active_sessions:
        if session.alias.lower() in user_message.lower():
            return session

    # Priority 4: If only one session exists
    if len(active_sessions) == 1:
        return active_sessions[0]

    # Priority 5: AI Brain resolves from context
    ai_guess = ai_brain.resolve_session(user_message, active_sessions)
    if ai_guess and ai_guess.confidence > 0.8:
        return ai_guess.session

    # Give up — ask user
    return AskUser(options=active_sessions)
```

---

## 6. Notification System

### 6.1 Instant Alerts

All four event types trigger an immediate push notification:

| Event | Emoji | Priority | Sound |
|-------|-------|----------|-------|
| Session waiting for input | ❓ | 🔴 Critical | Default |
| Token limit approaching (80%+) | ⚠️ | 🟡 Warning | Silent |
| Session crashed/errored | 🔴 | 🔴 Critical | Default |
| Task completed | ✅ | 🟢 Info | Silent |

Telegram notification sound control: Use `disable_notification=True` parameter in `aiogram` for silent alerts, `disable_notification=False` for audible ones.

### 6.2 Smart Batching

If multiple events fire within 5 seconds, they're combined into one message to prevent spam:

```
📬 3 Updates:
  ❓ 🔵 CountWize — Waiting for input
  ⚠️ 🟣 NPS-Solver — Tokens at 85%
  ✅ 🟠 Codexs-Site — Build complete
```

Implementation: Use an `asyncio` queue with a 5-second flush timer. Events are pushed to the queue. A background task drains it every 5 seconds. If only 1 event, send immediately. If 2+, combine into one message.

### 6.3 On-Demand Digest

No periodic spam. You ask when you want:

```
You: /digest
Bot: [sends full status dashboard]

You: "give me a summary"
Bot: [AI-generated summary of all session activity since last check]
```

### 6.4 Quiet Hours (Optional)

Configure via `/quiet 23:00-07:00` — during quiet hours:
- ❓ Input prompts → still alert (critical)
- 🔴 Crashes → still alert (critical)
- ⚠️ Token warnings → queued for morning
- ✅ Completions → queued for morning

---

## 7. AI Intelligence Layer

### 7.1 Purpose

The AI Brain (Claude Haiku via API) provides three capabilities:

| Capability | What It Does |
|-----------|--------------|
| **Summarize** | Condense 100+ lines of terminal output into 2–4 sentences |
| **Suggest** | Recommend the logical next action after a task completes |
| **Parse** | Understand natural language commands and route them correctly |

### 7.2 How Summaries Work

```
Raw terminal output (247 lines):
  Installing dependencies...
  npm WARN deprecated package@1.2...
  [many lines]
  ✓ Compiled successfully
  ✓ 42 tests passed
  ✗ 2 tests failed: auth.test.js, payment.test.js
  Done in 34.2s

AI Summary:
  "Build succeeded. 42/44 tests passed. 2 failures in
  auth.test.js and payment.test.js. Took 34 seconds."
```

### 7.3 Suggested Actions

After task completion, the AI analyzes context and suggests 1–3 next steps:

```
Context: Tests failed in auth module
Suggestions:
  1. "View failing test details" → /output NPS auth.test
  2. "Fix auth tests" → send "fix the failing auth tests" to Claude Code
  3. "Skip and continue" → send "continue with next task" to Claude Code
```

These appear as inline buttons.

### 7.4 Natural Language Parsing

The AI Brain handles converting casual messages to commands:

```
"yo what's my token situation" → /tokens (all sessions)
"kill that broken one" → /kill [session with error status]
"send yes to the waiting one" → /input [session waiting for input] yes
"start a new claude session for the website" → /new claude-code ~/projects/codexs-site
```

### 7.5 Cost Estimate

Using Claude Haiku for the AI layer keeps costs very small:

| Action | Tokens (approx.) | Cost |
|--------|-------------------|------|
| Summarize output | ~500 in / ~100 out | ~$0.0003 |
| Suggest next action | ~300 in / ~80 out | ~$0.0002 |
| Parse natural language | ~100 in / ~50 out | ~$0.0001 |
| **Daily estimate** (heavy use) | ~50 calls/day | **~$0.02/day** |

---

## 8. Auto-Responder Engine

### 8.1 What It Handles

The auto-responder catches **simple, predictable prompts** and answers them without bothering you.

| Pattern | Auto-Response | Notify? |
|---------|--------------|---------|
| `(y/n)` or `(Y/n)` where default is yes | Sends `y` | ✅ Silent log |
| `Press Enter to continue` | Sends Enter | ✅ Silent log |
| `(1/2)` simple choice with obvious default | Sends the default | ✅ Silent log |
| `retry? (y/n)` after a timeout | Sends `y` (retry) | ✅ Notify after |
| Permission prompts (`Allow?`) | **Does NOT auto-answer** | ❓ Asks you |
| Anything ambiguous or destructive | **Does NOT auto-answer** | ❓ Asks you |

### 8.2 Configuration

Auto-response rules are stored in SQLite and editable via Telegram:

```
/auto list                     — Show all rules
/auto add "pattern" "response" — Add new rule
/auto remove 3                 — Delete rule #3
/auto pause                    — Disable all auto-responses
/auto resume                   — Re-enable
```

### 8.3 Safety

- Auto-responses are **logged** so you can audit what the bot answered
- A `[ 🔙 Undo ]` button appears for 30 seconds after each auto-response
- Destructive-looking prompts (delete, remove, overwrite, drop) are **never** auto-answered
- You can see the auto-response log anytime: `/auto log`

---

## 9. Security Model

### 9.1 Access Control

| Layer | Implementation |
|-------|---------------|
| **Telegram User ID** | Only your numeric Telegram ID is authorized. Hardcoded on first setup. |
| **Destructive Action Confirm** | Kill, restart, and shell commands require a confirmation tap. |
| **Local Only** | The daemon only runs on your Mac. No cloud relay, no exposed ports. |
| **Bot Token** | Stored in `.env` file with `600` permissions (owner-only read). |
| **No Sensitive Data in Chat** | Tokens, API keys, passwords are redacted from output before sending to Telegram. |

### 9.2 Confirmation Flow for Destructive Actions

```
You: /kill CountWize

Bot: ⚠️ Confirm: Kill session 🔵 CountWize?
     This will terminate the Claude Code process.
     Unsaved work may be lost.

     [ 🗑️ Yes, Kill It ]  [ ↩️ Cancel ]

     ⏱️ Auto-cancels in 30 seconds.
```

Implementation: Store a `pending_confirmation` dict keyed by `(user_id, action_type, session_id)` with a 30-second TTL (time-to-live). If no response, delete the pending entry and send "Action cancelled (timeout)."

### 9.3 Sensitive Data Redaction

The Output Monitor scans terminal output before sending to Telegram and redacts:

```python
# Redaction patterns (regex)
REDACTION_PATTERNS = [
    # API keys
    (r'sk-ant-api\S+', '[REDACTED:ANTHROPIC_KEY]'),
    (r'sk-[a-zA-Z0-9]{20,}', '[REDACTED:API_KEY]'),
    (r'key-[a-zA-Z0-9]{20,}', '[REDACTED:API_KEY]'),
    (r'ghp_[a-zA-Z0-9]{36}', '[REDACTED:GITHUB_TOKEN]'),
    (r'gho_[a-zA-Z0-9]{36}', '[REDACTED:GITHUB_TOKEN]'),
    (r'npm_[a-zA-Z0-9]{36}', '[REDACTED:NPM_TOKEN]'),

    # Generic secrets in env vars
    (r'(?i)(password|secret|token|api_key)\s*=\s*\S+', r'\1=[REDACTED]'),

    # OAuth tokens
    (r'Bearer\s+[a-zA-Z0-9\-._~+/]+=*', 'Bearer [REDACTED]'),

    # .env file contents (entire lines)
    (r'^[A-Z_]+=(sk-|key-|ghp_|gho_|npm_)\S+$', '[REDACTED:ENV_LINE]'),
]
```

---

## 10. Session Management

### 10.1 Session Types

| Type | Started With | Use Case |
|------|-------------|----------|
| **Claude Code** | `claude` command in tmux | AI-assisted coding sessions |
| **Shell** | `zsh`/`bash` in tmux | Git, npm, deploy, scripts |
| **One-off** | `/shell <command>` | Quick commands, then auto-closes |

### 10.2 Session Registration

When you create a session, it's registered with:

```
Session #1:
  ├ ID: uuid-abc123
  ├ Alias: "CountWize"
  ├ Type: claude-code
  ├ Working Dir: ~/projects/countwize
  ├ tmux Session: conductor-1
  ├ tmux Window: 0
  ├ tmux Pane: 0
  ├ PID: 48291
  ├ Created: 2026-02-10 14:30:00
  ├ Status: running
  └ Token Usage: { used: 12400, limit: 21000, pct: 59 }
```

### 10.3 How tmux Sessions Are Created (Exact Commands)

```python
import libtmux

server = libtmux.Server()

# Create Claude Code session
def create_claude_code_session(alias: str, working_dir: str, session_number: int):
    session_name = f"conductor-{session_number}"
    session = server.new_session(
        session_name=session_name,
        start_directory=working_dir,
        attach=False,  # Don't attach — we're a daemon
    )
    pane = session.attached_window.attached_pane

    # Start Claude Code in the pane
    pane.send_keys("claude", enter=True)

    return session, pane

# Create shell session
def create_shell_session(alias: str, working_dir: str, session_number: int):
    session_name = f"conductor-{session_number}"
    session = server.new_session(
        session_name=session_name,
        start_directory=working_dir,
        attach=False,
    )
    return session, session.attached_window.attached_pane

# Send input to a session
def send_input(pane, text: str):
    pane.send_keys(text, enter=True)

# Kill a session
def kill_session(session_name: str):
    session = server.find_where({"session_name": session_name})
    if session:
        session.kill_session()
```

### 10.4 Session Recovery

If the daemon restarts (Mac reboot, crash), it:

1. Scans for existing `conductor-*` tmux sessions
2. Re-attaches monitors to found sessions
3. Sends you a notification: "Conductor restarted. Recovered 3 sessions."
4. Sessions that died during downtime are reported as crashed

```python
def recover_sessions():
    """Scan for existing conductor tmux sessions and re-attach monitors."""
    server = libtmux.Server()
    recovered = []
    for session in server.sessions:
        if session.name.startswith("conductor-"):
            number = int(session.name.split("-")[1])
            # Check if PID is still alive
            pane = session.attached_window.attached_pane
            pid = pane.get("pane_pid")
            if pid and is_pid_alive(int(pid)):
                recovered.append(re_register_session(session, number))
            else:
                mark_session_dead(session, number)
    return recovered
```

### 10.5 Project Directory Mapping

Sessions auto-detect their project name from the working directory:

```python
def guess_alias_from_dir(working_dir: str) -> str:
    """Convert directory path to a readable alias."""
    # ~/projects/countwize → "CountWize"
    # ~/projects/nps-solver → "NPS-Solver"
    folder_name = os.path.basename(working_dir)

    # Convert kebab-case and snake_case to Title Case
    parts = re.split(r'[-_]', folder_name)
    return "-".join(part.capitalize() for part in parts)
```

You can also set custom aliases: `/rename 1 FraudApp`

---

## 11. Rate Limit Handling

### 11.1 Detection

The Output Monitor watches for Claude Code rate limit patterns:

```python
# See Section 12 for the full pattern list
RATE_LIMIT_PATTERNS = [
    r"rate limit",
    r"usage limit",
    r"too many requests",
    r"please wait",
    r"try again in \d+",
    r"429",
    r"capacity",
    r"cooldown",
]
```

### 11.2 Auto-Pause Behavior

When a rate limit is detected:

```
1. Session is auto-paused (SIGSTOP to prevent wasted retries)
2. You get a notification:

   ⚠️ 🟣 NPS-Solver — Rate Limited
   Paused automatically. Limit resets in ~15 minutes.

   Token usage: 95% (19,950 / 21,000)

   [ ▶️ Resume Now ]  [ ⏰ Auto-Resume in 15m ]  [ 🔄 Switch Task ]

3. If you choose auto-resume, the daemon waits and resumes automatically
4. You get a follow-up: "🟣 NPS-Solver resumed after rate limit cooldown"
```

### 11.3 Auto-Resume Implementation

```python
async def schedule_auto_resume(session_id: str, delay_minutes: int):
    """Wait then resume a paused session."""
    await asyncio.sleep(delay_minutes * 60)
    session = get_session(session_id)
    if session and session.status == "paused":
        os.kill(session.pid, signal.SIGCONT)
        session.status = "running"
        await notify_user(f"▶️ {session.emoji} {session.alias} resumed after cooldown.")
```

---

## 12. Implementation Specs — Pattern Detection

**This is the most critical section.** The Output Monitor must correctly identify what's happening in each terminal session. Here are the EXACT patterns to match.

### 12.1 Claude Code Permission Prompts

When Claude Code wants to run a tool (bash command, file edit, etc.), it shows a permission prompt. The format in the terminal looks like this:

```
╭─────────────────────────────────────────────╮
│ Claude wants to run:                        │
│                                             │
│   rm -rf node_modules                       │
│                                             │
│ Allow? (y = yes, n = no, a = always allow)  │
╰─────────────────────────────────────────────╯
```

Alternative formats Claude Code uses:

```
# Format A: Tool permission
Do you want to allow Claude to use Bash(npm install)?
  Yes (y)  |  No (n)  |  Always (a)

# Format B: File edit permission
Claude wants to edit src/main.py
  Allow? [y/n/a]

# Format C: New tool first-use
Allow Claude to use the "Write" tool?
  (y)es / (n)o / (a)lways allow
```

**Regex patterns to detect ALL permission prompt variants:**

```python
PERMISSION_PROMPT_PATTERNS = [
    # "Claude wants to run/edit/use" patterns
    r"Claude wants to (?:run|edit|use|write|read|delete)",
    r"Do you want to allow Claude to use",
    r"Allow Claude to use",

    # The actual prompt part (what user needs to answer)
    r"Allow\?\s*\(?[yna]",
    r"\(y\)es\s*/\s*\(n\)o",
    r"\[y/n(?:/a)?\]",
    r"Yes \(y\)\s*\|\s*No \(n\)",

    # Generic confirmation from Claude Code
    r"Do you want to proceed",
    r"Would you like to continue",
    r"Press Enter to continue",
    r"Continue\?\s*\[",
]

# These are NEVER auto-responded — always forwarded to user
# because they involve granting permissions to Claude Code
```

### 12.2 Claude Code User-Facing Prompts

These are prompts where Claude Code is asking the USER for input (not permission-related):

```python
CLAUDE_CODE_INPUT_PROMPTS = [
    # Numbered choices
    r"(?:Choose|Select|Pick)\s+(?:one|an option|from)",
    r"^\s*\d+[\.\)]\s+\w+",  # "1. Option A\n2. Option B"
    r"\(\d+\)\s+\w+",        # "(1) Option A (2) Option B"

    # Open-ended questions
    r"\?\s*$",                # Any line ending with ?
    r"(?:Enter|Type|Provide|Input|Specify)\s+(?:a|the|your)",

    # Waiting indicator (cursor blinking on empty line after prompt)
    r">\s*$",                 # Prompt character waiting for input
    r"❯\s*$",                # Alternative prompt character
]
```

### 12.3 Rate Limit Patterns

```python
RATE_LIMIT_PATTERNS = [
    # Explicit rate limit messages
    r"(?i)rate\s*limit(?:ed)?",
    r"(?i)usage\s*limit\s*(?:reached|exceeded|hit)",
    r"(?i)too\s*many\s*requests",
    r"(?i)(?:please\s+)?wait\s+(?:\d+\s*(?:second|minute|hour)|\w+\s+before)",
    r"(?i)try\s*again\s*(?:in|after)\s*\d+",
    r"(?i)429\s*(?:error)?",
    r"(?i)capacity\s*(?:limit|exceeded)",
    r"(?i)cooldown",
    r"(?i)quota\s*(?:exceeded|reached)",

    # Claude Code specific
    r"(?i)you(?:'ve| have)\s+(?:reached|hit|exceeded)\s+(?:your|the)\s+(?:usage|message|token)\s+limit",
    r"(?i)limit\s+will\s+reset",
]
```

### 12.4 Error/Crash Patterns

```python
ERROR_PATTERNS = [
    # Process exit
    r"(?i)(?:error|err!|fatal|panic|exception|traceback|segfault)",
    r"(?i)process\s+exited\s+with\s+(?:code|status)\s+[^0]",
    r"(?i)command\s+(?:failed|not found)",
    r"(?i)killed|terminated|aborted",
    r"(?i)SIGTERM|SIGKILL|SIGSEGV",

    # npm/node errors
    r"npm\s+ERR!",
    r"(?i)unhandled\s+(?:promise\s+)?rejection",
    r"(?i)cannot\s+find\s+module",

    # Python errors
    r"Traceback \(most recent call last\)",
    r"(?:ModuleNotFoundError|ImportError|SyntaxError|TypeError|ValueError)",

    # Claude Code specific errors
    r"(?i)connection\s+(?:lost|reset|refused|timed?\s*out)",
    r"(?i)authentication\s+(?:failed|error|expired)",
    r"(?i)api\s+(?:error|unavailable)",
]
```

### 12.5 Task Completion Patterns

```python
COMPLETION_PATTERNS = [
    # Explicit completion signals
    r"(?i)(?:task|job|build|test|deployment?)\s+(?:complete[d]?|finish(?:ed)?|done|success(?:ful)?)",
    r"(?i)all\s+(?:tests?\s+)?pass(?:ed|ing)?",
    r"(?i)✓|✅|☑",
    r"(?i)successfully\s+(?:built|compiled|deployed|installed|created|updated)",

    # Claude Code returning to prompt (idle state after work)
    # This is detected by: active output for 10+ seconds → then silence for 30+ seconds
    # Combined with the presence of a prompt character (>, ❯, $)

    # Build tool completions
    r"(?i)compiled?\s+(?:successfully|with\s+\d+\s+warning)",
    r"(?i)build\s+succeeded",
    r"Done in \d+",
    r"\d+\s+passing",
]
```

### 12.6 Destructive Action Keywords (Never Auto-Respond)

```python
DESTRUCTIVE_KEYWORDS = [
    "delete", "remove", "drop", "truncate", "destroy",
    "overwrite", "replace all", "reset", "wipe", "purge",
    "force push", "hard reset", "rm -rf", "uninstall",
    "migrate", "rollback", "production", "deploy",
]
```

---

## 13. Implementation Specs — tmux Monitoring Algorithm

### 13.1 The Core Problem

tmux stores terminal output in a **scrollback buffer** (like a text file that grows as the terminal prints). We need to:
1. Read new output since last check
2. Not re-read old output (deduplication)
3. Not miss output that happened between checks
4. Be fast enough (<2 second latency from event to detection)

### 13.2 The Algorithm

```python
import asyncio
import libtmux

class OutputMonitor:
    def __init__(self, pane: libtmux.Pane, session_id: str):
        self.pane = pane
        self.session_id = session_id
        self.last_line_count = 0           # How many lines we've read so far
        self.last_content_hash = ""        # Hash of last captured content
        self.idle_seconds = 0              # Seconds since last new output
        self.active_output = False         # Was there recent output?
        self.poll_interval = 0.5           # Seconds between checks (500ms)

    async def monitor_loop(self):
        """Main monitoring loop — runs forever for each session."""
        while True:
            try:
                new_lines = self.capture_new_output()

                if new_lines:
                    self.idle_seconds = 0
                    self.active_output = True
                    await self.process_output(new_lines)
                else:
                    self.idle_seconds += self.poll_interval

                    # If was active but now idle for 30s → possible completion
                    if self.active_output and self.idle_seconds >= 30:
                        self.active_output = False
                        await self.check_for_completion()

            except Exception as e:
                logger.error(f"Monitor error for {self.session_id}: {e}")

            await asyncio.sleep(self.poll_interval)

    def capture_new_output(self) -> list[str]:
        """Capture only NEW lines from tmux pane since last check."""
        # capture_pane returns all visible + scrollback lines
        all_lines = self.pane.capture_pane(
            start="-500",    # Capture last 500 lines of scrollback
            end="-0",        # Up to current cursor position
        )

        # Only return lines we haven't seen before
        if len(all_lines) > self.last_line_count:
            new_lines = all_lines[self.last_line_count:]
            self.last_line_count = len(all_lines)

            # Filter out empty lines at the end (cursor position artifact)
            while new_lines and not new_lines[-1].strip():
                new_lines.pop()

            return new_lines

        return []

    async def process_output(self, lines: list[str]):
        """Analyze new output lines for patterns."""
        text = "\n".join(lines)

        # Check patterns in priority order
        if self.matches_permission_prompt(text):
            await self.handle_permission_prompt(text, lines)
        elif self.matches_input_prompt(text):
            await self.handle_input_prompt(text, lines)
        elif self.matches_rate_limit(text):
            await self.handle_rate_limit(text)
        elif self.matches_error(text):
            await self.handle_error(text, lines)
        elif self.matches_completion(text):
            await self.handle_completion(text, lines)

        # Always store output in rolling buffer for /output and /log commands
        self.output_buffer.extend(lines)
        # Keep buffer at max 5000 lines
        if len(self.output_buffer) > 5000:
            self.output_buffer = self.output_buffer[-5000:]
```

### 13.3 Polling Interval

| Scenario | Interval | Why |
|----------|----------|-----|
| Default | 500ms (0.5s) | Good balance of responsiveness vs CPU |
| Active output detected | 300ms (0.3s) | More responsive during active work |
| Session idle >5 minutes | 2000ms (2s) | Save CPU when nothing is happening |
| Session paused | 5000ms (5s) | Just checking if it was externally resumed |

```python
def get_poll_interval(self) -> float:
    if self.status == "paused":
        return 5.0
    elif self.idle_seconds > 300:  # 5 minutes idle
        return 2.0
    elif self.active_output:
        return 0.3
    else:
        return 0.5
```

### 13.4 CPU Impact

With 5 sessions monitored at 500ms intervals:
- Each `capture_pane` call: ~1ms CPU time
- 5 sessions × 2 calls/second = 10 calls/second
- Total CPU: ~10ms/second = **1% CPU usage**
- With adaptive polling (idle sessions): even less

---

## 14. Implementation Specs — AI System Prompts

### 14.1 Summarize Output Prompt

```python
SUMMARIZE_PROMPT = """You are a terminal output summarizer for a developer. You receive raw terminal output from a coding session.

Rules:
1. Summarize in 2-4 sentences maximum
2. Focus on: what happened, what succeeded, what failed
3. Include specific numbers (test counts, error counts, file names)
4. Skip noise: dependency installation details, warnings that don't matter, verbose logs
5. If there are errors, always mention the file name and error type
6. Use plain, simple English

Example input:
  npm install
  added 234 packages in 12s
  npm run test
  PASS src/auth.test.js (3 tests)
  PASS src/utils.test.js (5 tests)
  FAIL src/payment.test.js
    ● should process refund → Expected 200, received 500
  Test Suites: 1 failed, 2 passed, 3 total
  Tests: 1 failed, 8 passed, 9 total

Example output:
  "Dependencies installed. 8/9 tests passed. 1 failure in payment.test.js — the refund test expected status 200 but got 500."

Now summarize this terminal output:
---
{terminal_output}
---"""
```

### 14.2 Suggest Next Actions Prompt

```python
SUGGEST_PROMPT = """You are a helpful coding assistant. Based on the terminal output and session context, suggest 1-3 logical next actions the developer should take.

Rules:
1. Each suggestion must be actionable (a specific command or instruction)
2. Order by priority (most important first)
3. Format each as: {"label": "short button text", "command": "actual command to run"}
4. If tests failed → suggest viewing details or fixing
5. If build succeeded → suggest deploy or next task
6. If error occurred → suggest fix or debug
7. Max 3 suggestions

Session info:
- Project: {project_alias}
- Session type: {session_type}
- Working directory: {working_dir}

Terminal output (last 50 lines):
---
{terminal_output}
---

Respond in JSON only:
[
  {"label": "View error details", "command": "cat src/payment.test.js"},
  {"label": "Fix payment test", "command": "fix the failing refund test in payment.test.js"},
  {"label": "Run tests again", "command": "npm test"}
]"""
```

### 14.3 Natural Language Parser Prompt

```python
NLP_PARSE_PROMPT = """You are a command parser for a terminal management bot. Convert the user's natural language message into a structured command.

Available commands:
- status: Show session status (optional: session name/number)
- input: Send text to a session (requires: session, text)
- kill: Kill a session (requires: session)
- restart: Restart a session (requires: session)
- pause: Pause a session (requires: session)
- resume: Resume a session (requires: session)
- output: Show recent output (optional: session)
- log: Get full log file (optional: session)
- run: Execute shell command in session (requires: session, command)
- shell: Run one-off shell command (requires: command)
- tokens: Show token usage (optional: session)
- new: Create session (requires: type [cc/sh], directory)
- digest: Full status digest
- help: Show help

Active sessions:
{session_list_json}

Last prompt context (if any):
{last_prompt_context}

User message: "{user_message}"

Respond in JSON only:
{
  "command": "status",
  "session": "CountWize",  // or null if not specified
  "args": {},              // additional arguments
  "confidence": 0.95       // how sure you are (0.0-1.0)
}

If you cannot determine the command, respond:
{"command": "unknown", "confidence": 0.0, "clarification": "Which session do you mean?"}"""
```

---

## 15. Implementation Specs — Token Estimation

### 15.1 The Challenge

Claude Code does NOT expose a clear "tokens used: X/Y" counter in terminal output. Token tracking has to be estimated.

### 15.2 Estimation Strategy

**Method: Output Volume Tracking**

Since we can't read Claude Code's internal token counter, we estimate based on observable signals:

```python
class TokenEstimator:
    def __init__(self, plan_tier: str = "pro"):
        # Approximate limits per 5-hour window
        self.limits = {
            "pro": {"messages": 45, "description": "~45 messages per 5h"},
            "max_5x": {"messages": 225, "description": "~225 messages per 5h"},
            "max_20x": {"messages": 900, "description": "~900 messages per 5h"},
        }
        self.tier = plan_tier
        self.session_starts = {}   # session_id → datetime
        self.message_counts = {}   # session_id → int (observed request/response pairs)
        self.window_start = None   # When the 5-hour window started

    def on_claude_response(self, session_id: str, output_lines: list[str]):
        """Called when we detect Claude Code has responded (output appeared after prompt)."""
        if session_id not in self.message_counts:
            self.message_counts[session_id] = 0
        self.message_counts[session_id] += 1

        if self.window_start is None:
            self.window_start = datetime.now()

    def get_usage(self, session_id: str = None) -> dict:
        """Get estimated usage across all sessions or one session."""
        limit = self.limits[self.tier]["messages"]

        if session_id:
            used = self.message_counts.get(session_id, 0)
        else:
            used = sum(self.message_counts.values())

        pct = min(100, int((used / limit) * 100))

        # Time until window resets
        if self.window_start:
            elapsed = (datetime.now() - self.window_start).total_seconds()
            reset_seconds = max(0, (5 * 3600) - elapsed)
        else:
            reset_seconds = None

        return {
            "used": used,
            "limit": limit,
            "percentage": pct,
            "reset_in_seconds": reset_seconds,
            "tier": self.tier,
        }

    def check_thresholds(self) -> str | None:
        """Check if any warning threshold is crossed."""
        usage = self.get_usage()
        pct = usage["percentage"]
        if pct >= 95:
            return "critical"   # 🔴 auto-pause
        elif pct >= 90:
            return "danger"     # 🔴 strong warning
        elif pct >= 80:
            return "warning"    # 🟡 warning
        return None
```

### 15.3 Detecting Claude Code Message Exchanges

To count "messages" (request/response pairs), we watch for the pattern:
1. User prompt appears (we sent input or Claude Code asked for something)
2. Silence (Claude is thinking)
3. Output starts flowing (Claude is responding)
4. Output stops → **count as 1 message**

```python
def detect_message_boundary(self, new_lines: list[str]) -> bool:
    """Detect when Claude Code has completed a response (one message exchange)."""
    # If we were in an idle state and now see substantial output (>5 lines),
    # that's likely a new response from Claude
    if self.idle_seconds > 3 and len(new_lines) > 5:
        return True
    return False
```

### 15.4 Configuration

```yaml
# config.yaml
token_tracking:
  plan_tier: "pro"          # "pro", "max_5x", or "max_20x"
  warning_threshold: 80     # Percentage to trigger warning
  danger_threshold: 90      # Percentage to trigger strong warning
  critical_threshold: 95    # Percentage to auto-pause
  window_hours: 5           # Reset window (Anthropic standard)
```

---

## 16. Implementation Specs — Output Deduplication & Streaming

### 16.1 The Problem

Claude Code streams output character by character. When we poll with `capture_pane`, we might see:
- Same content twice (if nothing changed between polls)
- Partial lines (line is being written mid-poll)
- ANSI escape codes (colors, cursor movement)

### 16.2 Deduplication Solution

```python
class OutputBuffer:
    """Manages deduplicated output capture from a tmux pane."""

    def __init__(self):
        self.seen_line_hashes = set()      # Hashes of lines we've already processed
        self.last_capture_length = 0        # Number of lines in last capture
        self.partial_line = ""              # Incomplete line from last capture
        self.rolling_buffer = []            # Last 5000 lines of output

    def get_new_lines(self, pane) -> list[str]:
        """Get only truly new, complete lines from the pane."""
        raw = pane.capture_pane(start="-1000", end="-0")

        # Clean ANSI escape codes
        cleaned = [self._strip_ansi(line) for line in raw]

        # Only take lines after our last known position
        if len(cleaned) <= self.last_capture_length:
            return []  # No new lines

        new_lines = cleaned[self.last_capture_length:]
        self.last_capture_length = len(cleaned)

        # Deduplicate using hashes (handles tmux scrollback weirdness)
        truly_new = []
        for line in new_lines:
            line_hash = hashlib.md5(line.encode()).hexdigest()
            if line_hash not in self.seen_line_hashes:
                self.seen_line_hashes.add(line_hash)
                truly_new.append(line)

        # Prevent hash set from growing forever (keep last 10000)
        if len(self.seen_line_hashes) > 10000:
            self.seen_line_hashes = set(list(self.seen_line_hashes)[-5000:])

        self.rolling_buffer.extend(truly_new)
        if len(self.rolling_buffer) > 5000:
            self.rolling_buffer = self.rolling_buffer[-5000:]

        return truly_new

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """Remove ANSI escape codes (colors, cursor movement, etc.)."""
        ansi_pattern = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_pattern.sub('', text)
```

### 16.3 Streaming vs. Snapshot Decision

We use a **snapshot approach** with smart timing:

| Phase | What Happens | When We Snapshot |
|-------|-------------|-----------------|
| Idle | No output | Poll every 2s |
| Active streaming | Claude is writing output | Poll every 300ms, buffer lines |
| Prompt detected | A pattern match fires | Process immediately |
| Stream ended | 3+ seconds of silence after activity | Snapshot the full response |

**We do NOT try to stream to Telegram in real-time** because:
1. Telegram has rate limits (30 messages/second per bot, 20 messages/minute per chat)
2. Char-by-char streaming would be unreadable on phone
3. Smart snapshots with AI summaries are much more useful

---

## 17. Implementation Specs — Error Handling Strategy

### 17.1 Error Categories & Responses

| Error | Impact | Recovery |
|-------|--------|----------|
| **Telegram API timeout** | Can't send notification | Queue message, retry with exponential backoff (1s, 2s, 4s, max 60s) |
| **Telegram API 429 (rate limit)** | Too many messages | Pause sending for `Retry-After` header seconds |
| **Haiku API down** | No AI summaries | Fall back to raw output (last 20 lines as plain text) |
| **Haiku API timeout** | Slow summary | 10-second timeout; if exceeded, send raw output instead |
| **tmux session died externally** | Session gone | Detect via PID check; mark as "exited"; notify user |
| **tmux server not running** | All sessions gone | Start tmux server; attempt recovery; notify user |
| **SQLite locked** | Can't read/write state | Retry 3 times with 100ms delay; use WAL mode to prevent |
| **Daemon crash** | Everything stops | launchd auto-restarts; session recovery runs on startup |
| **Mac goes to sleep** | Timers freeze | On wake: recalculate all timers; check session health; notify user |
| **Internet drops** | Can't reach Telegram | Queue all notifications; flush when connection returns |

### 17.2 Global Error Handler

```python
import asyncio
import logging

logger = logging.getLogger("conductor")

class ErrorHandler:
    def __init__(self, notifier):
        self.notifier = notifier
        self.error_counts = {}   # error_type → count
        self.notification_queue = asyncio.Queue()

    async def handle(self, error: Exception, context: str):
        """Global error handler — log, count, and decide recovery."""
        error_type = type(error).__name__
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

        logger.error(f"[{context}] {error_type}: {error}")

        # If same error happens 5+ times in 5 minutes, alert user
        if self.error_counts[error_type] >= 5:
            await self.escalate(error_type, context)

    async def escalate(self, error_type: str, context: str):
        """Alert user about repeated errors."""
        try:
            await self.notifier.send(
                f"🔴 Repeated error in {context}: {error_type} "
                f"({self.error_counts[error_type]} times). "
                f"Check daemon logs: ~/.conductor/conductor.log"
            )
        except Exception:
            # If we can't even notify, just log
            logger.critical(f"Cannot notify user about {error_type}")

    def reset_counts(self):
        """Reset error counts periodically (every 5 minutes)."""
        self.error_counts.clear()
```

### 17.3 Notification Queue (Offline Resilience)

```python
class NotificationQueue:
    """Queue notifications when Telegram is unreachable."""

    def __init__(self, bot, chat_id):
        self.bot = bot
        self.chat_id = chat_id
        self.queue = asyncio.Queue()
        self.is_online = True

    async def send(self, text: str, **kwargs):
        """Try to send; queue if offline."""
        try:
            await self.bot.send_message(self.chat_id, text, **kwargs)
            self.is_online = True
            # Flush any queued messages
            await self._flush_queue()
        except Exception:
            self.is_online = False
            await self.queue.put((text, kwargs))
            logger.warning(f"Queued notification (offline). Queue size: {self.queue.qsize()}")

    async def _flush_queue(self):
        """Send all queued messages."""
        while not self.queue.empty():
            text, kwargs = await self.queue.get()
            try:
                await self.bot.send_message(self.chat_id, text, **kwargs)
                await asyncio.sleep(0.1)  # Respect rate limits
            except Exception:
                await self.queue.put((text, kwargs))
                break

    async def connectivity_checker(self):
        """Background task to check if Telegram is reachable."""
        while True:
            if not self.is_online:
                try:
                    await self.bot.get_me()
                    self.is_online = True
                    await self._flush_queue()
                except Exception:
                    pass
            await asyncio.sleep(30)  # Check every 30s
```

### 17.4 AI Fallback Chain

```python
async def get_summary(self, terminal_output: str) -> str:
    """Get AI summary with fallback chain."""
    # Try 1: Claude Haiku (fast, cheap)
    try:
        return await self._call_haiku(terminal_output, timeout=10)
    except asyncio.TimeoutError:
        logger.warning("Haiku timeout, falling back to raw output")
    except Exception as e:
        logger.warning(f"Haiku error: {e}, falling back to raw output")

    # Fallback: Dumb summary (last 20 lines, truncated)
    lines = terminal_output.strip().split("\n")
    last_20 = lines[-20:]
    return "📝 Raw output (AI unavailable):\n" + "\n".join(last_20)
```

---

## 18. Implementation Specs — Testing Strategy

### 18.1 Testing Approach

We use **three layers** of tests:

| Layer | What | How | Tools |
|-------|------|-----|-------|
| **Unit tests** | Pattern detection, redaction, formatting | Pure functions, no external dependencies | `pytest` |
| **Integration tests** | tmux interaction, SQLite queries | Real tmux sessions in test mode | `pytest` + `libtmux` |
| **End-to-end tests** | Full flow from terminal event to Telegram message | Mock Telegram API, real tmux | `pytest` + `aioresponses` |

### 18.2 Unit Test Examples

```python
# tests/test_detector.py
import pytest
from conductor.sessions.detector import PatternDetector

detector = PatternDetector()

class TestPermissionPrompts:
    """Test that all Claude Code permission prompt formats are detected."""

    @pytest.mark.parametrize("text", [
        "Claude wants to run: rm -rf node_modules\nAllow? (y/n/a)",
        "Do you want to allow Claude to use Bash(npm install)?\n  Yes (y)  |  No (n)",
        "Claude wants to edit src/main.py\n  Allow? [y/n/a]",
        "Allow Claude to use the \"Write\" tool?\n  (y)es / (n)o / (a)lways allow",
    ])
    def test_detects_permission_prompts(self, text):
        result = detector.classify(text)
        assert result.type == "permission_prompt"

    @pytest.mark.parametrize("text", [
        "Running npm install...\ninstalled 234 packages",
        "Tests passed: 42/42",
        "Building project...",
    ])
    def test_does_not_false_positive(self, text):
        result = detector.classify(text)
        assert result.type != "permission_prompt"


class TestRateLimits:
    @pytest.mark.parametrize("text", [
        "Rate limit exceeded. Please wait 30 seconds.",
        "You've reached your usage limit",
        "Error 429: Too many requests",
        "Usage limit reached. Limit will reset in 2 hours.",
    ])
    def test_detects_rate_limits(self, text):
        result = detector.classify(text)
        assert result.type == "rate_limit"


class TestErrorPatterns:
    @pytest.mark.parametrize("text", [
        "npm ERR! ENOENT: no such file",
        "Traceback (most recent call last):\n  File \"main.py\"",
        "FATAL: password authentication failed",
        "process exited with code 1",
    ])
    def test_detects_errors(self, text):
        result = detector.classify(text)
        assert result.type == "error"


class TestCompletionPatterns:
    @pytest.mark.parametrize("text", [
        "✓ Build succeeded",
        "All 42 tests passed",
        "Successfully deployed to production",
        "Done in 34.2s",
    ])
    def test_detects_completions(self, text):
        result = detector.classify(text)
        assert result.type == "completion"
```

```python
# tests/test_redactor.py
import pytest
from conductor.security.redactor import redact_sensitive

class TestRedaction:
    def test_redacts_anthropic_key(self):
        text = "export ANTHROPIC_API_KEY=sk-ant-api03-abcdef123456"
        result = redact_sensitive(text)
        assert "sk-ant" not in result
        assert "[REDACTED" in result

    def test_redacts_github_token(self):
        text = "Token: ghp_ABC123DEF456GHI789JKL012MNO345PQR678"
        result = redact_sensitive(text)
        assert "ghp_" not in result

    def test_preserves_normal_text(self):
        text = "Running npm test... 42 tests passed"
        result = redact_sensitive(text)
        assert result == text

    def test_redacts_bearer_token(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR..."
        result = redact_sensitive(text)
        assert "eyJ" not in result
```

```python
# tests/test_auto_responder.py
import pytest
from conductor.auto.responder import AutoResponder

responder = AutoResponder()

class TestAutoResponder:
    def test_auto_responds_to_yn_default_yes(self):
        result = responder.check("Continue? (Y/n)")
        assert result.should_respond == True
        assert result.response == "y"

    def test_auto_responds_to_enter(self):
        result = responder.check("Press Enter to continue...")
        assert result.should_respond == True
        assert result.response == ""

    def test_blocks_destructive_prompts(self):
        result = responder.check("Delete all data? (y/n)")
        assert result.should_respond == False
        assert "delete" in result.block_reason.lower()

    def test_blocks_permission_prompts(self):
        result = responder.check("Allow Claude to use Bash(rm -rf node_modules)?")
        assert result.should_respond == False
```

### 18.3 Integration Test Setup

```python
# tests/conftest.py
import pytest
import libtmux

@pytest.fixture
def tmux_server():
    """Create a real tmux server for integration tests."""
    server = libtmux.Server()
    yield server
    # Cleanup: kill all test sessions
    for session in server.sessions:
        if session.name.startswith("conductor-test-"):
            session.kill_session()

@pytest.fixture
def test_session(tmux_server):
    """Create a test tmux session with a shell."""
    session = tmux_server.new_session(
        session_name="conductor-test-1",
        attach=False,
    )
    pane = session.attached_window.attached_pane
    yield pane
    session.kill_session()
```

```python
# tests/test_monitor_integration.py
import asyncio
import pytest
from conductor.sessions.monitor import OutputMonitor

@pytest.mark.asyncio
async def test_captures_new_output(test_session):
    """Verify monitor captures output from a real tmux pane."""
    monitor = OutputMonitor(test_session, "test-session-1")

    # Send a command to the pane
    test_session.send_keys("echo 'HELLO_CONDUCTOR_TEST'", enter=True)
    await asyncio.sleep(1)  # Wait for output

    new_lines = monitor.capture_new_output()
    assert any("HELLO_CONDUCTOR_TEST" in line for line in new_lines)

@pytest.mark.asyncio
async def test_no_duplicate_output(test_session):
    """Verify same output isn't captured twice."""
    monitor = OutputMonitor(test_session, "test-session-1")

    test_session.send_keys("echo 'UNIQUE_LINE_12345'", enter=True)
    await asyncio.sleep(1)

    first_capture = monitor.capture_new_output()
    second_capture = monitor.capture_new_output()

    unique_in_first = [l for l in first_capture if "UNIQUE_LINE_12345" in l]
    unique_in_second = [l for l in second_capture if "UNIQUE_LINE_12345" in l]

    assert len(unique_in_first) == 1
    assert len(unique_in_second) == 0  # Should not appear again
```

### 18.4 Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run only unit tests (fast, no tmux needed)
pytest tests/test_detector.py tests/test_redactor.py tests/test_auto_responder.py -v

# Run integration tests (needs tmux)
pytest tests/test_monitor_integration.py -v

# Run with coverage report
pytest tests/ --cov=conductor --cov-report=term-missing
```

---

## 19. Command Reference

### Slash Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/status` | Show all session statuses | `/status` |
| `/status <n>` | Show one session's status | `/status CountWize` |
| `/new cc <dir>` | Start Claude Code session | `/new cc ~/projects/countwize` |
| `/new sh <dir>` | Start shell session | `/new sh ~/projects/nps` |
| `/kill <name\|#>` | Kill a session (confirms) | `/kill 2` |
| `/restart <name\|#>` | Restart a session (confirms) | `/restart CountWize` |
| `/pause <name\|#>` | Pause a session | `/pause NPS` |
| `/resume <name\|#>` | Resume a paused session | `/resume NPS` |
| `/input <name\|#> <text>` | Send text input to session | `/input 1 yes` |
| `/output <name\|#>` | Get AI summary of recent output | `/output CountWize` |
| `/log <name\|#>` | Get full output as .txt file | `/log 2` |
| `/run <name\|#> <cmd>` | Run a shell command in session | `/run CountWize git status` |
| `/shell <cmd>` | Run a one-off shell command | `/shell df -h` |
| `/tokens` | Show token usage for all sessions | `/tokens` |
| `/digest` | Full status digest on demand | `/digest` |
| `/auto list` | List auto-response rules | `/auto list` |
| `/auto add` | Add auto-response rule | `/auto add "y/n" "y"` |
| `/auto pause` | Pause auto-responder | `/auto pause` |
| `/quiet <range>` | Set quiet hours | `/quiet 23:00-07:00` |
| `/rename <#> <n>` | Rename a session | `/rename 2 FraudApp` |
| `/help` | Show command reference | `/help` |
| `/settings` | Show bot configuration | `/settings` |

### Natural Language Examples

| You Say | Bot Understands |
|---------|----------------|
| "what's going on?" | `/status` (all sessions) |
| "how's CountWize?" | `/status CountWize` |
| "show me the NPS log" | `/log NPS-Solver` |
| "yes" (after a prompt) | `/input [last-prompting-session] yes` |
| "kill the broken one" | `/kill [session with error]` |
| "start a new session for the website" | `/new cc ~/projects/codexs-site` |
| "run tests in CountWize" | `/run CountWize npm test` |
| "token check" | `/tokens` |
| "what did CountWize just do?" | `/output CountWize` |

---

## 20. Tech Stack

### Chosen Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| **Language** | Python 3.11+ | Best tmux library (`libtmux`), great async support, fast prototyping, strong Telegram bot ecosystem |
| **Telegram Bot** | `aiogram 3.x` | Async-native, modern, well-maintained, supports inline keyboards, callbacks, file uploads |
| **Terminal Multiplexer** | `tmux` (3.0+) | Industry standard for session management; libtmux provides clean Python API |
| **Database** | SQLite via `aiosqlite` (WAL mode) | Zero infrastructure, local file, perfect for single-user, supports async, WAL mode prevents locking |
| **AI Brain** | Claude Haiku API via `anthropic` SDK | Cheapest Claude model (~$0.02/day), fast responses, good enough for summaries |
| **Process Manager** | `launchd` (macOS native) | Native macOS daemon management; auto-restart on crash, start on boot |
| **Config** | `.env` + `config.yaml` | Secrets in `.env`, preferences in YAML |
| **Logging** | Python `logging` + `rich` | Structured logs to file + pretty console output for debugging |

### Dependencies

```
# requirements.txt

# Core
aiogram>=3.4.0          # Telegram bot framework
libtmux>=0.37.0         # tmux Python API
aiosqlite>=0.20.0       # Async SQLite
anthropic>=0.40.0       # Claude API client (for Haiku)
pyyaml>=6.0             # Config parsing
python-dotenv>=1.0.0    # Environment variables

# Utilities
rich>=13.0              # Pretty logging (local console)
aiofiles>=24.0          # Async file operations

# Testing
pytest>=8.0             # Test framework
pytest-asyncio>=0.23    # Async test support
aioresponses>=0.7       # Mock HTTP responses
```

---

## 21. Config File Examples

### 21.1 `.env` File

```bash
# ~/.conductor/.env
# ⚠️ SECRETS ONLY — never commit this file

# Telegram Bot Token (from @BotFather)
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Your Telegram User ID (from @userinfobot)
TELEGRAM_USER_ID=123456789

# Anthropic API Key (for AI Brain / Haiku)
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxx

# Log level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
```

File permissions: `chmod 600 ~/.conductor/.env`

### 21.2 `config.yaml` File

```yaml
# ~/.conductor/config.yaml
# User preferences — safe to edit anytime

# ── Session defaults ──
sessions:
  max_concurrent: 5                # Max sessions allowed
  default_type: "claude-code"      # Default session type for /new
  default_dir: "~/projects"        # Default working directory

  # Project alias mappings (override auto-detection)
  aliases:
    "~/projects/countwize": "CountWize"
    "~/projects/nps-solver": "NPS-Solver"
    "~/projects/codexs-site": "Codexs-Site"

# ── Token tracking ──
tokens:
  plan_tier: "pro"                 # "pro", "max_5x", "max_20x"
  warning_pct: 80                  # Yellow warning at this %
  danger_pct: 90                   # Red warning at this %
  critical_pct: 95                 # Auto-pause at this %
  window_hours: 5                  # Reset window

# ── Monitoring ──
monitor:
  poll_interval_ms: 500            # Default polling interval
  active_poll_interval_ms: 300     # When output is streaming
  idle_poll_interval_ms: 2000      # When session is idle >5min
  output_buffer_max_lines: 5000    # Rolling buffer size per session
  completion_idle_threshold_s: 30  # Seconds of silence = task done

# ── Notifications ──
notifications:
  batch_window_s: 5                # Combine events within this window
  confirmation_timeout_s: 30       # Auto-cancel destructive confirms

  quiet_hours:
    enabled: false
    start: "23:00"
    end: "07:00"
    timezone: "Asia/Makassar"      # Bali timezone (WITA)

  # Which events make sound
  sounds:
    input_required: true           # 🔴 Audible
    token_warning: false           # 🟡 Silent
    error: true                    # 🔴 Audible
    completed: false               # 🟢 Silent

# ── Auto-Responder ──
auto_responder:
  enabled: true

  # Default rules (can be modified via /auto commands)
  default_rules:
    - pattern: "(Y/n)"
      response: "y"
      match_type: "contains"
    - pattern: "(y/N)"
      response: "n"
      match_type: "contains"
    - pattern: "Press Enter to continue"
      response: ""
      match_type: "contains"
    - pattern: "retry\\? \\(y/n\\)"
      response: "y"
      match_type: "regex"

# ── AI Brain ──
ai:
  model: "claude-haiku-4-5-20251001"  # Cheapest, fastest
  summary_max_tokens: 200              # Keep summaries short
  suggestion_max_tokens: 300           # Keep suggestions concise
  nlp_max_tokens: 150                  # Keep command parsing lean
  timeout_seconds: 10                  # Fallback to raw output if slower
  fallback_lines: 20                   # Raw output lines when AI unavailable

# ── Security ──
security:
  redact_patterns: true               # Enable sensitive data redaction
  confirm_destructive: true           # Require confirmation for kill/restart
  log_all_commands: true              # Log every command for audit

# ── Logging ──
logging:
  file: "~/.conductor/conductor.log"
  max_size_mb: 50
  backup_count: 3                     # Keep 3 rotated log files
  console_output: false               # Set true for debugging
```

### 21.3 `launchd` Plist (macOS Daemon Config)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <!-- Unique label for this daemon -->
    <key>Label</key>
    <string>com.codexs.conductor</string>

    <!-- The command to run -->
    <key>ProgramArguments</key>
    <array>
        <!-- Use the full path to the venv python -->
        <string>/Users/dave/projects/conductor/.venv/bin/python</string>
        <string>-m</string>
        <string>conductor</string>
    </array>

    <!-- Working directory -->
    <key>WorkingDirectory</key>
    <string>/Users/dave/projects/conductor</string>

    <!-- Start on boot / login -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Auto-restart if it crashes -->
    <key>KeepAlive</key>
    <true/>

    <!-- Wait 5 seconds before restarting after crash -->
    <key>ThrottleInterval</key>
    <integer>5</integer>

    <!-- Logs -->
    <key>StandardOutPath</key>
    <string>/Users/dave/.conductor/daemon-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/dave/.conductor/daemon-stderr.log</string>

    <!-- Environment variables -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>HOME</key>
        <string>/Users/dave</string>
    </dict>
</dict>
</plist>
```

**Installing the daemon:**

```bash
# Copy plist to LaunchAgents (user-level daemon, not system)
cp scripts/com.codexs.conductor.plist ~/Library/LaunchAgents/

# Load the daemon (starts immediately)
launchctl load ~/Library/LaunchAgents/com.codexs.conductor.plist

# Check if it's running
launchctl list | grep conductor

# Manually stop
launchctl unload ~/Library/LaunchAgents/com.codexs.conductor.plist

# View logs
tail -f ~/.conductor/conductor.log
```

---

## 22. File & Folder Structure

```
conductor/
├── .env.example                    # Template for secrets (committed to git)
├── config.yaml                     # User preferences (committed, but overridden locally)
├── requirements.txt                # Python dependencies
├── pyproject.toml                  # Project metadata + pytest config
├── README.md                       # Setup & usage guide
├── CLAUDE.md                       # Instructions for Claude Code to understand this project
│
├── src/
│   └── conductor/
│       ├── __init__.py
│       ├── __main__.py             # Entry point: `python -m conductor`
│       ├── main.py                 # Startup: init all components, run event loop
│       ├── config.py               # Load .env + config.yaml, validate, provide defaults
│       │
│       ├── bot/                    # Telegram Bot Layer
│       │   ├── __init__.py
│       │   ├── bot.py              # Bot init, register handlers, middleware
│       │   ├── handlers/
│       │   │   ├── __init__.py
│       │   │   ├── commands.py     # /status, /kill, /new, /run, etc.
│       │   │   ├── callbacks.py    # Inline button callback handlers
│       │   │   ├── natural.py      # Natural language → command routing
│       │   │   └── fallback.py     # Unknown input handler
│       │   ├── keyboards.py        # Inline keyboard builders (buttons)
│       │   ├── formatter.py        # Message formatting (emoji, labels, monospace)
│       │   └── notifier.py         # Push notification sender + queue
│       │
│       ├── sessions/               # Session Management Layer
│       │   ├── __init__.py
│       │   ├── manager.py          # Create, kill, list, pause, resume sessions
│       │   ├── monitor.py          # Watch tmux output, detect patterns (Section 13)
│       │   ├── detector.py         # Pattern matching engine (Section 12)
│       │   ├── output_buffer.py    # Deduplication + ANSI stripping (Section 16)
│       │   └── recovery.py         # Recover sessions after daemon restart
│       │
│       ├── ai/                     # AI Intelligence Layer
│       │   ├── __init__.py
│       │   ├── brain.py            # Summarize, suggest, parse (Haiku calls)
│       │   ├── prompts.py          # System prompts (Section 14)
│       │   └── fallback.py         # Fallback when AI is unavailable
│       │
│       ├── auto/                   # Auto-Responder Engine
│       │   ├── __init__.py
│       │   ├── responder.py        # Pattern match + auto-reply logic
│       │   └── rules.py            # Default + custom rule management
│       │
│       ├── security/               # Security Layer
│       │   ├── __init__.py
│       │   ├── auth.py             # Telegram user ID verification middleware
│       │   ├── redactor.py         # Sensitive data scrubbing (Section 9.3)
│       │   └── confirm.py          # Destructive action confirmation flow
│       │
│       ├── tokens/                 # Token Tracking Layer
│       │   ├── __init__.py
│       │   └── estimator.py        # Token usage estimation (Section 15)
│       │
│       ├── db/                     # Database Layer
│       │   ├── __init__.py
│       │   ├── database.py         # Connection + migrations + WAL mode
│       │   ├── models.py           # Session, Command, AutoRule, Event dataclasses
│       │   └── queries.py          # All SQL queries as functions
│       │
│       └── utils/                  # Shared Utilities
│           ├── __init__.py
│           ├── logger.py           # Structured logging setup
│           └── errors.py           # Global error handler (Section 17)
│
├── scripts/
│   ├── install.sh                  # One-line setup script
│   ├── uninstall.sh                # Clean removal
│   └── com.codexs.conductor.plist  # launchd daemon config (Section 21.3)
│
└── tests/
    ├── conftest.py                 # Shared fixtures (tmux server, test sessions)
    ├── test_detector.py            # Pattern detection (Section 18.2)
    ├── test_redactor.py            # Sensitive data redaction
    ├── test_auto_responder.py      # Auto-response rules
    ├── test_formatter.py           # Message formatting
    ├── test_token_estimator.py     # Token tracking
    ├── test_output_buffer.py       # Deduplication
    └── test_monitor_integration.py # Real tmux integration tests (Section 18.3)
```

### CLAUDE.md (for Claude Code)

This file tells Claude Code how to work with the project:

```markdown
# Conductor — Project Instructions

## What This Is
A Telegram bot daemon that monitors and controls tmux terminal sessions.
See README.md for full architecture and plan.

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
- Secrets in .env, preferences in config.yaml

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
```

---

## 23. Database Schema

### SQLite Setup (WAL mode for concurrent access)

```python
async def init_database(db_path: str):
    """Initialize SQLite with WAL mode and create tables."""
    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA journal_mode=WAL")      # Prevent locking
    await db.execute("PRAGMA busy_timeout=5000")      # Wait 5s on lock
    await db.execute("PRAGMA synchronous=NORMAL")     # Good balance of speed/safety

    await db.executescript(SCHEMA)
    return db
```

### Full Schema

```sql
-- sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,                          -- UUID
    number INTEGER NOT NULL,                      -- Session number (1, 2, 3...)
    alias TEXT NOT NULL,                          -- Project name ("CountWize")
    type TEXT NOT NULL CHECK(type IN ('claude-code', 'shell', 'one-off')),
    working_dir TEXT NOT NULL,                    -- Absolute path
    tmux_session TEXT NOT NULL,                   -- tmux session name
    tmux_pane_id TEXT,                            -- tmux pane identifier
    pid INTEGER,                                  -- Process ID
    status TEXT NOT NULL DEFAULT 'running'
        CHECK(status IN ('running', 'paused', 'waiting', 'error', 'exited', 'rate_limited')),
    color_emoji TEXT NOT NULL DEFAULT '🔵',       -- Session label color
    token_used INTEGER DEFAULT 0,                 -- Estimated tokens used
    token_limit INTEGER DEFAULT 45,               -- Known token limit
    last_activity TEXT,                            -- ISO datetime of last output
    last_summary TEXT,                             -- Most recent AI summary
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- commands table (history log)
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK(source IN ('user', 'auto', 'system')),
    input TEXT NOT NULL,                          -- What was sent to terminal
    context TEXT,                                 -- Why (prompt text, auto-rule match)
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

-- auto_rules table
CREATE TABLE IF NOT EXISTS auto_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL,                        -- Regex or exact match string
    response TEXT NOT NULL,                       -- What to send
    match_type TEXT NOT NULL DEFAULT 'contains'
        CHECK(match_type IN ('regex', 'contains', 'exact')),
    enabled INTEGER NOT NULL DEFAULT 1,           -- 1 = active, 0 = paused
    hit_count INTEGER NOT NULL DEFAULT 0,         -- Times triggered
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- events table (notification log)
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL
        CHECK(event_type IN ('input_required', 'token_warning', 'error', 'completed', 'rate_limit', 'auto_response', 'system')),
    message TEXT NOT NULL,                        -- What was sent to Telegram
    acknowledged INTEGER NOT NULL DEFAULT 0,      -- User interacted with it
    telegram_message_id INTEGER,                  -- For editing/deleting messages
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_commands_session ON commands(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type, acknowledged);
```

---

## 24. Build Phases

### Phase 0: Prerequisites (Before Coding)

**Time**: 30 minutes

| Step | Action | Verify |
|------|--------|--------|
| 1 | Install tmux | `tmux -V` shows 3.0+ |
| 2 | Create Telegram bot via @BotFather | Have bot token |
| 3 | Get Telegram user ID via @userinfobot | Have numeric ID |
| 4 | Get Anthropic API key | Have `sk-ant-*` key |
| 5 | Create project directory + venv | `which python` shows venv path |
| 6 | Create `.env` from template | All 3 secrets populated |
| 7 | Install Python dependencies | `pip install -r requirements.txt` succeeds |

---

### Phase 1: Foundation (Days 1–2)

**Goal**: Daemon runs, tmux works, bot sends/receives messages.

| Task | Deliverable | Acceptance |
|------|------------|------------|
| Project scaffolding | All directories + `__init__.py` files | Structure matches Section 22 |
| Config system | `config.py` loads `.env` + `config.yaml` | All config values accessible |
| SQLite database + schema | `database.py` with migrations | All tables exist, WAL mode on |
| tmux session manager | `manager.py` — create, kill, list | Can create/kill sessions from Python |
| Telegram bot skeleton | Bot responds to `/start` and `/help` | Bot online in Telegram |
| Auth middleware | Rejects non-authorized users | Other users get "unauthorized" |
| `/status` command | Shows active sessions | Formatted dashboard appears |
| Daemon entry point | `__main__.py` runs everything | `python -m conductor` starts daemon |
| Logging setup | `logger.py` writes to file + console | Logs appear in `~/.conductor/conductor.log` |

**Phase 1 Handoff Pack (verify before starting Phase 2):**
```
✅ python -m conductor starts without errors
✅ /start in Telegram → bot responds with welcome
✅ /new cc ~/projects/test → tmux session "conductor-1" created
✅ /status → shows session #1 with correct info
✅ /kill 1 → confirmation prompt → confirm → session killed
✅ Random Telegram user messages bot → "unauthorized" response
✅ ~/.conductor/conductor.log has entries
✅ Ctrl+C stops daemon cleanly
```

---

### Phase 2: Monitoring + Notifications (Days 3–4)

**Goal**: Bot watches sessions and alerts you in real-time.

| Task | Deliverable | Acceptance |
|------|------------|------------|
| Output buffer | `output_buffer.py` with ANSI strip + dedup | No duplicate lines captured |
| Output monitor | `monitor.py` with async polling loop | Captures output <1s after it appears |
| Pattern detector | `detector.py` with all regex patterns | Passes all unit tests from Section 18 |
| Notification sender + queue | `notifier.py` with offline resilience | Messages arrive within 3 seconds |
| Inline keyboards | `keyboards.py` — button builders | Buttons render correctly in Telegram |
| Input relay | Send typed responses to sessions | "yes" goes to correct session |
| Callback handlers | `callbacks.py` for button taps | Tapping "Yes" sends "y" to correct session |
| Sensitive data redactor | `redactor.py` | Passes all redaction tests |
| Notification batching | Combine events within 5s window | Multiple events → 1 message |

**Phase 2 Handoff Pack:**
```
✅ Start Claude Code session via bot
✅ Claude Code asks "y/n" → Telegram notification with buttons within 3s
✅ Tap "Yes" → input sent, session continues
✅ Session crashes → 🔴 alert within 3 seconds
✅ API key appears in output → "[REDACTED]" in Telegram
✅ /status → dashboard with live data
✅ /output 1 → last 20 lines of output
✅ /log 1 → .txt file attachment sent
✅ Kill internet → messages queue → restore → messages flush
✅ pytest tests/test_detector.py → all pass
✅ pytest tests/test_redactor.py → all pass
```

---

### Phase 3: AI Brain + Auto-Responder (Days 5–6)

**Goal**: Bot is smart — summarizes, suggests, auto-answers simple prompts.

| Task | Deliverable | Acceptance |
|------|------------|------------|
| AI brain — summarizer | `brain.py` with Haiku calls | 100 lines → 2-4 sentence summary |
| AI brain — suggestion engine | Suggest next actions after completion | Relevant suggestions with buttons |
| AI brain — NLP parser | Parse natural language → commands | 10+ phrases correctly routed |
| AI fallback chain | Raw output when Haiku is down | Fallback works within 10s timeout |
| Auto-responder engine | `responder.py` with pattern matching | y/n auto-answered; destructive blocked |
| Auto-responder safety | Destructive keyword blocking | "Delete all?" → NOT auto-answered |
| Auto-response CRUD | `/auto list`, `/auto add`, `/auto remove` | Rules persist in SQLite |
| Undo button | 30s undo on auto-responses | Tap undo → retract response |
| Token estimator | `estimator.py` tracks message exchanges | `/tokens` shows usage per session |

**Phase 3 Handoff Pack:**
```
✅ "what's CountWize doing?" → AI summary response
✅ /output CountWize → AI summary of last activity
✅ Task completes → suggested next actions with buttons
✅ Simple "(Y/n)" prompt → auto-answered "y", logged
✅ "Delete database? (y/n)" → NOT auto-answered, forwarded to you
✅ /auto list → shows all rules with hit counts
✅ /auto add "pattern" "response" → rule created
✅ Undo button appears for 30s after auto-response
✅ /tokens → shows estimated usage with percentages
✅ Disconnect Haiku → output falls back to raw text (no crash)
✅ "kill the broken one" → correctly identifies errored session
✅ pytest tests/ → all tests pass
```

---

### Phase 4: Polish + Rate Limits + Recovery (Day 7)

**Goal**: Production-ready, handles edge cases, recovers from failures.

| Task | Deliverable | Acceptance |
|------|------------|------------|
| Rate limit detection | Detect Claude Code rate limit messages | Pattern matches rate limit output |
| Auto-pause on limit | Pause + notify + 3 options | Session paused, buttons shown |
| Auto-resume timer | `/resume in 15m` with asyncio timer | Auto-resumes and notifies |
| Session recovery | Re-attach after daemon restart | Restart daemon → sessions recovered |
| Quiet hours | `/quiet 23:00-07:00` with timezone support | Non-critical notifications suppressed |
| Global error handler | `errors.py` with escalation | Repeated errors → user alert |
| Mac sleep handling | Recalculate timers on wake | No stale timers after sleep |
| `/shell` one-off commands | Run command, return output, auto-close | `/shell ls` → output in chat |
| `/run` command in session | Run shell command in existing session | `/run CountWize git status` works |
| `/help` polished | Formatted help with all commands | Clean, readable help message |
| `/rename` command | Change session alias | `/rename 1 FraudApp` works |
| Install/uninstall scripts | `install.sh`, `uninstall.sh` | One-liner setup works end-to-end |
| CLAUDE.md project file | Instructions for Claude Code | Claude Code understands the project |

**Phase 4 Handoff Pack:**
```
✅ Rate limit message in terminal → auto-pause + notification with 3 options
✅ Tap "Auto-resume in 15m" → session resumes after 15 minutes
✅ Token at 80% → ⚠️ warning; at 95% → auto-pause
✅ Kill daemon → restart → "Recovered 3 sessions" message
✅ 5 events in 2s → 1 combined notification
✅ /quiet 23:00-07:00 → completions silenced, prompts still alert
✅ /log CountWize → .txt file in Telegram
✅ /shell df -h → disk usage in chat
✅ /run CountWize git log --oneline -5 → git log in chat
✅ Mac sleep → wake → daemon recalculates, notifies "I was asleep for 2h"
✅ Run 1 hour with 3+ active sessions → no crashes
✅ ./scripts/install.sh on fresh Mac → fully working
✅ pytest tests/ --cov → all pass, >80% coverage
```

---

## 25. Verification Checklist

### "Works in 2 Minutes" Test

After full installation:

```
1.  ✅ Run install script              → No errors
2.  ✅ Open Telegram, find bot          → Bot shows "online"
3.  ✅ Send /start                      → Welcome message
4.  ✅ Send /new cc ~/any-project       → "Session #1 created"
5.  ✅ Wait for Claude Code prompt      → Telegram notification
6.  ✅ Tap a button or type response    → Input delivered
7.  ✅ Send /status                     → Dashboard shows session
8.  ✅ Send "what's going on?"          → AI-powered status
9.  ✅ Send /kill 1 + confirm           → Session terminated
10. ✅ Unauthorized user messages bot   → Rejected
```

### Performance Targets

| Metric | Target |
|--------|--------|
| Notification latency | < 3 seconds from event to Telegram |
| Command response time | < 1 second for slash commands |
| AI summary time | < 5 seconds (Haiku API call) |
| Memory usage (daemon) | < 100 MB |
| CPU idle usage | < 2% |
| CPU active (5 sessions) | < 5% |
| SQLite size after 1 month | < 50 MB |

### Edge Cases Tested

| Scenario | Expected Behavior |
|----------|-------------------|
| Mac goes to sleep | Daemon pauses; resumes on wake; recalculates timers; sends notification |
| Internet drops | Commands queued; notifications sent when connection restored |
| tmux session killed externally | Daemon detects, marks as "exited", notifies user |
| 5 sessions all prompt at once | 5 separate notifications (or 1 batched if within 5s) |
| Very long output (10,000+ lines) | AI summarizes; full log as .txt file only |
| Bot token compromised | Only your Telegram ID can interact; attacker sees "unauthorized" |
| Daemon crashes | launchd auto-restarts within 5 seconds; session recovery kicks in |
| Haiku API is down | Fallback to raw output (last 20 lines); no crash |
| SQLite locked | Retry 3 times with 100ms delay; WAL mode prevents most locks |
| Empty session (no output yet) | /status shows "No activity yet"; /output shows "Nothing to summarize" |
| User sends gibberish | Bot: "I didn't understand that. Try /help for commands." |

---

## Appendix A: Visual Design Language

### Emoji System

| Element | Emoji | Usage |
|---------|-------|-------|
| Session label colors | 🔵🟣🟠🟢🔴🟤 | Assigned in order per session |
| Status: running | 🟢 | Active, processing |
| Status: waiting | ❓ | Needs user input |
| Status: paused | ⏸️ | Manually or auto-paused |
| Status: error | 🔴 | Crashed or failed |
| Status: complete | ✅ | Task finished |
| Status: rate limited | ⏳ | Paused due to rate limit |
| Token warning | ⚠️ | Approaching limit |
| Suggestion | 💡 | AI-generated next step |
| File attachment | 📎 | Log file sent |
| Dashboard | 📊 | Status overview |
| Security | 🔒 | Auth-related messages |
| System | ⚙️ | Daemon/config messages |

### Message Formatting Rules

1. Session label always first: `🔵 CountWize — message`
2. Short messages in plain text (no markdown abuse)
3. Status dashboards use monospace blocks (``` ``` in Telegram)
4. Buttons are concise: 1–3 words max
5. No walls of text — summarize first, file-attach the rest
6. Use `parse_mode="HTML"` in aiogram for bold/italic: `<b>bold</b>`, `<i>italic</i>`, `<code>monospace</code>`

---

## Appendix B: Project Naming

| Item | Name |
|------|------|
| Project | **Conductor** |
| Bot username | `@conductor_term_bot` (or similar available name) |
| Daemon process | `conductor` |
| Config directory | `~/.conductor/` |
| Database file | `~/.conductor/conductor.db` |
| Log file | `~/.conductor/conductor.log` |
| launchd label | `com.codexs.conductor` |
| tmux session prefix | `conductor-{number}` |
| Python package | `conductor` |
| pip install name | `conductor-bot` |

---

## Appendix C: Quick Reference Card

```
┌──────────────────── CONDUCTOR QUICK REF ────────────────────┐
│                                                              │
│  SESSIONS          MONITORING          CONTROL               │
│  /new cc <dir>     /status             /pause <#>            │
│  /new sh <dir>     /output <#>         /resume <#>           │
│  /kill <#>         /log <#>            /restart <#>          │
│  /rename <#> name  /tokens             /input <#> <text>     │
│                    /digest             /run <#> <cmd>         │
│                                        /shell <cmd>          │
│                                                              │
│  AUTO-RESPONDER    SETTINGS            NATURAL LANGUAGE       │
│  /auto list        /quiet HH:MM-HH:MM "what's going on?"    │
│  /auto add P R     /settings           "yes" / "no"          │
│  /auto remove #    /help               "kill the broken one" │
│  /auto pause                           "show me the log"     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

*Built for Dave @ Codexs.ai — because your terminals shouldn't stop just because you did.* 🎛️
