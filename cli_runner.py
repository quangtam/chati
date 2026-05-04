"""Chati CLI runner — persistent interactive sessions via PTY.

Keeps a long-running CLI process per thread using pseudo-terminals.
Messages are written to the PTY; responses are read until the next
prompt marker. Falls back to --no-interactive for CLIs that don't
support interactive mode.

Includes idle watchdog and per-thread concurrency.
"""

import asyncio
import logging
import os
import pty
import re
import select
import signal
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from cli_providers import CliProvider, create_provider
from config import Config

logger = logging.getLogger(__name__)

# Warn user if no output for this many seconds
IDLE_WARN_INTERVAL = 30

# Regex to detect the interactive prompt (e.g. "2% !> " or "!> ")
_PROMPT_RE = re.compile(r"\d*%?\s*!>\s*$")

# Strip ANSI for prompt detection
_ANSI_RE = re.compile(r"\x1b\[[\x20-\x3f]*[\x40-\x7e]|\x1b[\x20-\x2f]*[\x30-\x7e]|\x9b[\x20-\x3f]*[\x40-\x7e]")

# How long to wait for the initial prompt after spawning
_INIT_TIMEOUT = 60


@dataclass
class CliResult:
    """Result from a CLI execution."""

    output: str
    exit_code: int
    timed_out: bool = False


class _PtySession:
    """A persistent interactive CLI session using a pseudo-terminal."""

    def __init__(self, pid: int, fd: int) -> None:
        self.pid = pid
        self.fd = fd
        self.ready = False
        self._dead = False

    @property
    def alive(self) -> bool:
        if self._dead:
            return False
        try:
            os.kill(self.pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            self._dead = True
            return False

    def write(self, data: str) -> None:
        os.write(self.fd, data.encode("utf-8"))

    def read(self, timeout: float = 1.0) -> str | None:
        """Read available data from PTY. Returns None on timeout, '' on EOF."""
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return None
        try:
            data = os.read(self.fd, 8192)
            if not data:
                return ""
            return data.decode("utf-8", errors="replace")
        except OSError:
            self._dead = True
            return ""

    def kill(self) -> None:
        try:
            os.kill(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass
        try:
            os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            pass
        self._dead = True


class CliRunner:
    """Manages CLI subprocess execution with persistent PTY sessions."""

    def __init__(self, config: Config) -> None:
        self._config = config

        self._sessions: dict[int | None, _PtySession] = {}
        self._locks: dict[int | None, asyncio.Lock] = {}
        self._exit_codes: dict[int | None, int] = {}

        self._provider: CliProvider = create_provider(
            provider_name=config.cli_provider,
            cli_path=config.cli_path or None,
            api_key=config.cli_api_key,
            trust_all_tools=config.trust_all_tools,
            extra_args=list(config.cli_extra_args) if config.cli_extra_args else None,
        )

        logger.info(
            "CLI Provider: %s (%s)",
            self._provider.name,
            self._provider.config.cli_path,
        )

    @property
    def provider(self) -> CliProvider:
        return self._provider

    @property
    def _env(self) -> dict[str, str]:
        return self._provider.build_env(os.environ.copy())

    def _get_lock(self, thread_id: int | None) -> asyncio.Lock:
        if thread_id not in self._locks:
            self._locks[thread_id] = asyncio.Lock()
        return self._locks[thread_id]

    def is_busy(self, thread_id: int | None) -> bool:
        return self._get_lock(thread_id).locked()

    def get_exit_code(self, thread_id: int | None) -> int:
        return self._exit_codes.get(thread_id, 0)

    # ── PTY session management ───────────────────────────────────

    async def _get_or_create_session(
        self, thread_id: int | None, *, model: str | None = None
    ) -> _PtySession | None:
        """Get existing session or spawn a new interactive CLI via PTY."""
        session = self._sessions.get(thread_id)
        if session and session.alive:
            return session

        # Clean up dead session
        if session:
            session.kill()
            self._sessions.pop(thread_id, None)

        args = self._provider.build_interactive_args(model=model)
        if not args:
            return None

        env = self._env
        cwd = self._config.project_dir

        logger.info("Spawning PTY session [thread=%s]: %s", thread_id, " ".join(args))

        # Spawn in a thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        pid, fd = await loop.run_in_executor(
            None, lambda: self._spawn_pty(args, env, cwd)
        )

        session = _PtySession(pid, fd)
        self._sessions[thread_id] = session

        # Wait for initial prompt
        deadline = time.monotonic() + _INIT_TIMEOUT
        found_prompt = False

        while time.monotonic() < deadline:
            chunk = await loop.run_in_executor(
                None, lambda: session.read(timeout=2.0)
            )
            if chunk is None:
                continue
            if chunk == "":
                break  # EOF

            clean = _ANSI_RE.sub("", chunk)
            if _PROMPT_RE.search(clean.rstrip()):
                found_prompt = True
                break

        if found_prompt:
            session.ready = True
            logger.info("PTY session ready [thread=%s] in %.1fs", thread_id, time.monotonic() - (deadline - _INIT_TIMEOUT))
        else:
            logger.warning("PTY session failed to reach prompt [thread=%s]", thread_id)
            session.kill()
            self._sessions.pop(thread_id, None)
            return None

        return session

    @staticmethod
    def _spawn_pty(args: list[str], env: dict[str, str], cwd: str) -> tuple[int, int]:
        """Fork a PTY process (runs in executor thread)."""
        pid, fd = pty.fork()
        if pid == 0:
            # Child process
            os.chdir(cwd)
            os.environ.update(env)
            os.execvp(args[0], args)
            # Never reaches here
        return pid, fd

    def _kill_session(self, thread_id: int | None) -> None:
        """Kill and remove a session (sync, safe to call from anywhere)."""
        session = self._sessions.pop(thread_id, None)
        if session:
            session.kill()

    # ── Streaming execution ──────────────────────────────────────

    async def execute_stream(
        self,
        prompt: str,
        *,
        thread_id: int | None = None,
        model: str | None = None,
        resume: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Execute a prompt and yield output lines."""
        lock = self._get_lock(thread_id)

        async with lock:
            session = await self._get_or_create_session(thread_id, model=model)

            if session and session.alive:
                async for line in self._stream_pty(session, prompt, thread_id):
                    yield line
            else:
                async for line in self._stream_non_interactive(
                    prompt, thread_id=thread_id, model=model, resume=resume
                ):
                    yield line

    async def _stream_pty(
        self,
        session: _PtySession,
        prompt: str,
        thread_id: int | None,
    ) -> AsyncGenerator[str, None]:
        """Send prompt to PTY session and yield response chunks."""
        loop = asyncio.get_event_loop()

        # Send the prompt
        try:
            await loop.run_in_executor(None, lambda: session.write(prompt + "\n"))
        except OSError:
            logger.warning("PTY write failed [thread=%s]", thread_id)
            self._kill_session(thread_id)
            self._exit_codes[thread_id] = -1
            yield "❌ CLI session died. Send your message again to start a new session.\n"
            return

        logger.info("Sent to PTY [thread=%s]: %s", thread_id, prompt[:80])

        deadline = time.monotonic() + self._config.cli_timeout
        last_output_time = time.monotonic()
        last_warn_time = 0.0

        while True:
            now = time.monotonic()

            if now >= deadline:
                logger.warning("PTY stream timeout [thread=%s]", thread_id)
                self._kill_session(thread_id)
                self._exit_codes[thread_id] = -1
                yield "\n⏱ Global timeout reached. Session killed.\n"
                return

            if not session.alive:
                self._exit_codes[thread_id] = -1
                self._sessions.pop(thread_id, None)
                yield "\n❌ CLI process died unexpectedly.\n"
                return

            idle_seconds = now - last_output_time
            if idle_seconds >= IDLE_WARN_INTERVAL and now - last_warn_time >= IDLE_WARN_INTERVAL:
                remaining = int(deadline - now)
                yield f"\n⏳ Still working... no output for {int(idle_seconds)}s (timeout in {remaining}s)\n"
                last_warn_time = now

            # Read from PTY (non-blocking via executor)
            chunk = await loop.run_in_executor(
                None, lambda: session.read(timeout=2.0)
            )

            if chunk is None:
                continue  # Timeout, no data yet
            if chunk == "":
                # EOF — process died
                self._kill_session(thread_id)
                self._exit_codes[thread_id] = -1
                break

            last_output_time = time.monotonic()
            last_warn_time = 0.0

            # Check if we've hit the next prompt → response complete
            clean = _ANSI_RE.sub("", chunk)
            if _PROMPT_RE.search(clean.rstrip()):
                # Yield everything before the prompt
                before_prompt = _PROMPT_RE.split(clean.rstrip())[0]
                if before_prompt.strip():
                    yield before_prompt
                self._exit_codes[thread_id] = 0
                break

            yield chunk

    async def _stream_non_interactive(
        self,
        prompt: str,
        *,
        thread_id: int | None,
        model: str | None,
        resume: bool,
    ) -> AsyncGenerator[str, None]:
        """Fallback: non-interactive single-shot execution."""
        args = self._provider.build_args(prompt, model=model, resume=resume)
        logger.info("Non-interactive [thread=%s]: %s", thread_id, " ".join(args))

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._config.project_dir,
                env=self._env,
            )
            assert process.stdout is not None

            deadline = time.monotonic() + self._config.cli_timeout
            last_output_time = time.monotonic()
            last_warn_time = 0.0

            while True:
                now = time.monotonic()

                if now >= deadline:
                    try:
                        process.kill()
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except (ProcessLookupError, asyncio.TimeoutError):
                        pass
                    self._exit_codes[thread_id] = -1
                    yield "\n⏱ Global timeout reached. Process killed.\n"
                    return

                idle_seconds = now - last_output_time
                if idle_seconds >= IDLE_WARN_INTERVAL and now - last_warn_time >= IDLE_WARN_INTERVAL:
                    remaining = int(deadline - now)
                    yield f"\n⏳ Still working... no output for {int(idle_seconds)}s (timeout in {remaining}s)\n"
                    last_warn_time = now

                try:
                    line_bytes = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=max(min(5, deadline - now), 1),
                    )
                except asyncio.TimeoutError:
                    if process.returncode is not None:
                        break
                    continue

                if not line_bytes:
                    break

                last_output_time = time.monotonic()
                last_warn_time = 0.0
                yield line_bytes.decode("utf-8", errors="replace")

            await process.wait()
            self._exit_codes[thread_id] = process.returncode or 0

            if process.stderr:
                stderr_bytes = await process.stderr.read()
                stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
                if stderr and (process.returncode or 0) != 0:
                    yield f"\n⚠️ Stderr:\n{stderr}\n"

        except FileNotFoundError:
            self._exit_codes[thread_id] = -1
            yield f"❌ CLI not found at: {self._provider.config.cli_path}\n"
        except Exception as exc:
            self._exit_codes[thread_id] = -1
            yield f"❌ Unexpected error: {exc}\n"
            logger.exception("Stream error [thread=%s]", thread_id)

    # ── Cancel / Status / Models ─────────────────────────────────

    async def cancel(self, thread_id: int | None = None) -> bool:
        """Cancel the running CLI for a thread."""
        if thread_id in self._sessions:
            self._kill_session(thread_id)
            logger.info("Cancelled session [thread=%s]", thread_id)
            return True

        if thread_id is None and self._sessions:
            for tid in list(self._sessions.keys()):
                self._kill_session(tid)
            logger.info("Cancelled all sessions")
            return True

        return False

    async def check_status(self) -> str:
        """Check if CLI is available."""
        import shutil
        path = self._provider.config.cli_path
        if not shutil.which(path) and not os.path.isfile(path):
            return f"❌ CLI not found: {path}"

        try:
            test_args = self._provider.status_check_args()
            process = await asyncio.create_subprocess_exec(
                *test_args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=15,
            )
            output = stdout.decode("utf-8", errors="replace").strip()
            if process.returncode == 0 and output:
                active = sum(1 for s in self._sessions.values() if s.alive)
                status = f"✅ {self._provider.name} ready\n\n{output}"
                if active:
                    status += f"\n\n⚡ Active sessions: {active}"
                return status
            err = stderr.decode("utf-8", errors="replace").strip()
            return f"⚠️ {self._provider.name} issue:\n{err or output or 'Unknown error'}"
        except Exception as exc:
            return f"❌ Error checking {self._provider.name}: {exc}"

    async def list_models(self) -> list[dict]:
        """Fetch available models from CLI."""
        list_args = self._provider.list_models_args()
        if not list_args:
            return []

        try:
            process = await asyncio.create_subprocess_exec(
                *list_args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env,
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=15,
            )
            return self._provider.parse_models_output(
                stdout.decode("utf-8", errors="replace")
            )
        except Exception as exc:
            logger.error("Failed to list models: %s", exc)
            return []
