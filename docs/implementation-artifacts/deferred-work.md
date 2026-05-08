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

## Deferred from: code review of 5-1-screenshot-detection-forwarding (2026-05-08)

- **Caption HTML escaping** — `f"📸 {filename}"` and `f"📎 {filename} ({size_mb:.1f}MB)"` captions in `_send_screenshots` are not HTML-escaped. Benign today because no `parse_mode` is set on `reply_photo`/`reply_document`. Would become a bug if parse_mode is ever added. Fix: wrap filename with `_escape_html()`. [chati.py:1451,1457]
- **Extra DB call in `_stream_to_telegram`** — calls `db.resolve_thread_config()` just to get `project_dir` for screenshot path resolution. Could use `db.get_thread_config()` directly (lighter) or pass `project_dir` as a parameter to `_stream_to_telegram`. Minor perf nit, not a correctness issue. [chati.py:1188-1197]

## Deferred from: code review of 6-1-voice-input-whisper (2026-05-08)

- **Edit mode flag persistence** — `voice_edit_mode` in `bot_data` has no TTL. If user taps ✏️ but never types a replacement, the flag persists indefinitely. Next text message in that thread (even days later) gets intercepted as the "edit". Acceptable for v1 single-user bot; consider clearing on next voice message or adding a timeout in story 6.3. [chati.py:handle_message voice_edit_mode branch]

## Deferred from: code review of 6-2-voice-output-tts (2026-05-08)

- **Inline imports in `_send_voice_message`** — `io` and `InputFile` imported inside the function body; `InputFile` is already at module level. Minor style inconsistency. [chati.py:_send_voice_message]
- **`is_code_heavy` counts ``` delimiters** — code block ratio includes the opening/closing ``` fences, slightly inflating the code ratio. Story 6.3 spec explicitly plans to refine this to count only content inside blocks. [message_utils.py:is_code_heavy]
- **Separate OpenAI clients for Transcriber and Synthesizer** — `VoiceTranscriber` and `VoiceSynthesizer` each create their own `AsyncOpenAI` client. A shared client would reduce connection overhead. Story 6.3 spec mentions this optimization. [voice.py]


## Deferred from: code review of 6-3-voice-configuration (2026-05-08)

- `TTS_SPEED` env var crash on invalid input — `float(os.getenv(...))` with no try/except; pre-existing pattern across all env vars in config.py
- Voice edit mode flag (`voice_edit_mode` in bot_data) persists indefinitely with no timeout/cleanup — pre-existing from Story 6.1
- `_UpdateProxy` class fragility in group chat scenarios — proxy may not correctly forward all attributes; pre-existing from Story 6.1
- Non-atomic read-toggle-write race on rapid `/voice` double-tap — acceptable for single-user bot deployment
- Triple DB query in `_voice_status` for same thread_id — could be optimized to single `get_thread_config` call; acceptable for low-frequency command handler
