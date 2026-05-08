# Story 1.3: Project History & Quick Re-binding

Status: done

## Story

As a **user**,
I want to browse previously-used project directories and select one,
so that I don't have to type full paths on my phone.

## Acceptance Criteria

1. `/projects` command shows inline keyboard with all previously-used project directories
2. Tapping a project button binds current thread to that project (persisted in SQLite)
3. If no previous projects exist, message shows: "No previous projects found. Use `/project <path>` to bind a project."
4. Long paths display correctly (Telegram callback_data 64-byte limit handled via indexing)
5. Current thread's existing binding (if any) is marked in the list
6. Unit tests pass with ≥80% branch coverage

## Tasks / Subtasks

- [x] Task 1: Add `list_distinct_project_dirs()` to db.py (AC: #1)
  - [x] Returns `list[str]` of unique project directories from thread_config
  - [x] Ordered by most-recently-active first
- [x] Task 2: Implement `cmd_projects` handler in chati.py (AC: #1, #3, #5)
  - [x] Query distinct projects from db
  - [x] Build inline keyboard with project paths
  - [x] Handle empty case (no previous projects)
  - [x] Store paths list in `chat_data` for callback lookup
- [x] Task 3: Implement `handle_projects_callback` for selection (AC: #2, #4)
  - [x] Parse callback_data `project:<index>`
  - [x] Look up full path from stored list
  - [x] Call `db.upsert_thread_config()` to bind
  - [x] Edit message to show confirmation
- [x] Task 4: Register handlers in main() (AC: #1, #2)
  - [x] Add CommandHandler for `/projects`
  - [x] Add CallbackQueryHandler for pattern `^project:`
- [x] Task 5: Write tests (AC: #6)
  - [x] Test empty list behavior
  - [x] Test keyboard generation with 3 projects
  - [x] Test callback handler binds thread correctly
  - [x] Test invalid callback index handling

## Dev Notes

### Architecture Compliance

- Callback_data format: `project:<index>` (64-byte limit — use index, not full path) [Source: architecture.md#Format Patterns]
- Store path list in `chat_data` (per-chat ephemeral state, not in SQLite)
- Inline keyboard pattern already established in v1 for `/model` — reuse pattern

### Implementation Reference

```python
# db.py addition
async def list_distinct_project_dirs(path: str = DB_PATH) -> list[str]:
    """Return unique project directories, most-recently-active first."""
    async with get_db(path) as db:
        cursor = await db.execute("""
            SELECT project_dir, MAX(COALESCE(last_active_at, updated_at)) as last_used
            FROM thread_config
            GROUP BY project_dir
            ORDER BY last_used DESC
        """)
        rows = await cursor.fetchall()
        return [r["project_dir"] for r in rows]


# chati.py addition
@authorized
async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /projects — show inline keyboard of previous projects."""
    projects = await db.list_distinct_project_dirs(path=DB_PATH)
    if not projects:
        await update.message.reply_text(
            "No previous projects found. Use <code>/project &lt;path&gt;</code> to bind a project.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Store list for callback lookup
    context.chat_data["_projects_list"] = projects

    # Build keyboard (truncate display if too long)
    keyboard = []
    for idx, path in enumerate(projects):
        display = path if len(path) < 60 else "..." + path[-57:]
        keyboard.append([InlineKeyboardButton(display, callback_data=f"project:{idx}")])

    await update.message.reply_text(
        "📂 Select a project to bind this thread to:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_projects_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle project selection from inline keyboard."""
    query = update.callback_query
    await query.answer()

    try:
        idx = int(query.data.split(":", 1)[1])
        projects = context.chat_data.get("_projects_list", [])
        path = projects[idx]
    except (ValueError, IndexError, KeyError):
        await query.edit_message_text("⚠️ Invalid selection. Try /projects again.")
        return

    thread_id = _get_thread_id(update) or DEFAULT_THREAD_ID
    await db.upsert_thread_config(thread_id, project_dir=path, path=DB_PATH)
    thread_label = f"thread {thread_id}" if thread_id != DEFAULT_THREAD_ID else "main chat"
    await query.edit_message_text(
        f"✅ Bound {thread_label} to:\n<code>{_escape_html(path)}</code>",
        parse_mode=ParseMode.HTML,
    )
```

### Files to Modify

- `db.py` (UPDATE) — add `list_distinct_project_dirs()`
- `chati.py` (UPDATE) — add `cmd_projects`, `handle_projects_callback`, register handlers
- `tests/test_db.py` (UPDATE) — add tests for new db function
- `tests/test_cmd_projects.py` (NEW) — tests for /projects handler

### Anti-Patterns

- ❌ Don't put full path in callback_data (64-byte limit)
- ❌ Don't use global state for projects list — use `chat_data` (per-chat, ephemeral)

### References

- [Source: architecture.md#Command Structure]
- [Source: epics.md#Story 1.3]

## Dev Agent Record

### Agent Model Used

Claude (Auto) via Kiro

### Completion Notes List

- 11 new tests (3 db + 8 handler) — all passing
- Full test suite: 55 tests in 1.69s, zero regressions
- `list_distinct_project_dirs` orders by `MAX(last_active_at, updated_at) DESC`
- Callback data format `project:<index>` — safely within 64-byte limit
- Long paths (>55 chars) truncated with `...` prefix in button labels
- Current thread's binding marked with `✓` prefix in keyboard
- Error paths tested: invalid index, missing chat_data, malformed data

### File List

- `db.py` (UPDATE) — added `list_distinct_project_dirs()`
- `chati.py` (UPDATE) — added `cmd_projects`, `handle_projects_callback`, registered handlers
- `tests/test_db.py` (UPDATE) — 3 new tests for new db function
- `tests/test_cmd_projects.py` (NEW) — 8 handler tests
