# Story 2.8: Strip Spinner/Thinking Noise from Streaming Preview (Bug)

Status: done

## Story

As a **user**,
I want streaming output to hide CLI spinner/thinking animation frames,
So that my Telegram preview doesn't fill up with lines of "⠋ Thinking... ⠙ Thinking... ⠹ Thinking..." before the real response.

## Context / Bug Report

**Reported by Tony (2026-05-07) with screenshot:**

Telegram shows ~50 lines of "Thinking..." spinner frames interleaved with decorative characters before any real content. The CLI (Kiro) uses a braille spinner (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`) on the same terminal line via `\r` carriage-return overwrites. Our pipeline:

1. Strips ANSI colors correctly
2. Does NOT handle `\r` — so every spinner frame becomes its own visible line
3. Does NOT filter "Thinking..." / braille-spinner lines in the streaming preview path
4. Final-response extraction (`extract_final_response`) works only after the response completes, and only when the `> ` response marker is found

Result: During stream, users see dozens of spinner-frame lines; after completion they may still see residual noise if the `> ` marker isn't present.

**Root causes:**

- `chati._execute_and_reply_inner` (preview loop) and `chati._stream_to_telegram` (decision-reply preview) both just `strip_ansi(line).rstrip()` and append to the buffer. No spinner/thinking filter.
- `chati.runner.execute_stream` yields raw chunks (after ANSI strip) containing carriage returns and per-frame updates.
- `message_utils.extract_final_response` has a `Thinking\.{2,}` pattern but doesn't match frames that are prefixed with a braille char (`⠋ Thinking...`). It also doesn't handle standalone braille spinner chars.

## Acceptance Criteria (BDD)

**Given** CLI output contains `\r⠋ Thinking...\r⠙ Thinking...\r⠹ Thinking...` (spinner frames on same line)
**When** the streaming preview updates
**Then** no `Thinking...` lines appear in the Telegram preview
**And** no braille spinner characters (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⠟⠯⠷⠿` etc.) appear
**And** the preview shows only real content + status lines (e.g. "Reading file: ...")

**Given** CLI output contains carriage returns (`\r`)
**When** the streaming pipeline processes the chunk
**Then** text overwrites on the same line are collapsed — only the final post-`\r` text on each line is shown

**Given** the final response is composed
**When** `format_output` runs
**Then** any residual spinner/thinking frames are stripped regardless of whether `> ` marker is present

**Given** real content contains legitimate ellipsis `...` (e.g. "Let me think...")
**When** the filter runs
**Then** real content is preserved — only spinner animation frames (braille + "Thinking..." pattern) are removed

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for the new helper

## Tasks / Subtasks

- [x] Task 1: Add `strip_streaming_noise(text: str) -> str` helper in `message_utils.py` — collapses `\r` overwrites and strips spinner/thinking frames. Safe to call on streaming chunks (doesn't depend on `> ` marker).
- [x] Task 2: Update `_TOOL_LINE_PATTERNS` in `extract_final_response` to cover braille spinner chars and `⠋ Thinking...` variants.
- [x] Task 3: Apply `strip_streaming_noise` in both preview paths in `chati.py`: `_stream_to_telegram` and `_execute_and_reply_inner` (after `strip_ansi`, before appending to preview_buffer).
- [x] Task 4: Tests — `tests/test_message_utils_noise.py` covering spinner frames, CR collapsing, real-content preservation, final-output filtering.

## Dev Notes

### Design

**`\r` collapsing rule:** For each logical line, if it contains `\r`, keep only the portion after the last `\r`. Spinner writes like `\r⠋ Thinking...\r⠙ Thinking...\r⠹ Thinking...` collapse to just `⠹ Thinking...` which is then removed by the spinner filter.

**Spinner filter patterns:**

- Braille spinner chars (Unicode range U+2800–U+28FF)
- Optional braille-prefixed "Thinking..." / "Loading..." / arbitrary ellipsis-ending lines
- ASCII spinner chars like `|`, `/`, `-`, `\` when followed by "Thinking"
- Standalone ellipsis lines (`…`, `...`)

**Preserve real content:** Don't strip all `...` — only strip when line is JUST spinner/status like "⠋ Thinking...". A line ending with `...` mid-sentence stays.

**Where to apply:**

- **Preview path** (streaming) → use lightweight `strip_streaming_noise` that works on raw chunks
- **Final output** (`format_output`) → already calls `extract_final_response`; we enhance its patterns

### Why not just fix `extract_final_response`?

`extract_final_response` runs once at the end. During streaming, the preview is built line-by-line. We need a streaming-safe filter that doesn't wait for the full output.

### Files modified

- `message_utils.py` — add `strip_streaming_noise()`, enhance `_TOOL_LINE_PATTERNS`
- `chati.py` — apply `strip_streaming_noise` in both preview paths

### What must NOT break

- Final response extraction (Strategy 1 with `> ` marker) — unchanged
- Markdown to HTML conversion — unchanged
- Real content with legitimate ellipsis or Unicode symbols — preserved
- Status lines like "Reading file: foo.py" — preserved (user wants to see progress)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 via Kiro

### Completion Notes

✅ Root cause: pipeline stripped ANSI but didn't handle `\r` carriage-return overwrites or braille spinner frames. Every Kiro spinner tick (`\r⠋ Thinking...`) became a visible preview line.
✅ Added `strip_streaming_noise(text)` in `message_utils.py`:
  - `_collapse_carriage_returns()` keeps only the final post-`\r` segment per line
  - Removes braille spinner lines (`⠋⠙⠹⠸...` + optional "Thinking/Loading/Waiting/Processing/Working")
  - Removes ASCII spinner lines (`/`, `-`, `\`, `|` + "Thinking")
  - Removes bare ellipsis lines (`...`, `…`)
  - Strips stray braille chars embedded in real lines without killing the line
✅ Enhanced `_TOOL_LINE_PATTERNS` in `extract_final_response` to match braille-prefixed spinners and bare braille chars.
✅ Injected `strip_streaming_noise` at the top of `extract_final_response` so both Strategy 1 (`> ` marker path) and Strategy 2 (fallback) benefit from CR-collapsing + spinner stripping.
✅ Applied `strip_streaming_noise(strip_ansi(line))` in BOTH preview paths in `chati.py`:
  - `_execute_and_reply_inner` (primary streaming)
  - `_stream_to_telegram` (decision-reply streaming)
✅ Real content (legit ellipsis mid-sentence, "Reading file: ...", code blocks) is preserved.
✅ 23 new tests in `tests/test_message_utils_noise.py` cover CR collapsing, all spinner variants, preservation of real content, and end-to-end format_output with Kiro-like raw input.
✅ Full regression: 201/201 pass.

### File List

**Modified:**

- `message_utils.py` — added `_BRAILLE_SPINNER_RE`, `_SPINNER_LINE_RE`, `_collapse_carriage_returns()`, `strip_streaming_noise()`. Enhanced `_TOOL_LINE_PATTERNS` for braille spinners. Injected noise filter at start of `extract_final_response()`.
- `chati.py` — imported `strip_streaming_noise`; applied to both preview paths (`_stream_to_telegram` and `_execute_and_reply_inner`) after `strip_ansi`.

**Added:**

- `tests/test_message_utils_noise.py` — 23 tests: CR collapse edge cases (5), spinner filter variants (14), final-response integration (3), end-to-end format_output (1).

### Change Log

| Date       | Change                                             |
|------------|----------------------------------------------------|
| 2026-05-07 | Story opened to fix Thinking/spinner noise in preview. |
| 2026-05-07 | strip_streaming_noise + CR collapsing + enhanced final-output filter. 23 tests. Full suite 201/201. |


### Review Findings

Code review (2026-05-07).

**Patch — MEDIUM:**

- [ ] [Review][Patch] `_SPINNER_LINE_RE` ASCII-prefix pattern `[|/\\\-][ \t]+(?:Thinking|Loading|Waiting|Processing|Working)\.{0,}` with `\.{0,}` is equivalent to no trailing-dot requirement — matches real bullet like `- Loading config`. Change to `\.{2,}` (require at least 2 dots, matches spinner-style "...") or drop `\.{0,}` and require end anchor to avoid false-positives. [message_utils.py:_SPINNER_LINE_RE]
- [ ] [Review][Patch] Cross-chunk CR collapse impossible: `execute_stream` yields chunks already split at `\n`. Spinner frames straddling 2 chunks escape filtering. Either buffer across chunks or document limitation. [message_utils.py:strip_streaming_noise, chati.py streaming loops]
- [ ] [Review][Patch] Embedded braille-in-line stripping is too aggressive: silently drops legit Unicode braille content (e.g. accessibility docs, Japanese/Korean mockups). Consider only stripping when line also matches spinner grammar. [message_utils.py:strip_streaming_noise]

**Patch — LOW:**

- [x] [Review][Patch] Consolidated `_TOOL_LINE_PATTERNS`: removed braille/Thinking/ellipsis duplicates that `strip_streaming_noise()` already handles upstream. No redundant regex sweeps on large outputs. [message_utils.py:_TOOL_LINE_PATTERNS] — **fixed in tech-debt sweep 2026-05-07**
