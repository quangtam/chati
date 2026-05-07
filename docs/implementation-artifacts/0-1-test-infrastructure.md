# Story 0.1: Test Infrastructure Setup

Status: done

## Story

As a **developer**,
I want pytest infrastructure with shared fixtures and CI-safe PTY helpers,
so that TDD can proceed consistently without each story re-inventing test plumbing.

## Acceptance Criteria

1. `tests/conftest.py` exists with 5 shared fixtures: `in_memory_db`, `mock_provider`, `pty_process`, `session_context`, `telegram_update_factory`
2. `pytest-timeout` configured — any test exceeding 30s fails (not hangs)
3. `requirements-dev.txt` created with `pytest`, `pytest-asyncio`, `pytest-timeout`
4. PTY fixture force-kills process within 5s on test completion (pass or fail) — no zombie processes
5. All fixtures importable and functional — verified by a smoke test in `tests/test_conftest_smoke.py`

## Tasks / Subtasks

- [x] Task 1: Create `requirements-dev.txt` (AC: #3)
  - [x] Add `pytest>=8.0`, `pytest-asyncio>=0.23`, `pytest-timeout>=2.3`
  - [x] Verify install: `pip install -r requirements-dev.txt`
- [x] Task 2: Create `tests/conftest.py` with all fixtures (AC: #1, #2, #4)
  - [x] `in_memory_db` fixture — async, yields migrated SQLite `:memory:` connection
  - [x] `mock_provider` fixture — returns configurable `MockCliProvider` instance
  - [x] `pty_process` fixture — spawns real PTY with `cat`, force-kills on cleanup
  - [x] `session_context` fixture — depends on `in_memory_db`, provides seeded SessionManager-like context
  - [x] `telegram_update_factory` fixture — factory function returning fake `Update` objects
  - [x] Configure `pytest-timeout` default (30s) via `pytest.ini` or `conftest.py` marker
- [x] Task 3: Create `tests/test_conftest_smoke.py` (AC: #5)
  - [x] Test each fixture is importable and returns expected type
  - [x] Test PTY fixture spawns and cleans up
  - [x] Test in_memory_db fixture creates schema
- [x] Task 4: Add `pytest.ini` or `pyproject.toml` section for pytest config
  - [x] Set `asyncio_mode = auto`
  - [x] Set `timeout = 30`
  - [x] Set `testpaths = tests`

## Dev Notes

### Architecture Compliance

- **Naming**: `tests/test_{module}.py`, fixtures in `conftest.py` [Source: docs/planning-artifacts/architecture.md#Implementation Patterns]
- **Async**: All DB and PTY fixtures must be `async` — use `@pytest_asyncio.fixture` [Source: docs/planning-artifacts/architecture.md#Communication Patterns]
- **No global state**: Fixtures create fresh instances per test (no module-level singletons) [Source: docs/planning-artifacts/architecture.md#Enforcement Guidelines]

### Critical Implementation Details

**`in_memory_db` fixture:**
```python
@pytest_asyncio.fixture
async def in_memory_db():
    """Provides migrated in-memory SQLite for testing."""
    import aiosqlite
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("""
        CREATE TABLE thread_config (
            thread_id       INTEGER PRIMARY KEY,
            project_dir     TEXT NOT NULL,
            cli_provider    TEXT,
            model           TEXT,
            timeout_seconds INTEGER,
            last_active_at  TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    """)
    await db.commit()
    yield db
    await db.close()
```
[Source: docs/planning-artifacts/architecture.md#SQLite Access Pattern]

**`mock_provider` fixture:**
```python
@pytest.fixture
def mock_provider():
    """Configurable mock CliProvider for testing."""
    from cli_providers.base import CliProvider, CliProviderConfig

    class MockCliProvider(CliProvider):
        provider_id = "mock"
        name = "Mock CLI"
        default_cli_path = "echo"
        decision_prompt_patterns = []  # v2 extension

        def __init__(self, responses=None, **kwargs):
            config = CliProviderConfig(cli_path="echo", api_key="", trust_all_tools=True)
            super().__init__(config)
            self.responses = responses or ["mock response"]
            self.calls = []

        def build_args(self, prompt, *, model=None, resume=False):
            self.calls.append(("build_args", prompt, model, resume))
            return ["echo", prompt]

        def build_env(self, base_env):
            return base_env.copy()

    def _factory(responses=None):
        return MockCliProvider(responses=responses)

    return _factory
```
[Source: cli_providers/base.py — CliProvider ABC interface]

**`pty_process` fixture (CRITICAL — must prevent zombies):**
```python
@pytest_asyncio.fixture
async def pty_process():
    """Real PTY process for integration tests. Force-kills on cleanup."""
    import pty as pty_module
    import os
    import signal

    pid, fd = pty_module.fork()
    if pid == 0:
        # Child: run cat (echoes input back)
        os.execvp("cat", ["cat"])

    yield {"pid": pid, "fd": fd}

    # CLEANUP: Force kill within 5s — NEVER leave zombies
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        pass
    await asyncio.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
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
```
[Source: docs/planning-artifacts/architecture.md#Test Strategy]

**`telegram_update_factory` fixture:**
```python
@pytest.fixture
def telegram_update_factory():
    """Factory for fake Telegram Update objects."""
    from unittest.mock import MagicMock, AsyncMock

    def _create(
        user_id=123456789,
        chat_id=123456789,
        text="/start",
        message_thread_id=None,
    ):
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = user_id
        update.effective_chat = MagicMock()
        update.effective_chat.id = chat_id
        update.message = MagicMock()
        update.message.text = text
        update.message.message_thread_id = message_thread_id
        update.message.reply_text = AsyncMock()
        return update

    return _create
```
[Source: python-telegram-bot 21.10 Update object structure]

**`session_context` fixture:**
```python
@pytest_asyncio.fixture
async def session_context(in_memory_db):
    """Provides seeded thread_config data for session tests."""
    await in_memory_db.execute(
        "INSERT INTO thread_config (thread_id, project_dir, cli_provider, model) VALUES (?, ?, ?, ?)",
        (1001, "/home/test/project-a", "kiro", "sonnet"),
    )
    await in_memory_db.execute(
        "INSERT INTO thread_config (thread_id, project_dir) VALUES (?, ?)",
        (1002, "/home/test/project-b"),
    )
    await in_memory_db.commit()
    yield {"db": in_memory_db, "thread_ids": [1001, 1002]}
```

### Project Structure Notes

Files to create:
```
tests/
├── __init__.py              # Empty (makes tests a package for imports)
├── conftest.py              # All shared fixtures
└── test_conftest_smoke.py   # Verify fixtures work
requirements-dev.txt         # Test dependencies
pytest.ini                   # Pytest configuration
```

Files NOT to modify: No existing files are changed in this story.

### Dependencies

- `aiosqlite` must be installed (add to `requirements.txt` if not already there — needed for `in_memory_db` fixture)
- `python-telegram-bot==21.10` already installed (needed for understanding Update structure in mocks)

### Anti-Patterns to Avoid

- ❌ Do NOT use `time.sleep()` — use `asyncio.sleep()` in async fixtures
- ❌ Do NOT create module-level PTY processes — always per-test via fixture
- ❌ Do NOT skip force-kill cleanup — PTY zombies will kill CI
- ❌ Do NOT import from `db.py` or `session_manager.py` (they don't exist yet) — fixtures are self-contained for now
- ❌ Do NOT use `pytest-mock` — stdlib `unittest.mock` is sufficient

### References

- [Source: docs/planning-artifacts/architecture.md#Test Strategy & Priority]
- [Source: docs/planning-artifacts/architecture.md#Implementation Patterns]
- [Source: docs/planning-artifacts/architecture.md#SQLite Access Pattern]
- [Source: docs/planning-artifacts/architecture.md#Project Structure & Boundaries]
- [Source: docs/planning-artifacts/epics.md#Story 0.1]
- [Source: cli_providers/base.py — CliProvider ABC]
- [Source: cli_runner.py — _PtySession class]
- [Source: config.py — Config frozen dataclass]

## Dev Agent Record

### Agent Model Used

Claude (Auto) via Kiro

### Completion Notes List

- All 5 fixtures implemented and verified with 17 smoke tests (0.35s)
- PTY cleanup confirmed: zero orphan processes after test run
- `aiosqlite` added to requirements.txt for in_memory_db fixture
- pytest.ini configures asyncio_mode=auto, timeout=30s, testpaths=tests
- MockCliProvider implements full CliProvider ABC (build_args, build_env)
- Spike file `tests/spike_decision_forwarding.py` untouched — no conflicts

### File List

- `tests/__init__.py` (NEW)
- `tests/conftest.py` (NEW)
- `tests/test_conftest_smoke.py` (NEW)
- `requirements-dev.txt` (NEW)
- `pytest.ini` (NEW)
- `requirements.txt` (UPDATE — added `aiosqlite>=0.20.0`)
