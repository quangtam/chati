# Story 1.4: Per-Thread Provider Switching

Status: done

## Story

As a **user**,
I want to switch the CLI provider for the current thread,
so that I can use different AI CLIs for different projects.

## Acceptance Criteria

1. `/provider <name>` updates thread's provider in SQLite when no active process is running
2. Command rejected (with clear message) if an active CLI process is running — user must `/cancel` first
3. Invalid provider names return error listing available providers from registry
4. Provider switch persists across bot restarts (SQLite)
5. `/model` selections persist to SQLite `thread_config.model` for the current thread
6. Unit tests pass with ≥80% branch coverage

## Tasks / Subtasks

- [x] Task 1: Implement `cmd_provider` handler in chati.py (AC: #1, #2, #3, #4)
  - [x] Parse `/provider <name>` argument
  - [x] Validate provider name against `get_available_providers()`
  - [x] Check if CliRunner has active session for current thread — reject if yes
  - [x] Call `db.upsert_thread_config()` to persist
  - [x] Send confirmation with provider name
- [x] Task 2: Update `handle_model_callback` to persist to SQLite (AC: #5)
  - [x] After model selection confirmed, save to `thread_config.model`
- [x] Task 3: Register `/provider` handler in main()
- [x] Task 4: Write tests (AC: #6)
  - [x] Valid switch persists to SQLite
  - [x] Active session blocks switch
  - [x] Invalid provider shows available list
  - [x] Missing argument shows usage hint
  - [x] Model selection persists to SQLite

## Dev Notes

### Architecture Compliance

- Provider validation via `cli_providers.get_available_providers()` — returns dict[str, Type[CliProvider]]
- Active session check: `runner._sessions.get(thread_id)` with `.alive` property
- No need to instantiate new provider on switch — just persist; actual use happens on next message (next story: config resolution)

### Implementation Reference

```python
# chati.py
from cli_providers import get_available_providers

@authorized
async def cmd_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /provider <name> — switch CLI provider for current thread."""
    text = update.message.text or ""
    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        available = list(get_available_providers().keys())
        await update.message.reply_text(
            f"⚠️ Usage: <code>/provider &lt;name&gt;</code>\n\n"
            f"Available: <code>{', '.join(sorted(available))}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    name = parts[1].strip().lower()
    available = get_available_providers()
    if name not in available:
        await update.message.reply_text(
            f"⚠️ Unknown provider: <code>{_escape_html(name)}</code>\n\n"
            f"Available: <code>{', '.join(sorted(available.keys()))}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    thread_id = _get_thread_id(update) or DEFAULT_THREAD_ID

    # Check for active session
    session = runner._sessions.get(thread_id)
    if session and session.alive:
        await update.message.reply_text(
            "⚠️ Active process running. Use /cancel first, then try again.",
        )
        return

    await db.upsert_thread_config(thread_id, cli_provider=name, path=DB_PATH)

    thread_label = f"thread {thread_id}" if thread_id != DEFAULT_THREAD_ID else "main chat"
    provider_class = available[name]
    await update.message.reply_text(
        f"✅ {thread_label} provider switched to <b>{provider_class.name}</b> (<code>{name}</code>)",
        parse_mode=ParseMode.HTML,
    )
```

### Files to Modify

- `chati.py` (UPDATE) — add `cmd_provider`, update `handle_model_callback`, register handler
- `tests/test_cmd_provider.py` (NEW) — handler tests

### Anti-Patterns

- ❌ Don't instantiate new CliProvider — persistence only; creation happens in next story (config resolution)
- ❌ Don't allow switch while process alive — prevents orphaned processes

### References

- [Source: architecture.md#Command Structure]
- [Source: epics.md#Story 1.4]

## Dev Agent Record

### Agent Model Used

Claude (Auto) via Kiro

### Completion Notes List

- 9 new tests — all passing
- Full test suite: 64 tests in 1.72s, zero regressions
- `cmd_provider` validates via `get_available_providers()` — auto-discovers all 4 providers
- Active session check uses `runner._sessions[thread_id].alive` — same pattern as v1 cancel
- Dead sessions don't block switch (defensive — sessions can die unnoticed)
- Case-insensitive provider name matching (`/provider CLAUDE` works)
- Model selection persists to SQLite + user_data (backward compat)
- Graceful fallback if thread has no row yet (ValueError caught)

### File List

- `chati.py` (UPDATE) — added `cmd_provider`, updated `handle_model_callback`, registered handler, imported `get_available_providers`
- `tests/test_cmd_provider.py` (NEW) — 9 tests (7 provider + 2 model callback)
