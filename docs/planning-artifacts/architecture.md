---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
inputDocuments:
  - docs/planning-artifacts/prd.md
  - docs/architecture.md
  - docs/project-overview.md
  - docs/component-inventory.md
  - docs/source-tree-analysis.md
  - docs/development-guide.md
  - docs/deployment-guide.md
  - CLAUDE.md
workflowType: 'architecture'
lastStep: 8
status: 'complete'
completedAt: '2026-05-06'
project_name: 'Chati'
user_name: 'Tony'
date: '2026-05-06'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**

38 FRs across 8 capability areas. Architecturally significant groupings:

| Capability Area | FR Count | Architectural Impact |
|----------------|----------|---------------------|
| Session & Process Management | FR1-7 | Core orchestration layer redesign — concurrent sessions, lifecycle tracking |
| Adaptive Timeout | FR8-12 | New timeout state machine replacing simple countdown |
| Interactive Decision Forwarding | FR13-16 | New PTY state machine with human-in-the-loop flow |
| Multi-Project Management | FR17-23 | SQLite persistence layer, config resolution chain |
| CLI Information | FR24-27 | Provider abstraction extension, introspection methods |
| Output Processing | FR28-32 | Existing pipeline + media forwarding (screenshots) |
| Voice Communication | FR33-37 | External API integration layer (Growth phase) |
| Authentication | FR38 | Unchanged from v1 (whitelist decorator) |

**Non-Functional Requirements driving architecture:**

| NFR | Architectural Implication |
|-----|--------------------------|
| <1s warm stream start | Session pool must stay warm; no re-init on each message |
| <12s decision detection | Idle timer integrated into PTY read loop |
| 99% uptime | Systemd auto-restart, crash-safe SQLite, orphan cleanup |
| 5 concurrent PTY sessions | Bounded resource pool with eviction policy |
| WAL mode + busy_timeout | Specific SQLite connection configuration |
| Graceful degradation | Fallback paths for every external dependency |

**Scale & Complexity:**

- Primary domain: Async Python / subprocess orchestration
- Complexity level: Medium-High
- Estimated architectural components: 8-10
- New external dependency: `aiosqlite` (only addition to requirements.txt)

### Technical Constraints & Dependencies

| Constraint | Source | Impact |
|-----------|--------|--------|
| Single-process, single-machine | Deployment model (no horizontal scale needed) | Simplifies architecture — no distributed state |
| POSIX PTY required | `pty.fork()` for interactive sessions | Windows remains non-interactive fallback |
| Telegram 4096 char limit | API constraint | Message splitting logic unchanged |
| Telegram 30 edits/min/chat | API rate limit | Stream preview interval ≥1.5s |
| Python 3.12+ | Runtime requirement | Can use modern async patterns, `asyncio.TaskGroup` |
| Backward-compatible providers | Existing 4 providers must work unchanged | New provider methods must be optional with defaults |

### Cross-Cutting Concerns Identified

1. **Configuration Resolution** — 3-layer fallback (thread_config → .env → provider default) affects every command handler and session creation
2. **Error Handling & Graceful Degradation** — Every external touchpoint (CLI binary, Telegram API, SQLite, Whisper/TTS) needs fallback behavior
3. **Resource Lifecycle** — PTY sessions, SQLite connections, asyncio tasks all need coordinated cleanup on shutdown/crash
4. **Logging & Observability** — Session state transitions, decision forwarding events, resource usage all need structured logging for 99% uptime target
5. **Thread-awareness** — Every handler must resolve `thread_id` → config → session before acting; this is the new "request context" pattern

## Starter Template Evaluation

### Primary Technology Domain

Async Python / Telegram bot / subprocess orchestration — brownfield project with established codebase.

### Starter Template: Not Applicable

**Rationale:** Chati v2.0 is a brownfield evolution of v1.0.1. The project structure, tech stack, and architectural patterns are already established and proven in production. No starter template or scaffolding tool is needed.

### Inherited Architectural Foundation (from v1.0.1)

**Language & Runtime:**
- Python 3.12+ with type hints throughout
- Async-first design (`async def` handlers, `asyncio` event loop)
- No transpilation or build step — direct Python execution

**Project Structure (maintained):**
```
chati.py              # Entry point + Telegram handlers
cli_runner.py         # Subprocess orchestration + PTY management
config.py             # Frozen dataclass from .env
message_utils.py      # Output pipeline (ANSI strip, MD→HTML, split)
cli_providers/        # Pluggable driver package (auto-discovery)
```

**Dependencies (minimal, intentional):**
- `python-telegram-bot==21.10` — async Telegram SDK
- `python-dotenv==1.1.0` — .env loading
- `aiosqlite` (NEW for v2) — async SQLite access

**Patterns Established:**
- Pluggable Strategy pattern for CLI providers (auto-discovery via `pkgutil`)
- Frozen dataclass for immutable configuration
- Decorator-based auth (`@authorized`)
- Per-thread state isolation via dict keying (→ migrating to SQLite in v2)
- Streaming via progressive message edits

### v2.0 Structural Changes (Planned)

| Change | From (v1) | To (v2) | Rationale |
|--------|-----------|---------|-----------|
| State storage | In-memory dicts | SQLite + `aiosqlite` | Persist across restart (FR22) |
| Session management | Inline in `cli_runner.py` | Extracted session manager module | Complexity warrants separation (FR5-7) |
| PTY read loop | Simple stream → done | State machine with decision detection | FR13-16 require intermediate states |
| Config resolution | Single `.env` lookup | 3-layer fallback chain | Per-thread overrides (FR23) |
| Provider interface | `build_args` + `build_env` | + `parse_usage_output` + `status_info` | `/info` command (FR24-25) |

**Note:** No new files are created by a starter command. New modules will be introduced incrementally as epics are implemented.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
1. PTY State Machine Design — affects all streaming and decision forwarding code
2. Session Manager Extraction — affects module structure and all session-related features
3. SQLite Access Pattern — affects every command handler that reads/writes config

**Important Decisions (Shape Architecture):**
4. Decision Forwarding Detection Strategy — affects reliability of core v2 feature
5. Media Handler Architecture — affects Growth phase extensibility

**Deferred Decisions (Post-MVP):**
- Voice API provider selection (OpenAI Whisper vs alternatives) — defer to Growth phase
- TTS provider selection — defer to Growth phase
- Log aggregation tooling — defer until 99% uptime monitoring is needed

### Data Architecture

**Database:** SQLite via `aiosqlite`
- WAL mode mandatory, busy_timeout=5000ms
- Single file: `chati.db` in project root
- Schema defined in PRD (thread_config table)

**Access Pattern:** Repository functions in `db.py`
- Each function opens/closes its own connection
- No shared connection across coroutines
- Functions: `get_thread_config()`, `upsert_thread_config()`, `list_all_threads()`, `update_last_active()`
- Schema migration on startup (create tables if not exist)
- Testable with in-memory SQLite (`:memory:`)

**Rationale:** Connection-per-operation is simple, avoids asyncio lifecycle issues, and SQLite overhead is negligible for <100 threads. Repository pattern keeps DB logic isolated from business logic.

### Authentication & Security

**No changes from v1.0.1** — all decisions inherited:
- `@authorized` decorator checks `ALLOWED_USER_IDS`
- Telegram Bot token in `.env` only
- `CLI_TRUST_ALL_TOOLS` documented as explicit security trade-off
- No new auth mechanisms needed (single-user tool)

### Process & Session Architecture

**PTY State Machine:** Enum-based explicit states

```python
class PtyState(Enum):
    IDLE = "idle"                        # Session alive, no active task
    STREAMING = "streaming"              # Receiving output from CLI
    DETECTING_PROMPT = "detecting_prompt" # Idle threshold counting (12s)
    WAITING_FOR_USER = "waiting_for_user" # Prompt forwarded, timeout paused
    PIPING_REPLY = "piping_reply"        # User replied, piping to PTY
    DEAD = "dead"                        # Process exited or killed
```

**State Transitions:**
```
IDLE → STREAMING (user sends message, prompt written to PTY)
STREAMING → STREAMING (output received, timeout reset)
STREAMING → DETECTING_PROMPT (no output for 12s)
DETECTING_PROMPT → STREAMING (output resumes — false alarm)
DETECTING_PROMPT → WAITING_FOR_USER (prompt pattern matched)
WAITING_FOR_USER → PIPING_REPLY (user replies)
PIPING_REPLY → STREAMING (reply written, output resumes)
STREAMING → IDLE (response marker detected, task complete)
ANY → DEAD (process killed, timeout exceeded, crash)
```

**Rationale:** Explicit states enable structured logging of transitions (critical for 99% uptime debugging), clean timeout management (pause/resume per state), and testable state machine logic.

**Session Manager:** Extracted to `session_manager.py`

```python
class SessionManager:
    """Owns session pool, lifecycle, and resource enforcement."""
    _sessions: dict[int | None, PtySession]
    _max_sessions: int  # default 5, from .env

    async def get_or_create(self, thread_id, config) -> PtySession
    async def kill(self, thread_id) -> None
    async def kill_all(self) -> None
    async def cleanup_idle(self, max_idle_seconds=1800) -> list[int]
    async def cleanup_orphans(self) -> None  # startup only
    def get_status(self, thread_id) -> PtyState
    def list_all(self) -> dict[int, SessionInfo]
```

**Rationale:** Session lifecycle (create, kill, cleanup, orphan detection, max enforcement) is distinct from I/O streaming. Extraction enables: independent testing, clear resource boundaries, `/sessions` command implementation without touching streaming code.

### Decision Forwarding Detection

**Strategy:** Hybrid (generic heuristic + provider-specific patterns)

**Generic Detection (default for all providers):**
- Trigger: no output for ≥12 seconds (configurable idle threshold)
- Confirmation: last line matches common prompt patterns: `[y/N]`, `[Y/n]`, `(yes/no)`, ends with `?`
- If both conditions met → forward prompt to user

**Provider-Specific Extension:**
```python
class CliProvider:
    # Optional override — providers without this use generic detection
    decision_prompt_patterns: list[re.Pattern] = []
    decision_prompt_timeout: int = 12  # seconds, overridable
```

**Rationale:** Generic heuristic handles 80%+ of cases across all providers. Provider-specific patterns catch edge cases (e.g., Kiro's specific confirmation format). Backward-compatible — existing providers work without changes.

### Media & Output Architecture

**Strategy:** Simple conditional in output pipeline (no plugin system)

**Implementation approach:**
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

**Rationale:** YAGNI — only 2 media types planned (screenshots, voice). Plugin architecture is over-engineering for a solo-dev project with known, bounded media types. Refactor to plugin pattern only if a third media type emerges.

### Infrastructure & Deployment

**No changes from v1.0.1** — all decisions inherited:
- Single-process, single-machine deployment
- systemd for production (auto-restart on failure)
- Docker optional (for reproducibility)
- `./chati start|stop|restart|status|log` management scripts
- No CI/CD pipeline (solo dev, manual deploy via `git pull && ./chati restart`)

**New for v2:**
- `chati.db` file added to backup considerations
- Orphan process cleanup on startup (new in session manager)
- Memory monitoring: log warning if RSS > 500MB

### Decision Impact Analysis

**Implementation Sequence (dependency order):**
1. `db.py` — SQLite repository (no dependencies, foundation for everything)
2. `session_manager.py` — extract from `cli_runner.py` (depends on PtyState enum)
3. PTY state machine refactor in `cli_runner.py` (depends on session_manager)
4. Decision forwarding logic (depends on state machine)
5. New command handlers (`/project`, `/projects`, `/provider`, `/sessions`, `/info`)
6. Media handlers (Growth — depends on stable MVP)

**Cross-Component Dependencies:**
```
db.py ← session_manager.py ← cli_runner.py ← chati.py (handlers)
                                    ↑
                            cli_providers/ (detection patterns)
```

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**8 conflict areas** where AI agents could make different choices when implementing v2 features on top of v1 codebase.

### Naming Patterns

**Python Module & File Naming:**
- All modules: `snake_case.py` (e.g., `session_manager.py`, `db.py`)
- Classes: `PascalCase` (e.g., `SessionManager`, `PtyState`, `ThreadConfig`)
- Functions/methods: `snake_case` (e.g., `get_thread_config`, `cleanup_idle`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `MAX_SESSIONS`, `IDLE_WARN_INTERVAL`)
- Private methods: `_leading_underscore` (e.g., `_stream_pty`, `_kill_session`)
- Type aliases: `PascalCase` (e.g., `ThreadId = int | None`)

**SQLite Naming:**
- Tables: `snake_case`, singular (e.g., `thread_config`, not `thread_configs`)
- Columns: `snake_case` (e.g., `thread_id`, `project_dir`, `last_active_at`)
- Timestamps: `TEXT` with ISO 8601 format via `datetime('now')` — not Unix epoch

**Telegram Command Naming:**
- Commands: lowercase, no separators (e.g., `/info`, `/sessions`, `/projects`)
- Multi-word commands: concatenated (e.g., `/newproject` not `/new_project`) — but prefer single-word
- BMAD routing: underscore in Telegram (`/bmad_create_prd`) → hyphen for CLI (`/bmad-create-prd`)

**Log Messages:**
- Format: `f"[{module}] {action}: {detail}"` (e.g., `[SessionManager] cleanup_idle: killed 2 sessions`)
- Levels: `DEBUG` for state transitions, `INFO` for user actions, `WARNING` for degradation, `ERROR` for failures

### Structure Patterns

**Project Organization (v2 target):**
```
chati.py              # Entry point — handlers only, delegates to modules
cli_runner.py         # PTY I/O streaming (state machine lives here)
session_manager.py    # NEW — session pool, lifecycle, resource enforcement
db.py                 # NEW — SQLite repository functions
config.py             # Frozen dataclass from .env (unchanged)
message_utils.py      # Output pipeline (unchanged)
cli_providers/        # Pluggable drivers (extended with detection patterns)
```

**Rules:**
- No nested packages beyond `cli_providers/` — flat root structure
- Each module has a single responsibility (one reason to change)
- New modules only when existing file would exceed ~500 lines or mix concerns
- No `utils/` or `helpers/` catch-all packages — name modules by what they do

**Test Organization (when added):**
- Tests in `tests/` directory at project root
- Mirror source structure: `tests/test_db.py`, `tests/test_session_manager.py`
- Test file naming: `test_{module_name}.py`
- Use `pytest` with `pytest-asyncio` for async tests

### Format Patterns

**Configuration Values:**
- `.env` keys: `UPPER_SNAKE_CASE` (e.g., `CLI_TIMEOUT`, `MAX_SESSIONS`)
- SQLite config values: stored as-is (TEXT for strings, INTEGER for numbers, NULL for "use default")
- Boolean in `.env`: string `"true"` / `"false"` (parsed with `val.lower() == "true"`)

**Telegram Message Formatting:**
- All bot responses: Telegram HTML (not Markdown) — `<b>`, `<code>`, `<pre>`, `<i>`
- Error messages: plain text (no HTML) to avoid parse failures on error path
- Status indicators: emoji prefix (🟢 ⏳ 💤 ❌ ⚠️ ✅ 💳)
- Inline keyboards: `callback_data` format = `{action}:{value}` (e.g., `model:sonnet`, `project:/home/user/app`)

**Dataclass Patterns:**
- Immutable config: `@dataclass(frozen=True)` (existing pattern from `Config`)
- Mutable state: regular `@dataclass` with type hints (e.g., `SessionInfo`)
- No `attrs` or `pydantic` — stdlib `dataclasses` only (zero new deps philosophy)

### Communication Patterns

**Async Patterns:**
- All I/O-bound functions: `async def`
- Blocking I/O (PTY read, `os.read`): wrap in `loop.run_in_executor(None, ...)`
- Per-thread serialization: `asyncio.Lock` per `thread_id` (unchanged from v1)
- Background tasks: `asyncio.create_task()` with proper exception handling via `task.add_done_callback()`
- Task cancellation: always handle `asyncio.CancelledError` gracefully

**State Transitions (PTY State Machine):**
- All transitions logged at `DEBUG` level: `f"[PTY:{thread_id}] {old_state} → {new_state}: {reason}"`
- Invalid transitions raise `RuntimeError` (programming error, not user error)
- State checks before actions: `if session.state != PtyState.IDLE: raise BusyError(...)`

**Inter-module Communication:**
- No global mutable state — pass dependencies via constructor or function args
- `chati.py` creates `SessionManager` and `CliRunner` at startup, passes to handlers
- Handlers receive context via `python-telegram-bot`'s `context.bot_data` dict

### Process Patterns

**Error Handling:**
- User-facing errors: catch, log at `ERROR`, send friendly message to Telegram
- Programming errors: let crash, systemd restarts (fail-fast for bugs)
- External service errors (Telegram API, CLI binary): catch, log at `WARNING`, graceful fallback
- SQLite errors: catch `aiosqlite.Error`, log, retry once, then report to user
- Never swallow exceptions silently — always log or re-raise

**Error Message Format (to user):**
```
⚠️ {short description}
{one-line context if helpful}
{suggested action if applicable}
```
Example: `⚠️ CLI binary not found\nExpected: kiro-cli\nRun: kiro-cli login`

**Graceful Shutdown:**
- On SIGTERM/SIGINT: kill all PTY sessions, close SQLite connections, then exit
- On crash: systemd restarts, startup runs `cleanup_orphans()`
- PID file: write on start, remove on clean exit, check-and-clean on startup if stale

**Resource Cleanup Pattern:**
```python
# Always use try/finally for resources
session = await session_manager.get_or_create(thread_id, config)
try:
    async for chunk in cli_runner.stream(session, prompt):
        yield chunk
finally:
    await session_manager.update_last_active(thread_id)
```

### Enforcement Guidelines

**All AI Agents implementing Chati v2 MUST:**

1. Follow existing v1 code style — read `chati.py` and `cli_runner.py` before writing new code
2. Use `async def` for any function that touches I/O (SQLite, PTY, Telegram API)
3. Use type hints on all function signatures (return types included)
4. Use f-strings for string formatting (no `.format()` or `%`)
5. Use double quotes for strings consistently
6. Log state transitions at DEBUG, user actions at INFO, failures at ERROR
7. Handle `asyncio.CancelledError` in any long-running coroutine
8. Never introduce new dependencies without explicit approval — stdlib + existing deps first
9. Keep functions under 50 lines where possible — extract helpers when logic is complex
10. Write docstrings for public classes and functions (one-line summary minimum)

**Anti-Patterns (NEVER do these):**
- ❌ Global mutable state (use dependency injection via constructors)
- ❌ Bare `except:` or `except Exception:` without logging
- ❌ Synchronous I/O in async context (blocks event loop)
- ❌ `time.sleep()` in async code (use `asyncio.sleep()`)
- ❌ Hardcoded magic numbers (use named constants)
- ❌ Nested callbacks deeper than 2 levels (refactor to sequential async)
- ❌ `import *` (always explicit imports)

## Project Structure & Boundaries

### Complete Project Directory Structure

```
chati/
├── chati.py                    # Entry point: Telegram handlers, command routing, streaming orchestration
├── cli_runner.py               # PTY I/O: state machine transitions, streaming, decision detection
├── session_manager.py          # NEW: session pool, lifecycle, cleanup, PtyState enum, PtySession class
├── db.py                       # NEW: SQLite repository (async context manager pattern)
├── config.py                   # Frozen dataclass from .env (unchanged)
├── message_utils.py            # Output pipeline: ANSI strip, MD→HTML, split (unchanged)
│
├── cli_providers/              # Pluggable CLI driver package
│   ├── __init__.py             # Re-exports: CliProvider, create_provider, get_available_providers
│   ├── base.py                 # CliProvider ABC (extended: decision_prompt_patterns, parse_usage_output)
│   ├── registry.py             # Auto-discovery via pkgutil (unchanged)
│   ├── kiro.py                 # Kiro driver (+ decision_prompt_patterns)
│   ├── claude.py               # Claude Code driver (+ decision_prompt_patterns)
│   ├── gemini.py               # Gemini driver
│   └── codex.py                # Codex driver
│
├── tests/                      # NEW: test suite
│   ├── conftest.py             # Shared fixtures (in-memory SQLite, mock providers, PTY process)
│   ├── test_cli_runner.py      # State machine transition tests (HIGHEST PRIORITY)
│   ├── test_integration_pty.py # Integration: real PTY flows (spawn→stream→complete, cancel, timeout)
│   ├── test_session_manager.py # Session lifecycle, concurrent sessions, cleanup
│   ├── test_db.py              # SQLite repository CRUD tests
│   ├── test_message_utils.py   # Output pipeline tests (pure functions)
│   └── test_providers.py       # Provider build_args/detection pattern tests
│
├── chati                       # Bash management script (start/stop/restart/status/log)
├── chati.bat                   # Windows management script
├── setup.sh                    # Interactive setup wizard (POSIX)
├── setup.bat                   # Interactive setup wizard (Windows)
│
├── .env                        # Runtime secrets (GITIGNORED)
├── .env.example                # Template with all env var documentation
├── chati.db                    # NEW: SQLite database (GITIGNORED, created on first run)
├── chati.log                   # Log output (GITIGNORED)
├── .chati.pid                  # PID file (GITIGNORED)
│
├── requirements.txt            # python-telegram-bot, python-dotenv, aiosqlite
├── requirements-dev.txt        # NEW: pytest, pytest-asyncio, pytest-timeout
├── .gitignore                  # Excludes .env, .venv, *.db, *.log, *.pid, __pycache__
├── CLAUDE.md                   # AI agent context (updated for v2)
├── README.md                   # User-facing documentation
├── LICENSE                     # MIT
│
├── docs/                       # Project documentation
│   ├── planning-artifacts/     # PRD, architecture (this doc), epics
│   ├── implementation-artifacts/ # Sprint status, stories
│   └── ...                     # Setup guides, overview, etc.
│
└── assets/                     # Static assets for README
    ├── demo.mp4
    └── screenshot.jpg
```

### Architectural Boundaries

**Module Responsibility Boundaries:**

| Module | Owns | Does NOT own |
|--------|------|-------------|
| `chati.py` | Telegram handlers, command routing, streaming UX (edits, typing), media sending, decision forwarding UX | PTY I/O, session lifecycle, database access |
| `cli_runner.py` | PTY read/write, state machine transitions, decision detection, timeout logic | Session creation/destruction, config resolution, Telegram messaging |
| `session_manager.py` | `PtyState` enum, `PtySession` class, session pool, max enforcement, idle cleanup, orphan detection, status reporting | PTY I/O, streaming, Telegram interaction |
| `db.py` | SQLite CRUD, schema migration, async context manager for connections | Business logic, validation beyond type checks |
| `config.py` | `.env` loading, validation, immutable config object | Dynamic config (that's SQLite's job) |
| `message_utils.py` | Text transformation (ANSI→clean→HTML→split) | Telegram API calls, file I/O |
| `cli_providers/` | CLI command construction, env setup, detection patterns, usage parsing | Subprocess execution (that's cli_runner's job) |

**Key Design Decision: PtyState lives in `session_manager.py`**

`session_manager.py` owns `PtyState` enum and `PtySession` dataclass because it owns session objects. `cli_runner.py` imports from `session_manager` — no circular dependency.

### Decision Forwarding Data Flow (Option B — Break + Resume)

```
Phase 1: Stream until decision detected
─────────────────────────────────────────
chati.py calls: cli_runner.execute_stream(session, prompt)
    → async generator yields str chunks (normal output)
    → state machine: IDLE → STREAMING
    → idle threshold hit + prompt pattern matched
    → state machine: STREAMING → DETECTING_PROMPT → WAITING_FOR_USER
    → generator yields DecisionPrompt object
    → generator RETURNS (ends — no zombie generator in memory)

Phase 2: Forward to user and wait
─────────────────────────────────────────
chati.py receives DecisionPrompt
    → formats prompt with context
    → sends to Telegram
    → stores pending_decision[thread_id] = True
    → waits for user reply (no generator held)

Phase 3: Pipe reply and resume streaming
─────────────────────────────────────────
User replies → chati.py detects pending_decision[thread_id]
    → calls: cli_runner.pipe_reply_stream(session, user_answer)
    → state machine: WAITING_FOR_USER → PIPING_REPLY → STREAMING
    → NEW async generator yields remaining output
    → stream completes → state machine: STREAMING → IDLE
```

**Type contract:**
```python
# cli_runner.py
async def execute_stream(
    session: PtySession, prompt: str
) -> AsyncGenerator[str | DecisionPrompt, None]:
    """Yields output chunks. If DecisionPrompt yielded, generator ends."""
    ...

async def pipe_reply_stream(
    session: PtySession, reply: str
) -> AsyncGenerator[str | DecisionPrompt, None]:
    """Pipes reply to PTY, yields remaining output. May yield another DecisionPrompt."""
    ...
```

**Rationale:** No generator zombie in memory during user think-time. Each phase is a separate function call — testable independently. Aligns with state machine (WAITING_FOR_USER = no active generator). Handles chained decisions (pipe_reply_stream can also yield DecisionPrompt).

### SQLite Access Pattern (Async Context Manager)

```python
# db.py
from contextlib import asynccontextmanager
import aiosqlite

DB_PATH = "chati.db"

@asynccontextmanager
async def get_db():
    """Async context manager for SQLite connections."""
    db = await aiosqlite.connect(DB_PATH, timeout=30)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    try:
        yield db
        await db.commit()
    finally:
        await db.close()

# Usage:
async def get_thread_config(thread_id: int) -> ThreadConfig | None:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM thread_config WHERE thread_id = ?", (thread_id,)
        )
        row = await cursor.fetchone()
        return ThreadConfig(**row) if row else None
```

**Rationale:** Context manager prevents connection leaks on exceptions. `row_factory = Row` enables dict-like access. Each function is self-contained and testable with in-memory SQLite.

### Requirements to Structure Mapping

**MVP Feature → Module Mapping:**

| MVP Feature | Primary Module | Supporting Modules |
|-------------|---------------|-------------------|
| Adaptive timeout | `cli_runner.py` (state machine) | `session_manager.py` (per-thread timeout from config) |
| Decision forwarding | `cli_runner.py` (detection + yield) + `chati.py` (forwarding UX + pipe_reply) | `cli_providers/` (patterns) |
| Parallel multi-project | `session_manager.py` + `db.py` | `chati.py` (commands), `config.py` (MAX_SESSIONS) |
| `/info` command | `chati.py` (handler) | `cli_providers/` (usage parsing), `db.py` (session stats) |
| `/project` + `/projects` | `chati.py` (handlers) | `db.py` (CRUD + history query) |
| `/provider` + `/sessions` | `chati.py` (handlers) | `db.py`, `session_manager.py` (status) |
| SQLite persistence | `db.py` | All modules that read/write config |

**Cross-Cutting Concerns → Location:**

| Concern | Where it lives |
|---------|---------------|
| Config resolution (3-layer) | Handler resolves: `db.get_thread_config()` → `config.py` defaults → provider default |
| Error handling | Each module handles its own; `chati.py` is final catch-all for user messaging |
| Logging | Python stdlib `logging` per module; format per patterns doc |
| Resource cleanup | `session_manager.py` owns cleanup; `chati.py` triggers on shutdown signal |
| Auth | `chati.py` only (`@authorized` decorator) |

### Test Strategy & Priority

**Test priority (risk-based, highest first):**

1. **`test_cli_runner.py`** — State machine transitions (highest risk: complex, async, race conditions)
2. **`test_integration_pty.py`** — Real PTY flows with simple commands (`cat`, `echo`). Tests: spawn→stream→complete, cancel mid-stream, timeout→cleanup, concurrent isolation
3. **`test_session_manager.py`** — Session lifecycle, max enforcement, idle cleanup
4. **`test_message_utils.py`** — Pure functions, easy wins, high ROI
5. **`test_db.py`** — CRUD with in-memory SQLite (low risk, SQLite is battle-tested)
6. **`test_providers.py`** — Provider registry, detection patterns

**Critical test fixtures (conftest.py):**
- `in_memory_db` — SQLite `:memory:` with migrated schema
- `mock_provider` — Deterministic output, configurable responses
- `pty_process` — Real PTY with `cat`/`echo`, **force-kill cleanup with timeout**
- `session_context` — SessionManager with seeded data
- `telegram_update_factory` — Factory for fake Telegram Update objects

**Test dependencies:** `pytest`, `pytest-asyncio`, `pytest-timeout` (mandatory — PTY hang = CI hang)

### Integration Points

**Internal Communication:**
- Modules communicate via function calls and return values (no message bus)
- `chati.py` is orchestrator — calls other modules; they don't call each other
- Exception: `cli_runner.py` imports `PtyState`/`PtySession` from `session_manager.py` and calls `cli_providers/` for patterns

**External Integrations:**

| External System | Integration Point | Protocol |
|----------------|-------------------|----------|
| Telegram Bot API | `chati.py` via `python-telegram-bot` | HTTPS long polling |
| CLI subprocesses | `cli_runner.py` via `pty.fork()` / `asyncio.subprocess` | PTY fd read/write |
| SQLite | `db.py` via `aiosqlite` | File I/O (WAL mode) |
| Whisper API (Growth) | `chati.py` (inline) | HTTPS REST |
| TTS API (Growth) | `chati.py` (inline) | HTTPS REST |

### File Change Summary for v2

**New files:**
1. `db.py` — ~120-150 lines (context manager + repository functions + migration)
2. `session_manager.py` — ~200-250 lines (PtyState, PtySession, SessionManager)
3. `tests/` — 7 test files + conftest
4. `requirements-dev.txt` — test dependencies

**Modified files:**
1. `cli_runner.py` — refactored: remove session management, add state machine, implement execute_stream + pipe_reply_stream
2. `chati.py` — new command handlers, refactor `_execute_and_reply` into smaller methods, decision forwarding UX
3. `cli_providers/base.py` — add optional `decision_prompt_patterns`, `parse_usage_output()`
4. `cli_providers/kiro.py`, `claude.py` — add provider-specific detection patterns
5. `requirements.txt` — add `aiosqlite`
6. `.env.example` — add `MAX_SESSIONS`, document new vars
7. `.gitignore` — add `*.db`
8. `CLAUDE.md` — update for v2 architecture

**Unchanged:** `config.py`, `message_utils.py`, `cli_providers/registry.py`, `__init__.py`, `gemini.py`, `codex.py`, management scripts, setup scripts

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**
- Python 3.12+ ↔ `aiosqlite` ↔ `asyncio` ↔ `python-telegram-bot` 21.10 — all async-native, no conflicts
- SQLite WAL mode ↔ `aiosqlite` context manager — compatible (WAL set per-connection)
- Enum-based state machine ↔ session manager extraction — clean separation, no circular deps
- Hybrid decision detection ↔ provider ABC extension — backward-compatible (optional methods)

**Pattern Consistency:**
- Naming: snake_case modules/functions, PascalCase classes — consistent with v1
- Async: all I/O functions are `async def` — no sync/async mixing
- Error handling: each module owns its errors, chati.py is catch-all — uniform
- Logging: structured `[Module] action: detail` format — uniform across modules

**Structure Alignment:**
- Flat root supports all decisions (no deep nesting needed)
- `session_manager.py` owns PtyState → `cli_runner.py` imports → no circular dependency
- `db.py` standalone (no app module imports) → testable in isolation
- `cli_providers/` extension is additive → backward-compatible

### Requirements Coverage ✅

All 38 FRs have architectural support. All NFRs addressed. No gaps in coverage.

### Implementation Readiness ✅

All decisions documented with rationale. Code examples for key patterns. Module boundaries explicit. Requirements-to-module mapping complete.

### Critical Issues Found & Resolved (from Party Mode Review)

#### Issue 1: Thread Pool Starvation Risk

**Problem:** Each PTY session uses `loop.run_in_executor()` with blocking `select.select()` for reads. Default executor has limited threads (~8). With 5 concurrent sessions each holding a thread for reads, new session spawns could deadlock silently.

**Resolution:** Use dedicated `ThreadPoolExecutor` for PTY operations:
```python
# In cli_runner.py or session_manager.py initialization
import concurrent.futures
pty_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="pty"
)
# Usage:
await loop.run_in_executor(pty_executor, blocking_pty_read, fd, timeout)
```
This isolates PTY blocking I/O from the default executor, preventing starvation of other async operations.

#### Issue 2: Message Handling During WAITING_FOR_USER

**Problem:** When a decision prompt is pending and user sends another message in the same thread — is it a decision reply or a new prompt? Architecture didn't specify.

**Resolution:** Explicit behavior documented:
- If `pending_decision[thread_id]` is set, **treat next message as decision reply** (pipe to PTY)
- If user sends `/cancel` while decision pending → kill session, clear pending state
- If user sends `/new` while decision pending → kill session, start fresh
- Other commands (`/info`, `/sessions`, `/status`) work normally regardless of pending state
- Only free-form text is intercepted as decision reply

#### Issue 3: Per-Thread State Isolation

**Problem:** `context.user_data` is per-user, not per-thread. Storing thread-specific state there causes cross-thread pollution (e.g., `/new` in thread A affects thread B).

**Resolution:** Use `context.bot_data` with thread_id keys for all thread-specific runtime state:
```python
# Instead of: context.user_data["model"] (per-user, shared across threads)
# Use: context.bot_data[f"thread:{thread_id}:pending_decision"] (per-thread)
```
Persistent config (model, provider, project_dir) already lives in SQLite per-thread. Runtime state (pending_decision, stream_task) uses `bot_data` with thread_id prefix.

#### Issue 4: Decision Detection False Positives

**Problem:** Generic heuristic (idle 12s + ends with `?`) will false-positive on CLI explanations containing question marks or "Do you want to..." in prose.

**Resolution:** Two-layer confirmation:
1. **Idle threshold** (12s no output) — necessary condition
2. **Pattern match on LAST LINE only** — `[y/N]`, `[Y/n]`, `(yes/no)`, or provider-specific patterns
3. **Exclude if last line > 100 chars** — real prompts are short; explanations are long
4. **Tunable per-provider** — `decision_prompt_timeout` and `decision_prompt_max_line_length` overridable

This reduces false positives significantly. Remaining edge cases handled by user: if bot incorrectly forwards a non-prompt, user just sends their intended message and it goes to CLI as normal text.

#### Issue 5: Backpressure in Streaming

**Problem:** CLI can output faster than Telegram rate limit allows message edits (30/min/chat). Buffer could grow unbounded.

**Resolution:** Already handled by existing v1 design (maintained in v2):
- `_STREAM_PREVIEW_MAX = 3000` chars — buffer truncated to last N lines
- Message edits every 1.5s — rate-limited by design
- Final response sent after stream completes — no real-time pressure
- If Telegram API rejects edit (rate limit), skip that edit cycle, try next interval

No architectural change needed — existing pattern is sufficient.

### Architecture Completeness Checklist

**Requirements Analysis**
- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped

**Architectural Decisions**
- [x] Critical decisions documented with versions
- [x] Technology stack fully specified
- [x] Integration patterns defined
- [x] Performance considerations addressed

**Implementation Patterns**
- [x] Naming conventions established
- [x] Structure patterns defined
- [x] Communication patterns specified
- [x] Process patterns documented

**Project Structure**
- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] Requirements to structure mapping complete

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High — all 16 checklist items verified, critical issues from peer review resolved, all FRs covered.

**Key Strengths:**
- Minimal new dependencies (only `aiosqlite`) — low risk surface
- Clear module boundaries with explicit ownership tables
- Decision forwarding pattern (Option B) is testable and zombie-free
- State machine is explicit and loggable — supports 99% uptime debugging
- Backward-compatible provider extension
- Thread pool isolation prevents silent deadlocks
- Per-thread state isolation via `bot_data` + SQLite

**Recommended Spike Before Full Implementation:**

Before committing to full implementation, run a focused spike:
1. Create mock PTY that yields a DecisionPrompt after 5s of output
2. Let generator return (Option B pattern)
3. Wait 2-3 minutes (simulating user think-time)
4. Send 2-3 other messages from same user (different threads)
5. Send decision reply
6. Call `pipe_reply_stream()` and verify output resumes cleanly
7. Verify: no memory leak, no zombie generators, no thread pool exhaustion

If spike passes → proceed with full implementation. If not → fallback to explicit state + callback (more verbose but more debuggable).

### Implementation Handoff

**AI Agent Guidelines:**
- Follow all architectural decisions exactly as documented
- Use implementation patterns consistently across all components
- Respect project structure and boundaries
- Use dedicated `pty_executor` for all blocking PTY operations
- Store per-thread runtime state in `context.bot_data[f"thread:{thread_id}:..."]`
- Refer to this document for all architectural questions

**Implementation Sequence (TDD — test accompanies each module):**
1. `tests/test_db.py` + `db.py` — SQLite repository (foundation)
2. `tests/test_session_manager.py` + `session_manager.py` — PtyState, PtySession, SessionManager
3. `tests/test_cli_runner.py` + `cli_runner.py` refactor — state machine + execute_stream + pipe_reply_stream
4. `tests/test_integration_pty.py` — real PTY integration flows (spike validation)
5. `chati.py` — new command handlers + decision forwarding UX + `_execute_and_reply` split
6. `cli_providers/` — add detection patterns to kiro.py, claude.py
7. `tests/test_message_utils.py` + `tests/test_providers.py` — remaining test coverage
