# Story 1.2: Thread-to-Project Binding (/project command)

Status: done

## Story

As a **user**,
I want to bind the current thread to a specific project directory,
so that all CLI commands in this thread operate on that project.

## Acceptance Criteria

1. `/project <path>` binds the current thread to the specified directory
2. Path validation — non-existent path → error message, no binding created
3. Path with spaces supported — entire text after `/project ` treated as path
4. Binding persisted in SQLite (survives bot restart)
5. `init_db()` called on bot startup to ensure schema + default row exist
6. Handler integrates with existing `@authorized` + `_get_thread_id()` patterns
7. Tests cover all AC scenarios

## Tasks / Subtasks

- [x] Task 1: Add `cmd_project` handler to `chati.py` (AC: #1, #2, #3, #6)
  - [x] Parse path from message text (handle spaces)
  - [x] Validate path exists via `os.path.isdir()`
  - [x] Call `db.upsert_thread_config(thread_id, project_dir=path)`
  - [x] Reply with confirmation or error message
- [x] Task 2: Register handler in `main()` function (AC: #1)
  - [x] Add `CommandHandler("project", cmd_project)`
- [x] Task 3: Call `init_db()` on startup (AC: #4, #5)
  - [x] In `main()` before `app.run_polling()`
  - [x] Pass `config.project_dir` as default
- [x] Task 4: Write tests (AC: #7)
  - [x] Test valid path binding
  - [x] Test non-existent path error
  - [x] Test path with spaces
  - [x] Test persistence after restart (new DB connection)

## Dev Notes

### Architecture Compliance

- Handler in `chati.py` (not separate module) — per architecture "chati.py owns handlers" [Source: architecture.md#Architectural Boundaries]
- Uses existing `@authorized` decorator [Source: chati.py]
- Uses existing `_get_thread_id(update)` → maps None to `DEFAULT_THREAD_ID=0` [Source: db.py]
- Uses `db.upsert_thread_config()` for persistence [Source: db.py]

### Thread ID Mapping

Critical: `_get_thread_id()` returns `int | None` where `None` = main chat. SQLite schema requires `INTEGER PRIMARY KEY`, so map:
```python
thread_id = _get_thread_id(update) or DEFAULT_THREAD_ID  # None → 0
```

### Path Parsing Pattern

Telegram message: `/project /home/user/my project/`
- `update.message.text` = `"/project /home/user/my project/"`
- Strip command prefix: `text[len("/project "):]` or `text.split(maxsplit=1)[1]`

### Handler Reference

```python
@authorized
async def cmd_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bind current thread to a project directory."""
    text = update.message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text(
            "⚠️ Usage: <code>/project &lt;path&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    path = parts[1].strip()
    if not os.path.isdir(path):
        await update.message.reply_text(
            f"⚠️ Path not found: <code>{_escape_html(path)}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    thread_id = _get_thread_id(update) or DEFAULT_THREAD_ID
    await db.upsert_thread_config(thread_id, project_dir=path)
    await update.message.reply_text(
        f"✅ Thread bound to project:\n<code>{_escape_html(path)}</code>",
        parse_mode=ParseMode.HTML,
    )
```

### Test Strategy

- Use `telegram_update_factory` fixture for mock updates
- Use `tempfile.TemporaryDirectory()` for valid paths in tests
- Use fresh DB per test via `path=` parameter in db functions
- Mock the `_global` db state by passing explicit path

### Anti-Patterns

- ❌ Don't use `context.user_data` — that's per-user, not per-thread
- ❌ Don't forget thread_id mapping (None → 0)
- ❌ Don't validate path with `os.path.exists()` — use `isdir()` (file ≠ project dir)

### References

- [Source: architecture.md#Module Responsibility Boundaries]
- [Source: chati.py — existing handler patterns]
- [Source: db.py — upsert_thread_config signature]
- [Source: epics.md#Story 1.2]

## Dev Agent Record

### Agent Model Used

Claude (Auto) via Kiro

### Completion Notes List

- 6 tests passing in tests/test_cmd_project.py
- Handler integrates with existing `@authorized` + `_get_thread_id()` patterns
- `init_db()` wired into `main()` on startup
- Path validation via `os.path.isdir()` — file paths rejected
- Space-containing paths handled via `maxsplit=1`

### File List

- `chati.py` (UPDATE) — added `cmd_project` handler, registered command, added `init_db()` call
- `tests/test_cmd_project.py` (NEW) — 6 handler tests
