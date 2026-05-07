# Story 2.5: Streaming Output with Progressive Edits

Status: done

## Story

As a **user**,
I want to see CLI output streaming in real-time via progressive message edits,
so that I know the CLI is working and can follow progress.

## Acceptance Criteria

1. Preview message edited every 1.5 seconds with latest output ✅ (v1 behavior)
2. Preview buffer exceeds 3000 characters → truncate to last 3000 ✅ (v1 behavior)
3. Typing indicators sent every 4 seconds while streaming ✅ (v1 behavior)
4. Stream completes → preview deleted, final formatted response sent ✅ (v1 behavior)
5. ANSI stripping continues to work (regression) ✅
6. Message splitting at 4096 chars continues to work (regression) ✅

## Completion Notes

All streaming features from v1 maintained after Epic 1/2 refactoring:
- `_STREAM_UPDATE_INTERVAL = 1.5` in chati.py (unchanged)
- `_STREAM_PREVIEW_MAX = 3000` in chati.py (unchanged)
- `_TYPING_KEEPALIVE_INTERVAL = 4.0` in chati.py (unchanged)
- ANSI stripping via `strip_ansi()` from message_utils (unchanged)
- Message splitting via `split_message()` from message_utils (unchanged)

New in v2.5:
- `_execute_and_reply_inner` now resolves per-thread config via `db.resolve_thread_config()`
- Passes `timeout_seconds=resolved_timeout` to `runner.execute_stream()` for per-thread timeout
- Falls back to `.env` defaults gracefully if resolution fails

Tests: 106 passing. No streaming-specific tests added (would require Telegram API mocking — deferred; regression tests in other stories cover the integration points).

## File List

- `chati.py` (UPDATE) — added resolve_thread_config call in `_execute_and_reply_inner`, pass timeout_seconds to execute_stream
