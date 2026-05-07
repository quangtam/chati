# Story 1.1: SQLite Database Layer

Status: done

## Story

As a **developer**,
I want a SQLite persistence layer with async context manager and schema migration,
so that thread configuration can be stored and retrieved reliably across bot restarts.

## Acceptance Criteria

1. `db.py` module created with async context manager `get_db()` that sets WAL mode + busy_timeout=5000 per connection
2. Schema migration: on first startup (no `chati.db` exists), `init_db()` creates `thread_config` table and a default row (thread_id=NULL) using `.env PROJECT_DIR`
3. Existing `chati.db` preserved across restarts — no destructive migrations
4. Repository functions implemented: `get_thread_config()`, `upsert_thread_config()`, `list_all_threads()`, `update_last_active()`
5. Concurrent coroutines can write simultaneously without "database is locked" errors (WAL mode validated)
6. `ThreadConfig` dataclass exposed for type-safe access to config data
7. Unit tests pass with ≥80% branch coverage for new code

## Tasks / Subtasks

- [x] Task 1: Create `ThreadConfig` dataclass and `get_db()` context manager (AC: #1, #6)
  - [x] `@dataclass(frozen=True)` with all fields matching schema
  - [x] `get_db()` using `@asynccontextmanager` pattern
  - [x] WAL mode + busy_timeout=5000 on every connection
- [x] Task 2: Implement `init_db()` for schema migration (AC: #2, #3)
  - [x] Create `thread_config` table if not exists
  - [x] Insert default row (thread_id=NULL mapped as 0) from `.env PROJECT_DIR`
  - [x] Idempotent — safe to call on every startup
- [x] Task 3: Implement repository functions (AC: #4)
  - [x] `get_thread_config(thread_id)` → `ThreadConfig | None`
  - [x] `upsert_thread_config(thread_id, **kwargs)` → updates changed fields only
  - [x] `list_all_threads()` → `list[ThreadConfig]`
  - [x] `update_last_active(thread_id)` → updates last_active_at timestamp
- [x] Task 4: Write comprehensive tests (AC: #5, #7)
  - [x] Test WAL mode enabled
  - [x] Test concurrent writes (5 coroutines)
  - [x] Test CRUD operations
  - [x] Test init_db() idempotency
  - [x] Test default row creation

## Dev Notes

### Architecture Compliance

- Async context manager pattern (NOT open/close per function) [Source: architecture.md#SQLite Access Pattern]
- `aiosqlite` library (no other deps)
- Connection per operation (not shared across coroutines)
- PRAGMA WAL + busy_timeout set inside context manager
- Schema migration on startup (idempotent)

### Schema (from architecture.md)

```sql
CREATE TABLE thread_config (
    thread_id       INTEGER PRIMARY KEY,
    project_dir     TEXT NOT NULL,
    cli_provider    TEXT,              -- NULL = use .env CLI_PROVIDER
    model           TEXT,              -- NULL = use provider default
    timeout_seconds INTEGER,           -- NULL = use .env CLI_TIMEOUT
    last_active_at  TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
```

### Default Thread Handling

- Default thread (main chat, no topic) uses `thread_id = 0` (SQLite requires PK, use 0 as sentinel for NULL)
- Application code translates `None` ↔ `0` at the boundary
- On first startup, create row with `thread_id=0` using `.env PROJECT_DIR`

### Implementation Reference

```python
# db.py skeleton
from contextlib import asynccontextmanager
from dataclasses import dataclass
import aiosqlite

DB_PATH = "chati.db"
DEFAULT_THREAD_ID = 0  # sentinel for "no thread_id" (main chat)


@dataclass(frozen=True)
class ThreadConfig:
    thread_id: int
    project_dir: str
    cli_provider: str | None = None
    model: str | None = None
    timeout_seconds: int | None = None
    last_active_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@asynccontextmanager
async def get_db(path: str = DB_PATH):
    db = await aiosqlite.connect(path, timeout=30)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    try:
        yield db
        await db.commit()
    finally:
        await db.close()
```

### Files to Create/Modify

- `db.py` (NEW) — ~150 lines
- `tests/test_db.py` (NEW) — comprehensive coverage

### Anti-Patterns

- ❌ Don't share connections across coroutines
- ❌ Don't forget WAL mode (causes "database is locked")
- ❌ Don't use `time.sleep()` in tests — use `asyncio.sleep()`

### References

- [Source: architecture.md#Data Architecture]
- [Source: architecture.md#SQLite Access Pattern]
- [Source: epics.md#Story 1.1]

## Dev Agent Record

### Agent Model Used

Claude (Auto) via Kiro

### Completion Notes List

- 21 tests passing in 0.11s (db.py) + 17 smoke tests = 38 total, 0 regressions
- WAL mode + busy_timeout=5000 verified in dedicated tests
- Concurrent writes (5 coroutines) tested and working
- Migration idempotency verified across multiple init_db() calls
- Default row creation only when table empty and path provided
- All functions accept `path` param for testability (default `DB_PATH`)
- `upsert_thread_config` uses conditional UPDATE (only changed fields) to preserve existing values

### File List

- `db.py` (NEW) — 215 lines: ThreadConfig, get_db, init_db, CRUD functions
- `tests/test_db.py` (NEW) — 21 comprehensive tests
