# Story 4.2: Session List Command (/sessions)

Status: ready-for-dev

## Story

As a **user**,
I want to see all my active sessions across threads with their status,
So that I can manage multiple projects and know which sessions need attention.

## Acceptance Criteria (BDD)

**Given** user has 3 active threads with sessions
**When** user sends `/sessions`
**Then** a formatted list is displayed showing each thread with:
- Thread name/ID
- Bound project directory
- Provider + model
- Status indicator: 🟢 active / ⏳ waiting for input / 💤 idle / ❌ dead

**Given** user has more than 10 active threads
**When** user sends `/sessions`
**Then** the list is paginated (first 10 shown with "..." indicator)

**Given** user has no active sessions
**When** user sends `/sessions`
**Then** message shows: "No active sessions. Send a message in any thread to start one."

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

## Tasks / Subtasks

- [ ] Task 1: Implement `cmd_sessions()` handler in `chati.py`
- [ ] Task 2: Register `/sessions` command in `main()`
- [ ] Task 3: Write tests in `tests/test_cmd_sessions.py`

## Dev Notes

### Epic 4 Context

This is story 4.2 of 3 in Epic 4 "CLI Information & Session Visibility":
- **4.1 (done before this)**: `/info` — session details for current thread
- **4.2 (this)**: `/sessions` — list ALL active sessions across threads
- **4.3**: Enhanced `/status` + `/help` — CLI health + full command reference

### Architecture Requirements

**FRs covered:** FR7 (view all active sessions with per-thread status indicators)

**Module ownership per architecture:**
- `chati.py` — owns the `/sessions` handler (command routing, Telegram messaging)
- `session_manager.py` — provides `list_all()` → `dict[int | None, PtySession]` and `get_status_emoji()`
- `db.py` — provides `get_thread_config()` for project_dir per thread

### Implementation Guide

#### Task 1: Implement `cmd_sessions()` in chati.py

The handler must:

1. Get all sessions via `runner._session_mgr.list_all()`
2. For each session, fetch thread config from SQLite for project_dir
3. Format a list with status emoji, thread ID, project, provider, model
4. Paginate if >10 sessions (show first 10 + "... and N more")

**With active sessions — format:**

```
📋 Active Sessions (3/5 slots)

🟢 Thread 12345
   📁 my-project | 📡 Kiro | 🤖 sonnet
   ⏱️ 15m | 💬 8 messages

⏳ Thread 67890
   📁 other-app | 📡 Claude | 🤖 opus
   ⏱️ 42m | ⚠️ Waiting for input

💤 Thread 11111
   📁 api-server | 📡 Kiro | 🤖 auto
   ⏱️ 28m | Idle

━━━━━━━━━━━━━━━━━━━━
Slots: 3/5 used | /cancel <thread> to free
```

**With no sessions — format:**

```
📋 No active sessions.

Send a message in any thread to start one.
Slots available: 5/5
```

**Key implementation details:**

```python
@authorized
async def cmd_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sessions — list all active sessions across threads."""
    await update.message.reply_chat_action(ChatAction.TYPING)

    sessions = runner._session_mgr.list_all()
    if not sessions:
        max_s = runner._session_mgr.max_sessions
        await update.message.reply_text(
            f"📋 No active sessions.\n\n"
            f"Send a message in any thread to start one.\n"
            f"Slots available: {max_s}/{max_s}"
        )
        return

    # Build session list
    active_count = runner._session_mgr.active_count()
    max_sessions = runner._session_mgr.max_sessions
    lines = [f"📋 <b>Active Sessions</b> ({active_count}/{max_sessions} slots)\n"]

    items = list(sessions.items())
    display_items = items[:10]

    for tid, session in display_items:
        emoji = SessionManager.get_status_emoji(session.state)
        # Duration
        duration = _format_duration(time.monotonic() - session.created_at)
        # Thread config from DB (best-effort)
        thread_config = await db.get_thread_config(tid or DEFAULT_THREAD_ID, path=DB_PATH)
        project = Path(thread_config.project_dir).name if thread_config else "—"
        provider = thread_config.cli_provider or config.cli_provider if thread_config else config.cli_provider
        model = thread_config.model or "default" if thread_config else "default"
        msg_count = _thread_sessions.get(tid, 0)

        lines.append(f"{emoji} <b>Thread {tid or 'main'}</b>")
        lines.append(f"   📁 {project} | 📡 {provider} | 🤖 {model}")
        lines.append(f"   ⏱️ {duration} | 💬 {msg_count} messages")
        lines.append("")

    if len(items) > 10:
        lines.append(f"... and {len(items) - 10} more")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"Slots: {active_count}/{max_sessions} | /cancel to free")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
```

**`_format_duration()` helper** (shared with `/info` from story 4.1):

```python
def _format_duration(seconds: float) -> str:
    """Format elapsed seconds as human-readable duration."""
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {secs}s"
```

This helper should already exist from story 4.1. If not, create it here.

#### Task 2: Register command in main()

Add after the `/info` handler (which was added in 4.1):

```python
app.add_handler(CommandHandler("sessions", cmd_sessions))
```

#### Task 3: Tests

Create `tests/test_cmd_sessions.py` with:
- Test `/sessions` with 0 sessions → "No active sessions" message
- Test `/sessions` with 1-3 sessions → formatted list with correct emojis
- Test `/sessions` with sessions in different states (IDLE, STREAMING, WAITING_FOR_USER, DEAD)
- Test pagination: 11+ sessions → first 10 shown + "... and N more"
- Test thread with no DB config → graceful fallback to defaults
- Test `_format_duration()` edge cases (if not already tested in 4.1)

### Files to Create/Modify

| File   | Action | Description |
|--------|--------|-------------|
| `chati.py` | UPDATE | Add `cmd_sessions()` handler + register in `main()` |
| `tests/test_cmd_sessions.py` | NEW | Unit tests for /sessions command |

### Critical Guardrails

1. **DO NOT shell out to CLI** — `/sessions` reads from memory (SessionManager) + SQLite only
2. **DO NOT modify session state** — read-only command, never transitions state
3. **DO NOT break existing commands** — additive only
4. **Use `@authorized` decorator** — same auth pattern as all commands
5. **Use Telegram HTML format** — `parse_mode=ParseMode.HTML`
6. **Handle None thread_id** — display as "main" in the list
7. **Graceful DB failures** — if `get_thread_config()` fails for a thread, show "—" for project
8. **Import `time`** — needed for duration calculation (already imported if 4.1 is done)
9. **Import `Path` from pathlib** — already imported at top of chati.py
10. **Reuse `_format_duration()`** — must exist from story 4.1, do NOT duplicate
11. **Import `SessionManager`** — needed for `get_status_emoji()` static method

### Dependencies on Story 4.1

This story assumes 4.1 is already implemented. Specifically:
- `_format_duration()` helper function exists in `chati.py`
- `/info` command is registered (for ordering reference)
- `parse_usage_output()` exists on `CliProvider` base (not used here, but confirms pattern)

If 4.1 is NOT done yet, implement `_format_duration()` in this story.

### Existing Code to Leverage

**SessionManager.list_all()** (session_manager.py line 270):
```python
def list_all(self) -> dict[int | None, PtySession]:
    """Return a shallow copy of the session pool."""
    return dict(self._sessions)
```

**SessionManager.get_status_emoji()** (session_manager.py line 340):
```python
@staticmethod
def get_status_emoji(state: PtyState) -> str:
    return {
        PtyState.IDLE: "💤",
        PtyState.STREAMING: "🟢",
        PtyState.DETECTING_PROMPT: "🟢",
        PtyState.WAITING_FOR_USER: "⏳",
        PtyState.PIPING_REPLY: "🟢",
        PtyState.DEAD: "❌",
    }.get(state, "❓")
```

**SessionManager.active_count()** (session_manager.py line 274):
```python
def active_count(self) -> int:
    return sum(1 for s in self._sessions.values() if s.state != PtyState.DEAD)
```

### What Must NOT Break

- All existing commands (especially `/info` from 4.1)
- Decision forwarding flow (pending_decision routing)
- Background cleanup task
- Session state machine transitions
- Message routing (free-form text → CLI)
- `/cancel` command (still works per-thread)

### Testing Patterns

From existing test files:
- Use `pytest` + `pytest-asyncio`
- Mock SessionManager with pre-seeded sessions in different states
- Mock `db.get_thread_config()` to return test ThreadConfig objects
- Use `unittest.mock.AsyncMock` for async DB calls
- Test file: `tests/test_cmd_sessions.py`

## Project Context Reference

- **Project:** Chati v2.0 — Telegram bot bridging AI coding CLIs
- **Stack:** Python 3.12+, python-telegram-bot 21.10, aiosqlite, pytest
- **Architecture:** Flat module structure, async-first, no new dependencies
- **Session pool:** Max 5 concurrent PTY sessions (configurable via MAX_SESSIONS)
- **State:** PtyState enum — IDLE, STREAMING, DETECTING_PROMPT, WAITING_FOR_USER, PIPING_REPLY, DEAD

## Completion Notes

Ultimate context engine analysis completed — comprehensive developer guide created.
