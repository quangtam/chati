# Story 3.4: Decision Reply Timeout

Status: done

## Story

As a **system**,
I want decisions unanswered for 30 minutes to auto-expire,
so that sessions don't hang indefinitely.

## Acceptance Criteria

1. `DECISION_REPLY_TIMEOUT` configurable via `.env` (default 1800s)
2. Background task checks WAITING_FOR_USER sessions every minute
3. Sessions waiting > timeout are killed, user notified
4. Pending_decision flag cleared on timeout
5. Tests pass

## Tasks / Subtasks

- [ ] Task 1: Add `cleanup_expired_decisions()` to SessionManager
- [ ] Task 2: Background task in chati.py main() runs it periodically
- [ ] Task 3: Send notification to user + clear bot_data flag
- [ ] Task 4: Tests

## Dev Notes

Expiry logic: session in WAITING_FOR_USER + (now - last_active_at) > timeout.
`last_active_at` is refreshed on every transition (including WAITING_FOR_USER), so this measures "time since prompt was forwarded".

### References
- [Source: epics.md#Story 3.4]

## Dev Agent Record

### Agent Model Used
Claude (Auto) via Kiro

### Completion Notes List

### File List
