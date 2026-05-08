"""Telegram message utilities.

Handles ANSI stripping, Markdown → Telegram HTML conversion,
and message splitting (4096 char limit).
"""

import re
from html import escape as html_escape

# ── ANSI Stripping ───────────────────────────────────────────────

_ANSI_ESCAPE_RE = re.compile(
    r"(\x1b"
    r"("
    r"\[[\x20-\x3f]*[\x40-\x7e]"  # CSI: ESC[ ... final byte
    r"|\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC: ESC] ... BEL/ST
    r"|[()][A-Z0-9]"       # Character set selection
    r"|[\x20-\x2f]*[\x30-\x7e]"  # Other ESC sequences
    r")"
    r"|\x9b[\x20-\x3f]*[\x40-\x7e]"  # Bare CSI (0x9b)
    r")"
)


def strip_ansi(text: str) -> str:
    """Remove all ANSI/VT escape sequences from text."""
    return _ANSI_ESCAPE_RE.sub("", text)


# ── Streaming noise filter ───────────────────────────────────────

# Braille spinner characters commonly used by CLIs (Kiro, npm, etc.)
# Unicode range U+2800–U+28FF covers all braille patterns.
_BRAILLE_SPINNER_RE = re.compile(r"[\u2800-\u28FF]")

# Lines that are pure CLI spinner/thinking frames (to be removed entirely).
_SPINNER_LINE_RE = re.compile(
    r"^[ \t]*(?:"
    r"[\u2800-\u28FF]+[ \t]*(?:Thinking|Loading|Waiting|Processing|Working)?[.\u2026]{0,}"
    r"|[|/\\\-][ \t]+(?:Thinking|Loading|Waiting|Processing|Working)[.\u2026]{2,}"
    r"|Thinking[.\u2026]{2,}"
    r"|Loading[.\u2026]{2,}"
    r"|\.{3,}"
    r"|\u2026+"  # ellipsis char
    r")[ \t]*$"
)

# Tool invocation lines that appear in streaming output (early pattern for strip_streaming_noise).
# Full _TOOL_LINE_RE is defined later with more patterns; this covers the most common ones.
_TOOL_STREAM_LINE_RE = re.compile(
    r"^[ \t]*(?:"
    r"(?:Reading|Writing|Executing|Searching|Listing|Creating|Deleting|Updating|Running|Spawning|Invoking) (?:directory|file|command|shell|for|in|to):.*"
    r"|Invoked\s+.*"
    r"|Spawn(?:ed|ing)\s+.*"
    r"|Successfully (?:read|wrote|created|deleted|updated|executed).*"
    r"|Found \d+ (?:results?|files?|matches?).*"
    r"|- Completed in [\d.]+s.*"
    r"|\(using tool:.*\)"
    r")$",
    re.IGNORECASE,
)


def _collapse_carriage_returns(line: str) -> str:
    """Keep only the text after the LAST \\r on each line.

    Spinner animation writes like "\\r⠋ Thinking...\\r⠙ Thinking..."
    collapse to just the final frame.
    """
    if "\r" not in line:
        return line
    # Split on \r; the last non-empty segment is what the terminal would show
    segments = line.split("\r")
    # Keep the last non-empty segment; if all empty, return empty
    for seg in reversed(segments):
        if seg:
            return seg
    return ""


def strip_streaming_noise(text: str) -> str:
    """Clean a streaming chunk for live preview display.

    Handles:
    - Carriage-return overwrites (\\r) — collapses to final frame per line
    - Braille spinner frames (⠋⠙⠹...) — removes full spinner-only lines
    - "Thinking..." / "Loading..." animation lines — removes them
    - Bare ellipsis lines (... or …) — removes them
    - Tool invocation lines (Searching for:, Reading file:, etc.) — removes them

    Preserves real content including lines that end with "..." mid-sentence.

    Safe to call on streaming chunks (doesn't require full output).
    """
    # Split into lines, collapse CR per-line, filter spinner-only lines
    out_lines: list[str] = []
    for raw in text.split("\n"):
        line = _collapse_carriage_returns(raw)
        if _SPINNER_LINE_RE.match(line):
            continue
        if _TOOL_STREAM_LINE_RE.match(line):
            continue
        # Strip braille spinner chars only if the line looks like a spinner
        # (contains braille + optional spinner keywords). Preserve braille in
        # real content (accessibility docs, Unicode art, etc.)
        if _BRAILLE_SPINNER_RE.search(line):
            # Only strip if line is mostly braille + whitespace + spinner words
            without_braille = _BRAILLE_SPINNER_RE.sub("", line).strip()
            spinner_words = {"thinking", "loading", "waiting", "processing", "working"}
            if not without_braille or without_braille.lower().rstrip(".…") in spinner_words:
                continue  # Pure spinner line — drop entirely
            # Line has braille prefix followed by real content (e.g. "⠴ Thinking...> response")
            # Strip the braille+spinner prefix, keep the rest
            line = re.sub(
                r"^[\u2800-\u28FF]+\s*(?:Thinking|Loading|Waiting|Processing|Working)?[.\u2026]*\s*",
                "",
                line,
            ).strip()
            if not line:
                continue
        # After stripping spinner prefix, check again for tool lines
        if _TOOL_STREAM_LINE_RE.match(line):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# ── Telegram Message Limits ──────────────────────────────────────

MAX_MESSAGE_LENGTH = 4096
CONTINUATION_OVERHEAD = 40


# ── Markdown → Telegram HTML Conversion ──────────────────────────

def markdown_to_telegram_html(text: str) -> str:
    """Convert Markdown output from CLI to Telegram-supported HTML.

    Telegram HTML supports: <b>, <i>, <u>, <s>, <code>, <pre>,
    <a href>, <blockquote>, <tg-spoiler>.

    Strategy:
    - Fenced code blocks → <pre>
    - Inline code → <code>
    - Headings → bold line with emoji
    - Bold/italic → <b>/<i>
    - Tables → <pre> (monospace, best readability)
    - Horizontal rules → unicode line
    - Links → <a href>
    - Everything else → HTML-escaped plain text
    """
    lines = text.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # ── Fenced code blocks ───────────────────────────────
        if line.strip().startswith("```"):
            code_lines: list[str] = []
            lang = line.strip().removeprefix("```").strip()
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            code_content = html_escape("\n".join(code_lines))
            if lang:
                result.append(f'<pre><code class="language-{html_escape(lang)}">{code_content}</code></pre>')
            else:
                result.append(f"<pre>{code_content}</pre>")
            continue

        # ── Tables (consecutive lines with |) ────────────────
        if "|" in line and line.strip().startswith("|"):
            table_lines: list[str] = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip().startswith("|"):
                row = lines[i].strip()
                # Skip separator rows (|---|---|)
                if re.match(r"^\|[\s\-:|]+\|$", row):
                    i += 1
                    continue
                # Clean up: strip outer pipes, normalize inner pipes
                cells = [c.strip() for c in row.strip("|").split("|")]
                table_lines.append("  ".join(cells))
                i += 1
            table_content = html_escape("\n".join(table_lines))
            result.append(f"<pre>{table_content}</pre>")
            continue

        # ── Headings → bold with level indicator ─────────────
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            # Convert inline markdown within heading
            heading_text = _inline_markdown_to_html(heading_text)
            if level == 1:
                result.append(f"\n<b>{'━' * 20}</b>")
                result.append(f"<b>{heading_text}</b>")
                result.append(f"<b>{'━' * 20}</b>\n")
            elif level == 2:
                result.append(f"\n<b>▸ {heading_text}</b>\n")
            else:
                result.append(f"\n<b>• {heading_text}</b>")
            i += 1
            continue

        # ── Horizontal rules ─────────────────────────────────
        if re.match(r"^[\s]*[-*_]{3,}[\s]*$", line):
            result.append("─" * 30)
            i += 1
            continue

        # ── Blockquotes ──────────────────────────────────────
        if line.strip().startswith(">"):
            quote_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_text = re.sub(r"^>\s?", "", lines[i])
                quote_lines.append(quote_text)
                i += 1
            quote_content = _inline_markdown_to_html("\n".join(quote_lines))
            result.append(f"<blockquote>{quote_content}</blockquote>")
            continue

        # ── Unordered list items ─────────────────────────────
        list_match = re.match(r"^(\s*)[-*+]\s+(.+)$", line)
        if list_match:
            indent = len(list_match.group(1)) // 2
            item_text = _inline_markdown_to_html(list_match.group(2))
            prefix = "  " * indent + "•"
            result.append(f"{prefix} {item_text}")
            i += 1
            continue

        # ── Ordered list items ───────────────────────────────
        olist_match = re.match(r"^(\s*)\d+[.)]\s+(.+)$", line)
        if olist_match:
            indent = len(olist_match.group(1)) // 2
            item_text = _inline_markdown_to_html(olist_match.group(2))
            prefix = "  " * indent + "▹"
            result.append(f"{prefix} {item_text}")
            i += 1
            continue

        # ── Regular line → inline markdown conversion ────────
        result.append(_inline_markdown_to_html(line))
        i += 1

    return "\n".join(result)


def _inline_markdown_to_html(text: str) -> str:
    """Convert inline Markdown formatting to Telegram HTML.

    Handles: bold, italic, strikethrough, inline code, links.
    HTML-escapes everything else.
    """
    # Extract inline code first to protect from further processing
    code_spans: list[str] = []
    placeholder = "\x00ICODE_{}\x00"

    def _save_code(m: re.Match) -> str:
        code_spans.append(f"<code>{html_escape(m.group(1))}</code>")
        return placeholder.format(len(code_spans) - 1)

    text = re.sub(r"`([^`]+)`", _save_code, text)

    # HTML-escape the rest (must happen before adding HTML tags)
    text = html_escape(text)

    # Bold+italic: ***text*** or ___text___
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", text)
    text = re.sub(r"___(.+?)___", r"<b><i>\1</i></b>", text)

    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # Italic: *text* or _text_ (but not inside words like file_name)
    text = re.sub(r"(?<!\w)\*([^*]+?)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", r"<i>\1</i>", text)

    # Strikethrough: ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # Links: [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # Restore inline code spans
    for idx, code_html in enumerate(code_spans):
        text = text.replace(placeholder.format(idx), code_html)

    return text


# ── Message Splitting ────────────────────────────────────────────

def split_message(text: str) -> list[str]:
    """Split a long message into Telegram-safe chunks.

    Tries to split at natural boundaries:
    1. Double newlines (paragraph breaks)
    2. Single newlines
    3. Spaces
    4. Hard cut at max length
    """
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    chunks: list[str] = []
    remaining = text
    max_len = MAX_MESSAGE_LENGTH - CONTINUATION_OVERHEAD

    while remaining:
        if len(remaining) <= MAX_MESSAGE_LENGTH:
            chunks.append(remaining)
            break

        chunk = remaining[:max_len]
        split_idx = _find_split_point(chunk)

        chunks.append(remaining[:split_idx].rstrip())
        remaining = remaining[split_idx:].lstrip("\n")

    if len(chunks) > 1:
        total = len(chunks)
        chunks = [
            f"{chunk}\n\n📄 [{i + 1}/{total}]"
            for i, chunk in enumerate(chunks)
        ]

    return chunks


def _find_split_point(text: str) -> int:
    """Find the best point to split text."""
    # Try </pre> boundary first (don't split inside code blocks)
    idx = text.rfind("</pre>")
    if idx > len(text) // 3:
        return idx + len("</pre>")

    # Try double newline (paragraph break)
    idx = text.rfind("\n\n")
    if idx > len(text) // 2:
        return idx

    # Try single newline
    idx = text.rfind("\n")
    if idx > len(text) // 2:
        return idx

    # Try space
    idx = text.rfind(" ")
    if idx > len(text) // 2:
        return idx

    return len(text)


# ── CLI Output Filtering ──────────────────────────────────────────

# Patterns to strip from CLI output (applied after ANSI stripping).
# These match tool invocations, thinking blocks, trust warnings, etc.

# Trust warning block at the top
_TRUST_WARNING_RE = re.compile(
    r"All tools are now trusted[^\n]*\n"
    r"(?:Agents can sometimes[^\n]*\n)?"
    r"(?:\s*\n)*"
    r"(?:Learn more at[^\n]*\n)?",
)

# Credits/time footer: Credits: 0.15 • Time: 11s (with possible unicode chars)
_CREDITS_RE = re.compile(r"^.*Credits:.*Time:.*$", re.MULTILINE)

# Tool invocation lines — patterns for CLI tool-call noise (not spinners).
# NOTE: spinner/Thinking/ellipsis patterns are handled by strip_streaming_noise()
# which runs BEFORE this regex in extract_final_response(). Don't duplicate them here.
_TOOL_LINE_PATTERNS = [
    r"Reading (?:directory|file):.*",
    r"Writing (?:file|to):.*",
    r"Executing (?:command|shell):.*",
    r"Searching (?:for|in):.*",
    r"Listing (?:directory|files):.*",
    r"Creating (?:file|directory):.*",
    r"Deleting (?:file|directory):.*",
    r"Updating file:.*",
    r"Running (?:command|tool):.*",
    r"Spawning (?:agent|task):.*",
    r"Invoking (?:tool|agent):.*",
    r"Invoked\s+.*",
    r"Spawn(?:ed|ing)\s+.*",
    r"Successfully (?:read|wrote|created|deleted|updated|executed).*",
    r"Found \d+ (?:results?|files?|matches?).*",
    r"- Completed in [\d.]+s.*",
    r"\(using tool:.*\)",
]

_TOOL_LINE_RE = re.compile(
    r"^[ \t]*(?:" + "|".join(_TOOL_LINE_PATTERNS) + r")$",
    re.MULTILINE,
)

# Lines starting with status indicators (✓, ✗, ⚡, etc.)
_STATUS_LINE_RE = re.compile(
    r"^[ \t]*[✓✗✔✘⚡→←↑↓▸▹●○◆◇■□]\s+.*$",
    re.MULTILINE,
)

# The "λ↯" prompt prefix and similar decorative prefixes
_PROMPT_PREFIX_RE = re.compile(r"^.*[λ↯]+.*$", re.MULTILINE)

# The "> " prefix on the first line of the actual response
_RESPONSE_PREFIX_RE = re.compile(r"^> ", re.MULTILINE)

# Cursor control sequences that survive ANSI stripping
_CURSOR_JUNK_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def extract_final_response(text: str) -> str:
    """Extract only the final response from CLI output.

    Strategy: Find the last response block (starts with "> " after tool
    invocations) and return everything from there. Falls back to
    regex-based filtering if no "> " marker is found.
    """
    # First pass: collapse carriage returns and strip spinner frames.
    # This handles animation noise regardless of which strategy runs below.
    text = strip_streaming_noise(text)

    # Remove cursor junk and residual control chars
    text = _CURSOR_JUNK_RE.sub("", text)

    # Strategy 1: Find the "> " response marker.
    # Some CLIs prefix the actual response with "> " on the first line.
    # We want the LAST occurrence (in case of multi-turn spawn output).
    lines = text.split("\n")
    response_start = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("> ") and not stripped.startswith("> ✓") and not stripped.startswith("> -"):
            response_start = i

    if response_start >= 0:
        # Take from response start to end, strip the "> " prefix
        response_lines = lines[response_start:]
        # Remove "> " prefix from first line
        response_lines[0] = re.sub(r"^>\s?", "", response_lines[0])

        # Find and remove credits footer at the end
        result_lines: list[str] = []
        for line in response_lines:
            if re.match(r"^.*Credits:.*Time:.*$", line):
                continue
            result_lines.append(line)

        text = "\n".join(result_lines)
    else:
        # Strategy 2: Fallback — regex-based filtering
        text = _TRUST_WARNING_RE.sub("", text)
        text = _PROMPT_PREFIX_RE.sub("", text)
        text = _TOOL_LINE_RE.sub("", text)
        text = _STATUS_LINE_RE.sub("", text)
        text = _CREDITS_RE.sub("", text)
        text = _RESPONSE_PREFIX_RE.sub("", text)

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ── Main Format Function ────────────────────────────────────────

def format_output(text: str, is_error: bool = False) -> str:
    """Format CLI output for Telegram display.

    Pipeline: strip ANSI → extract final response → strip noise → convert MD → HTML.
    """
    # Strip ANSI escape codes
    text = strip_ansi(text)

    # Extract only the final response (remove thinking, tools, etc.)
    text = extract_final_response(text)

    # Second noise pass — catches any spinner lines or tool invocation lines
    # that survived inside the response block (e.g. Kiro emitting ⠴ Thinking…
    # or tool lines after the "> " marker).
    lines = [
        l for l in text.split("\n")
        if not _SPINNER_LINE_RE.match(l) and not _TOOL_LINE_RE.match(l)
    ]
    text = "\n".join(lines)

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Convert Markdown to Telegram HTML
    text = markdown_to_telegram_html(text)

    # Clean up: collapse excessive newlines introduced by conversion
    text = re.sub(r"\n{3,}", "\n\n", text)

    if is_error:
        return f"❌ <b>Error:</b>\n\n{text}"
    return text.strip()


# ── Code-Heavy Detection (Story 6.2 / hardened in 6.3) ───────────

# Matches fenced code blocks with optional language specifier.
# Non-greedy so multiple blocks are matched individually.
# Does NOT match inline code (single backticks).
_CODE_BLOCK_PATTERN = re.compile(
    r"```(?:[a-zA-Z0-9_+-]*\n)?([\s\S]*?)```",
    re.MULTILINE,
)


def is_code_heavy(text: str, threshold: float = 0.5) -> bool:
    """Determine if text is code-heavy (>threshold ratio of code block content).

    Only fenced code blocks (triple backtick) are counted. Inline code
    (single backtick) is NOT counted. The ratio is calculated on the
    CONTENT inside code blocks, excluding the ``` delimiters themselves.

    Operates on raw markdown (before HTML conversion) so delimiters are
    still present.

    Args:
        text: The response text to analyze (raw markdown).
        threshold: Ratio above which response is considered code-heavy (default 0.5).

    Returns:
        True if code block content characters exceed threshold of total characters.
    """
    if not text or len(text) < 6:  # Minimum viable code block: ```\n```
        return False

    total_chars = len(text)
    # group(1) is the content captured between the opening and closing ```
    code_content_chars = sum(len(m.group(1)) for m in _CODE_BLOCK_PATTERN.finditer(text))

    return (code_content_chars / total_chars) > threshold


# ── Screenshot Detection (Story 5.1) ─────────────────────────────

# URLs we must NOT treat as local file paths — strip these before detection.
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)

# Absolute paths: must start with `/`
# Relative paths: must start with `./`
# Supported extensions: png, jpg, jpeg, gif, webp (case-insensitive)
# Path characters: exclude whitespace and common string delimiters that
# would end a path token in CLI output.
_SCREENSHOT_PATTERN = re.compile(
    r"""
    (?<![A-Za-z0-9])  # not preceded by alphanumeric (avoids partial matches inside words)
    (
        /[^\s'"<>|()\[\]]+\.(?:png|jpg|jpeg|gif|webp)    # absolute path
        |
        \.\/[^\s'"<>|()\[\]]+\.(?:png|jpg|jpeg|gif|webp) # relative ./path
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def detect_screenshots(text: str) -> list[str]:
    """Extract image file paths from CLI output text.

    Scans for absolute paths (starting with `/`) or relative paths
    (starting with `./`) ending in supported image extensions:
    ``.png``, ``.jpg``, ``.jpeg``, ``.gif``, ``.webp``.

    URLs (``http://`` / ``https://``) are explicitly excluded.

    Args:
        text: Raw CLI output text (ANSI sequences will be stripped).

    Returns:
        List of detected file path strings in order of first appearance.
        Duplicates are removed. Empty list if no image paths found.
    """
    if not text:
        return []

    # Strip ANSI sequences — paths may be embedded in color codes.
    cleaned = strip_ansi(text)

    # Remove URLs first so their path components are not misread as local files.
    cleaned = _URL_PATTERN.sub(" ", cleaned)

    seen: set[str] = set()
    ordered: list[str] = []
    for match in _SCREENSHOT_PATTERN.finditer(cleaned):
        path = match.group(1)
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered
