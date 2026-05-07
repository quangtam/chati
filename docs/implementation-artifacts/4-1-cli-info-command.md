# Story 4.1: CLI Info Command (/info)

Status: review

## Story

As a **user**,
I want to see full information about my current CLI session,
So that I know what provider, model, and resources I'm using.

## Acceptance Criteria (BDD)

**Given** user sends `/info` in a thread with an active session
**When** the command is processed
**Then** a message is displayed showing:
- Provider name (e.g., "Kiro")
- Logged-in user (if detectable by provider)
- Active model
- Session duration (time since session created)
- Messages sent this session
- Token/credit usage (best-effort, if provider supports it)

**Given** user sends `/info` in a thread with no active session
**When** the command is processed
**Then** thread config is shown (bound project, provider, model) with note "No active session"

**Given** a provider does not implement `parse_usage_output()`
**When** `/info` is requested
**Then** token/credit section shows "Usage data not available for this provider"

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

## Tasks / Subtasks

- [x] Task 1: Add `parse_usage_output()` optional method to `CliProvider` base class
- [x] Task 2: Implement `cmd_info()` handler in `chati.py`
- [x] Task 3: Register `/info` command in `main()`
- [x] Task 4: Write tests in `tests/test_cmd_info.py`

## Dev Notes

### Epic 4 Context

Epic 4 is "CLI Information & Session Visibility" — 3 stories total:
- **4.1 (this)**: `/info` — session details for current thread
- **4.2**: `/sessions` — list all active sessions across threads
- **4.3**: Enhanced `/status` + `/help` — CLI health + full command reference

This is the first story in Epic 4. Stories 4.2 and 4.3 will build on patterns established here.

### Architecture Requirements

**FRs covered:** FR24 (view session info), FR25 (best-effort token/credit usage)

**Module ownership per architecture:**
- `chati.py` — owns the `/info` handler (command routing, Telegram messaging)
- `cli_providers/base.py` — owns `parse_usage_output()` (optional method on ABC)
- `session_manager.py` — provides session state/duration via `PtySession` fields
- `db.py` — provides thread config via `get_thread_config()`

**Key design rule:** `/info` is a READ-ONLY command. It queries state but never mutates it.

### Implementation Guide

#### Task 1: Add `parse_usage_output()` to CliProvider base

In `cli_providers/base.py`, add this optional method to the `CliProvider` ABC:

```python
def parse_usage_output(self, stdout: str) -> str | None:
    """Parse CLI output for usage/token information.

    Returns a human-readable usage string, or None if not supported.
    Override in subclass to extract provider-specific usage data.
    """
    return None
```

This is a **no-op default** — providers that don't support usage reporting just return None. No existing providers need changes for this story (usage parsing is best-effort per FR25).

#### Task 2: Implement `cmd_info()` in chati.py

The handler must:

1. Get `thread_id` via `_get_thread_id(update)`
2. Resolve thread config from SQLite: `await db.get_thread_config(thread_id or DEFAULT_THREAD_ID)`
3. Check if an active session exists: `runner._session_mgr.get(thread_id)`
4. Format response based on whether session exists or not

**With active session — format:**
```
ℹ️ Session Info

📡 Provider: {provider_name}
🤖 Model: {model or "default"}
📁 Project: {project_dir_basename}
⏱️ Duration: {formatted_duration}
💬 Messages: {message_count}
📊 Status: {status_emoji} {state_name}

💳 Usage: {usage_text or "Not available for this provider"}
```

**Without active session — format:**
```
ℹ️ Thread Info (no active session)

📁 Project: {project_dir or "Not set"}
📡 Provider: {provider or "default"}
🤖 Model: {model or "default"}

Send a message to start a session.
```

**Duration calculation:**
```python
import time
elapsed = time.monotonic() - session.created_at
hours, remainder = divmod(int(elapsed), 3600)
minutes, seconds = divmod(remainder, 60)
# Format: "1h 23m" or "5m 12s" or "45s"
```

**Message count:** Use `_thread_sessions.get(thread_id, 0)` — the existing in-memory counter.

**Usage data:** For now, `parse_usage_output()` returns None for all providers. Show "Usage data not available for this provider". Future stories can implement provider-specific parsing.

**Logged-in user:** The existing `check_status()` method runs `kiro-cli whoami` (or `--version` for others). For `/info`, we do NOT want to shell out on every call (too slow). Instead:
- Show provider name only (e.g., "Kiro CLI")
- Logged-in user detection is best-effort — skip for now, add in 4.3 when `/status` is enhanced

#### Task 3: Register command in main()

Add after the existing `/provider` handler:
```python
app.add_handler(CommandHandler("info", cmd_info))
```

#### Task 4: Tests

Create `tests/test_cmd_info.py` with:
- Test `/info` with active session → shows provider, model, duration, messages, status
- Test `/info` with no session → shows thread config with "no active session" note
- Test `/info` with no thread config in DB → shows defaults from .env
- Test duration formatting (edge cases: <1min, >1hr, >24hr)
- Test message count display

Use existing test patterns from `tests/test_cmd_project.py` and `tests/test_cmd_provider.py`.

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `cli_providers/base.py` | UPDATE | Add `parse_usage_output()` method |
| `chati.py` | UPDATE | Add `cmd_info()` handler + register in `main()` |
| `tests/test_cmd_info.py` | NEW | Unit tests for /info command |

### Critical Guardrails

1. **DO NOT shell out to CLI for /info** — it must be instant (read from memory + SQLite only)
2. **DO NOT modify session state** — /info is read-only, never transitions state
3. **DO NOT break existing commands** — /info is additive, no refactoring of existing handlers
4. **Use `@authorized` decorator** — same auth pattern as all other commands
5. **Use Telegram HTML format** — `parse_mode=ParseMode.HTML` (not Markdown)
6. **Error messages in plain text** — no HTML on error path (existing pattern)
7. **Handle None thread_id** — use `DEFAULT_THREAD_ID` (0) when not in a thread
8. **Duration uses `time.monotonic()`** — matches `PtySession.created_at` field type
9. **Keep function under 50 lines** — extract `_format_duration()` helper if needed

### Existing Code Patterns to Follow

From `cmd_status()` (line 303):
```python
@authorized
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_chat_action(ChatAction.TYPING)
    # ... gather info ...
    await update.message.reply_text(status)
```

From `cmd_project()` — SQLite access pattern:
```python
thread_id = _get_thread_id(update) or DEFAULT_THREAD_ID
thread_config = await db.get_thread_config(thread_id, path=DB_PATH)
```

From `handle_model_callback()` — accessing session manager:
```python
session = runner._session_mgr.get(thread_id)
```

### What Must NOT Break

- All existing commands (`/status`, `/help`, `/model`, `/project`, `/projects`, `/provider`, `/cancel`, `/new`, `/resume`, `/skills`, `/start`)
- Decision forwarding flow (pending_decision routing in `handle_message`)
- Background cleanup task
- Session state machine transitions
- Message routing (free-form text → CLI)

### Previous Epic Intelligence

Epic 3 (decision forwarding) established:
- `runner._session_mgr` is the canonical way to access SessionManager from chati.py
- `_get_thread_id(update)` returns `int | None` — always handle None case
- `context.bot_data[f"thread:{tid}:pending_decision"]` pattern for per-thread runtime state
- `_thread_sessions` dict tracks message count per thread (in-memory, not persisted)
- All handlers use `@authorized` decorator
- Telegram HTML formatting with emoji prefixes for status indicators

### Testing Patterns

From existing test files:
- Use `pytest` + `pytest-asyncio` (async tests with `@pytest.mark.asyncio`)
- Mock Telegram Update objects via fixtures in `conftest.py`
- Use in-memory SQLite for DB tests
- Test file naming: `tests/test_cmd_info.py`
- Each test function: `async def test_info_with_active_session(...):`

## Project Context Reference

- **Project:** Chati v2.0 — Telegram bot bridging AI coding CLIs
- **Stack:** Python 3.12+, python-telegram-bot 21.10, aiosqlite, pytest
- **Architecture:** Flat module structure, async-first, no new dependencies
- **Provider:** Pluggable CLI drivers (kiro, claude, gemini, codex)
- **State:** PtyState enum in session_manager.py (6 states)
- **DB:** SQLite WAL mode, thread_config table, async context manager

## Completion Notes

Ultimate context engine analysis completed — comprehensive developer guide created.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 via Kiro

### Implementation Plan

- **Task 1** — Added `parse_usage_output()` as an optional no-op method on `CliProvider` ABC. Default returns `None` so existing providers (Kiro, Claude, Gemini, Codex) inherit without changes. Future stories can override per-provider.
- **Task 2** — Implemented `cmd_info()` in `chati.py`. Two branches: active session (shows provider/model/project/duration/messages/status/usage) vs. no-session (shows thread config + hint). Added `_format_duration()` helper (reusable by Story 4.2 for `/sessions`).
- **Task 3** — Registered `/info` as a `CommandHandler` in `main()`, after `/provider`. Uses `@authorized` decorator like all other handlers.
- **Task 4** — 18 tests in `tests/test_cmd_info.py` covering: duration formatting edge cases (7 tests), active/dead/missing session branches, HTML parse mode, state mutation prevention, emoji selection, usage fallback, None thread_id handling, and base `parse_usage_output()` default behavior. Local `telegram_update_factory` wrapper patches `reply_chat_action` as AsyncMock (base conftest only wires `reply_text`).

### Key Design Decisions

- **Read-only guarantee**: `/info` never shells out (instant response) and never transitions session state. Verified by `test_info_does_not_mutate_session_state`.
- **Model resolution precedence**: thread_config.model → context.user_data["model"] → "default". Matches existing patterns from `cmd_model`.
- **DEAD session treated as no-session**: Shows "no active session" branch. Prevents confusing output when session died but wasn't cleaned up yet.
- **Logged-in user**: Deferred to Story 4.3's enhanced `/status` (requires `check_status()` shell-out). `/info` only shows provider name, per guardrail #1.

### Completion Notes

✅ All 4 Acceptance Criteria satisfied.
✅ All 4 Tasks complete with tests.
✅ 25 new tests pass; full suite 167/167 pass — no regressions.
✅ Diagnostics clean on all modified files.
✅ `/info` is read-only, instant (no CLI shell-out), and HTML-formatted.
✅ Output prioritizes user-centric info: Project (bold) → Status → Pending alert → Provider/Model → Session usage → Technical debug block (below separator). Mobile-first glance order.

### File List

**Modified:**

- `chati.py` — added `time` import, extended `session_manager` import (`PtyState`, `SessionManager`), added `_format_duration()` helper, added `cmd_info()` handler, registered `/info` CommandHandler in `main()`
- `cli_providers/base.py` — added optional `parse_usage_output(stdout: str) -> str | None` method on `CliProvider` ABC (default returns None)

**Added:**

- `tests/test_cmd_info.py` — 18 unit tests covering `cmd_info`, `_format_duration`, and `parse_usage_output` base default

### Change Log

| Date       | Change                                                       |
|------------|--------------------------------------------------------------|
| 2026-05-07 | Story 4.1 implemented: `/info` command + `parse_usage_output` ABC method + 18 tests. All ACs satisfied. |
| 2026-05-07 | Enhanced `/info` output with richer debug context: thread ID, PID, ready flag, last activity timestamp, session pool usage, full project path, per-thread timeout, CLI binary path, pending-decision reply-timeout countdown. +4 tests (22 total). |
| 2026-05-07 | Restructured layout by information priority: Project (bold, top), Status, pending-decision alert, Provider/Model, session usage, then technical details below a separator. Removed redundant "Session Info"/"Thread Info" headers. +3 tests for priority order (25 total). |
