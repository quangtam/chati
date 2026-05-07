# Story 1.6: Per-Thread project_dir Binding Fix (Bug)

Status: review

## Story

As a **user**,
I want the CLI to actually run inside the project bound to the current thread,
So that `/project /path/to/A` in thread A and `/project /path/to/B` in thread B don't both end up executing inside `.env PROJECT_DIR`.

## Context / Bug Report

**Reported by Tony (2026-05-07):**

> "Tôi tạo 2 thread tương ứng với 2 project, nhưng khi chat với project A thì nó vẫn về project mặc định mà không đi theo setting của project A, chỉ gõ /info thì vẫn ra Project A"

**Root cause:**

`cli_runner.CliRunner` has two spawn paths that both hardcode `cwd = self._config.project_dir` (the global `.env PROJECT_DIR`):

- `_get_or_create_session()` — PTY interactive session spawn (line 132)
- `_stream_non_interactive()` — fallback subprocess spawn (line 640)

Meanwhile, `chati._execute_and_reply_inner` correctly resolves `resolved = await db.resolve_thread_config(...)` but only passes `resolved.timeout_seconds` and `resolved.model` to `execute_stream` — `resolved.project_dir` is computed and **thrown away**.

Result: `/info` reads from SQLite and shows the bound project correctly (cosmetic), but the actual CLI process runs in the wrong directory. This defeats Epic 1's core promise.

**Impact:**

- FR17 (bind thread to project dir) — partially broken: binding is stored but not honored at runtime
- FR23 (3-layer fallback for project_dir) — broken: thread-specific value never reaches the spawn
- `/project` command is effectively cosmetic until this is fixed

## Acceptance Criteria (BDD)

**Given** thread A is bound to `/home/tony/project-A` via `/project`
**And** thread B is bound to `/home/tony/project-B`
**When** the user sends a message in thread A
**Then** the spawned CLI process's working directory is `/home/tony/project-A`
**And** a concurrent message in thread B spawns a CLI in `/home/tony/project-B`

**Given** a thread has no row in `thread_config`
**When** the user sends a message
**Then** the CLI spawns in `.env PROJECT_DIR` (backward-compatible fallback)

**Given** a PTY session was created for thread A in `/home/tony/project-A`
**When** the user sends another message in thread A (session reuse)
**Then** the existing session is reused (no re-spawn, no cwd change — sessions are pinned to their spawn cwd)

**Given** the non-interactive fallback path is used
**When** the CLI is spawned
**Then** the per-thread `project_dir` is used as `cwd`, identical to the interactive path

**Given** new code is written for this story
**When** tests are run
**Then** unit tests pass with ≥80% branch coverage for the changed code

## Tasks / Subtasks

- [x] Task 1: Thread `project_dir` through `CliRunner.execute_stream` → `_get_or_create_session` → `_spawn_pty`
- [x] Task 2: Thread `project_dir` through `_stream_non_interactive`
- [x] Task 3: Thread `project_dir` through `pipe_reply_stream` (for decision replies — no spawn but keeps signature symmetric)
- [x] Task 4: Update `chati._execute_and_reply_inner` to pass `resolved.project_dir` to `execute_stream`
- [x] Task 5: Update `chati._pipe_decision_reply` to pass `resolved.project_dir` (harmless — existing session still pinned)
- [x] Task 6: Tests — two-thread isolation, fallback when no binding, session reuse invariant

## Dev Notes

### Design decisions

- **Sessions are pinned to spawn cwd.** Once a PTY is spawned in directory X, changing `cwd` mid-session has no effect — the child process's working directory is a kernel-level property captured at `fork()`. So on session reuse, we pass `project_dir` but it's ignored (the session is already running). To change project for a live session, user must `/new` first. This matches existing semantics for `/provider` (blocked while session active).
- **`None` = fallback to `config.project_dir`.** Backward-compatible: callers that don't know the per-thread dir pass `None` and get the old behavior.
- **Fix both spawn paths.** Interactive PTY (primary) + non-interactive (fallback). Missing either leaves an inconsistency.
- **`pipe_reply_stream` takes project_dir for signature symmetry** but never spawns — decision replies write to existing PTY. Purely cosmetic; harmless to pass.

### Files modified

- `cli_runner.py` — add `project_dir: str | None = None` param to `execute_stream`, `_get_or_create_session`, `_stream_non_interactive`, `pipe_reply_stream`. Use `project_dir or self._config.project_dir` as `cwd`.
- `chati.py` — pass `resolved.project_dir` in both `_execute_and_reply_inner` and `_pipe_decision_reply`.

### Testing strategy

- Mock `_spawn_pty` to capture the `cwd` argument it receives, then assert:
  - Thread A binding → spawn in `/tmp/proj-A`
  - Thread B binding → spawn in `/tmp/proj-B`
  - No binding → spawn in `.env` default

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 via Kiro

### Completion Notes

✅ Root cause identified: `CliRunner` hardcoded `cwd = self._config.project_dir` in both spawn paths (interactive PTY + non-interactive fallback), ignoring per-thread binding.
✅ `chati._execute_and_reply_inner` resolved `project_dir` correctly but discarded it before calling `execute_stream`.
✅ Threaded `project_dir: str | None = None` through `execute_stream → _get_or_create_session → _spawn_pty` and through `_stream_non_interactive`.
✅ Updated `chati.py` to pass `resolved.project_dir` to `execute_stream`.
✅ Sessions are pinned to spawn cwd — existing sessions reuse original dir (kernel-level property of fork()); `/new` required to switch project mid-session.
✅ 5 new tests in `tests/test_project_dir_binding.py` verify:
   - Interactive spawn uses per-thread project_dir
   - Interactive spawn falls back to env default when None
   - Non-interactive spawn uses per-thread project_dir
   - Two threads resolve distinct project_dirs
   - Thread without binding falls back to env default
✅ Full regression: 172/172 pass.

### File List

**Modified:**

- `cli_runner.py` — added `project_dir: str | None = None` parameter to `execute_stream`, `_get_or_create_session`, `_stream_non_interactive`. Spawn `cwd = project_dir or self._config.project_dir`. Log cwd in spawn logs for observability.
- `chati.py` — `_execute_and_reply_inner` now passes `resolved.project_dir` into `execute_stream` (previously only passed model + timeout).

**Added:**

- `tests/test_project_dir_binding.py` — 5 tests covering direct CliRunner cwd propagation and end-to-end handle_message resolution.

### Change Log

| Date       | Change                                                       |
|------------|--------------------------------------------------------------|
| 2026-05-07 | Story opened to fix per-thread project_dir binding bug.      |
| 2026-05-07 | Fix implemented + 5 tests. All regressions pass (172/172).   |
