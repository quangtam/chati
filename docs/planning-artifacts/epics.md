---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
status: 'complete'
completedAt: '2026-05-06'
inputDocuments:
  - docs/planning-artifacts/prd.md
  - docs/planning-artifacts/architecture.md
---

# Chati - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for Chati v2.0, decomposing the requirements from the PRD and Architecture into implementable stories following the TDD implementation sequence defined in the architecture.

## Requirements Inventory

### Functional Requirements

- FR1: User can send free-form text messages that are forwarded to the active CLI session in the current thread
- FR2: User can start a new CLI session for the current thread, discarding previous conversation context
- FR3: User can resume a previous CLI session in the current thread
- FR4: User can cancel a running CLI process in the current thread without affecting other threads
- FR5: System can maintain multiple concurrent PTY sessions (up to 5) across different threads without interference
- FR6: System can detect when a PTY session has died and report its status accurately
- FR7: User can view all active sessions with per-thread status indicators (active, waiting for input, idle, dead)
- FR8: System can reset the idle timeout deadline each time new output is received from the CLI subprocess
- FR9: System can pause the timeout clock when an interactive decision prompt is detected
- FR10: System can resume the timeout clock after the user responds to a decision prompt
- FR11: System can warn the user when a session has been idle beyond a configurable threshold
- FR12: User can configure per-thread timeout overrides that persist across bot restarts
- FR13: System can detect when the CLI subprocess is waiting for user input (via regex pattern matching + idle threshold)
- FR14: System can forward the detected prompt to the user with surrounding context sufficient to make a decision
- FR15: User can reply to a forwarded decision prompt and have their response piped back into the PTY subprocess
- FR16: System can resume normal streaming after the user's reply is delivered to the subprocess
- FR17: User can bind the current thread to a specific project directory on the server
- FR18: System can validate that a specified project directory exists before accepting the binding
- FR19: User can browse previously-used project directories and select one for re-binding without typing the path
- FR20: User can switch the CLI provider for the current thread (when no active process is running)
- FR21: User can select an AI model for the current thread via inline keyboard
- FR22: System can persist thread configuration (project_dir, provider, model, timeout) in SQLite across bot restarts
- FR23: System can resolve configuration using fallback chain: thread-specific → global default → provider default
- FR24: User can view current session information including provider name, logged-in user (if detectable), active model, session duration, and messages sent
- FR25: System can display best-effort token/credit usage when the CLI provider supports it
- FR26: User can check CLI binary availability and authentication status
- FR27: User can view a help guide listing all available commands and their usage
- FR28: System can strip ANSI escape sequences from CLI output and convert Markdown to Telegram HTML
- FR29: System can split messages exceeding 4096 characters at natural boundaries (paragraph, line, space)
- FR30: System can stream CLI output progressively by editing a preview message at regular intervals
- FR31: System can send typing indicators while CLI is processing
- FR32: System can forward CLI-generated screenshot files as inline Telegram photos (with fallback to document for >10MB)
- FR33: User can send a voice message that is transcribed to text via speech-to-text API
- FR34: System can present transcription to user for confirmation before forwarding to CLI (confirm / edit / cancel)
- FR35: System can synthesize text responses into voice messages (OGG opus format) sent via Telegram
- FR36: System can detect code-heavy responses (>50% code blocks) and skip voice synthesis, sending text only
- FR37: System can send text version alongside voice response for accessibility and reference
- FR38: System can restrict bot access to a whitelist of authorized Telegram user IDs

### NonFunctional Requirements

- NFR1: Stream start latency (cold) <3 seconds
- NFR2: Stream start latency (warm) <1 second
- NFR3: Decision prompt detection <12 seconds idle threshold
- NFR4: Decision reply delivery <500ms
- NFR5: SQLite read operations <50ms
- NFR6: SQLite write operations <200ms
- NFR7: 5 concurrent PTY sessions without degradation
- NFR8: 99% uptime (≤7.3 hours downtime per month)
- NFR9: Auto-restart on crash via systemd
- NFR10: Bot restart must not lose thread→project bindings (SQLite persists)
- NFR11: Maximum 5 concurrent PTY sessions (configurable)
- NFR12: Idle session cleanup after 30 minutes
- NFR13: Orphan process detection on startup
- NFR14: Memory monitoring: log warning if RSS >500MB
- NFR15: All bot interactions gated by ALLOWED_USER_IDS whitelist
- NFR16: Log rotation: 7-day retention
- NFR17: Outbound HTTPS only (no inbound connections)
- NFR18: WAL mode mandatory for SQLite
- NFR19: Graceful degradation for all external dependencies
- NFR20: Voice transcription <3 seconds (Growth)
- NFR21: Voice synthesis <4 seconds (Growth)

### Additional Requirements

From Architecture document:

- **Dedicated thread pool executor** for PTY reads (`ThreadPoolExecutor(max_workers=8, thread_name_prefix="pty")`) to prevent thread pool starvation
- **PtyState enum** lives in `session_manager.py` — 6 states: IDLE, STREAMING, DETECTING_PROMPT, WAITING_FOR_USER, PIPING_REPLY, DEAD
- **Option B decision forwarding** — generator yields DecisionPrompt then returns; `pipe_reply_stream()` is separate generator
- **Async context manager** for SQLite (`get_db()` with WAL + busy_timeout per connection)
- **Per-thread runtime state** in `context.bot_data[f"thread:{thread_id}:..."]` (not `user_data`)
- **Pending decision handling** — next message in thread = decision reply; `/cancel` = abort
- **Decision reply timeout** — 30min configurable, auto-kill session on expiry
- **Decision detection false-positive mitigation** — last line only, max 100 chars, provider-overridable
- **v1→v2 migration** — on first startup, create `chati.db` with default row from `.env PROJECT_DIR`
- **`_execute_and_reply` refactoring** — split into `_handle_stream()`, `_handle_decision_prompt()`, `_send_final_response()`
- **TDD implementation sequence** — test file accompanies each module implementation
- **Spike recommended** — validate decision forwarding pattern with mock PTY before full implementation

### UX Design Requirements

Not applicable — Chati uses Telegram's native UI. No custom UX design document.

### FR Coverage Map

FR1:  Epic 2 - Forward text to active CLI session
FR2:  Epic 2 - Start new session (/new)
FR3:  Epic 2 - Resume previous session
FR4:  Epic 2 - Cancel running process (/cancel)
FR5:  Epic 2 - Maintain concurrent PTY sessions
FR6:  Epic 2 - Detect dead PTY sessions
FR7:  Epic 2 + Epic 4 - Session status indicators
FR8:  Epic 2 - Reset timeout on output
FR9:  Epic 2 - Pause timeout on decision detection
FR10: Epic 2 - Resume timeout after decision reply
FR11: Epic 2 - Idle warning
FR12: Epic 1 - Per-thread timeout override (persisted in SQLite)
FR13: Epic 3 - Detect CLI waiting for input
FR14: Epic 3 - Forward prompt with context
FR15: Epic 3 - Pipe user reply to PTY
FR16: Epic 3 - Resume streaming after reply
FR17: Epic 1 - Bind thread to project directory
FR18: Epic 1 - Validate project path exists
FR19: Epic 1 - Browse previously-used projects
FR20: Epic 1 - Switch provider per-thread
FR21: Epic 1 - Select model via inline keyboard
FR22: Epic 1 - Persist config in SQLite
FR23: Epic 1 - Config resolution fallback chain
FR24: Epic 4 - View session info (/info)
FR25: Epic 4 - Best-effort token/credit usage
FR26: Epic 4 - Check CLI availability (/status)
FR27: Epic 4 - Help guide (/help)
FR28: Epic 2 - Strip ANSI + MD→HTML (regression verification)
FR29: Epic 2 - Split messages >4096 chars (regression verification)
FR30: Epic 2 - Stream output progressively
FR31: Epic 2 - Typing indicators
FR32: Epic 5 - Screenshot forwarding
FR33: Epic 6 - Voice transcription (Whisper)
FR34: Epic 6 - Transcription confirmation UX
FR35: Epic 6 - Voice synthesis (TTS)
FR36: Epic 6 - Skip TTS for code-heavy
FR37: Epic 6 - Text alongside voice
FR38: Epic 2 - Whitelist auth (regression verification)

## Epic List

### Epic 0: Test Infrastructure (Foundation)
Shared test fixtures and pytest configuration must exist before TDD can proceed.
**FRs covered:** None (engineering infrastructure)

### Epic 1: SQLite Persistence & Multi-Project Foundation
Users can bind threads to different projects, switch providers per-thread, and have all configuration survive bot restarts.
**FRs covered:** FR12, FR17, FR18, FR19, FR20, FR21, FR22, FR23

### Epic 2: Adaptive Timeout & Reliable Streaming
Users experience zero silent timeouts — the system resets deadlines on output, warns on idle, and supports per-thread timeout configuration. Parallel sessions run without interference. Includes regression verification of output pipeline (FR28, FR29) and auth (FR38).
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR28, FR29, FR30, FR31, FR38

### Epic 3: Interactive Decision Forwarding
When the CLI needs human judgment, the question surfaces on the user's phone with context. User replies, and execution resumes seamlessly.
**FRs covered:** FR13, FR14, FR15, FR16

### Epic 4: CLI Information & Session Visibility
Users can see full CLI context, session stats, and manage all active sessions from one place.
**FRs covered:** FR7, FR24, FR25, FR26, FR27

### Epic 5: Screenshot Forwarding (Growth)
CLI-generated screenshots appear as inline photos in Telegram — visual proof of task completion.
**FRs covered:** FR32

### Epic 6: Voice Communication (Growth)
Users can send voice messages that get transcribed, confirmed, and forwarded to CLI. Responses can optionally come back as voice.
**FRs covered:** FR33, FR34, FR35, FR36, FR37

## Epic 1: SQLite Persistence & Multi-Project Foundation

Users can bind threads to different projects, switch providers per-thread, and have all configuration survive bot restarts.

### Story 1.1: SQLite Database Layer

As a **developer**,
I want a SQLite persistence layer with async context manager and schema migration,
So that thread configuration can be stored and retrieved reliably across bot restarts.

**Acceptance Criteria:**

**Given** the bot starts for the first time (no `chati.db` exists)
**When** any database operation is attempted
**Then** `chati.db` is created with `thread_config` table and a default row using `.env PROJECT_DIR`
**And** WAL mode and busy_timeout=5000 are set on every connection

**Given** the bot starts with an existing `chati.db`
**When** the database is accessed
**Then** existing data is preserved and accessible without migration errors

**Given** two concurrent coroutines access the database simultaneously
**When** both perform write operations
**Then** both succeed without "database is locked" errors (WAL mode)

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

### Story 1.2: Thread-to-Project Binding (/project command)

As a **user**,
I want to bind the current thread to a specific project directory,
So that all CLI commands in this thread operate on that project.

**Acceptance Criteria:**

**Given** user is in a Telegram thread
**When** user sends `/project /home/tony/myapp`
**Then** the thread is bound to `/home/tony/myapp` and confirmation message is sent

**Given** user sends `/project /nonexistent/path`
**When** the system validates the path
**Then** an error message is shown: "⚠️ Path not found: /nonexistent/path"
**And** no binding is created

**Given** user sends `/project /path/with spaces/project`
**When** the command is parsed
**Then** the entire text after `/project ` is treated as the path (spaces handled)

**Given** a thread binding is created
**When** the bot restarts
**Then** the binding persists (stored in SQLite)

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

### Story 1.3: Project History & Quick Re-binding (/projects command)

As a **user**,
I want to browse previously-used project directories and select one,
So that I don't have to type full paths on my phone.

**Acceptance Criteria:**

**Given** user has previously bound threads to 3 different projects
**When** user sends `/projects`
**Then** an inline keyboard appears with all 3 previously-used project directories

**Given** the inline keyboard is displayed
**When** user taps a project directory button
**Then** the current thread is bound to that project and confirmation is sent

**Given** user has never used `/project` before
**When** user sends `/projects`
**Then** a message appears: "No previous projects found. Use `/project <path>` to bind a project."

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

### Story 1.4: Per-Thread Provider Switching (/provider command)

As a **user**,
I want to switch the CLI provider for the current thread,
So that I can use different AI CLIs for different projects.

**Acceptance Criteria:**

**Given** user is in a thread with no active CLI process
**When** user sends `/provider claude`
**Then** the thread's provider is updated to `claude` in SQLite and confirmation is sent

**Given** user is in a thread with an active CLI process running (including WAITING_FOR_USER state)
**When** user sends `/provider kiro`
**Then** the command is rejected with message: "⚠️ Active process running. Use `/cancel` first."

**Given** user sends `/provider invalidname`
**When** the provider name is validated against the registry
**Then** an error message is shown listing available providers

**Given** a provider switch is saved
**When** the bot restarts
**Then** the per-thread provider preference persists

**Given** user selects a model via `/model` inline keyboard
**When** the selection is confirmed
**Then** the model choice is persisted to SQLite `thread_config.model` for the current thread

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

### Story 1.5: Configuration Resolution Chain

As a **system**,
I want to resolve thread configuration using a 3-layer fallback chain,
So that per-thread overrides take precedence while global defaults still apply.

**Acceptance Criteria:**

**Given** a thread has `cli_provider = "claude"` in SQLite and `.env` has `CLI_PROVIDER=kiro`
**When** the system resolves the provider for that thread
**Then** `claude` is used (thread-specific wins)

**Given** a thread has `model = NULL` in SQLite and `.env` has no default model
**When** the system resolves the model for that thread
**Then** the provider's hardcoded default model is used (final fallback)

**Given** a thread has `timeout_seconds = 900` in SQLite
**When** the system resolves timeout for that thread
**Then** 900 seconds is used instead of `.env CLI_TIMEOUT`

**Given** a thread has no row in SQLite (new thread, first message)
**When** the system resolves configuration
**Then** all values fall back to `.env` defaults

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

## Epic 2: Adaptive Timeout & Reliable Streaming

Users experience zero silent timeouts — the system resets deadlines on output, warns on idle, and supports per-thread timeout configuration. Parallel sessions run without interference.

### Story 2.1: Session Manager Extraction & PTY State Machine

As a **developer**,
I want session lifecycle management extracted into `session_manager.py` with an explicit state machine,
So that PTY sessions have observable, debuggable state transitions.

**Acceptance Criteria:**

**Given** the `session_manager.py` module is created
**When** a new PTY session is spawned
**Then** it starts in `PtyState.IDLE` and transitions to `STREAMING` when a prompt is written

**Given** a session is in `STREAMING` state
**When** output is received from the PTY
**Then** the state remains `STREAMING` and the idle timeout resets

**Given** any state transition occurs
**When** the transition is logged
**Then** the log format is `[PTY:{thread_id}] {old_state} → {new_state}: {reason}` at DEBUG level

**Given** an invalid state transition is attempted (e.g., IDLE → PIPING_REPLY)
**When** the transition is requested
**Then** a `RuntimeError` is raised (programming error)

### Story 2.2: Concurrent Session Pool & Resource Enforcement

As a **user**,
I want to run up to 5 CLI sessions simultaneously across different threads,
So that I can work on multiple projects without interference.

**Acceptance Criteria:**

**Given** 5 PTY sessions are already active
**When** a 6th session is requested
**Then** the request is rejected with message: "⚠️ Maximum sessions reached (5). Use `/cancel` in another thread to free a slot."

**Given** 3 sessions are active in different threads
**When** user sends messages in each thread
**Then** each session streams independently without blocking or context bleed

**Given** a dedicated `pty_executor` (ThreadPoolExecutor, max_workers=8)
**When** PTY blocking reads are executed
**Then** they run in the dedicated executor, not the default asyncio executor

**Given** the bot starts up
**When** orphan CLI processes from a previous run are detected
**Then** they are killed and resources freed before accepting new messages

### Story 2.3: Adaptive Timeout with Reset-on-Output

As a **user**,
I want the timeout to reset every time the CLI produces output,
So that long-running tasks (test suites, builds) don't get killed mid-execution.

**Acceptance Criteria:**

**Given** a CLI session is streaming output
**When** new output arrives
**Then** the idle timeout deadline resets to `now + timeout_seconds`

**Given** a CLI session has been idle for 30 seconds (configurable `IDLE_WARN_INTERVAL`)
**When** no output has been received
**Then** a warning message is sent to the user: "⏳ CLI has been idle for 30s..."

**Given** a CLI session exceeds the global timeout (default 600s, or per-thread override)
**When** no output has been received for the full timeout duration
**Then** the session is killed and user is notified: "⚠️ Session timed out after {X}s"

**Given** a session is in `WAITING_FOR_USER` state (decision prompt pending)
**When** the timeout clock is checked
**Then** the timeout is paused (not counting idle time while waiting for human reply)

**Given** CLI output arrives as single bytes (e.g., progress bar animation)
**When** timeout reset logic runs
**Then** meaningful output is defined as ≥1 complete line (newline-terminated); single bytes without newline do NOT reset the timeout

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

### Story 2.4: Session Operations (new, resume, cancel)

As a **user**,
I want to start fresh sessions, resume existing ones, and cancel running processes,
So that I have full control over my CLI sessions per thread.

**Acceptance Criteria:**

**Given** user sends `/new` in a thread with an active session
**When** the command is processed
**Then** the existing session is killed and a fresh session starts on next message

**Given** user sends a message in a thread with a warm (IDLE) session
**When** the message is forwarded to CLI
**Then** the existing session is reused (no cold start)

**Given** user sends `/cancel` in a thread with a running process
**When** the cancel is processed
**Then** the PTY process receives SIGTERM, then SIGKILL after 5s if unresponsive
**And** user is notified: "✅ Process cancelled"
**And** other threads are unaffected

**Given** user sends `/cancel` in a thread with no active process
**When** the command is processed
**Then** a message is shown: "No active process in this thread."

**Given** a session is in `DEAD` state and user sends a new free-form message
**When** the message is processed
**Then** a fresh session is auto-started (no need for explicit `/new`)
**And** user is notified: "Previous session expired. Starting fresh."

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

### Story 2.5: Streaming Output with Progressive Edits

As a **user**,
I want to see CLI output streaming in real-time via progressive message edits,
So that I know the CLI is working and can follow progress.

**Acceptance Criteria:**

**Given** a CLI session is producing output
**When** the streaming loop runs
**Then** a preview message is edited every 1.5 seconds with the latest output

**Given** the preview buffer exceeds 3000 characters
**When** the message is edited
**Then** only the last 3000 characters are shown (truncated from the beginning)

**Given** a CLI session is active
**When** the streaming loop runs
**Then** typing indicators (`ChatAction.TYPING`) are sent every 4 seconds

**Given** the stream completes (response marker detected or process exits)
**When** the final response is ready
**Then** the preview message is deleted and the formatted final response is sent

**Given** CLI output contains ANSI escape sequences
**When** the output is processed through the pipeline
**Then** all ANSI sequences are stripped cleanly (regression: FR28)

**Given** a final response exceeds 4096 characters
**When** the message is split
**Then** splits occur at natural boundaries and each chunk is ≤4096 characters (regression: FR29)

**Given** HTML conversion produces invalid markup
**When** Telegram rejects the message
**Then** fallback to plain text (strip HTML tags) and retry

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

### Story 2.6: Idle Session Cleanup & Status Reporting

As a **user**,
I want idle sessions to be cleaned up automatically and session status visible,
So that resources aren't wasted and I can see what's running.

**Acceptance Criteria:**

**Given** a session has been in `IDLE` state for 30 minutes (configurable)
**When** the cleanup task runs
**Then** the session is killed and resources freed

**Given** a session's PTY process has died unexpectedly
**When** the system checks session status
**Then** the state is updated to `DEAD` and reported accurately

**Given** user sends `/sessions` (or system needs status for `/info`)
**When** session status is queried
**Then** each thread shows correct status: 🟢 active / ⏳ waiting / 💤 idle / ❌ dead

**Given** the bot process receives SIGTERM
**When** graceful shutdown begins
**Then** all PTY sessions are killed, SQLite connections closed, then process exits

## Epic 3: Interactive Decision Forwarding

When the CLI needs human judgment, the question surfaces on the user's phone with context. User replies, and execution resumes seamlessly.

### Story 3.1: Decision Prompt Detection (Hybrid Strategy)

As a **system**,
I want to detect when the CLI subprocess is waiting for user input,
So that the question can be forwarded instead of silently timing out.

**Acceptance Criteria:**

**Given** a CLI session is streaming and output stops for ≥12 seconds
**When** the last line of output matches a prompt pattern (`[y/N]`, `[Y/n]`, `(yes/no)`, ends with `?`)
**And** the last line is ≤100 characters
**Then** the state transitions to `DETECTING_PROMPT → WAITING_FOR_USER`
**And** a `DecisionPrompt` object is yielded from the generator

**Given** a CLI session is streaming and output stops for ≥12 seconds
**When** the last line does NOT match any prompt pattern
**Then** the state remains `STREAMING` and idle warning fires normally (not decision detection)

**Given** a provider has custom `decision_prompt_patterns` defined
**When** the idle threshold is reached
**Then** provider-specific patterns are checked IN ADDITION to generic patterns

**Given** the last line of output is >100 characters
**When** idle threshold is reached and the line ends with `?`
**Then** it is NOT treated as a decision prompt (likely explanation text, not a real prompt)

**Given** the session is in `DETECTING_PROMPT` state (idle threshold counting)
**When** user sends a new message in the same thread
**Then** the message is queued until detection resolves (either prompt confirmed or output resumes)

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

### Story 3.2: Decision Prompt Forwarding to User

As a **user**,
I want to see the CLI's question on my phone with enough context to make a decision,
So that I can respond without scrolling back through the stream.

**Acceptance Criteria:**

**Given** a `DecisionPrompt` is detected
**When** the generator yields it and returns
**Then** `chati.py` formats and sends a message to Telegram:
```
⚠️ CLI is waiting for input. Detected prompt:

{last 5 lines of output as context}

Reply to proceed, or /cancel to abort.
```

**Given** a decision prompt is forwarded
**When** the pending state is stored
**Then** `context.bot_data[f"thread:{thread_id}:pending_decision"]` is set to `True`

**Given** a decision prompt is forwarded
**When** the streaming preview message exists
**Then** the preview message is kept (not deleted) so user has context

### Story 3.3: Decision Reply Piping & Stream Resumption

As a **user**,
I want to reply to a forwarded decision and have execution resume,
So that the CLI continues working without me needing to restart.

**Acceptance Criteria:**

**Given** a decision is pending for a thread (`pending_decision = True`)
**When** user sends a free-form text message in that thread
**Then** the message is piped to the PTY via `pipe_reply_stream(session, reply)`
**And** `pending_decision` is cleared
**And** a new streaming loop begins with the resumed output

**Given** a decision is pending
**When** user sends `/cancel`
**Then** the session is killed, pending state cleared, user notified: "✅ Decision cancelled. Session ended."

**Given** `pipe_reply_stream()` is called
**When** the reply is written to PTY and output resumes
**Then** the state transitions: `WAITING_FOR_USER → PIPING_REPLY → STREAMING`
**And** the new generator yields remaining output normally

**Given** `pipe_reply_stream()` yields output
**When** another decision prompt is detected mid-stream
**Then** the same detection → forward → reply cycle repeats (chained decisions supported)

**Given** a decision is pending (WAITING_FOR_USER state)
**When** the PTY process dies unexpectedly
**Then** `pending_decision` is cleared, user is notified: "⚠️ Session died while waiting for your reply. Send a new message to start fresh."

**Given** user sends an empty or whitespace-only reply to a decision prompt
**When** the reply is processed
**Then** the whitespace is piped to PTY as-is (CLI decides how to handle empty input)

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

### Story 3.4: Decision Reply Timeout

As a **system**,
I want decisions that go unanswered for 30 minutes to auto-expire,
So that sessions don't hang indefinitely waiting for a reply that never comes.

**Acceptance Criteria:**

**Given** a decision prompt has been forwarded to the user
**When** 30 minutes pass without a reply (configurable via `DECISION_REPLY_TIMEOUT` in `.env`)
**Then** the session is killed (state → DEAD)
**And** user is notified: "⚠️ Decision timed out after 30 minutes. Session ended. Send a new message to start fresh."
**And** `pending_decision` is cleared

**Given** a decision is pending and user replies at minute 29
**When** the reply is received before timeout
**Then** the reply is piped normally and timeout is cancelled

**Given** `DECISION_REPLY_TIMEOUT` is not set in `.env`
**When** the system resolves the timeout value
**Then** the default of 1800 seconds (30 minutes) is used

## Epic 0: Test Infrastructure (Foundation)

Test infrastructure must exist before TDD can proceed. Shared fixtures prevent each story from re-inventing test plumbing.

### Story 0.1: Test Infrastructure Setup

As a **developer**,
I want pytest infrastructure with shared fixtures and CI-safe PTY helpers,
So that TDD can proceed consistently without each story re-inventing test plumbing.

**Acceptance Criteria:**

**Given** `tests/conftest.py` is created
**When** pytest runs
**Then** the following fixtures are available:
- `in_memory_db` — SQLite `:memory:` with migrated `thread_config` schema
- `mock_provider` — fake CliProvider with deterministic, configurable output
- `pty_process` — real PTY spawning `cat` or `echo`, with force-kill cleanup (timeout 5s)
- `session_context` — SessionManager instance with seeded test data
- `telegram_update_factory` — factory function creating fake Telegram Update objects

**Given** `pytest-timeout` is configured
**When** any test exceeds 30 seconds
**Then** it fails with timeout error (not hangs indefinitely)

**Given** `requirements-dev.txt` is created
**When** dev installs test dependencies
**Then** `pytest`, `pytest-asyncio`, and `pytest-timeout` are available

**Given** a PTY fixture is used in a test
**When** the test completes (pass or fail)
**Then** the PTY process is force-killed within 5 seconds (no zombie processes)

## Epic 4: CLI Information & Session Visibility

Users can see full CLI context, session stats, and manage all active sessions from one place.

### Story 4.1: CLI Info Command (/info)

As a **user**,
I want to see full information about my current CLI session,
So that I know what provider, model, and resources I'm using.

**Acceptance Criteria:**

**Given** user sends `/info` in a thread with an active session
**When** the command is processed
**Then** a message is displayed showing:
- Provider name (e.g., "Kiro")
- Logged-in user (if detectable by provider)
- Active model
- Session duration (time since session created)
- Messages sent this session
- Token/credit usage (best-effort, if provider supports it)

**Given** user sends `/info` in a thread with no active session
**When** the command is processed
**Then** thread config is shown (bound project, provider, model) with note "No active session"

**Given** a provider does not implement `parse_usage_output()`
**When** `/info` is requested
**Then** token/credit section shows "Usage data not available for this provider"

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

### Story 4.2: Session List Command (/sessions)

As a **user**,
I want to see all my active sessions across threads with their status,
So that I can manage multiple projects and know which sessions need attention.

**Acceptance Criteria:**

**Given** user has 3 active threads with sessions
**When** user sends `/sessions`
**Then** a formatted list is displayed showing each thread with:
- Thread name/ID
- Bound project directory
- Provider + model
- Status indicator: 🟢 active / ⏳ waiting for input / 💤 idle / ❌ dead

**Given** user has more than 10 active threads
**When** user sends `/sessions`
**Then** the list is paginated (first 10 shown with "..." indicator)

**Given** user has no active sessions
**When** user sends `/sessions`
**Then** message shows: "No active sessions. Send a message in any thread to start one."

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

### Story 4.3: Enhanced Status & Help Commands

As a **user**,
I want `/status` to show CLI health in parallel context and `/help` to document all v2 commands,
So that I can troubleshoot issues and discover available features.

**Acceptance Criteria:**

**Given** user sends `/status`
**When** the command is processed
**Then** the response shows:
- CLI binary availability (found/not found)
- Authentication status (logged in / not logged in, if detectable)
- Active session count (e.g., "3/5 sessions active")
- Current thread's session state (if any)

**Given** user sends `/help`
**When** the command is processed
**Then** all v2 commands are listed with brief descriptions:
- `/project`, `/projects`, `/provider`, `/info`, `/sessions`
- `/model`, `/new`, `/resume`, `/cancel`, `/status`
- `/skills`, `/help`, `/start`

**Given** the CLI binary is not found on the system
**When** user sends `/status`
**Then** a clear error is shown: "⚠️ CLI binary not found: {binary_name}\nInstall and login: {setup_guide_link}"

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

## Epic 5: Screenshot Forwarding (Growth)

CLI-generated screenshots appear as inline photos in Telegram — visual proof of task completion.

### Story 5.1: Screenshot Detection & Inline Photo Forwarding

As a **user**,
I want CLI-generated screenshots to appear as inline photos in my Telegram thread,
So that I can see visual proof of task completion without opening my laptop.

**Acceptance Criteria:**

**Given** CLI output contains a file path to an image (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`)
**When** the stream completes and output is processed
**Then** the image is sent as an inline photo via Telegram `sendPhoto`

**Given** the detected image file is larger than 10MB
**When** the system attempts to send it
**Then** it falls back to `sendDocument` (file attachment) instead of inline photo

**Given** the detected image file path does not exist on disk
**When** the system attempts to send it
**Then** the error is logged and text response is sent normally (graceful degradation)

**Given** CLI output contains multiple image paths
**When** the stream completes
**Then** all images are sent as separate photos in order

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

## Epic 6: Voice Communication (Growth)

Users can send voice messages that get transcribed, confirmed, and forwarded to CLI. Responses can optionally come back as voice.

### Story 6.1: Voice Input — Whisper Transcription & Confirmation

As a **user**,
I want to send voice messages that get transcribed and confirmed before forwarding to CLI,
So that I can code hands-free with confidence the transcription is correct.

**Acceptance Criteria:**

**Given** user sends a voice message in Telegram
**When** the bot receives the audio
**Then** the audio is sent to Whisper API for transcription
**And** response time is <3 seconds for 5-15s audio clips

**Given** transcription is received from Whisper
**When** the result is ready
**Then** an inline keyboard is shown: "✅ Send / ✏️ Edit / 🗑️ Cancel" with the transcribed text

**Given** user taps "✅ Send"
**When** the confirmation is received
**Then** the transcribed text is forwarded to CLI as if user typed it

**Given** user taps "✏️ Edit"
**When** the edit option is selected
**Then** user can type a corrected version which replaces the transcription

**Given** user taps "🗑️ Cancel"
**When** the cancel is selected
**Then** the transcription is discarded and no message is sent to CLI

**Given** Whisper API is unavailable or times out (>10s)
**When** the transcription fails
**Then** user is notified: "⚠️ Voice transcription temporarily unavailable. Please type your message."

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code

### Story 6.2: Voice Output — TTS Response Synthesis

As a **user**,
I want CLI responses to optionally come back as voice messages,
So that I can listen to results while walking or commuting.

**Acceptance Criteria:**

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

### Story 6.3: Voice Configuration & Code Detection

As a **system**,
I want voice features to be configurable and code-heavy detection to be reliable,
So that voice doesn't fire inappropriately and users have control.

**Acceptance Criteria:**

**Given** a response contains markdown code blocks (``` delimited)
**When** code block ratio is calculated
**Then** the ratio = (characters inside code blocks) / (total characters)
**And** if ratio > 0.5, response is classified as "code-heavy"

**Given** voice output is a Growth feature
**When** the feature is not yet implemented
**Then** all voice-related code paths gracefully no-op (feature flag pattern)

**Given** Whisper and TTS API keys are not configured in `.env`
**When** a voice message is received
**Then** the bot responds: "Voice features not configured. Please type your message."

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for new code
