# Story 6.1: Voice Input — Whisper Transcription & Confirmation

Status: ready-for-dev

## Story

As a **user**,
I want to send voice messages that get transcribed and confirmed before forwarding to CLI,
So that I can code hands-free with confidence the transcription is correct.

## Acceptance Criteria (BDD)

**Given** user sends a voice message in Telegram
**When** the bot receives the audio
**Then** the audio is sent to Whisper API for transcription
**And** response time is <3 seconds for 5-15s audio clips

**Given** transcription is received from Whisper
**When** the result is ready
**Then** an inline keyboard is shown: "✅ Send / ✏️ Edit / 🗑️ Cancel" with the transcribed text

**Given** user taps "✅ Send"
**When** the confirmation is received
**Then** the transcribed text is forwarded to CLI as if user typed it

**Given** user taps "✏️ Edit"
**When** the edit option is selected
**Then** user can type a corrected version which replaces the transcription

**Given** user taps "🗑️ Cancel"
**When** the cancel is selected
**Then** the transcription is discarded and no message is sent to CLI

**Given** Whisper API is unavailable or times out (>10s)
**When** the transcription fails
**Then** user is notified: "⚠️ Voice transcription temporarily unavailable. Please type your message."

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

## Tasks / Subtasks

- [ ] Task 1: Add `openai` dependency and voice config to `config.py` + `.env.example`
- [ ] Task 2: Create `voice.py` module with `transcribe_voice()` function
- [ ] Task 3: Add `handle_voice_message()` handler in `chati.py`
- [ ] Task 4: Add `handle_voice_callback()` for confirm/edit/cancel inline keyboard
- [ ] Task 5: Handle "edit mode" — next text message replaces transcription
- [ ] Task 6: Register handlers in `main()` and wire up filters
- [ ] Task 7: Write tests in `tests/test_voice_input.py`

## Dev Notes

### Epic 6 Context

This is story 6.1 (first of 3) of Epic 6 "Voice Communication (Growth)":
- **6.1 (this)**: Voice input — Whisper transcription + confirm-first UX
- **6.2 (next)**: Voice output — TTS response synthesis
- **6.3 (last)**: Voice configuration & code detection

**FRs covered:** FR33 (voice message transcription via speech-to-text API), FR34 (transcription confirmation UX: confirm/edit/cancel)

**NFRs:** NFR20 (voice transcription <3 seconds for 5-15s clips)

### Architecture Requirements

**Module ownership per architecture:**
- `chati.py` — owns Telegram handlers (voice message handler, callback handler)
- `voice.py` — NEW module for voice-specific logic (transcription, future TTS)
- Architecture says: "Whisper API (Growth) | `chati.py` (inline) | HTTPS REST"

**Key architectural decisions:**
- Architecture deferred voice API provider selection to Growth phase — we're now in Growth
- Use OpenAI Whisper API (cloud) — not local whisper model (too heavy for single-machine deploy)
- Voice is a NEW module — justified because it introduces external API integration distinct from CLI subprocess management
- Keep it simple: no plugin system, direct OpenAI client usage

**New dependency required:** `openai` Python package (for Whisper API access)
- This is the ONE exception to the "no new deps" rule — architecture explicitly planned for external API integration in Growth phase
- Use `openai>=1.0.0` (the new client-based API, not the legacy `openai.Audio.transcribe()`)

### Implementation Guide

#### Task 1: Config & Dependencies

**Add to `requirements.txt`:**
```
# Voice transcription (v2.0 Growth)
openai>=1.0.0
```

**Add to `config.py` Config dataclass:**
```python
# v2.0 Growth: Voice features
openai_api_key: str = ""  # Required for voice features
voice_enabled: bool = False  # Feature flag — graceful no-op when disabled
whisper_model: str = "gpt-4o-mini-transcribe"  # OpenAI transcription model
whisper_timeout: int = 10  # seconds before giving up on transcription
```

**Add to `Config.from_env()`:**
```python
openai_api_key = os.getenv("OPENAI_API_KEY", "")
voice_enabled = openai_api_key != ""  # Auto-enable if key is configured
whisper_model = os.getenv("WHISPER_MODEL", "gpt-4o-mini-transcribe")
whisper_timeout = int(os.getenv("WHISPER_TIMEOUT", "10"))
```

**Add to `.env.example`:**
```bash
# ── Voice Features (Growth) ──────────────────────────────────────
# OPENAI_API_KEY=your-openai-key          # Required for voice transcription
# WHISPER_MODEL=gpt-4o-mini-transcribe    # or gpt-4o-transcribe for higher quality
# WHISPER_TIMEOUT=10                       # seconds before transcription timeout
```

#### Task 2: Create `voice.py` Module

**NEW file at project root: `voice.py`**

This module encapsulates all voice-related logic (transcription now, TTS in story 6.2).

```python
"""Voice features for Chati v2.0 (Growth phase).

Handles:
- Voice message transcription via OpenAI Whisper API
- (Future: TTS response synthesis in story 6.2)
"""

import asyncio
import logging
import tempfile
from pathlib import Path

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class VoiceTranscriber:
    """Async wrapper for OpenAI Whisper transcription."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini-transcribe", timeout: int = 10):
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout)
        self._model = model
        self._timeout = timeout

    async def transcribe(self, audio_path: str | Path) -> str | None:
        """Transcribe an audio file using OpenAI Whisper API.

        Args:
            audio_path: Path to the audio file (OGG, MP3, etc.)

        Returns:
            Transcribed text string, or None on failure.
        """
        try:
            with open(audio_path, "rb") as audio_file:
                response = await asyncio.wait_for(
                    self._client.audio.transcriptions.create(
                        model=self._model,
                        file=audio_file,
                        response_format="text",
                    ),
                    timeout=self._timeout,
                )
            # response is a string when response_format="text"
            text = response.strip() if isinstance(response, str) else response.text.strip()
            logger.info("[Voice] transcription complete: %d chars", len(text))
            return text if text else None
        except asyncio.TimeoutError:
            logger.warning("[Voice] transcription timed out after %ds", self._timeout)
            return None
        except Exception as exc:
            logger.error("[Voice] transcription failed: %s", exc)
            return None
```

**Key design decisions:**
- Use `AsyncOpenAI` — matches project's async-first pattern
- `asyncio.wait_for()` wraps the API call with configurable timeout
- Returns `None` on any failure — caller handles graceful degradation
- Accepts file path (not bytes) — Telegram downloads to temp file first

#### Task 3: `handle_voice_message()` in `chati.py`

**Voice message flow:**
1. User sends voice message → Telegram delivers `update.message.voice`
2. Bot downloads the voice file to a temp directory
3. Bot sends file to Whisper API for transcription
4. On success: show inline keyboard with transcription text
5. On failure: send error message

```python
@authorized
async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice messages — transcribe via Whisper and show confirmation."""
    if not config.voice_enabled:
        await update.message.reply_text(
            "🎤 Voice features not configured. Please type your message.\n"
            "Set OPENAI_API_KEY in .env to enable voice input."
        )
        return

    await update.message.reply_chat_action(ChatAction.TYPING)

    # Download voice file from Telegram
    voice = update.message.voice
    voice_file = await context.bot.get_file(voice.file_id)

    # Save to temp file (Telegram voice messages are OGG format)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
        await voice_file.download_to_drive(tmp_path)

    try:
        # Transcribe
        text = await voice_transcriber.transcribe(tmp_path)

        if not text:
            await update.message.reply_text(
                "⚠️ Voice transcription temporarily unavailable. Please type your message."
            )
            return

        # Store transcription for callback handling
        thread_id = _get_thread_id(update)
        context.bot_data[f"thread:{thread_id}:voice_transcription"] = text

        # Show confirmation with inline keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Send", callback_data=f"voice:send:{thread_id}"),
                InlineKeyboardButton("✏️ Edit", callback_data=f"voice:edit:{thread_id}"),
                InlineKeyboardButton("🗑️ Cancel", callback_data=f"voice:cancel:{thread_id}"),
            ]
        ])

        await update.message.reply_text(
            f"🎤 <b>Transcription:</b>\n\n<i>{_escape_html(text)}</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
    finally:
        # Clean up temp file
        import os
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
```

**CRITICAL:** The `voice_transcriber` instance must be created at module level (alongside `runner`):
```python
# After config = Config.from_env() and runner = CliRunner(config)
voice_transcriber = None
if config.voice_enabled:
    from voice import VoiceTranscriber
    voice_transcriber = VoiceTranscriber(
        api_key=config.openai_api_key,
        model=config.whisper_model,
        timeout=config.whisper_timeout,
    )
```

#### Task 4: `handle_voice_callback()` for Inline Keyboard

```python
async def handle_voice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice transcription confirmation callbacks (send/edit/cancel)."""
    query = update.callback_query
    await query.answer()

    # Parse callback_data: "voice:{action}:{thread_id}"
    parts = query.data.split(":")
    if len(parts) != 3:
        return
    _, action, thread_id_str = parts
    thread_id = int(thread_id_str) if thread_id_str != "None" else None

    transcription_key = f"thread:{thread_id}:voice_transcription"
    text = context.bot_data.get(transcription_key)

    if action == "send":
        # Clear stored transcription
        context.bot_data.pop(transcription_key, None)
        # Remove inline keyboard
        await query.edit_message_reply_markup(reply_markup=None)
        await query.edit_message_text(
            f"🎤 ✅ <i>{_escape_html(text)}</i>",
            parse_mode=ParseMode.HTML,
        )
        # Forward to CLI as if user typed it
        # Create a synthetic "update" context and call execute
        await _execute_and_reply(update, context, text)

    elif action == "edit":
        # Set edit mode — next text message replaces transcription
        context.bot_data[f"thread:{thread_id}:voice_edit_mode"] = True
        await query.edit_message_reply_markup(reply_markup=None)
        await query.edit_message_text(
            f"🎤 ✏️ Original: <i>{_escape_html(text)}</i>\n\n"
            "Type your corrected message:",
            parse_mode=ParseMode.HTML,
        )

    elif action == "cancel":
        # Discard transcription
        context.bot_data.pop(transcription_key, None)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.edit_message_text("🎤 🗑️ Voice message cancelled.")
```

#### Task 5: Edit Mode Handling

In `handle_message()`, add a check BEFORE the pending_decision check:

```python
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle free-form text messages."""
    text = update.message.text
    if not text or not text.strip():
        return

    thread_id = _get_thread_id(update)

    # Voice edit mode — user is typing corrected transcription
    edit_key = f"thread:{thread_id}:voice_edit_mode"
    if context.bot_data.get(edit_key):
        context.bot_data.pop(edit_key, None)
        context.bot_data.pop(f"thread:{thread_id}:voice_transcription", None)
        # Forward the corrected text to CLI
        await _execute_and_reply(update, context, text.strip())
        return

    # If a decision is pending, treat this message as the reply
    pending_key = f"thread:{thread_id}:pending_decision"
    if context.bot_data.get(pending_key):
        # ... existing decision reply logic
```

#### Task 6: Handler Registration in `main()`

Add these handlers in `main()` BEFORE the free-form text handler:

```python
# Voice message handler
app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))

# Voice confirmation callback
app.add_handler(CallbackQueryHandler(handle_voice_callback, pattern=r"^voice:"))
```

**Handler order matters!** The voice handler uses `filters.VOICE` which is distinct from `filters.TEXT`, so there's no conflict. But the callback handler must be registered alongside other `CallbackQueryHandler`s.

#### Task 7: Tests

**Test file: `tests/test_voice_input.py`**

Test cases:
1. **Voice disabled** — `config.voice_enabled = False` → sends "not configured" message
2. **Transcription success** — mock Whisper returns text → inline keyboard shown with transcription
3. **Transcription failure** — mock Whisper returns None → error message sent
4. **Transcription timeout** — mock Whisper times out → error message sent
5. **Callback: Send** — user taps ✅ → transcription forwarded to `_execute_and_reply`
6. **Callback: Edit** — user taps ✏️ → edit mode set, next text message forwarded
7. **Callback: Cancel** — user taps 🗑️ → transcription discarded, keyboard removed
8. **Edit mode flow** — after ✏️, user types corrected text → forwarded to CLI
9. **File download** — verify voice file is downloaded and cleaned up
10. **Temp file cleanup** — verify temp file deleted even on error

**Mocking strategy:**
- Mock `VoiceTranscriber.transcribe()` — don't call real OpenAI API in tests
- Mock `context.bot.get_file()` and `voice_file.download_to_drive()` — don't download real files
- Use existing `telegram_update_factory` fixture for creating fake updates
- Mock `update.message.voice` with a fake `Voice` object containing `file_id`

### File Structure

| File | Action | Description |
|------|--------|-------------|
| `voice.py` | NEW | VoiceTranscriber class wrapping OpenAI Whisper API |
| `chati.py` | UPDATE | Add `handle_voice_message()`, `handle_voice_callback()`, edit mode in `handle_message()`, register handlers |
| `config.py` | UPDATE | Add `openai_api_key`, `voice_enabled`, `whisper_model`, `whisper_timeout` fields |
| `.env.example` | UPDATE | Add voice config section |
| `requirements.txt` | UPDATE | Add `openai>=1.0.0` |
| `tests/test_voice_input.py` | NEW | Comprehensive tests for voice input flow |

### Technical Requirements

- **Python 3.12+** — use modern syntax (type hints, walrus operator OK)
- **New dependency:** `openai>=1.0.0` (AsyncOpenAI client for Whisper API)
- **python-telegram-bot 21.10** — use `filters.VOICE`, `get_file()`, `download_to_drive()`
- **Async patterns** — all handlers are `async def`, use `AsyncOpenAI` client
- **Error handling** — Whisper API failures → graceful degradation (text fallback message)
- **Type hints** — all function signatures fully typed
- **Docstrings** — one-line summary minimum for all public functions
- **Feature flag** — `voice_enabled` auto-detects from OPENAI_API_KEY presence

### Architecture Compliance

- `voice.py` is a NEW module — justified by architecture's "new modules only when existing file would exceed ~500 lines or mix concerns" rule. Voice transcription is a distinct concern from CLI subprocess management ✓
- `chati.py` owns Telegram handlers and orchestration ✓
- Graceful degradation when API unavailable ✓
- Feature flag pattern (no-op when not configured) ✓
- Follows naming conventions (snake_case functions, PascalCase classes) ✓
- Flat root structure maintained (no nested packages) ✓
- `@authorized` decorator on voice handler ✓

### Testing Requirements

- **Framework:** pytest + pytest-asyncio (existing infrastructure)
- **Coverage:** ≥80% branch coverage for new code
- **Fixtures needed:**
  - Mock `VoiceTranscriber` (don't call real API)
  - Mock Telegram `Voice` object and file download
  - Existing `telegram_update_factory` from conftest
- **Test file:** `tests/test_voice_input.py`
- **Run command:** `python -m pytest tests/test_voice_input.py -v`

### Previous Story Intelligence

**From Story 5.1 (screenshot forwarding, just created):**
- Same integration pattern: post-processing in `_execute_and_reply_inner()` and `_stream_to_telegram()`
- Same graceful degradation approach: log error, continue with text
- Same feature flag pattern: auto-enable based on config presence

**From Epic 4 (most recent implemented work):**
- Inline keyboard pattern already established in `/model` and `/projects` commands
- `CallbackQueryHandler` with pattern matching already used
- `context.bot_data[f"thread:{thread_id}:..."]` pattern for per-thread state

**From Epic 3 (decision forwarding):**
- "Next message intercept" pattern already proven with `pending_decision`
- Same pattern reused for voice edit mode: set flag → next message is intercepted → flag cleared
- Order of checks in `handle_message()` matters: voice_edit → pending_decision → normal execute

### Git Intelligence

- Branch: `v2.0` (all v2 work happens here)
- Pattern: atomic commits per story
- New module `voice.py` follows same pattern as `session_manager.py` and `db.py` additions

### Potential Pitfalls & Guardrails

1. **Temp file leak** — Always use `try/finally` to clean up downloaded voice files
2. **OGG format** — Telegram voice messages are OGG Opus; OpenAI Whisper accepts OGG natively (no conversion needed)
3. **File size** — Telegram voice messages are typically small (<1MB for 15s); OpenAI limit is 25MB — no issue
4. **Callback data length** — Telegram limits callback_data to 64 bytes; `voice:send:12345` is well within limit
5. **Race condition** — User could send another voice message while confirmation is pending; store transcription per-thread to avoid conflicts
6. **Edit mode timeout** — If user taps ✏️ but never types, the edit_mode flag persists; consider clearing on next voice message or after timeout (acceptable for v1 of this feature)
7. **Callback from wrong user** — The `@authorized` decorator is on the message handler but callbacks need separate auth check; verify `query.from_user.id` is in allowed_user_ids
8. **Import order** — `voice.py` import should be conditional on `config.voice_enabled` to avoid import errors when `openai` package isn't installed
9. **API key security** — Never log the API key; only reference by name in error messages

### OpenAI Whisper API Reference (Latest)

**Endpoint:** `POST https://api.openai.com/v1/audio/transcriptions`

**Models available (as of 2026):**
- `gpt-4o-mini-transcribe` — fast, cost-effective (recommended default)
- `gpt-4o-transcribe` — higher quality, slightly slower
- `whisper-1` — legacy model, still supported

**Python SDK usage (openai>=1.0.0):**
```python
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key="...")
with open("audio.ogg", "rb") as f:
    result = await client.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=f,
        response_format="text",  # Returns plain string
    )
# result is the transcribed text string
```

**Supported input formats:** mp3, mp4, mpeg, mpga, m4a, wav, webm, ogg
**Max file size:** 25MB
**Pricing:** ~$0.006/minute of audio

Content was rephrased for compliance with licensing restrictions. Source: [OpenAI Speech-to-Text docs](https://developers.openai.com/api/docs/guides/speech-to-text/)

### Project Context Reference

- **Project:** Chati v2.0 — Telegram bot that proxies AI coding CLIs
- **Tech stack:** Python 3.12+, python-telegram-bot 21.10, aiosqlite, asyncio
- **Architecture:** Flat module structure, async-first, graceful degradation on all external APIs
- **Testing:** pytest + pytest-asyncio, TDD approach, tests in `tests/` directory
- **Deployment:** Single-process, systemd, single-machine
- **This is a Growth phase feature** — MVP is stable, this adds ambient coding capability

---

*Ultimate context engine analysis completed — comprehensive developer guide created*
