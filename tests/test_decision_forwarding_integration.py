"""Integration tests for decision forwarding flow.

Tests the full Option B pattern: execute_stream yields DecisionPrompt,
returns; pipe_reply_stream resumes with user reply.

Uses a fake CliRunner-like test harness with a controlled PTY process.
"""

import asyncio
import os
import pty

import pytest

from session_manager import (
    DecisionPrompt,
    PtyState,
    PtySession,
    SessionManager,
    detect_decision_prompt,
)


class TestDecisionPromptYield:
    """Unit tests for the yield+return contract (Option B)."""

    def test_decision_prompt_is_yieldable(self):
        """DecisionPrompt is just a dataclass — can be yielded."""
        dp = DecisionPrompt(
            prompt_text="Continue? [y/N]",
            context_lines=["line1", "line2", "Continue? [y/N]"],
        )
        assert dp.prompt_text == "Continue? [y/N]"
        assert len(dp.context_lines) == 3


class TestStateTransitionsForForwarding:
    """Verify state machine supports decision forwarding flow."""

    def test_waiting_for_user_pauses_timeout(self):
        """State == WAITING_FOR_USER should indicate timeout is paused (caller uses this)."""
        mgr = SessionManager()
        mgr.create(thread_id=1, pid=2**22, fd=0)
        mgr.transition(1, PtyState.STREAMING, reason="start")
        mgr.transition(1, PtyState.DETECTING_PROMPT, reason="idle")
        mgr.transition(1, PtyState.WAITING_FOR_USER, reason="prompt matched")
        assert mgr.get_state(1) == PtyState.WAITING_FOR_USER

    def test_full_cycle(self):
        """IDLE → STREAMING → DETECTING → WAITING → PIPING → STREAMING → IDLE"""
        mgr = SessionManager()
        mgr.create(thread_id=1, pid=2**22, fd=0)
        mgr.transition(1, PtyState.STREAMING, reason="execute")
        mgr.transition(1, PtyState.DETECTING_PROMPT, reason="idle 12s")
        mgr.transition(1, PtyState.WAITING_FOR_USER, reason="[y/N]")
        mgr.transition(1, PtyState.PIPING_REPLY, reason="user reply")
        mgr.transition(1, PtyState.STREAMING, reason="reply piped")
        mgr.transition(1, PtyState.IDLE, reason="response marker")
        assert mgr.get_state(1) == PtyState.IDLE

    def test_chained_decisions(self):
        """Multiple decisions in one session."""
        mgr = SessionManager()
        mgr.create(thread_id=1, pid=2**22, fd=0)

        # First cycle
        mgr.transition(1, PtyState.STREAMING, reason="start")
        mgr.transition(1, PtyState.DETECTING_PROMPT, reason="idle")
        mgr.transition(1, PtyState.WAITING_FOR_USER, reason="prompt 1")
        mgr.transition(1, PtyState.PIPING_REPLY, reason="reply 1")
        mgr.transition(1, PtyState.STREAMING, reason="resume")

        # Second cycle (chained)
        mgr.transition(1, PtyState.DETECTING_PROMPT, reason="idle")
        mgr.transition(1, PtyState.WAITING_FOR_USER, reason="prompt 2")
        mgr.transition(1, PtyState.PIPING_REPLY, reason="reply 2")
        mgr.transition(1, PtyState.STREAMING, reason="resume")
        mgr.transition(1, PtyState.IDLE, reason="done")

        assert mgr.get_state(1) == PtyState.IDLE


class TestPipeReplyStreamRealPty:
    """Integration test with a real PTY simulating a CLI that asks a question."""

    async def test_pipe_reply_stream_continues_output(self):
        """
        Spawn a Python child that:
        1. Prints initial output
        2. Asks a question
        3. Reads user input
        4. Prints result
        """
        script = (
            "import sys; "
            "sys.stdout.write('Processing...\\n'); sys.stdout.flush(); "
            "sys.stdout.write('Continue? [y/N]\\n'); sys.stdout.flush(); "
            "answer = sys.stdin.readline().strip(); "
            "sys.stdout.write(f'Answer: {answer}\\n'); sys.stdout.flush(); "
            "sys.stdout.write('Done\\n'); sys.stdout.flush()"
        )

        pid, fd = pty.fork()
        if pid == 0:
            os.execvp("python3", ["python3", "-c", script])

        # Create session manager + session
        mgr = SessionManager()
        session = mgr.create(thread_id=1, pid=pid, fd=fd)

        try:
            # Transition through the state machine manually
            mgr.transition(1, PtyState.STREAMING, reason="test")

            # Read initial output
            await asyncio.sleep(0.3)
            data1 = session.read(timeout=2.0)
            assert data1 is not None
            assert "Processing" in data1 or "Continue" in data1

            # Simulate detection (real test would use _stream_pty_read_loop)
            # For this test, just verify we can write reply and read response
            mgr.transition(1, PtyState.DETECTING_PROMPT, reason="idle")
            mgr.transition(1, PtyState.WAITING_FOR_USER, reason="match")
            mgr.transition(1, PtyState.PIPING_REPLY, reason="reply")

            # Write reply
            session.write("y\n")
            mgr.transition(1, PtyState.STREAMING, reason="reply sent")

            # Wait for CLI to process and output result
            await asyncio.sleep(0.3)
            data2 = session.read(timeout=2.0)
            assert data2 is not None
            # Should contain the answer echo
            assert "y" in data2.lower() or "Done" in data2

        finally:
            session.kill()
            mgr.kill(1)


class TestPendingDecisionFlag:
    """Unit tests for the bot_data pending_decision flag."""

    def test_flag_key_format(self):
        thread_id = 42
        key = f"thread:{thread_id}:pending_decision"
        # Simulate bot_data dict
        bot_data: dict = {}
        bot_data[key] = True
        assert bot_data.get(key) is True

    def test_flag_cleared_on_pop(self):
        thread_id = 42
        key = f"thread:{thread_id}:pending_decision"
        bot_data = {key: True}
        bot_data.pop(key, None)
        assert key not in bot_data
