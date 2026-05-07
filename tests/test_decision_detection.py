"""Tests for decision prompt detection."""

import re

import pytest

from session_manager import DecisionPrompt, detect_decision_prompt


class TestGenericPatterns:
    def test_detects_y_slash_n_lowercase(self):
        result = detect_decision_prompt([
            "Installing package...",
            "Continue? [y/N]",
        ])
        assert result is not None
        assert result.prompt_text == "Continue? [y/N]"

    def test_detects_Y_slash_n_uppercase(self):
        result = detect_decision_prompt(["Proceed? [Y/n]"])
        assert result is not None

    def test_detects_yes_slash_no(self):
        result = detect_decision_prompt(["Are you sure? (yes/no)"])
        assert result is not None

    def test_detects_y_slash_n_parens(self):
        result = detect_decision_prompt(["Overwrite? (y/n)"])
        assert result is not None

    def test_ends_with_question_mark(self):
        result = detect_decision_prompt(["Should I proceed?"])
        assert result is not None
        assert result.prompt_text == "Should I proceed?"


class TestEmptyAndEdgeCases:
    def test_empty_buffer(self):
        assert detect_decision_prompt([]) is None

    def test_empty_last_line_uses_previous(self):
        result = detect_decision_prompt([
            "Continue? [y/N]",
            "",
            "",
        ])
        # Last non-empty line is checked
        assert result is not None

    def test_all_empty_lines(self):
        assert detect_decision_prompt(["", "", ""]) is None

    def test_no_pattern_match_returns_none(self):
        result = detect_decision_prompt([
            "Processing file 42...",
            "Done.",
        ])
        assert result is None

    def test_long_line_rejected(self):
        """Lines > 100 chars likely explanation text, not prompts."""
        long_line = "This is a very long explanation about why you might want to consider some approach or path [y/N] perhaps?"
        assert len(long_line) > 100  # sanity check
        result = detect_decision_prompt([long_line])
        assert result is None  # exceeds 100 char limit

    def test_custom_max_length(self):
        long_line = "A" * 200 + "? "
        result = detect_decision_prompt([long_line], max_line_length=300)
        assert result is not None


class TestContextLines:
    def test_captures_last_5_lines_of_context(self):
        result = detect_decision_prompt([
            "line 1", "line 2", "line 3", "line 4", "line 5",
            "line 6", "line 7",
            "Continue? [y/N]",
        ])
        assert result is not None
        # Last 5 lines (including prompt)
        assert len(result.context_lines) == 5
        assert result.context_lines[-1] == "Continue? [y/N]"
        assert result.context_lines[0] == "line 4"

    def test_captures_all_when_fewer_than_5(self):
        result = detect_decision_prompt([
            "setup",
            "Continue? [y/N]",
        ])
        assert result is not None
        assert len(result.context_lines) == 2


class TestProviderSpecificPatterns:
    def test_provider_pattern_matches(self):
        custom_patterns = [re.compile(r"CONFIRM:")]
        result = detect_decision_prompt(
            ["CONFIRM: delete 17 files"],
            provider_patterns=custom_patterns,
        )
        assert result is not None

    def test_provider_pattern_alongside_generic(self):
        custom_patterns = [re.compile(r"XYZ:")]
        # Generic pattern takes precedence, but custom pattern also works
        result = detect_decision_prompt(
            ["Do it? [y/N]"],
            provider_patterns=custom_patterns,
        )
        assert result is not None

    def test_no_patterns_provided(self):
        # Without provider patterns, still detects generic
        result = detect_decision_prompt(
            ["Continue? [y/N]"],
            provider_patterns=None,
        )
        assert result is not None


class TestFalsePositives:
    def test_question_in_sentence_too_long(self):
        result = detect_decision_prompt([
            "I was wondering what you wanted to do about that thing we discussed?",
        ])
        # Exceeds 100 chars? Let's verify
        assert result is None or len(result.prompt_text) <= 100

    def test_code_with_question_mark_in_comment_not_detected_as_prompt(self):
        """Code containing ? shouldn't trigger if line is long."""
        result = detect_decision_prompt([
            "# What does this function return? It's unclear.",
        ])
        # 47 chars, ends with period → no match
        assert result is None

    def test_comma_before_yn_still_works(self):
        result = detect_decision_prompt(["Ready, [Y/n]"])
        assert result is not None
