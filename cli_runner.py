"""Chati CLI runner — executes prompts via any supported AI CLI.

Uses the CliProvider abstraction to support Kiro, Claude Code,
Gemini CLI, and Codex CLI with a unified interface.
Supports streaming output and session resume.
"""

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from cli_providers import CliProvider, create_provider
from config import Config

logger = logging.getLogger(__name__)


@dataclass
class CliResult:
    """Result from a CLI execution."""

    output: str
    exit_code: int
    timed_out: bool = False


class CliRunner:
    """Manages CLI subprocess execution via provider abstraction."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._active_process: asyncio.subprocess.Process | None = None
        self.last_exit_code: int = 0

        # Create the CLI provider
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
        """The active CLI provider."""
        return self._provider

    @property
    def _env(self) -> dict[str, str]:
        """Build environment variables via the provider."""
        return self._provider.build_env(os.environ.copy())

    async def execute(
        self,
        prompt: str,
        *,
        model: str | None = None,
        resume: bool = False,
    ) -> CliResult:
        """Execute a prompt via CLI (non-streaming)."""
        args = self._provider.build_args(prompt, model=model, resume=resume)
        logger.info("Executing: %s", " ".join(args))

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._config.project_dir,
                env=self._env,
            )
            self._active_process = process

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._config.cli_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("CLI timed out after %ds", self._config.cli_timeout)
                process.kill()
                await process.wait()
                self._active_process = None
                return CliResult(
                    output=f"⏱ CLI timed out after {self._config.cli_timeout}s. "
                    "Use /cancel or try a simpler prompt.",
                    exit_code=-1,
                    timed_out=True,
                )

            self._active_process = None
            stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

            output = stdout
            if not output and stderr:
                output = stderr
            elif stderr and process.returncode != 0:
                output = f"{stdout}\n\n⚠️ Stderr:\n{stderr}" if stdout else stderr
            if not output:
                output = "(CLI returned empty output)"

            return CliResult(output=output, exit_code=process.returncode or 0)

        except FileNotFoundError:
            msg = f"❌ CLI not found at: {self._provider.config.cli_path}"
            logger.error(msg)
            return CliResult(output=msg, exit_code=-1)
        except Exception as exc:
            msg = f"❌ Unexpected error: {exc}"
            logger.exception(msg)
            return CliResult(output=msg, exit_code=-1)

    async def execute_stream(
        self,
        prompt: str,
        *,
        model: str | None = None,
        resume: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Execute a prompt and yield output lines as they arrive."""
        args = self._provider.build_args(prompt, model=model, resume=resume)
        logger.info("Streaming: %s", " ".join(args))

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._config.project_dir,
                env=self._env,
            )
            self._active_process = process
            assert process.stdout is not None

            deadline = asyncio.get_event_loop().time() + self._config.cli_timeout

            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    logger.warning("Stream timed out after %ds", self._config.cli_timeout)
                    process.kill()
                    await process.wait()
                    self._active_process = None
                    self.last_exit_code = -1
                    yield f"\n⏱ Timed out after {self._config.cli_timeout}s."
                    return

                try:
                    line_bytes = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=min(remaining, 60),
                    )
                except asyncio.TimeoutError:
                    if process.returncode is None:
                        continue
                    break

                if not line_bytes:
                    break

                yield line_bytes.decode("utf-8", errors="replace")

            await process.wait()
            self._active_process = None
            self.last_exit_code = process.returncode or 0

            if process.stderr:
                stderr_bytes = await process.stderr.read()
                stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
                if stderr and self.last_exit_code != 0:
                    yield f"\n⚠️ Stderr:\n{stderr}\n"

        except FileNotFoundError:
            self.last_exit_code = -1
            yield f"❌ CLI not found at: {self._provider.config.cli_path}\n"
        except Exception as exc:
            self.last_exit_code = -1
            yield f"❌ Unexpected error: {exc}\n"
            logger.exception("Stream error")

    async def cancel(self) -> bool:
        """Cancel the currently running CLI process."""
        if self._active_process and self._active_process.returncode is None:
            self._active_process.kill()
            await self._active_process.wait()
            self._active_process = None
            logger.info("Cancelled active CLI process")
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
                return f"✅ {self._provider.name} ready\n\n{output}"
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
