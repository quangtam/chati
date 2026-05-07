# Story 2.1: Session Manager Extraction & PTY State Machine

Status: done

## Story

As a **developer**,
I want session lifecycle management extracted into `session_manager.py` with an explicit state machine,
so that PTY sessions have observable, debuggable state transitions.

## Acceptance Criteria

1. `session_manager.py` module created with `PtyState` enum (6 states: IDLE, STREAMING, DETECTING_PROMPT, WAITING_FOR_USER, PIPING_REPLY, DEAD)
2. `PtySession` dataclass exposes `state`, `pid`, `fd`, `thread_id`, `created_at` fields
3. `SessionManager` class owns session pool (`dict[int | None, PtySession]`) and exposes `get`, `create`, `kill`, `transition`, `list_all`, `get_state` methods
4. New session starts in `PtyState.IDLE`; transitions to `STREAMING` when prompt written
5. Output received in STREAMING state keeps state as STREAMING (no state change on normal read)
6. State transition logged at DEBUG level: `[PTY:{thread_id}] {old_state} → {new_state}: {reason}`
7. Invalid transition raises `RuntimeError` (e.g., IDLE → PIPING_REPLY without going through STREAMING)
8. `cli_runner.py` refactored to use `SessionManager` instead of raw `_PtySession` + `_sessions` dict
9. Backward-compatible: existing tests (`test_cmd_provider.py`) still pass without modification
10. Unit tests pass with ≥80% branch coverage

## Tasks / Subtasks

- [x] Task 1: Create `session_manager.py` (AC: #1, #2, #3)
  - [x] `PtyState` enum (6 states)
  - [x] `PtySession` dataclass with state field (non-frozen, state mutable)
  - [x] `SessionManager` class with session pool + lifecycle methods
  - [x] Define valid state transitions as class-level dict
- [x] Task 2: Implement state machine methods (AC: #4, #5, #6, #7)
  - [x] `create(thread_id, pid, fd)` → returns session in IDLE
  - [x] `transition(thread_id, new_state, reason)` → validates + logs
  - [x] `get_state(thread_id)` → current state or None
  - [x] Raise `RuntimeError` for invalid transitions
- [x] Task 3: Refactor `cli_runner.py` to use SessionManager (AC: #8, #9)
  - [x] Import `PtyState`, `PtySession`, `SessionManager` from session_manager
  - [x] Replace `_PtySession` class usage with `PtySession`
  - [x] Replace `self._sessions: dict` with `self._session_mgr: SessionManager`
  - [x] Keep `runner._sessions` property (returns session_mgr internal dict) for backward compat
  - [x] Call `transition()` at state change points: prompt written, prompt found, kill
- [x] Task 4: Tests (AC: #10)
  - [x] `tests/test_session_manager.py` — state machine transitions
  - [x] Test invalid transition raises RuntimeError
  - [x] Test state logged at DEBUG
  - [x] Test SessionManager.create/kill/get
  - [x] Verify `test_cmd_provider.py` still passes (backward compat check)

## Dev Notes

### Architecture Compliance

- `PtyState` + `PtySession` live in `session_manager.py` (owner of session objects) [Source: architecture.md#Key Design Decision]
- No circular dependency — `cli_runner.py` imports from `session_manager.py`, not vice versa
- `SessionManager` has NO knowledge of streaming I/O (that stays in cli_runner) [Source: architecture.md#Module Responsibility Boundaries]

### State Transition Map

```python
# Valid transitions: key = from_state, value = set of allowed to_states
VALID_TRANSITIONS = {
    PtyState.IDLE: {PtyState.STREAMING, PtyState.DEAD},
    PtyState.STREAMING: {PtyState.STREAMING, PtyState.DETECTING_PROMPT, PtyState.IDLE, PtyState.DEAD},
    PtyState.DETECTING_PROMPT: {PtyState.STREAMING, PtyState.WAITING_FOR_USER, PtyState.DEAD},
    PtyState.WAITING_FOR_USER: {PtyState.PIPING_REPLY, PtyState.DEAD},
    PtyState.PIPING_REPLY: {PtyState.STREAMING, PtyState.DEAD},
    PtyState.DEAD: set(),  # Terminal state
}
```

Self-transition `STREAMING → STREAMING` allowed (output received without state change).

### PtySession Design

```python
@dataclass
class PtySession:
    """PTY-backed CLI session with explicit lifecycle state."""
    thread_id: int | None
    pid: int
    fd: int
    state: PtyState = PtyState.IDLE
    created_at: float = field(default_factory=time.monotonic)
    ready: bool = False  # True once initial prompt reached

    @property
    def alive(self) -> bool:
        """Check if underlying PTY process is alive (state != DEAD)."""
        if self.state == PtyState.DEAD:
            return False
        try:
            os.kill(self.pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def write(self, data: str) -> None: ...
    def read(self, timeout: float = 1.0) -> str | None: ...
    def kill(self) -> None: ...  # sets state = DEAD
```

### SessionManager Interface

```python
class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[int | None, PtySession] = {}

    def get(self, thread_id: int | None) -> PtySession | None: ...
    def create(self, thread_id: int | None, pid: int, fd: int) -> PtySession: ...
    def kill(self, thread_id: int | None) -> bool: ...  # calls session.kill()
    def transition(self, thread_id: int | None, to_state: PtyState, reason: str = "") -> None: ...
    def get_state(self, thread_id: int | None) -> PtyState | None: ...
    def list_all(self) -> dict[int | None, PtySession]: ...  # returns copy
    def active_count(self) -> int: ...  # count of non-DEAD sessions
```

### Files to Modify

- `session_manager.py` (NEW) — ~180 lines: PtyState enum, PtySession dataclass, SessionManager class
- `cli_runner.py` (UPDATE) — replace `_PtySession` + `_sessions` dict with `SessionManager`
- `tests/test_session_manager.py` (NEW) — state machine + lifecycle tests

### Backward Compatibility

Existing tests expect `runner._sessions[thread_id]` access (e.g. `clean_runner._sessions.clear()` in test_cmd_provider.py). Keep this working via property:

```python
# In CliRunner
@property
def _sessions(self) -> dict[int | None, PtySession]:
    """Backward-compat: expose session_mgr's internal dict."""
    return self._session_mgr._sessions
```

### Anti-Patterns

- ❌ Don't put PtyState in cli_runner.py (would create circular dep when extracting further modules)
- ❌ Don't make transitions automatic — caller must explicitly call `transition()`
- ❌ Don't allow DEAD → * transitions (terminal state)
- ❌ Don't use singleton pattern for SessionManager (per-CliRunner instance is fine)

### References

- [Source: architecture.md#Core Architectural Decisions → Session Manager Extraction]
- [Source: architecture.md#Decision Forwarding Data Flow]
- [Source: cli_runner.py — existing _PtySession, _sessions dict]
- [Source: epics.md#Story 2.1]

## Dev Agent Record

### Agent Model Used

Claude (Auto) via Kiro

### Completion Notes List

- 26 new tests passing (session_manager); 96 total tests in 1.74s; zero regressions
- `PtyState` enum with 6 states + `VALID_TRANSITIONS` dict enforcing valid moves
- `PtySession` dataclass replaces old `_PtySession` class (backward-compatible interface: write, read, kill, alive)
- `SessionManager` owns pool — `create`, `get`, `kill`, `transition`, `get_state`, `list_all`, `active_count`
- State transitions logged at DEBUG: `[PTY:{thread_id}] {from} → {to}: {reason}`
- `cli_runner.py` now calls `_session_mgr.transition()` at key state change points (prompt written → STREAMING, response complete → IDLE, process died → DEAD)
- Backward-compat preserved: `runner._sessions` property (getter + setter) — existing test fixtures work unchanged
- Test strategy: fake PIDs (2^22) for state-only tests; real PTY via fixture only when alive checks matter

### File List

- `session_manager.py` (NEW) — 179 lines: PtyState enum, VALID_TRANSITIONS, PtySession dataclass, SessionManager class
- `cli_runner.py` (UPDATE) — removed `_PtySession` class; use `SessionManager`; added state transition calls
- `tests/test_session_manager.py` (NEW) — 26 tests covering enum, session, manager, transitions, logging
