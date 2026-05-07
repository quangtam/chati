# Story 3.3: Decision Reply Piping & Stream Resumption

Status: done

## Story

As a **user**,
I want to reply to a forwarded decision prompt and have the CLI continue processing.

## Acceptance Criteria

1. `CliRunner.pipe_reply_stream(thread_id, reply)` — new async generator
2. Transitions WAITING_FOR_USER → PIPING_REPLY → STREAMING
3. Writes reply to PTY, continues reading output until next prompt marker or decision
4. When `pending_decision` is set for a thread, next free-form message → `pipe_reply_stream` instead of `execute_stream`
5. Can yield another DecisionPrompt (chained decisions)
6. `/cancel` clears pending state and kills session
7. Empty/whitespace reply still piped (CLI decides how to handle)
8. Tests pass

## Tasks / Subtasks

- [ ] Task 1: Implement `pipe_reply_stream` in CliRunner
- [ ] Task 2: Update handle_message to check pending_decision flag
- [ ] Task 3: Route to pipe_reply_stream or execute_stream based on flag
- [ ] Task 4: Clear pending flag on reply, /cancel, /new
- [ ] Task 5: Tests

## Dev Notes

### pipe_reply_stream logic

```python
async def pipe_reply_stream(
    self,
    thread_id: int | None,
    reply: str,
    timeout_seconds: int | None = None,
) -> AsyncGenerator[str | DecisionPrompt, None]:
    session = self._session_mgr.get(thread_id)
    if not session or not session.alive:
        yield "❌ Session no longer available. Send a new message to start fresh.\n"
        return
    
    # Transition WAITING_FOR_USER → PIPING_REPLY
    self._session_mgr.transition(thread_id, PtyState.PIPING_REPLY, reason="user reply")
    
    # Write reply to PTY
    session.write(reply + "\n")
    
    # Transition → STREAMING and yield remaining output
    self._session_mgr.transition(thread_id, PtyState.STREAMING, reason="reply piped")
    
    # Reuse _stream_pty logic by calling inner loop directly
    # Actually simpler: extract the read loop into a shared helper
    async for chunk in self._stream_pty_loop(session, thread_id, timeout_seconds):
        yield chunk
```

### References
- [Source: architecture.md#Decision Forwarding Data Flow]
- [Source: epics.md#Story 3.3]

## Dev Agent Record

### Agent Model Used
Claude (Auto) via Kiro

### Completion Notes List

### File List
