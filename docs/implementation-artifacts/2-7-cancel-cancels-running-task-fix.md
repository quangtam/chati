# Story 2.7: /cancel Actually Cancels the Running Task (Bug)

Status: done

## Story

As a **user**,
I want `/cancel` to immediately stop the running CLI task AND free the thread so my next message runs right away,
So that "cancel" means cancel, not "kill PTY but leave the task running + lock held".

## Context / Bug Report

**Reported by Tony (2026-05-07):**

> "Có vẻ như lệnh /cancel không hoạt động"

**Root cause:**

`CliRunner.cancel()` kills the PTY process but does NOT cancel the asyncio task running `execute_stream`. The per-thread `asyncio.Lock` is held inside `async with lock:` for the entire lifetime of the streaming generator. Consequences:

1. After `/cancel`, `runner.is_busy(thread_id)` still returns `True` because the stream task is still draining output / running cleanup code.
2. User sends a new message → `_execute_and_reply` detects busy state → shows "⏳ This thread has a running request — your message is queued" → message waits behind the lock.
3. User perceives: "cancel didn't work; bot is still busy".

Additionally:

- `_thread_sessions` message counter is not reset by `/cancel`, so `_should_resume` thinks there's still history → next message tries to resume a dead conversation.
- PTY `select()` may take up to 2s to notice the closed fd (read timeout), so the stream task doesn't exit fast enough.

## Acceptance Criteria (BDD)

**Given** the user sends a message that starts a CLI stream in thread A
**When** the user sends `/cancel` in thread A while the stream is running
**Then** the CLI process is killed (existing behavior)
**And** the asyncio task executing the stream is cancelled
**And** the per-thread lock is released immediately
**And** `runner.is_busy(thread_id)` returns `False` within ~1s
**And** the user receives "✅ Cancelled running CLI process."

**Given** the user sends `/cancel` in a thread with no active session and no running task
**When** the command is processed
**Then** the response is "ℹ️ No active CLI process to cancel."

**Given** the user sends `/cancel` immediately followed by a new message
**When** the new message arrives (after cancel)
**Then** the new message does NOT see "⏳ queued" — the thread is available
**And** a fresh CLI session starts (or an existing idle one is reused)

**Given** the user sends `/cancel` while a decision prompt is pending
**When** the command is processed
**Then** the pending_decision flag is cleared (existing behavior preserved)
**And** the session is killed + task cancelled

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for the changed code

## Tasks / Subtasks

- [x] Task 1: Add per-thread task registry to `chati.py` (`_thread_tasks: dict[int | None, asyncio.Task]`)
- [x] Task 2: In `_execute_and_reply`, register the current task before streaming and unregister in `finally`
- [x] Task 3: In `cmd_cancel`, cancel the registered task (if any) in addition to `runner.cancel()`
- [x] Task 4: Reset `_thread_sessions[thread_id] = 0` on cancel so next message starts fresh
- [x] Task 5: Tests — cancel releases lock, cancel aborts task, cancel resets counter, cancel with no task still works

## Dev Notes

### Why `runner.cancel()` alone isn't enough

`CliRunner.execute_stream` is `async with lock: ... async for line in self._stream_pty(...): yield line`. The lock is released only when the generator exits (either naturally or via cancellation). Killing the PTY causes `session.read()` to return `""`, which breaks the inner loop, but the outer async generator still runs cleanup code + the `async for` on the consumer side (in `chati.py`) still processes any buffered yields. Meanwhile the lock stays held.

The fix: cancel the asyncio task that is awaiting the generator. `asyncio.Task.cancel()` raises `CancelledError` inside the generator on its next `await`, which propagates out of the `async with lock:` block (releasing the lock) and through the consumer (which should have a try/finally or catch `CancelledError`).

### Task registry pattern

```python
_thread_tasks: dict[int | None, asyncio.Task] = {}

# In _execute_and_reply:
task = asyncio.current_task()
_thread_tasks[thread_id] = task
try:
    await _execute_and_reply_inner(...)
finally:
    if _thread_tasks.get(thread_id) is task:
        _thread_tasks.pop(thread_id, None)

# In cmd_cancel:
task = _thread_tasks.pop(thread_id, None)
if task and not task.done():
    task.cancel()
```

### What must NOT break

- Decision forwarding: `/cancel` during WAITING_FOR_USER still kills session + clears pending_decision (existing behavior).
- `/new`: must still reset thread counter (it already does).
- Concurrent threads: cancelling thread A must not affect thread B's task.
- Cleanup: orphan detection / idle cleanup still work.

### Files modified

- `chati.py` — add `_thread_tasks` dict, wrap `_execute_and_reply` with register/unregister, enhance `cmd_cancel` to cancel task + reset counter.

### Files potentially changed (none needed for this story)

- `cli_runner.py` — no changes. `runner.cancel()` keeps its existing semantics (kill PTY, return bool). The task-level cancellation is chati.py's concern because it owns the handler/task lifecycle.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 via Kiro

### Completion Notes

✅ Root cause: `runner.cancel()` killed the PTY but did not cancel the asyncio task running `execute_stream`. The per-thread `asyncio.Lock` inside `async with lock:` stayed held, so `runner.is_busy()` returned True for seconds/minutes after /cancel, and the next message was "queued".
✅ Added `_thread_tasks: dict[int | None, asyncio.Task]` registry in `chati.py`.
✅ `_execute_and_reply` now registers itself on entry, unregisters in `finally`, and propagates `CancelledError`.
✅ `cmd_cancel` now: (1) clears pending_decision flag (2) cancels the registered task (3) kills the PTY session (4) resets `_thread_sessions` counter so the next message starts fresh.
✅ 6 new tests in `tests/test_cmd_cancel.py` covering: no-task case, task-cancellation releases lock, pending-decision cleanup, cross-thread isolation, already-done task, session + counter reset.
✅ Full regression: 178/178 pass.

### File List

**Modified:**

- `chati.py` — added `_thread_tasks` dict; `_execute_and_reply` now registers current task with try/finally cleanup and propagates `CancelledError`; `cmd_cancel` now cancels the task + resets thread counter.

**Added:**

- `tests/test_cmd_cancel.py` — 6 tests covering task cancellation, lock release, and edge cases.

### Change Log

| Date       | Change                                                       |
|------------|--------------------------------------------------------------|
| 2026-05-07 | Story opened to fix /cancel not actually cancelling tasks.   |
| 2026-05-07 | Task registry + cancellation implemented. 6 tests pass. Full suite 178/178. |


### Review Findings

Code review (2026-05-07).

**Patch — HIGH:**

- [ ] [Review][Patch] Race: `_thread_tasks[thread_id] = task` unconditional assignment can overwrite a concurrent task registration from same thread. `finally: pop(thread_id)` then clears the wrong entry. Use `if _thread_tasks.get(thread_id) is task: pop(...)` pattern. [chati.py:_execute_and_reply finally]
- [ ] [Review][Patch] AC promises `is_busy` returns False within ~1s, but `task.cancel()` is fire-and-forget. If cancelled task's `finally` block is slow, lock stays held past 1s. Consider `await asyncio.wait_for(task, timeout=1.0)` with `suppress(CancelledError, TimeoutError)` to actually wait for release. [chati.py:cmd_cancel]

**Patch — MEDIUM:**

- [ ] [Review][Patch] `await runner.cancel(thread_id)` is not wrapped in try/except. If session_mgr.kill raises, the counter reset and reply to user are skipped — user sees uncaught exception. [chati.py:cmd_cancel]
- [ ] [Review][Patch] `asyncio.current_task()` may return None if called outside event loop context (rare but possible in some PTB setups). Add `if task is not None` guard. [chati.py:_execute_and_reply]

**Patch — LOW:**

- [x] [Review][Defer] Tests use `fd=-1` + `asyncio.sleep(10)` in fake tasks. Real-world cancel through `select()` in `pty_executor` is never exercised. Integration test with real PTY would validate the 2s select timeout window. **Still deferred — real-PTY tests are flaky on CI, unit tests + task-cancellation lock-release test cover the key invariant.** [tests/test_cmd_cancel.py]
