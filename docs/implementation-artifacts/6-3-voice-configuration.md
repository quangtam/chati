# Story 6.3: Voice Configuration & Code Detection

Status: review

## Story

As a **system**,
I want voice features to be configurable and code-heavy detection to be reliable,
So that voice doesn't fire inappropriately and users have control.

## Acceptance Criteria (BDD)

**Given** a response contains markdown code blocks (``` delimited)
**When** code block ratio is calculated
**Then** the ratio = (characters inside code blocks) / (total characters)
**And** if ratio > 0.5, response is classified as "code-heavy"

**Given** voice output is a Growth feature
**When** the feature is not yet implemented
**Then** all voice-related code paths gracefully no-op (feature flag pattern)

**Given** Whisper and TTS API keys are not configured in `.env`
**When** a voice message is received
**Then** the bot responds: "Voice features not configured. Please type your message."

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

## Tasks / Subtasks

- [x] Task 1: Persist `/voice` toggle to SQLite (survive bot restarts)
- [x] Task 2: Add `voice_output` column migration to `db.py` with backward-compatible schema evolution
- [x] Task 3: Extend `resolve_thread_config()` to include `voice_output` in resolution chain
- [x] Task 4: Harden `is_code_heavy()` with edge cases (inline code, nested blocks, empty blocks)
- [x] Task 5: Add `/voice status` subcommand showing current voice config for the thread
- [x] Task 6: Ensure graceful no-op when `openai` package is not installed
- [x] Task 7: Update `/help` and `/info` to reflect voice feature state
- [x] Task 8: Write tests in `tests/test_voice_configuration.py`

## Dev Notes

### Epic 6 Context

This is story 6.3 (final) of Epic 6 "Voice Communication (Growth)":

- **6.1 (done)**: Voice input — Whisper transcription + confirm-first UX
- **6.2 (done)**: Voice output — TTS response synthesis
- **6.3 (this)**: Voice configuration & code detection (hardening + persistence)

This story completes Epic 6. After this, epic-6 status should be "done".

**FRs covered:** FR36 (reliable code-heavy detection), plus hardening of FR33-37 configuration paths

**This is a hardening/polish story** — it doesn't introduce new user-facing features but makes the voice system production-ready by:
1. Persisting voice preferences across bot restarts (SQLite)
2. Hardening code-heavy detection edge cases
3. Ensuring graceful degradation when dependencies are missing
4. Providing visibility into voice configuration state

### Architecture Requirements

**Module ownership per architecture:**

- `db.py` — owns SQLite schema and persistence (voice_output column)
- `config.py` — owns .env-based configuration
- `voice.py` — owns voice service initialization (graceful import handling)
- `message_utils.py` — owns `is_code_heavy()` (pure function hardening)
- `chati.py` — owns command handlers and orchestration

**Key architectural principle:** Configuration resolution uses 3-layer fallback chain:
1. Per-thread SQLite value (if not NULL)
2. Global .env default
3. Hardcoded fallback

Voice output follows this same pattern: `thread_config.voice_output` → `VOICE_OUTPUT_ENABLED` → `False`

### Implementation Guide

#### Task 1: Persist `/voice` Toggle to SQLite

Story 6.2 introduced `/voice` toggle storing state in `context.bot_data` (in-memory only). This task makes it survive bot restarts by writing to SQLite.

**Modify `cmd_voice()` in `chati.py`:**
```python
@authorized
async def cmd_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /voice — toggle voice output for this thread (persisted)."""
    if not config.voice_enabled:
        await update.message.reply_text(
            "🎤 Voice features not configured.\n"
            "Set OPENAI_API_KEY in .env to enable voice."
        )
        return

    thread_id = _get_thread_id(update)
    thread_key = f"thread:{thread_id}:voice_output"

    # Resolve current state from SQLite → .env → default
    current = await _resolve_voice_output(thread_id)
    new_state = not current

    # Persist to SQLite
    await db.upsert_voice_output(
        thread_id if thread_id is not None else DEFAULT_THREAD_ID,
        voice_output=new_state,
        path=DB_PATH,
    )

    # Also update in-memory cache for immediate effect
    context.bot_data[thread_key] = new_state

    if new_state:
        await update.message.reply_text(
            "🔊 Voice output <b>enabled</b> for this thread.\n"
            "CLI responses will include voice messages (except code-heavy ones).\n"
            "<i>Setting persisted — survives bot restart.</i>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            "🔇 Voice output <b>disabled</b> for this thread.\n"
            "Use /voice again to re-enable.\n"
            "<i>Setting persisted — survives bot restart.</i>",
            parse_mode=ParseMode.HTML,
        )
```

**Update `_is_voice_output_enabled()` to check SQLite on cache miss:**
```python
async def _is_voice_output_enabled(thread_id: int | None, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if voice output is enabled for this thread (cached + persisted)."""
    thread_key = f"thread:{thread_id}:voice_output"

    # Check in-memory cache first (fast path)
    cached = context.bot_data.get(thread_key)
    if cached is not None:
        return cached

    # Cache miss — resolve from SQLite
    resolved = await _resolve_voice_output(thread_id)
    context.bot_data[thread_key] = resolved
    return resolved


async def _resolve_voice_output(thread_id: int | None) -> bool:
    """Resolve voice output setting: SQLite → .env → False."""
    tid = thread_id if thread_id is not None else DEFAULT_THREAD_ID
    tc = await db.get_thread_config(tid, path=DB_PATH)
    if tc and hasattr(tc, "voice_output") and tc.voice_output is not None:
        return bool(tc.voice_output)
    return config.voice_output_enabled
```

**Note:** `_is_voice_output_enabled` becomes `async` — update all call sites in `_execute_and_reply_inner()` and `_stream_to_telegram()`.

#### Task 2: Schema Migration — `voice_output` Column

Add `voice_output` column to `thread_config` table. Use backward-compatible ALTER TABLE approach:

**Add to `db.py` `init_db()` function (after CREATE TABLE):**
```python
# v2.0 Growth: voice_output column (added in story 6.3)
# ALTER TABLE is idempotent-safe with try/except
try:
    await db.execute(
        "ALTER TABLE thread_config ADD COLUMN voice_output INTEGER DEFAULT NULL"
    )
    logger.info("[db] init_db: added voice_output column")
except Exception:
    pass  # Column already exists — expected on subsequent startups
```

**Update `ThreadConfig` dataclass:**
```python
@dataclass(frozen=True)
class ThreadConfig:
    """Immutable per-thread configuration."""

    thread_id: int
    project_dir: str
    cli_provider: str | None = None
    model: str | None = None
    timeout_seconds: int | None = None
    voice_output: int | None = None  # NULL=default, 1=enabled, 0=disabled
    last_active_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
```

**Update `_row_to_config()`:**
```python
def _row_to_config(row: aiosqlite.Row) -> ThreadConfig:
    """Convert SQLite Row to ThreadConfig dataclass."""
    return ThreadConfig(
        thread_id=row["thread_id"],
        project_dir=row["project_dir"],
        cli_provider=row["cli_provider"],
        model=row["model"],
        timeout_seconds=row["timeout_seconds"],
        voice_output=row["voice_output"] if "voice_output" in row.keys() else None,
        last_active_at=row["last_active_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
```

**Add new repository function:**
```python
async def upsert_voice_output(
    thread_id: int, *, voice_output: bool, path: str = DB_PATH
) -> None:
    """Set voice_output preference for a thread."""
    async with get_db(path) as db_conn:
        cursor = await db_conn.execute(
            "SELECT thread_id FROM thread_config WHERE thread_id = ?", (thread_id,)
        )
        exists = await cursor.fetchone() is not None

        if exists:
            await db_conn.execute(
                "UPDATE thread_config SET voice_output = ?, updated_at = datetime('now') WHERE thread_id = ?",
                (1 if voice_output else 0, thread_id),
            )
        else:
            # Need project_dir for insert — use env default
            await db_conn.execute(
                "INSERT INTO thread_config (thread_id, project_dir, voice_output) VALUES (?, ?, ?)",
                (thread_id, "", 1 if voice_output else 0),
            )
    logger.debug("[db] upsert_voice_output: thread_id=%d voice_output=%s", thread_id, voice_output)
```

#### Task 3: Extend `resolve_thread_config()` with `voice_output`

**Update `ResolvedConfig` dataclass:**
```python
@dataclass(frozen=True)
class ResolvedConfig:
    """Fully-resolved per-thread configuration."""

    thread_id: int
    project_dir: str
    cli_provider: str
    model: str | None
    timeout_seconds: int
    voice_output: bool  # NEW: resolved voice output preference
```

**Update `resolve_thread_config()` to include voice_output:**
```python
async def resolve_thread_config(
    thread_id: int,
    *,
    env_project_dir: str,
    env_cli_provider: str,
    env_model: str | None = None,
    env_timeout_seconds: int = 600,
    env_voice_output: bool = False,  # NEW
    path: str = DB_PATH,
) -> ResolvedConfig:
    # ... existing resolution logic ...

    if row:
        # ... existing fields ...
        voice_output = bool(row.voice_output) if row.voice_output is not None else env_voice_output
    else:
        # ... existing fields ...
        voice_output = env_voice_output

    return ResolvedConfig(
        # ... existing fields ...
        voice_output=voice_output,
    )
```

#### Task 4: Harden `is_code_heavy()` Edge Cases

The basic `is_code_heavy()` was introduced in story 6.2. This task hardens it for production:

**Edge cases to handle:**

1. **Inline code (single backticks)** — should NOT count as code blocks. Only triple-backtick fenced blocks count.
2. **Nested/escaped backticks** — ````code```` inside prose should not trigger false positives
3. **Empty code blocks** — ```` ``` ``` ```` with no content should count as 0 chars (not the delimiters themselves)
4. **Unclosed code blocks** — a single ``` without closing should not match
5. **Language specifier** — ````python` should still match as code block start

**Refined implementation:**
```python
_CODE_BLOCK_PATTERN = re.compile(
    r"```(?:[a-zA-Z]*\n)?[\s\S]*?```",
    re.MULTILINE,
)


def is_code_heavy(text: str, threshold: float = 0.5) -> bool:
    """Determine if text is code-heavy (>threshold ratio of code blocks).

    Only counts fenced code blocks (triple backtick). Inline code (`single`)
    is NOT counted. The ratio is calculated on the CONTENT inside code blocks
    (excluding the ``` delimiters themselves).

    Args:
        text: The response text to analyze (raw markdown, before HTML conversion)
        threshold: Ratio above which response is considered code-heavy (default 0.5)

    Returns:
        True if code block content characters exceed threshold of total characters.
    """
    if not text or len(text) < 6:  # Minimum: ```\n```
        return False

    total_chars = len(text)

    # Sum characters INSIDE code blocks (excluding delimiters)
    code_content_chars = 0
    for match in _CODE_BLOCK_PATTERN.finditer(text):
        block = match.group()
        # Strip opening ``` (with optional language) and closing ```
        lines = block.split("\n")
        # Remove first line (```lang) and last line (```)
        if len(lines) >= 2:
            inner_lines = lines[1:-1]  # Everything between opening and closing
            code_content_chars += sum(len(line) + 1 for line in inner_lines)  # +1 for newlines

    if total_chars == 0:
        return False

    return (code_content_chars / total_chars) > threshold
```

**Key change from 6.2:** Count only the CONTENT inside code blocks, not the ``` delimiters. This gives a more accurate ratio of "how much of this response is actual code."

#### Task 5: `/voice status` Subcommand

Extend `/voice` to accept an optional argument showing current configuration:

```python
@authorized
async def cmd_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /voice — toggle or show voice config for this thread."""
    if not config.voice_enabled:
        await update.message.reply_text(
            "🎤 Voice features not configured.\n"
            "Set OPENAI_API_KEY in .env to enable voice."
        )
        return

    thread_id = _get_thread_id(update)
    args = context.args  # e.g., ["status"] for "/voice status"

    if args and args[0].lower() == "status":
        await _voice_status(update, context, thread_id)
        return

    # Default: toggle (existing behavior from 6.2)
    # ... toggle logic ...


async def _voice_status(
    update: Update, context: ContextTypes.DEFAULT_TYPE, thread_id: int | None
) -> None:
    """Show voice configuration status for this thread."""
    voice_out = await _resolve_voice_output(thread_id)
    source = "per-thread (SQLite)" if await _has_thread_voice_override(thread_id) else "global default"

    lines = [
        "🎤 <b>Voice Configuration</b>\n",
        f"Voice features: {'✅ enabled' if config.voice_enabled else '❌ disabled'}",
        f"Whisper model: <code>{config.whisper_model}</code>",
        f"TTS model: <code>{config.tts_model}</code>",
        f"TTS voice: <code>{config.tts_voice}</code>",
        f"",
        f"<b>This thread:</b>",
        f"Voice output: {'🔊 on' if voice_out else '🔇 off'} ({source})",
        f"",
        f"<i>Use /voice to toggle, /voice status to see this.</i>",
    ]

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )


async def _has_thread_voice_override(thread_id: int | None) -> bool:
    """Check if this thread has an explicit voice_output override in SQLite."""
    tid = thread_id if thread_id is not None else DEFAULT_THREAD_ID
    tc = await db.get_thread_config(tid, path=DB_PATH)
    return tc is not None and hasattr(tc, "voice_output") and tc.voice_output is not None
```

#### Task 6: Graceful No-Op When `openai` Not Installed

The `voice.py` module imports `openai`. If the package isn't installed (user hasn't run `pip install openai`), the bot should still start without crashing.

**In `chati.py` module-level initialization:**
```python
# Voice services (Growth phase — graceful no-op if openai not installed)
voice_transcriber = None
voice_synthesizer = None

if config.voice_enabled:
    try:
        from voice import VoiceTranscriber, VoiceSynthesizer
        voice_transcriber = VoiceTranscriber(
            api_key=config.openai_api_key,
            model=config.whisper_model,
            timeout=config.whisper_timeout,
        )
        voice_synthesizer = VoiceSynthesizer(
            api_key=config.openai_api_key,
            model=config.tts_model,
            voice=config.tts_voice,
            timeout=config.tts_timeout,
        )
        logger.info("[Voice] services initialized (whisper=%s, tts=%s)", config.whisper_model, config.tts_model)
    except ImportError:
        logger.warning("[Voice] openai package not installed — voice features disabled")
        # voice_transcriber and voice_synthesizer remain None
    except Exception as exc:
        logger.error("[Voice] failed to initialize: %s", exc)
```

**In `voice.py` top-level:**
```python
try:
    from openai import AsyncOpenAI
except ImportError:
    raise ImportError(
        "openai package required for voice features. "
        "Install with: pip install openai>=1.0.0"
    )
```

This way:
- If `openai` is not installed and `OPENAI_API_KEY` is not set → `config.voice_enabled = False` → no import attempted → bot starts fine
- If `openai` is not installed but `OPENAI_API_KEY` IS set → `config.voice_enabled = True` → import fails → caught in `chati.py` → warning logged → voice disabled at runtime

#### Task 7: Update `/help` and `/info`

**Update `/help` command to include `/voice`:**
Add to the command list in `cmd_help()`:
```
/voice — Toggle voice output for this thread (or /voice status)
```

**Update `/info` command to show voice state:**
Add a line to the `/info` output when voice is enabled:
```python
if config.voice_enabled:
    voice_out = await _resolve_voice_output(thread_id)
    info_lines.append(f"🎤 Voice output: {'on' if voice_out else 'off'}")
```

#### Task 8: Tests

**Test file: `tests/test_voice_configuration.py`**

Test cases for persistence:

1. `/voice` toggle writes to SQLite — verify `voice_output` column updated
2. Bot restart loads voice preference from SQLite — verify in-memory cache populated
3. Per-thread override in SQLite takes precedence over global .env default
4. Thread with NULL voice_output falls back to global config
5. New thread (no SQLite row) falls back to global config

Test cases for `is_code_heavy()` hardening:

6. Inline code (`single backtick`) NOT counted as code block
7. Empty code block (``` followed by ```) → 0 code chars
8. Code block with language specifier (```python) → correctly matched
9. Unclosed code block (single ```) → not matched (no false positive)
10. Multiple code blocks → all counted correctly
11. Code block content only (excluding delimiters) counted in ratio
12. Very short text (<6 chars) → returns False
13. 100% code block → returns True
14. Text with only inline code → returns False

Test cases for graceful degradation:

15. `openai` not installed + `OPENAI_API_KEY` set → warning logged, voice disabled
16. `openai` not installed + `OPENAI_API_KEY` not set → no warning, voice disabled
17. Voice handler called when voice disabled → "not configured" message
18. `/voice status` shows correct config even when voice disabled

Test cases for `/voice status`:

19. Shows global config values (model, voice, enabled state)
20. Shows per-thread override source when set
21. Shows "global default" source when no override

Test cases for schema migration:

22. `init_db()` on fresh database → `voice_output` column exists
23. `init_db()` on existing database without column → column added
24. `init_db()` on existing database with column → no error (idempotent)

### File Structure

| File | Action | Description |
|------|--------|-------------|
| `db.py` | UPDATE | Add `voice_output` column migration, `upsert_voice_output()`, update `ThreadConfig` + `ResolvedConfig` + `_row_to_config()` |
| `chati.py` | UPDATE | Persist `/voice` to SQLite, add `/voice status`, make `_is_voice_output_enabled` async, update `/help` + `/info`, graceful import |
| `voice.py` | UPDATE | Add explicit ImportError for missing `openai` package |
| `message_utils.py` | UPDATE | Harden `is_code_heavy()` — count content only, handle edge cases |
| `config.py` | NO CHANGE | All voice config fields already added in stories 6.1 + 6.2 |
| `tests/test_voice_configuration.py` | NEW | Comprehensive tests for persistence, code detection, graceful degradation |

### Technical Requirements

- **Python 3.12+** — modern syntax, type hints throughout
- **aiosqlite** — schema migration (ALTER TABLE ADD COLUMN)
- **No new dependencies** — this story only hardens existing code
- **Backward-compatible schema** — ALTER TABLE with try/except for idempotency
- **Async patterns** — `_is_voice_output_enabled` becomes async (SQLite lookup on cache miss)
- **Error handling** — ImportError caught gracefully, schema migration idempotent
- **Type hints** — all function signatures fully typed
- **Docstrings** — one-line summary minimum for all public functions

### Architecture Compliance

- `db.py` owns persistence (voice_output column + upsert function) ✓
- 3-layer config resolution maintained (SQLite → .env → default) ✓
- Graceful degradation when `openai` not installed ✓
- Feature flag pattern preserved (`config.voice_enabled`) ✓
- No new dependencies ✓
- Flat root structure maintained ✓
- Schema migration is idempotent (safe to run on every startup) ✓

### Testing Requirements

- **Framework:** pytest + pytest-asyncio (existing infrastructure)
- **Coverage:** ≥80% branch coverage for new code
- **Fixtures needed:**
  - `in_memory_db` (existing) — for SQLite persistence tests
  - `tmp_path` — for isolated DB files
  - Existing `telegram_update_factory` from conftest
- **Test file:** `tests/test_voice_configuration.py`
- **Run command:** `python -m pytest tests/test_voice_configuration.py -v`

### Previous Story Intelligence

**From Story 6.2 (voice output — direct predecessor):**

- `VoiceSynthesizer` class exists in `voice.py`
- `is_code_heavy()` exists in `message_utils.py` (basic version — this story hardens it)
- `/voice` command exists but stores state in-memory only (this story persists to SQLite)
- `_is_voice_output_enabled()` is sync and checks `context.bot_data` only — this story makes it async with SQLite fallback
- `voice_output_enabled` config field exists in `config.py`
- `_strip_html_for_tts()` helper exists in `chati.py`

**From Story 6.1 (voice input):**

- `voice.py` module exists with `VoiceTranscriber`
- `openai>=1.0.0` in `requirements.txt`
- `config.voice_enabled` auto-detects from `OPENAI_API_KEY` presence
- Conditional import pattern: `if config.voice_enabled: from voice import ...`

**From Story 1.5 (configuration resolution chain):**

- 3-layer fallback pattern: thread SQLite → .env → hardcoded default
- `resolve_thread_config()` function in `db.py` — extend with `voice_output`
- `ResolvedConfig` dataclass — add `voice_output: bool` field

**From Story 1.1 (SQLite database layer):**

- Schema migration pattern: `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE` with try/except
- `init_db()` is idempotent — called on every startup
- `_row_to_config()` maps SQLite rows to dataclass — must handle new column gracefully on old DBs

### Git Intelligence

- Branch: `v2.0`
- Pattern: atomic commits per story
- This story completes Epic 6 — commit message should note epic completion

### Potential Pitfalls & Guardrails

1. **Schema migration on existing DBs** — `ALTER TABLE ADD COLUMN` will fail if column already exists. Wrap in try/except (SQLite doesn't support `IF NOT EXISTS` for columns).
2. **`_row_to_config()` backward compat** — Old databases won't have `voice_output` column. Use `row.keys()` check or try/except when accessing the field.
3. **Async conversion of `_is_voice_output_enabled`** — This function is called in `_execute_and_reply_inner()` and `_stream_to_telegram()`. Both are already async, so adding `await` is safe. But verify all call sites are updated.
4. **Cache invalidation** — When `/voice` persists to SQLite, also update `context.bot_data` cache. On bot restart, cache starts empty and is populated on first access (lazy loading).
5. **`upsert_voice_output` for new threads** — If thread has no row in `thread_config`, we need to INSERT. But `project_dir` is NOT NULL. Use empty string or resolve from .env default. Better: only UPDATE if row exists, skip if not (voice toggle only meaningful for threads that have been used).
6. **`is_code_heavy` regression** — Changing the counting logic (content-only vs full match) changes the threshold behavior. Ensure tests cover the boundary (exactly 50%) with both old and new counting.
7. **Import order in tests** — Tests that mock `openai` import must use `unittest.mock.patch` on the import path, not the module itself.
8. **`/voice status` when voice disabled** — Should still show config values (what WOULD be used if enabled), not just "disabled".

### Project Context Reference

- **Project:** Chati v2.0 — Telegram bot that proxies AI coding CLIs
- **Tech stack:** Python 3.12+, python-telegram-bot 21.10, aiosqlite, openai, asyncio
- **Architecture:** Flat module structure, async-first, graceful degradation on all external APIs
- **Testing:** pytest + pytest-asyncio, TDD approach, tests in `tests/` directory
- **Deployment:** Single-process, systemd, single-machine
- **This story completes Epic 6** — all voice features (input, output, config) are production-ready after this

---

*Ultimate context engine analysis completed — comprehensive developer guide created*

---

## Dev Agent Record

### Implementation Plan

- Tasks 1–3 were partially pre-implemented in prior sessions (db.py had `voice_output` column, `upsert_voice_output`, and `ThreadConfig.voice_output`). This session completed the remaining work.
- Task 1: Updated `cmd_voice` in `chati.py` to call `db.upsert_voice_output()` on toggle, persisting state to SQLite. Also updated in-memory cache for immediate effect.
- Task 3: Extended `ResolvedConfig` dataclass with `voice_output: bool` field and updated `resolve_thread_config()` to accept `env_voice_output` parameter and resolve from SQLite → env → False.
- Task 4: `is_code_heavy()` was already hardened in `message_utils.py` (content-only ratio, inline code excluded, language specifiers handled).
- Task 5: Added `_voice_status()` helper and `/voice status` subcommand to `cmd_voice`. Shows whisper model, TTS model, TTS voice, and per-thread override source.
- Task 6: Graceful import handling was already in place in `chati.py` (try/except ImportError around voice module import).
- Task 7: `/help` already listed `/voice`. `/info` already appended voice state. Both updated to use `await _is_voice_output_enabled()` (now async).
- Task 8: Converted `_is_voice_output_enabled` to async with SQLite fallback. Added `_resolve_voice_output()` and `_has_thread_voice_override()` helpers. Updated all call sites to `await`. Unskipped all 8 previously-skipped tests and added 7 new tests (persistence, resolve chain, toggle persistence). Fixed 2 regressions in `test_voice_output.py` (sync → async call sites).

### Completion Notes

- All 8 tasks complete. 339 tests pass, 0 failures.
- `_is_voice_output_enabled` is now async — resolves from in-memory cache first, then SQLite, then global config.
- `/voice` toggle persists to SQLite and updates in-memory cache atomically.
- `/voice status` shows full voice config including per-thread override source.
- `ResolvedConfig.voice_output` field added to 3-layer resolution chain.
- All previously-skipped tests in `test_voice_configuration.py` now pass (33 total).
- Epic 6 is complete — all voice features (input, output, configuration) are production-ready.

## File List

- `chati.py` — Updated: `_is_voice_output_enabled` made async with SQLite fallback; added `_resolve_voice_output()` and `_has_thread_voice_override()` helpers; `cmd_voice` persists to SQLite and adds `/voice status` subcommand; `_voice_status()` helper added; all call sites updated to `await`
- `db.py` — Updated: `ResolvedConfig` dataclass gains `voice_output: bool` field; `resolve_thread_config()` gains `env_voice_output` parameter and resolves voice_output in 3-layer chain
- `tests/test_voice_configuration.py` — Updated: removed all `@pytest.mark.skip` decorators; added 7 new tests for persistence, resolve chain, and toggle; 33 tests total
- `tests/test_voice_output.py` — Updated: fixed 2 tests calling `_is_voice_output_enabled` without `await`

## Change Log

- 2026-05-08: Story 6.3 implemented — voice configuration hardening complete. Persisted /voice toggle to SQLite, added /voice status subcommand, made _is_voice_output_enabled async with SQLite fallback, extended ResolvedConfig with voice_output field, unskipped and expanded test suite (33 tests). Epic 6 complete.
