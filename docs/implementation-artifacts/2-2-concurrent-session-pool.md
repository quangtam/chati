# Story 2.2: Concurrent Session Pool & Resource Enforcement

Status: done

## Story

As a **user**,
I want to run up to 5 CLI sessions simultaneously across different threads,
so that I can work on multiple projects without interference.

## Acceptance Criteria

1. `MAX_SESSIONS` constant (default 5) configurable via `.env` — respected by SessionManager
2. Attempting to create a 6th session returns None/error with message to user
3. Dedicated `pty_executor` (ThreadPoolExecutor, max_workers=8) used for PTY blocking I/O
4. `cleanup_orphans()` method on SessionManager — kills orphaned PTY processes at startup
5. Sessions run independently without cross-thread interference
6. Unit tests pass with ≥80% branch coverage

## Tasks / Subtasks

- [ ] Task 1: Add `MAX_SESSIONS` to Config (AC: #1)
- [ ] Task 2: Enforce max in SessionManager.create (AC: #1, #2)
  - [ ] Raise `SessionLimitExceeded` exception
  - [ ] `can_create()` helper returns bool
- [ ] Task 3: Add dedicated `pty_executor` to SessionManager (AC: #3)
  - [ ] `ThreadPoolExecutor(max_workers=8, thread_name_prefix="pty")`
  - [ ] Exposed as property
- [ ] Task 4: Implement `cleanup_orphans()` (AC: #4)
  - [ ] Cross-platform PID probing (os.kill with signal 0)
  - [ ] Log orphans killed
- [ ] Task 5: Update `cli_runner.py` to use pty_executor + handle SessionLimitExceeded
- [ ] Task 6: Tests

## Dev Notes

- `SessionLimitExceeded` exception class in session_manager
- `pty_executor` owned by SessionManager, cleaned up on shutdown
- Orphan detection: only checks sessions tracked by current SessionManager; for true orphan cleanup across restarts, would need external PID file tracking (out of scope for MVP)

### References
- [Source: architecture.md#Process & Session Architecture]
- [Source: epics.md#Story 2.2]

## Dev Agent Record

### Agent Model Used
Claude (Auto) via Kiro

### Completion Notes List

### File List
