"""Chati CLI runner — executes prompts via any supported AI CLI.

Supports per-thread parallel execution: different threads run
concurrent CLI processes, same thread queues sequentially.
Includes idle watchdog and stuck detection.
"""

import asyncio
import logging
import os
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

from cli_providers import CliProvider, create_provider
from config import Config

logger = logging.getLogger(__name__)

# If no new output for this many seconds, consider the process stuck
IDLE_TIMEOUT = 90


@dataclass
class CliResult:
    """Result from a CLI execution."""

    output: str
    exit_code: int
    timed_out: bool = False


class CliRunner:
    """Manages CLI subprocess execution with per-thread concurrency."""

    def __init__(self, config: Config) -> None:
        self._config = config

        # Per-thread process tracking: thread_id → active process
        self._processes: dict[int | None, asyncio.subprocess.Process] = {}
        # Per-thread exit code
        self._exit_codes: dict[int | None, int] = {}
        # Per-thread lock: ensures sequential execution within same thread
        self._locks: dict[int | None, asyncio.Lock] = {}

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
        """Get or create a lock for a thread."""
        if thread_id not in self._locks:
            self._locks[thread_id] = asyncio.Lock()
        return self._locks[thread_id]

    def is_busy(self, thread_id: int | None) -> bool:
        """Check if a thread has an active CLI process."""
        proc = self._processes.get(thread_id)
        return proc is not None and proc.returncode is None

    def get_exit_code(self, thread_id: int | None) -> int:
        """Get the last exit code for a thread."""
        return self._exit_codes.get(thread_id, 0)

    async def execute_stream(
        self,
        prompt: str,
        *,
        thread_id: int | None = None,
        model: str | None = None,
        resume: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Execute a prompt and yield output lines as they arrive.

        Per-thread: acquires a lock so same-thread messages queue,
        but different threads run in parallel.
        """
        lock = self._get_lock(thread_id)

        async with lock:
            async for line in self._stream_inner(
                prompt, thread_id=thread_id, model=model, resume=resume
            ):
                yield line

    async def _stream_inner(
        self,
        prompt: str,
        *,
        thread_id: int | None,
        model: str | None,
        resume: bool,
    ) -> AsyncGenerator[str, None]:
        """Inner streaming implementation with watchdog."""
        args = self._provider.build_args(prompt, model=model, resume=resume)
        logger.info("Streaming [thread=%s]: %s", thread_id, " ".join(args))

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._config.project_dir,
                env=self._env,
            )
            self._processes[thread_id] = process
            assert process.stdout is not None

            deadline = time.monotonic() + self._config.cli_timeout
            last_output_time = time.monotonic()
            idle_warnings = 0

            while True:
                now = time.monotonic()

                if now >= deadline:
                    logger.warning("Stream global timeout [thread=%s]", thread_id)
                    await self._kill_process(process, thread_id)
                    yield "\n⏱ Global timeout reached. Process killed.\n"
                    return

                idle_seconds = now - last_output_time
                if idle_seconds >= IDLE_TIMEOUT:
                    logger.warning("Stream idle %ds [thread=%s]", int(idle_seconds), thread_id)
                    await self._kill_process(process, thread_id)
                    yield f"\n⏱ No output for {int(idle_seconds)}s — process stuck. Killed.\n"
                    return

                if idle_seconds >= IDLE_TIMEOUT / 2 and idle_warnings == 0:
                    idle_warnings = 1
                    yield f"\n⏳ Waiting for output ({int(idle_seconds)}s)...\n"

                read_timeout = min(10, deadline - now, IDLE_TIMEOUT - idle_seconds)
                try:
                    line_bytes = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=max(read_timeout, 1),
                    )
                except asyncio.TimeoutError:
                    if process.returncode is not None:
                        break
                    continue

                if not line_bytes:
                    break

                last_output_time = time.monotonic()
                idle_warnings = 0
                yield line_bytes.decode("utf-8", errors="replace")

            await process.wait()
            self._exit_codes[thread_id] = process.returncode or 0
            self._processes.pop(thread_id, None)

            if process.stderr:
                stderr_bytes = await process.stderr.read()
                stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
                if stderr and (process.returncode or 0) != 0:
                    yield f"\n⚠️ Stderr:\n{stderr}\n"

        except FileNotFoundError:
            self._exit_codes[thread_id] = -1
            self._processes.pop(thread_id, None)
            yield f"❌ CLI not found at: {self._provider.config.cli_path}\n"
        except Exception as exc:
            self._exit_codes[thread_id] = -1
            self._processes.pop(thread_id, None)
            yield f"❌ Unexpected error: {exc}\n"
            logger.exception("Stream error [thread=%s]", thread_id)

    async def _kill_process(
        self, process: asyncio.subprocess.Process, thread_id: int | None
    ) -> None:
        """Kill a subprocess and clean up."""
        try:
            process.kill()
            await asyncio.wait_for(process.wait(), timeout=5)
        except (ProcessLookupError, asyncio.TimeoutError):
            pass
        self._exit_codes[thread_id] = -1
        self._processes.pop(thread_id, None)

    async def cancel(self, thread_id: int | None = None) -> bool:
        """Cancel the running CLI process for a thread.

        If thread_id is None and no process for None, cancels ALL.
        """
        if thread_id in self._processes:
            proc = self._processes[thread_id]
            if proc.returncode is None:
                await self._kill_process(proc, thread_id)
                logger.info("Cancelled CLI process [thread=%s]", thread_id)
                return True

        # Fallback: cancel all if no specific thread match
        if thread_id is None and self._processes:
            for tid, proc in list(self._processes.items()):
                if proc.returncode is None:
                    await self._kill_process(proc, tid)
            logger.info("Cancelled all CLI processes")
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
                active = len([p for p in self._processes.values() if p.returncode is None])
                status = f"✅ {self._provider.name} ready\n\n{output}"
                if active:
                    status += f"\n\n⚡ Active processes: {active}"
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
