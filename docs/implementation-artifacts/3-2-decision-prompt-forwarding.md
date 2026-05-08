# Story 3.2: Decision Prompt Forwarding to User

Status: done

## Story

As a **user**,
I want to see the CLI's question on my phone with enough context to make a decision,
so that I can respond without scrolling back through the stream.

## Acceptance Criteria

1. `_stream_pty` yields `DecisionPrompt` instead of `str` when detection triggers
2. Generator returns after yielding DecisionPrompt (Option B pattern per architecture)
3. State machine transitions: STREAMING → DETECTING_PROMPT → WAITING_FOR_USER before yield
4. `_execute_and_reply_inner` detects DecisionPrompt objects, sends formatted message to Telegram
5. Message format: "⚠️ CLI waiting for input:\n\n{context lines}\n\nReply to proceed, or /cancel to abort."
6. `context.bot_data[f"thread:{thread_id}:pending_decision"]` set to True for pending reply tracking
7. Streaming preview message kept (not deleted) so user has full context
8. Tests pass

## Tasks / Subtasks

- [ ] Task 1: Track line buffer in `_stream_pty` for detection
- [ ] Task 2: Call `detect_decision_prompt` on idle threshold
- [ ] Task 3: Transition DETECTING_PROMPT → WAITING_FOR_USER on match
- [ ] Task 4: Update type signature: `AsyncGenerator[str | DecisionPrompt, None]`
- [ ] Task 5: Update `_execute_and_reply_inner` to handle DecisionPrompt yields
- [ ] Task 6: Store pending state in bot_data
- [ ] Task 7: Tests

## Dev Notes

### Detection Point in _stream_pty

After idle threshold reached AND state is STREAMING:
1. Transition STREAMING → DETECTING_PROMPT
2. Call detect_decision_prompt(buffer)
3. If matched: transition → WAITING_FOR_USER, yield DecisionPrompt, RETURN
4. If no match: transition back → STREAMING, yield idle warning, continue

### Message Format

```
⚠️ <b>CLI is waiting for input</b>

<pre>{last 5 lines formatted}</pre>

Reply to proceed, or /cancel to abort.
```

### References
- [Source: architecture.md#Decision Forwarding Data Flow]
- [Source: epics.md#Story 3.2]

## Dev Agent Record

### Agent Model Used
Claude (Auto) via Kiro

### Completion Notes List

### File List
