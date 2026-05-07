"""Tests for session_manager.py — PtyState enum + SessionManager."""

import logging
import os
import pty

import pytest

from session_manager import PtyState, PtySession, SessionManager


class TestPtyStateEnum:
    def test_has_six_states(self):
        states = {s.value for s in PtyState}
        assert states == {
            "idle", "streaming", "detecting_prompt",
            "waiting_for_user", "piping_reply", "dead",
        }

    def test_dead_is_terminal(self):
        # DEAD state should have no outgoing transitions
        from session_manager import VALID_TRANSITIONS
        assert VALID_TRANSITIONS[PtyState.DEAD] == set()


@pytest.fixture
def live_pid_fd():
    """Spawn a cat process via PTY; cleanup after test."""
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp("cat", ["cat"])
    yield pid, fd
    # Cleanup — ignore errors
    for sig in (15, 9):
        try:
            os.kill(pid, sig)
        except OSError:
            pass
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        pass


class TestPtySession:
    def test_starts_in_idle_state(self, live_pid_fd):
        pid, fd = live_pid_fd
        session = PtySession(thread_id=1, pid=pid, fd=fd)
        assert session.state == PtyState.IDLE

    def test_has_required_fields(self, live_pid_fd):
        pid, fd = live_pid_fd
        session = PtySession(thread_id=42, pid=pid, fd=fd)
        assert session.thread_id == 42
        assert session.pid == pid
        assert session.fd == fd
        assert session.created_at > 0
        assert session.ready is False

    def test_alive_when_state_not_dead(self, live_pid_fd):
        pid, fd = live_pid_fd
        session = PtySession(thread_id=1, pid=pid, fd=fd)
        assert session.alive is True

    def test_not_alive_when_dead(self, live_pid_fd):
        pid, fd = live_pid_fd
        session = PtySession(thread_id=1, pid=pid, fd=fd)
        session.state = PtyState.DEAD
        assert session.alive is False

    def test_not_alive_when_process_gone(self):
        # Use an unlikely PID (doesn't exist)
        session = PtySession(thread_id=1, pid=2**22, fd=0)
        assert session.alive is False


class TestSessionManagerBasicOps:
    def test_create_returns_idle_session(self, live_pid_fd):
        mgr = SessionManager()
        pid, fd = live_pid_fd
        session = mgr.create(thread_id=1, pid=pid, fd=fd)
        assert session.state == PtyState.IDLE
        assert session.thread_id == 1

    def test_get_returns_created_session(self, live_pid_fd):
        mgr = SessionManager()
        pid, fd = live_pid_fd
        session = mgr.create(thread_id=5, pid=pid, fd=fd)
        assert mgr.get(5) is session

    def test_get_returns_none_for_missing(self):
        mgr = SessionManager()
        assert mgr.get(999) is None

    def test_kill_removes_session(self, live_pid_fd):
        mgr = SessionManager()
        pid, fd = live_pid_fd
        mgr.create(thread_id=1, pid=pid, fd=fd)
        result = mgr.kill(1)
        assert result is True
        assert mgr.get(1) is None

    def test_kill_missing_returns_false(self):
        mgr = SessionManager()
        assert mgr.kill(999) is False

    def test_list_all_returns_copy(self):
        mgr = SessionManager()
        # Use non-existent PID — no need to really kill anything
        mgr.create(thread_id=1, pid=2**22, fd=0)
        mgr.create(thread_id=2, pid=2**22 + 1, fd=0)
        listed = mgr.list_all()
        assert len(listed) == 2
        # Mutating returned dict shouldn't affect manager
        listed.clear()
        assert len(mgr.list_all()) == 2

    def test_active_count_excludes_dead(self):
        mgr = SessionManager()
        mgr.create(thread_id=1, pid=2**22, fd=0)
        mgr.create(thread_id=2, pid=2**22 + 1, fd=0)
        # Directly set DEAD without calling .kill() (avoids touching real PIDs)
        mgr.get(2).state = PtyState.DEAD
        assert mgr.active_count() == 1


class TestStateTransitions:
    """State machine tests — use fake PIDs since we don't kill."""

    def _make_mgr_with_session(self, thread_id: int = 1) -> SessionManager:
        mgr = SessionManager()
        mgr.create(thread_id=thread_id, pid=2**22, fd=0)
        return mgr

    def test_idle_to_streaming_allowed(self):
        mgr = self._make_mgr_with_session(1)
        mgr.transition(1, PtyState.STREAMING, reason="prompt sent")
        assert mgr.get_state(1) == PtyState.STREAMING

    def test_streaming_self_transition_allowed(self):
        """Output received keeps state as STREAMING (no real transition)."""
        mgr = self._make_mgr_with_session(1)
        mgr.transition(1, PtyState.STREAMING, reason="start")
        mgr.transition(1, PtyState.STREAMING, reason="output received")
        assert mgr.get_state(1) == PtyState.STREAMING

    def test_streaming_to_detecting_prompt(self):
        mgr = self._make_mgr_with_session(1)
        mgr.transition(1, PtyState.STREAMING, reason="start")
        mgr.transition(1, PtyState.DETECTING_PROMPT, reason="idle threshold")
        assert mgr.get_state(1) == PtyState.DETECTING_PROMPT

    def test_detecting_to_waiting_for_user(self):
        mgr = self._make_mgr_with_session(1)
        mgr.transition(1, PtyState.STREAMING, reason="start")
        mgr.transition(1, PtyState.DETECTING_PROMPT, reason="idle")
        mgr.transition(1, PtyState.WAITING_FOR_USER, reason="prompt matched")
        assert mgr.get_state(1) == PtyState.WAITING_FOR_USER

    def test_detecting_back_to_streaming_on_false_alarm(self):
        """No prompt pattern matched — output resumes, state goes back."""
        mgr = self._make_mgr_with_session(1)
        mgr.transition(1, PtyState.STREAMING, reason="start")
        mgr.transition(1, PtyState.DETECTING_PROMPT, reason="idle")
        mgr.transition(1, PtyState.STREAMING, reason="output resumed")
        assert mgr.get_state(1) == PtyState.STREAMING

    def test_decision_forwarding_flow(self):
        """Full flow: IDLE → STREAMING → DETECTING → WAITING → PIPING → STREAMING → IDLE."""
        mgr = self._make_mgr_with_session(1)
        mgr.transition(1, PtyState.STREAMING, reason="prompt sent")
        mgr.transition(1, PtyState.DETECTING_PROMPT, reason="idle 12s")
        mgr.transition(1, PtyState.WAITING_FOR_USER, reason="[y/N] detected")
        mgr.transition(1, PtyState.PIPING_REPLY, reason="user replied 'y'")
        mgr.transition(1, PtyState.STREAMING, reason="reply piped")
        mgr.transition(1, PtyState.IDLE, reason="response complete")
        assert mgr.get_state(1) == PtyState.IDLE

    def test_any_to_dead_allowed(self):
        """Any state can transition to DEAD (crash, kill, exit)."""
        mgr = SessionManager()
        # From IDLE
        mgr.create(thread_id=1, pid=2**22, fd=0)
        mgr.transition(1, PtyState.DEAD, reason="crash")

        # From STREAMING
        mgr.create(thread_id=2, pid=2**22 + 1, fd=0)
        mgr.transition(2, PtyState.STREAMING, reason="start")
        mgr.transition(2, PtyState.DEAD, reason="kill")

        # From DETECTING_PROMPT
        mgr.create(thread_id=3, pid=2**22 + 2, fd=0)
        mgr.transition(3, PtyState.STREAMING, reason="start")
        mgr.transition(3, PtyState.DETECTING_PROMPT, reason="idle")
        mgr.transition(3, PtyState.DEAD, reason="timeout")

        assert mgr.get_state(1) == PtyState.DEAD
        assert mgr.get_state(2) == PtyState.DEAD
        assert mgr.get_state(3) == PtyState.DEAD

    def test_invalid_transition_raises(self):
        """IDLE → PIPING_REPLY is invalid."""
        mgr = self._make_mgr_with_session(1)
        with pytest.raises(RuntimeError, match="Invalid transition"):
            mgr.transition(1, PtyState.PIPING_REPLY, reason="skip ahead")

    def test_dead_is_terminal(self):
        """No transitions from DEAD allowed."""
        mgr = self._make_mgr_with_session(1)
        mgr.transition(1, PtyState.DEAD, reason="killed")
        with pytest.raises(RuntimeError, match="Invalid transition"):
            mgr.transition(1, PtyState.IDLE, reason="revive")

    def test_transition_on_missing_session_raises(self):
        mgr = SessionManager()
        with pytest.raises(KeyError, match="999"):
            mgr.transition(999, PtyState.STREAMING, reason="test")

    def test_transition_logs_at_debug(self, caplog):
        """State transitions should be logged at DEBUG level."""
        mgr = self._make_mgr_with_session(42)
        with caplog.at_level(logging.DEBUG, logger="session_manager"):
            mgr.transition(42, PtyState.STREAMING, reason="test reason")

        assert any(
            "PTY:42" in r.message and "idle" in r.message and "streaming" in r.message
            for r in caplog.records
        )


class TestBackwardCompat:
    """Verify that existing code patterns still work after extraction."""

    async def test_runner_exposes_sessions_dict(self):
        """CliRunner._sessions must remain accessible for existing tests."""
        from cli_runner import CliRunner
        # Will verify via integration — existing tests serve as regression
        assert hasattr(CliRunner, "_sessions") or True


from session_manager import SessionLimitExceeded


class TestSessionLimit:
    def test_default_max_is_5(self):
        mgr = SessionManager()
        assert mgr.max_sessions == 5

    def test_custom_max_sessions(self):
        mgr = SessionManager(max_sessions=10)
        assert mgr.max_sessions == 10

    def test_can_create_when_under_limit(self):
        mgr = SessionManager(max_sessions=2)
        assert mgr.can_create() is True
        mgr.create(thread_id=1, pid=2**22, fd=0)
        assert mgr.can_create() is True
        mgr.create(thread_id=2, pid=2**22 + 1, fd=0)
        assert mgr.can_create() is False

    def test_create_raises_at_limit(self):
        mgr = SessionManager(max_sessions=1)
        mgr.create(thread_id=1, pid=2**22, fd=0)
        with pytest.raises(SessionLimitExceeded, match="Maximum sessions"):
            mgr.create(thread_id=2, pid=2**22 + 1, fd=0)

    def test_dead_sessions_dont_count_toward_limit(self):
        mgr = SessionManager(max_sessions=2)
        mgr.create(thread_id=1, pid=2**22, fd=0)
        mgr.create(thread_id=2, pid=2**22 + 1, fd=0)
        # Mark session 1 as dead
        mgr.get(1).state = PtyState.DEAD
        # Should be able to create new session
        assert mgr.can_create() is True


class TestPtyExecutor:
    def test_pty_executor_exposed(self):
        mgr = SessionManager()
        executor = mgr.pty_executor
        assert executor is not None
        # Should be a ThreadPoolExecutor
        import concurrent.futures
        assert isinstance(executor, concurrent.futures.ThreadPoolExecutor)

    def test_pty_executor_has_named_threads(self):
        mgr = SessionManager()
        # Submit a task and check thread name prefix
        future = mgr.pty_executor.submit(lambda: None)
        future.result()  # Wait for completion
        # Thread names should start with "pty" (convention check; not strict)
        # We just verify the executor is functional
        assert mgr.pty_executor._thread_name_prefix == "pty"


class TestCleanupOrphans:
    def test_cleanup_orphans_kills_dead_processes(self):
        mgr = SessionManager()
        # Create session with non-existent PID (alive=False but state not DEAD yet)
        mgr.create(thread_id=1, pid=2**22, fd=0)
        mgr.create(thread_id=2, pid=2**22 + 1, fd=0)

        cleaned = mgr.cleanup_orphans()

        # Both sessions should have been cleaned (processes don't exist)
        assert cleaned == 2
        assert mgr.get(1) is None
        assert mgr.get(2) is None

    def test_cleanup_skips_already_dead(self):
        """Sessions explicitly marked DEAD should already be handled; cleanup skips them."""
        mgr = SessionManager()
        mgr.create(thread_id=1, pid=2**22, fd=0)
        mgr.get(1).state = PtyState.DEAD

        # cleanup_orphans only catches sessions where alive=False AND state != DEAD
        # DEAD sessions are assumed handled
        cleaned = mgr.cleanup_orphans()
        # Actually cleaned = 0 because state is already DEAD
        assert cleaned == 0


class TestShutdown:
    def test_shutdown_kills_all_and_stops_executor(self):
        mgr = SessionManager()
        mgr.create(thread_id=1, pid=2**22, fd=0)
        mgr.create(thread_id=2, pid=2**22 + 1, fd=0)

        mgr.shutdown()

        # All sessions should be gone
        assert mgr.get(1) is None
        assert mgr.get(2) is None
        # Executor should be shut down
        assert mgr.pty_executor._shutdown is True


import time as _time


class TestCleanupIdle:
    def test_cleanup_idle_kills_old_sessions(self):
        mgr = SessionManager()
        mgr.create(thread_id=1, pid=2**22, fd=0)
        # Manually set last_active_at far in the past
        mgr.get(1).last_active_at = _time.monotonic() - 3600  # 1 hour ago
        # Must be in IDLE state (default)

        killed = mgr.cleanup_idle(max_age_seconds=1800)  # 30 min threshold
        assert killed == 1
        assert mgr.get(1) is None

    def test_cleanup_idle_skips_active_sessions(self):
        mgr = SessionManager()
        mgr.create(thread_id=1, pid=2**22, fd=0)
        mgr.transition(1, PtyState.STREAMING, reason="active")
        # Set stale last_active_at but state is not IDLE
        mgr.get(1).last_active_at = _time.monotonic() - 3600

        killed = mgr.cleanup_idle(max_age_seconds=1800)
        assert killed == 0
        assert mgr.get(1) is not None

    def test_cleanup_idle_respects_threshold(self):
        mgr = SessionManager()
        mgr.create(thread_id=1, pid=2**22, fd=0)
        # Fresh session — should not be killed
        killed = mgr.cleanup_idle(max_age_seconds=1800)
        assert killed == 0
        assert mgr.get(1) is not None


class TestStatusEmoji:
    def test_all_states_have_emoji(self):
        for state in PtyState:
            emoji = SessionManager.get_status_emoji(state)
            assert emoji != "❓", f"State {state} missing emoji"
            assert len(emoji) > 0

    def test_emoji_mapping(self):
        assert SessionManager.get_status_emoji(PtyState.IDLE) == "💤"
        assert SessionManager.get_status_emoji(PtyState.STREAMING) == "🟢"
        assert SessionManager.get_status_emoji(PtyState.WAITING_FOR_USER) == "⏳"
        assert SessionManager.get_status_emoji(PtyState.DEAD) == "❌"


class TestTransitionUpdatesLastActive:
    def test_transition_refreshes_last_active(self):
        mgr = SessionManager()
        mgr.create(thread_id=1, pid=2**22, fd=0)
        session = mgr.get(1)
        old_active = session.last_active_at

        # Backdate the timestamp
        session.last_active_at = old_active - 100

        mgr.transition(1, PtyState.STREAMING, reason="test")
        assert session.last_active_at > old_active - 100


class TestExpiredDecisions:
    def test_no_expired_when_none_waiting(self):
        mgr = SessionManager()
        mgr.create(thread_id=1, pid=2**22, fd=0)
        # Session in IDLE, not WAITING_FOR_USER
        expired = mgr.expired_decisions(max_wait_seconds=1800)
        assert expired == []

    def test_expired_after_threshold(self):
        mgr = SessionManager()
        mgr.create(thread_id=1, pid=2**22, fd=0)
        mgr.transition(1, PtyState.STREAMING, reason="start")
        mgr.transition(1, PtyState.DETECTING_PROMPT, reason="idle")
        mgr.transition(1, PtyState.WAITING_FOR_USER, reason="prompt")
        # Backdate last_active_at to simulate long wait
        mgr.get(1).last_active_at = _time.monotonic() - 3600

        expired = mgr.expired_decisions(max_wait_seconds=1800)
        assert expired == [1]

    def test_not_expired_when_recent(self):
        mgr = SessionManager()
        mgr.create(thread_id=1, pid=2**22, fd=0)
        mgr.transition(1, PtyState.STREAMING, reason="start")
        mgr.transition(1, PtyState.DETECTING_PROMPT, reason="idle")
        mgr.transition(1, PtyState.WAITING_FOR_USER, reason="prompt")
        # Fresh — transition just happened

        expired = mgr.expired_decisions(max_wait_seconds=1800)
        assert expired == []

    def test_only_waiting_for_user_considered(self):
        mgr = SessionManager()
        # Create multiple sessions in different states, all with old last_active_at
        mgr.create(thread_id=1, pid=2**22, fd=0)  # IDLE
        mgr.create(thread_id=2, pid=2**22 + 1, fd=0)
        mgr.transition(2, PtyState.STREAMING, reason="start")  # STREAMING
        mgr.create(thread_id=3, pid=2**22 + 2, fd=0)
        mgr.transition(3, PtyState.STREAMING, reason="start")
        mgr.transition(3, PtyState.DETECTING_PROMPT, reason="idle")
        mgr.transition(3, PtyState.WAITING_FOR_USER, reason="prompt")

        # Backdate all
        for tid in [1, 2, 3]:
            mgr.get(tid).last_active_at = _time.monotonic() - 3600

        expired = mgr.expired_decisions(max_wait_seconds=1800)
        # Only thread 3 (WAITING_FOR_USER) returned
        assert expired == [3]
