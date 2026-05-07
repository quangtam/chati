# Story 2.4: Session Operations (new, resume, cancel)

Status: done

## Story

As a **user**,
I want to start fresh sessions, resume existing ones, and cancel running processes,
so that I have full control over my CLI sessions per thread.

## Acceptance Criteria

1. `/new` kills existing session and fresh spawns on next message
2. Warm session reused (no cold start)
3. `/cancel` SIGKILLs process, notifies user
4. `/cancel` in thread with no active process shows friendly message
5. Dead session auto-starts fresh on next free-form message (existing v1 behavior via `_get_or_create_session.alive` check)

## Completion Notes

All ACs already satisfied by v1 implementation + Story 2.1/2.2 refactoring:
- `cmd_cancel` / `cmd_new_session` / `cmd_resume` already implemented in `chati.py`
- `_get_or_create_session` checks `.alive` and cleans up dead sessions automatically
- SessionManager.kill() sets state to DEAD and removes from pool
- No new code needed beyond the SessionManager refactor in Story 2.1

Tests: existing smoke tests + session_manager tests cover lifecycle behavior (106 tests passing).

## File List

No new files. Existing chati.py handlers + session_manager.py handle all AC.
