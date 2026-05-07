"""Tests for strip_streaming_noise + enhanced extract_final_response (Story 2.8)."""

import pytest

from message_utils import (
    _collapse_carriage_returns,
    extract_final_response,
    format_output,
    strip_streaming_noise,
)


class TestCollapseCarriageReturns:
    def test_no_cr_returns_unchanged(self):
        assert _collapse_carriage_returns("hello world") == "hello world"

    def test_single_cr_keeps_final(self):
        assert _collapse_carriage_returns("hello\rworld") == "world"

    def test_multiple_cr_keeps_last(self):
        assert _collapse_carriage_returns("a\rb\rc\rd") == "d"

    def test_trailing_cr_keeps_preceding(self):
        # Real spinner pattern: last \r is followed by nothing — terminal
        # cursor is back at column 0 waiting for next frame
        assert _collapse_carriage_returns("final\r") == "final"

    def test_all_empty_segments(self):
        assert _collapse_carriage_returns("\r\r\r") == ""


class TestStripStreamingNoise:
    """Verify spinner/thinking filter preserves real content."""

    def test_braille_spinner_thinking_removed(self):
        text = "⠋ Thinking...\n⠙ Thinking...\n⠹ Thinking...\n"
        assert strip_streaming_noise(text).strip() == ""

    def test_all_spinner_states_removed(self):
        # All braille spinner chars Kiro might emit
        text = "\n".join(f"{c} Thinking..." for c in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
        assert strip_streaming_noise(text).strip() == ""

    def test_thinking_without_braille_removed(self):
        assert strip_streaming_noise("Thinking...\nThinking......").strip() == ""

    def test_bare_ellipsis_line_removed(self):
        assert strip_streaming_noise("...\n…\n").strip() == ""

    def test_carriage_return_spinner_collapsed(self):
        # Real pattern from Kiro: many frames on single line via \r
        text = "\r⠋ Thinking...\r⠙ Thinking...\r⠹ Thinking..."
        out = strip_streaming_noise(text)
        assert out.strip() == ""

    def test_cr_with_final_real_content(self):
        # Spinner finishes, real text written on same line
        text = "\r⠋ Thinking...\r⠙ Thinking...\rHello world"
        out = strip_streaming_noise(text)
        assert "Hello world" in out
        assert "Thinking" not in out

    def test_preserves_real_content(self):
        text = (
            "Reading file: src/app.py\n"
            "Let me think about this carefully...\n"
            "Here's the result:\n"
            "def foo():\n"
            "    pass\n"
        )
        out = strip_streaming_noise(text)
        assert "Reading file: src/app.py" in out
        assert "Let me think about this carefully..." in out
        assert "Here's the result:" in out
        assert "def foo():" in out

    def test_mixed_noise_and_content(self):
        text = (
            "⠋ Thinking...\n"
            "⠙ Thinking...\n"
            "Reading file: foo.py\n"
            "⠹ Thinking...\n"
            "Here is the code:\n"
            "...\n"
            "⠸ Thinking...\n"
        )
        out = strip_streaming_noise(text)
        # Spinner lines gone
        assert "Thinking" not in out
        # Real content kept
        assert "Reading file: foo.py" in out
        assert "Here is the code:" in out
        # Bare ellipsis line gone
        assert "\n...\n" not in out

    def test_loading_and_waiting_variants_removed(self):
        text = "⠋ Loading...\n⠙ Waiting...\n⠹ Processing...\n⠸ Working...\n"
        assert strip_streaming_noise(text).strip() == ""

    def test_ascii_spinner_variants_removed(self):
        text = "/ Thinking...\n- Thinking...\n\\ Thinking...\n| Thinking...\n"
        assert strip_streaming_noise(text).strip() == ""

    def test_embedded_braille_in_real_line_stripped(self):
        # Rare: braille char appears inline with real content
        text = "Step ⠋ 1 of 5"
        out = strip_streaming_noise(text)
        # Either the whole line is kept minus braille, or removed if it was spinner.
        # "Step  1 of 5" is real content → must survive
        assert "Step" in out
        assert "1 of 5" in out
        assert "⠋" not in out

    def test_bare_braille_line_removed(self):
        text = "⠋\n⠙\n⠹\n"
        assert strip_streaming_noise(text).strip() == ""

    def test_empty_input(self):
        assert strip_streaming_noise("") == ""

    def test_preserves_mid_sentence_ellipsis(self):
        # Lines that END with ... mid-sentence are legitimate content
        text = "Well, that's tricky...\n"
        out = strip_streaming_noise(text)
        assert "Well, that's tricky..." in out


class TestExtractFinalResponseWithNoise:
    """Verify extract_final_response strips noise even without `> ` marker."""

    def test_strips_spinner_in_fallback_path(self):
        # No `> ` marker → falls through to regex filters
        text = (
            "Executing command: ls\n"
            "⠋ Thinking...\n"
            "⠙ Thinking...\n"
            "file1.py\n"
            "file2.py\n"
        )
        out = extract_final_response(text)
        assert "Thinking" not in out
        assert "file1.py" in out
        assert "file2.py" in out

    def test_strips_spinner_in_response_marker_path(self):
        # With `> ` marker → Strategy 1
        text = (
            "⠋ Thinking...\n"
            "⠙ Thinking...\n"
            "> Here is the answer:\n"
            "42\n"
        )
        out = extract_final_response(text)
        assert "Thinking" not in out
        assert "Here is the answer:" in out
        assert "42" in out

    def test_collapses_cr_overwrites(self):
        # Many spinner frames on a single terminal line via \r
        text = (
            "\r⠋ Thinking...\r⠙ Thinking...\r⠹ Thinking...\r"
            "> Final answer\n"
        )
        out = extract_final_response(text)
        assert "Thinking" not in out
        assert "Final answer" in out


class TestFormatOutputEndToEnd:
    """Verify the complete pipeline hides spinner noise."""

    def test_kiro_like_output_is_clean(self):
        raw = (
            "\x1b[?25l"  # hide cursor
            "\r⠋ Thinking...\r⠙ Thinking...\r⠹ Thinking...\r⠸ Thinking..."
            "\x1b[?25h"  # show cursor
            "\n> Here is your answer:\nHello world\n"
            "\nCredits: 0.05 • Time: 2s\n"
        )
        out = format_output(raw)
        assert "Thinking" not in out
        assert "Hello world" in out
        assert "Here is your answer" in out
        assert "Credits" not in out
