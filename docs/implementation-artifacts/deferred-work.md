# Deferred Work Log

Accumulated list of issues knowingly deferred during code reviews. Revisit periodically.

## Deferred from: code review of story 4-1-cli-info-command (2026-05-07) — RESOLVED 2026-05-07

All items in this batch were swept during the tech-debt cleanup on the same day:

- **W1 — ✅ FIXED**: Added `os.path.isdir(cwd)` guard in `_get_or_create_session` and `_stream_non_interactive`. Non-existent project dirs now fail fast with a clear error log (+ user-facing message in non-interactive path) instead of leaving the PTY child to crash on `os.chdir()`.
- **W2 — KEPT AS-IS (not a real issue)**: `session_manager.py:PtySession.ready` is informational by design. Not enforced because there's only one writer (`_get_or_create_session`) and readers only use it for display. Closed without code change.
- **W3 — ✅ FIXED**: Consolidated `_TOOL_LINE_PATTERNS` — removed the 3 overlapping matchers (braille, Thinking, ellipsis) that `strip_streaming_noise()` already handles. No redundant regex sweeps.
- **W4 — ✅ FIXED**: Extracted `patch_allowed_users`, `clean_state`, `temp_db_path`, and the enhanced `telegram_update_factory` (with awaitable `reply_chat_action` by default) into `tests/conftest.py`. Removed duplicated fixtures from 8 test files.

## Deferred from: code review of 4-2 session-list / cleanup sweep 2026-05-07 — RESOLVED 2026-05-07

- **✅ FIXED**: N+1 DB query in `cmd_sessions` — now batches via `db.list_all_threads()` + in-memory dict lookup.
- **✅ FIXED**: `cmd_sessions` pagination now stable — sorts by `thread_id` (None → main chat first).
- **✅ FIXED**: `_thread_sessions` counter stale after cleanup — main cleanup loop now snapshots pool before/after and resets counter for cleaned-up thread_ids.

## Deferred from: code review of 1-6 binding fix — RESOLVED 2026-05-07

- **✅ FIXED**: INFO log no longer includes full `cwd` path. Downgraded to DEBUG. User action lines still at INFO.

## Deferred from: code review of 2-7 /cancel fix — STILL DEFERRED

- **⏸ DEFERRED**: Real-PTY integration test for `/cancel` timing via the `select()` loop in `pty_executor`. Real PTYs are flaky on CI runners and the unit tests already verify the lock-release contract (task cancellation releases the per-thread `asyncio.Lock`). If CI ever gets reliable PTY tooling, re-evaluate.

## Deferred from: code review of 2-8 spinner noise fix — RESOLVED 2026-05-07

- **✅ FIXED**: See W3 above — duplicate braille patterns removed from `_TOOL_LINE_PATTERNS`.

---

## Currently Open (to revisit)

- **`cmd_cancel` real-PTY integration test** — only item still deferred as of 2026-05-07. Tracked above.
