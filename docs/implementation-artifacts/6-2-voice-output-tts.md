# Story 6.2: Voice Output — TTS Response Synthesis

Status: ready-for-dev

## Story

As a **user**,
I want CLI responses to optionally come back as voice messages,
So that I can listen to results while walking or commuting.

## Acceptance Criteria (BDD)

**Given** a CLI response is ready and voice output is enabled for the thread
**When** the response contains <50% code blocks
**Then** the text is synthesized via TTS API and sent as a Telegram voice message (OGG opus)
**And** the text version is ALSO sent (voice is additive, not replacement)

**Given** a CLI response contains >50% code blocks
**When** voice output would normally trigger
**Then** TTS is skipped and only text response is sent (code is unlistenable)

**Given** TTS API is unavailable or times out (>10s)
**When** synthesis fails
**Then** only text response is sent with note: "🔇 Voice temporarily unavailable"
**And** no retry is attempted

**Given** TTS synthesis succeeds
**When** the voice message is sent
**Then** response time is <4 seconds for typical text responses

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

## Tasks / Subtasks

- [ ] Task 1: Add TTS config to `config.py` and `.env.example`
- [ ] Task 2: Add `VoiceSynthesizer` class to `voice.py` with `synthesize()` method
- [ ] Task 3: Add `is_code_heavy()` helper to `message_utils.py`
- [ ] Task 4: Integrate TTS into `_execute_and_reply_inner()` and `_stream_to_telegram()`
- [ ] Task 5: Add per-thread voice output toggle via `/voice` command
- [ ] Task 6: Write tests in `tests/test_voice_output.py`

## Dev Notes

### Epic 6 Context

This is story 6.2 (second of 3) of Epic 6 "Voice Communication (Growth)":

- **6.1 (previous)**: Voice input — Whisper transcription + confirm-first UX
- **6.2 (this)**: Voice output — TTS response synthesis
- **6.3 (next)**: Voice configuration & code detection (refinements)

**FRs covered:** FR35 (synthesize text responses into voice messages, OGG opus), FR36 (detect code-heavy responses >50% and skip TTS), FR37 (send text version alongside voice for accessibility)

**NFRs:** NFR21 (voice synthesis <4 seconds for typical responses)

**Dependency:** This story depends on story 6.1 being implemented first (shared `voice.py` module, `openai` dependency, `config.voice_enabled` flag).

### Architecture Requirements

**Module ownership per architecture:**

- `voice.py` — owns TTS synthesis logic (extends module created in 6.1)
- `message_utils.py` — owns `is_code_heavy()` (pure text analysis function)
- `chati.py` — owns Telegram voice message sending and orchestration

**Architecture reference (from Media & Output Architecture):**
```python
# In output processing, after stream completes:
if screenshot_path := detect_screenshot(output):
    await send_photo_or_document(chat_id, screenshot_path)
elif voice_enabled(thread_config) and not is_code_heavy(response):
    voice_msg = await synthesize_voice(response)
    await send_voice(chat_id, voice_msg)
# Always send text response (voice is additive, not replacement)
await send_text_response(chat_id, formatted_response)
```

**Key design principle:** Voice is ADDITIVE — text response is ALWAYS sent. Voice message is sent IN ADDITION to text, not as a replacement. This ensures accessibility and provides a reference the user can copy/paste.

### Implementation Guide

#### Task 1: TTS Config

**Add to `config.py` Config dataclass (after whisper fields from 6.1):**
```python
# v2.0 Growth: TTS (voice output)
tts_model: str = "gpt-4o-mini-tts"  # OpenAI TTS model
tts_voice: str = "coral"  # Default voice (alloy, ash, coral, echo, fable, nova, onyx, sage, shimmer)
tts_timeout: int = 10  # seconds before giving up on synthesis
voice_output_enabled: bool = False  # Per-user default (can be toggled per-thread)
```

**Add to `Config.from_env()`:**
```python
tts_model = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
tts_voice = os.getenv("TTS_VOICE", "coral")
tts_timeout = int(os.getenv("TTS_TIMEOUT", "10"))
voice_output_enabled = os.getenv("VOICE_OUTPUT_ENABLED", "false").lower() == "true"
```

**Add to `.env.example`:**
```bash
# TTS_MODEL=gpt-4o-mini-tts              # OpenAI TTS model
# TTS_VOICE=coral                         # Voice: alloy, ash, coral, echo, fable, nova, onyx, sage, shimmer
# TTS_TIMEOUT=10                          # seconds before TTS timeout
# VOICE_OUTPUT_ENABLED=false              # Enable voice responses globally (user can toggle per-thread)
```

**Add to SQLite `thread_config` table (schema migration in `db.py`):**
```sql
ALTER TABLE thread_config ADD COLUMN voice_output INTEGER DEFAULT NULL;
-- NULL = use global default, 1 = enabled, 0 = disabled
```

#### Task 2: `VoiceSynthesizer` Class in `voice.py`

Extend the existing `voice.py` module (created in story 6.1) with a TTS class:

```python
class VoiceSynthesizer:
    """Async wrapper for OpenAI TTS synthesis."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini-tts",
        voice: str = "coral",
        timeout: int = 10,
    ):
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout)
        self._model = model
        self._voice = voice
        self._timeout = timeout

    async def synthesize(self, text: str) -> bytes | None:
        """Synthesize text to OGG Opus audio bytes.

        Args:
            text: Text to synthesize (will be truncated to 4096 chars for TTS)

        Returns:
            OGG Opus audio bytes ready for Telegram sendVoice, or None on failure.
        """
        # TTS has input limits — truncate gracefully
        if len(text) > 4096:
            text = text[:4093] + "..."

        try:
            response = await asyncio.wait_for(
                self._client.audio.speech.create(
                    model=self._model,
                    voice=self._voice,
                    input=text,
                    response_format="opus",  # OGG Opus — required by Telegram voice messages
                ),
                timeout=self._timeout,
            )
            # response.content is bytes
            audio_bytes = response.content
            logger.info("[Voice] TTS synthesis complete: %d bytes", len(audio_bytes))
            return audio_bytes if audio_bytes else None
        except asyncio.TimeoutError:
            logger.warning("[Voice] TTS synthesis timed out after %ds", self._timeout)
            return None
        except Exception as exc:
            logger.error("[Voice] TTS synthesis failed: %s", exc)
            return None
```

**Key design decisions:**

- Output format is `opus` — this produces OGG Opus which Telegram requires for voice messages
- Returns raw bytes — caller wraps in `InputFile` for Telegram API
- Truncates to 4096 chars — TTS models have input limits; long responses get text-only
- Same `AsyncOpenAI` client pattern as `VoiceTranscriber` (reuse same client instance)
- Returns `None` on any failure — graceful degradation

**Shared client optimization:** Both `VoiceTranscriber` and `VoiceSynthesizer` can share the same `AsyncOpenAI` client instance to reduce connection overhead:

```python
# In voice.py module-level or factory function:
def create_voice_services(api_key: str, config) -> tuple[VoiceTranscriber, VoiceSynthesizer]:
    """Create voice services sharing a single OpenAI client."""
    client = AsyncOpenAI(api_key=api_key, timeout=max(config.whisper_timeout, config.tts_timeout))
    transcriber = VoiceTranscriber(client=client, model=config.whisper_model, timeout=config.whisper_timeout)
    synthesizer = VoiceSynthesizer(client=client, model=config.tts_model, voice=config.tts_voice, timeout=config.tts_timeout)
    return transcriber, synthesizer
```

#### Task 3: `is_code_heavy()` in `message_utils.py`

Add a pure function that determines if a response is code-heavy (>50% code blocks):

```python
import re

_CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```", re.MULTILINE)


def is_code_heavy(text: str, threshold: float = 0.5) -> bool:
    """Determine if text is code-heavy (>threshold ratio of code blocks).

    Code-heavy responses should skip TTS synthesis because code is unlistenable.

    Args:
        text: The response text to analyze (raw markdown, before HTML conversion)
        threshold: Ratio above which response is considered code-heavy (default 0.5)

    Returns:
        True if code block characters exceed threshold of total characters.
    """
    if not text:
        return False

    total_chars = len(text)
    code_chars = sum(len(match.group()) for match in _CODE_BLOCK_PATTERN.finditer(text))

    return (code_chars / total_chars) > threshold
```

**Important:** This function operates on the RAW output (before `format_output()` strips markdown), because `format_output()` converts markdown to HTML and removes the ``` delimiters. The code-heavy check must happen on the raw CLI output.

#### Task 4: Integration into Response Handlers

**In `_execute_and_reply_inner()` — after text chunks are sent:**

```python
    # Send text response (always)
    for chunk in chunks:
        await _send_html_with_fallback(update, chunk)

    # Voice output (additive — FR37: text always sent alongside voice)
    if voice_synthesizer and _is_voice_output_enabled(thread_id, context):
        # Check code-heavy before TTS (FR36)
        raw_for_code_check = extract_final_response(full_output) or full_output
        if not is_code_heavy(raw_for_code_check):
            # Strip HTML/formatting for TTS input — synthesize plain text
            plain_text = _strip_html_for_tts(output)
            if plain_text and len(plain_text) > 10:  # Skip trivially short responses
                audio_bytes = await voice_synthesizer.synthesize(plain_text)
                if audio_bytes:
                    await _send_voice_message(update, audio_bytes)
                else:
                    await update.message.reply_text("🔇 Voice temporarily unavailable")
```

**In `_stream_to_telegram()` — same pattern after text chunks:**

```python
    for chunk in split_message(final):
        await _send_html_with_fallback(update, chunk)

    # Voice output (additive)
    if voice_synthesizer and _is_voice_output_enabled(thread_id, context):
        raw_for_code_check = raw_output
        if not is_code_heavy(raw_for_code_check):
            plain_text = _strip_html_for_tts(final)
            if plain_text and len(plain_text) > 10:
                audio_bytes = await voice_synthesizer.synthesize(plain_text)
                if audio_bytes:
                    await _send_voice_message(update, audio_bytes)
                else:
                    await update.message.reply_text("🔇 Voice temporarily unavailable")
```

**Helper functions in `chati.py`:**

```python
async def _send_voice_message(update: Update, audio_bytes: bytes) -> None:
    """Send audio bytes as a Telegram voice message."""
    import io
    from telegram import InputFile

    try:
        voice_file = InputFile(io.BytesIO(audio_bytes), filename="response.ogg")
        await update.message.reply_voice(voice=voice_file)
    except Exception as exc:
        logger.warning("[Voice] failed to send voice message: %s", exc)


def _is_voice_output_enabled(thread_id: int | None, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if voice output is enabled for this thread."""
    # Per-thread override (from /voice toggle)
    thread_key = f"thread:{thread_id}:voice_output"
    per_thread = context.bot_data.get(thread_key)
    if per_thread is not None:
        return per_thread
    # Fall back to global config
    return config.voice_output_enabled


def _strip_html_for_tts(html_text: str) -> str:
    """Strip HTML tags and entities for plain-text TTS input."""
    import re
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", html_text)
    # Decode common HTML entities
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text
```

#### Task 5: `/voice` Command for Per-Thread Toggle

Add a simple toggle command so users can enable/disable voice output per-thread:

```python
@authorized
async def cmd_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /voice — toggle voice output for this thread."""
    if not config.voice_enabled:
        await update.message.reply_text(
            "🎤 Voice features not configured.\n"
            "Set OPENAI_API_KEY in .env to enable voice."
        )
        return

    thread_id = _get_thread_id(update)
    thread_key = f"thread:{thread_id}:voice_output"

    # Toggle current state
    current = context.bot_data.get(thread_key, config.voice_output_enabled)
    new_state = not current
    context.bot_data[thread_key] = new_state

    if new_state:
        await update.message.reply_text(
            "🔊 Voice output <b>enabled</b> for this thread.\n"
            "CLI responses will include voice messages (except code-heavy ones).",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            "🔇 Voice output <b>disabled</b> for this thread.\n"
            "Use /voice again to re-enable.",
            parse_mode=ParseMode.HTML,
        )
```

**Register in `main()`:**
```python
app.add_handler(CommandHandler("voice", cmd_voice))
```

**Update `/help` command** to include `/voice` in the command list.

#### Task 6: Tests

**Test file: `tests/test_voice_output.py`**

Test cases for `is_code_heavy()`:

1. All code (100% code blocks) → returns True
2. No code (0% code blocks) → returns False
3. Exactly 50% code → returns False (threshold is >0.5, not >=)
4. 51% code → returns True
5. Empty string → returns False
6. Mixed content with multiple code blocks → correct ratio calculation
7. Nested backticks (not code blocks) → not counted

Test cases for `VoiceSynthesizer`:

8. Successful synthesis → returns bytes
9. Timeout → returns None
10. API error → returns None
11. Empty text → returns None
12. Long text (>4096 chars) → truncated before sending

Test cases for integration:

13. Voice enabled + non-code response → voice message sent after text
14. Voice enabled + code-heavy response → only text sent (no voice)
15. Voice disabled → no voice attempt
16. TTS fails → text sent + "🔇 Voice temporarily unavailable" note
17. `/voice` toggle → flips per-thread state
18. Per-thread override takes precedence over global config
19. Short response (<10 chars) → skip TTS (not worth synthesizing)

**Mocking strategy:**

- Mock `VoiceSynthesizer.synthesize()` — don't call real OpenAI API
- Mock `update.message.reply_voice()` — verify it's called with correct args
- `is_code_heavy()` is a pure function — test directly without mocks

### File Structure

| File | Action | Description |
|------|--------|-------------|
| `voice.py` | UPDATE | Add `VoiceSynthesizer` class, optional shared client factory |
| `message_utils.py` | UPDATE | Add `is_code_heavy()` function + `_CODE_BLOCK_PATTERN` |
| `chati.py` | UPDATE | Add `_send_voice_message()`, `_is_voice_output_enabled()`, `_strip_html_for_tts()`, `cmd_voice()`, integrate TTS into response handlers |
| `config.py` | UPDATE | Add `tts_model`, `tts_voice`, `tts_timeout`, `voice_output_enabled` |
| `.env.example` | UPDATE | Add TTS config vars |
| `db.py` | UPDATE | Add `voice_output` column to `thread_config` schema migration |
| `tests/test_voice_output.py` | NEW | Tests for TTS synthesis, code detection, integration |

### Technical Requirements

- **Python 3.12+** — modern syntax, type hints throughout
- **openai>=1.0.0** — already added in story 6.1 (shared dependency)
- **python-telegram-bot 21.10** — use `reply_voice()` with `InputFile`
- **Telegram voice format** — OGG Opus required; OpenAI TTS `response_format="opus"` produces this
- **Async patterns** — `VoiceSynthesizer.synthesize()` is async, uses `asyncio.wait_for()`
- **No additional dependencies** — reuses `openai` package from story 6.1
- **Error handling** — TTS failures → graceful degradation (text-only + note)
- **Type hints** — all function signatures fully typed
- **Docstrings** — one-line summary minimum for all public functions

### Architecture Compliance

- `voice.py` extended (not new module) — keeps voice logic consolidated ✓
- `message_utils.py` owns `is_code_heavy()` (pure text analysis) ✓
- `chati.py` owns Telegram API calls and orchestration ✓
- Voice is ADDITIVE — text always sent first, voice is bonus ✓
- Graceful degradation on TTS failure ✓
- Feature flag pattern (disabled by default, toggle per-thread) ✓
- No new dependencies beyond what 6.1 introduced ✓
- Flat root structure maintained ✓

### Testing Requirements

- **Framework:** pytest + pytest-asyncio (existing infrastructure)
- **Coverage:** ≥80% branch coverage for new code
- **Fixtures needed:**
  - Mock `VoiceSynthesizer` (don't call real API)
  - Mock `update.message.reply_voice()` for verifying voice sends
  - Existing `telegram_update_factory` from conftest
- **Test file:** `tests/test_voice_output.py`
- **Run command:** `python -m pytest tests/test_voice_output.py -v`

### Previous Story Intelligence

**From Story 6.1 (voice input — direct predecessor):**

- `voice.py` module already exists with `VoiceTranscriber` class
- `openai>=1.0.0` already in `requirements.txt`
- `config.voice_enabled` and `config.openai_api_key` already exist
- `AsyncOpenAI` client pattern established — reuse same client for TTS
- Module-level initialization pattern: `voice_transcriber = VoiceTranscriber(...)` — add `voice_synthesizer` alongside it
- Feature flag pattern: check `config.voice_enabled` before any voice operation

**From Story 5.1 (screenshot forwarding):**

- Post-processing pattern after text response: screenshots sent AFTER text chunks
- Same integration points: end of `_execute_and_reply_inner()` and `_stream_to_telegram()`
- Order: text response → screenshots → voice (all additive)

**From architecture (Media & Output Architecture):**

- Explicit ordering: screenshots first, then voice, then always text
- Actually: text ALWAYS sent (it's the primary), screenshots and voice are additive
- The architecture pseudocode shows: `send_text_response` at the end, but for UX the text should come FIRST (user sees text immediately, voice arrives moments later)

### Git Intelligence

- Branch: `v2.0`
- Pattern: atomic commits per story
- This story extends `voice.py` created in 6.1 — not a new module

### Potential Pitfalls & Guardrails

1. **OGG Opus format** — OpenAI's `response_format="opus"` produces raw Opus in OGG container. Telegram's `sendVoice` requires OGG Opus. This should work directly without conversion. If Telegram rejects it, the fallback is `response_format="mp3"` + ffmpeg conversion (but try opus first).
2. **TTS input length** — OpenAI TTS models have input limits. `gpt-4o-mini-tts` supports up to ~4096 chars. Truncate gracefully with "..." suffix.
3. **Response ordering** — Text MUST be sent BEFORE voice. User sees text immediately; voice arrives 2-4s later. Never block text delivery waiting for TTS.
4. **Code-heavy check timing** — Must check on RAW output (before `format_output()` converts markdown to HTML). The ``` delimiters are stripped during HTML conversion.
5. **Voice message size** — Telegram voice messages have no strict size limit (unlike photos at 10MB), but very long audio (>10min) may fail. For typical CLI responses (<2000 chars), audio will be <30s.
6. **Shared client lifecycle** — If `VoiceTranscriber` and `VoiceSynthesizer` share an `AsyncOpenAI` client, ensure the client isn't closed prematurely. Module-level instances persist for bot lifetime.
7. **Don't block on TTS** — If TTS is slow, the text response is already sent. The voice message arrives asynchronously. Consider using `asyncio.create_task()` for non-blocking TTS if latency is a concern (but simpler to await inline for v1).
8. **Empty/trivial responses** — Skip TTS for responses shorter than ~10 chars (e.g., "Done." or "✅"). Not worth the API call.
9. **HTML stripping** — TTS input must be plain text. Strip all HTML tags and decode entities before sending to OpenAI. Don't send `<b>`, `<code>`, etc. to TTS.
10. **Per-thread state persistence** — The `/voice` toggle stores state in `context.bot_data` (in-memory). For persistence across restarts, also write to SQLite `thread_config.voice_output`. Story 6.3 may handle this more thoroughly.

### OpenAI TTS API Reference (Latest)

**Endpoint:** `POST https://api.openai.com/v1/audio/speech`

**Models available (as of 2026):**

- `gpt-4o-mini-tts` — newest, most reliable, supports prompting for tone/accent/speed
- `tts-1` — lower latency, lower quality
- `tts-1-hd` — higher quality, higher latency

**Voices (13 built-in):** alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer, verse, marin, cedar

**Recommended:** `coral` (natural, warm) or `marin`/`cedar` (highest quality)

**Output formats:** mp3 (default), opus, aac, flac, wav, pcm

**Python SDK usage (openai>=1.0.0):**
```python
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key="...")
response = await client.audio.speech.create(
    model="gpt-4o-mini-tts",
    voice="coral",
    input="Text to synthesize",
    response_format="opus",  # OGG Opus for Telegram voice messages
)
audio_bytes = response.content  # Raw bytes
```

**Key facts:**

- `response_format="opus"` produces OGG Opus — exactly what Telegram needs for `sendVoice`
- Input limit: ~4096 characters per request
- Typical latency: 1-3 seconds for short text
- `gpt-4o-mini-tts` supports `instructions` parameter for tone control (optional, not needed for v1)

Content was rephrased for compliance with licensing restrictions. Source: [OpenAI Text-to-Speech docs](https://developers.openai.com/api/docs/guides/text-to-speech)

### Project Context Reference

- **Project:** Chati v2.0 — Telegram bot that proxies AI coding CLIs
- **Tech stack:** Python 3.12+, python-telegram-bot 21.10, aiosqlite, openai, asyncio
- **Architecture:** Flat module structure, async-first, graceful degradation on all external APIs
- **Testing:** pytest + pytest-asyncio, TDD approach, tests in `tests/` directory
- **Deployment:** Single-process, systemd, single-machine
- **This is a Growth phase feature** — builds on story 6.1's voice infrastructure

---

*Ultimate context engine analysis completed — comprehensive developer guide created*
