# Story 2.3: Adaptive Timeout with Reset-on-Output

Status: done

## Story

As a **user**,
I want the timeout to reset every time the CLI produces meaningful output,
so that long-running tasks don't get killed mid-execution.

## Acceptance Criteria

1. Timeout resets on meaningful output (newline-terminated line, not single bytes)
2. Per-thread timeout override from `thread_config.timeout_seconds` takes precedence over global
3. Idle warning fires after `IDLE_WARN_INTERVAL` seconds (30s default)
4. Timeout paused while in `PtyState.WAITING_FOR_USER` (for Story 3.x decision forwarding)
5. Unit tests pass

## Tasks / Subtasks

- [ ] Task 1: Accept per-thread timeout in `_stream_pty` (AC: #2)
- [ ] Task 2: Add output debounce (AC: #1) — line-based reset
- [ ] Task 3: Pause timeout when state is WAITING_FOR_USER (AC: #4)
- [ ] Task 4: Use `resolve_thread_config` to get timeout
- [ ] Task 5: Tests

## Dev Notes

Existing code already resets on every chunk — we refine to only reset on newline-bearing chunks. The `\n` character signals a complete line = meaningful output.

For per-thread timeout, `execute_stream()` resolves config via `db.resolve_thread_config()` and passes to `_stream_pty`.

### References
- [Source: architecture.md#Adaptive Timeout]
- [Source: epics.md#Story 2.3]

## Dev Agent Record

### Agent Model Used
Claude (Auto) via Kiro

### Completion Notes List

### File List
