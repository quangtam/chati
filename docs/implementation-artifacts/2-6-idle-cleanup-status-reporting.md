# Story 2.6: Idle Session Cleanup & Status Reporting

Status: done

## Story

As a **user**,
I want idle sessions to be cleaned up automatically and session status visible,
so that resources aren't wasted and I can see what's running.

## Acceptance Criteria

1. `IDLE_SESSION_MAX_AGE` configurable via `.env` (default 1800s = 30min)
2. Background cleanup task runs every 5 minutes
3. Sessions idle for > max_age are killed (state transitions to DEAD, removed from pool)
4. Dead sessions detected at get-time (already covered via `session.alive` check)
5. SessionManager.get_status() returns display-ready status indicator per state
6. Graceful shutdown on SIGTERM: kills all sessions + closes DB connections
7. Tests pass

## Tasks / Subtasks

- [ ] Task 1: Add `IDLE_SESSION_MAX_AGE` + `CLEANUP_INTERVAL` to Config
- [ ] Task 2: Track `last_active_at` in PtySession (update on prompt write)
- [ ] Task 3: Implement `cleanup_idle()` in SessionManager
- [ ] Task 4: Background cleanup task started in chati.py main()
- [ ] Task 5: Add `get_status_emoji()` helper to SessionManager (for /sessions display)
- [ ] Task 6: Tests

## Dev Notes

Periodic task uses `asyncio.create_task` with `asyncio.sleep(interval)`. Must handle `CancelledError` gracefully on shutdown.

Status emoji mapping:
- IDLE → 💤
- STREAMING → 🟢
- DETECTING_PROMPT → 🟢 (still streaming from user POV)
- WAITING_FOR_USER → ⏳
- PIPING_REPLY → 🟢
- DEAD → ❌

### References
- [Source: architecture.md#Process Lifecycle]
- [Source: epics.md#Story 2.6]

## Dev Agent Record

### Agent Model Used
Claude (Auto) via Kiro

### Completion Notes List

### File List
