"""Base class and config for CLI providers."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CliProviderConfig:
    """Provider-specific configuration passed at init time."""

    cli_path: str
    api_key: str
    trust_all_tools: bool = True
    extra_args: list[str] | None = None


class CliProvider(ABC):
    """Abstract base for all CLI provider drivers.

    Subclasses MUST set:
        provider_id:      str — unique key used in .env CLI_PROVIDER
        name:             str — human-readable name for Telegram messages
        default_cli_path: str — binary name for PATH auto-detection

    Subclasses MUST implement:
        build_args()  — construct the CLI command list
        build_env()   — inject provider-specific env vars

    Subclasses MAY override:
        response_marker     — stdout prefix that marks response start
        supports_resume()   — True if CLI has --resume or equivalent
        supports_model_selection() — True if CLI has --model
        list_models_args()  — command to list available models
        parse_models_output() — parse that command's stdout
        status_check_args() — command to verify CLI is working
    """

    # ── Required class attributes (set in subclass) ──────────────
    provider_id: str = ""
    name: str = "Unknown"
    default_cli_path: str = ""

    # ── Optional class attributes ────────────────────────────────
    # Prefix that marks the start of the actual AI response in stdout.
    # Empty string means all output is treated as response (no tool noise).
    response_marker: str = ""

    # v2.0: Provider-specific decision prompt patterns (optional override).
    # Used in addition to generic patterns ([y/N], [Y/n], etc.) for detecting
    # when the CLI is waiting for interactive input.
    decision_prompt_patterns: list[re.Pattern] = []

    def __init__(self, config: CliProviderConfig) -> None:
        self.config = config

    # ── Abstract methods ─────────────────────────────────────────

    @abstractmethod
    def build_args(
        self,
        prompt: str,
        *,
        model: str | None = None,
        resume: bool = False,
    ) -> list[str]:
        """Build the full CLI command as a list of strings."""

    @abstractmethod
    def build_env(self, base_env: dict[str, str]) -> dict[str, str]:
        """Return env dict with provider-specific variables added."""

    # ── Optional overrides ───────────────────────────────────────

    def supports_resume(self) -> bool:
        """Whether this CLI supports conversation resume."""
        return False

    def supports_model_selection(self) -> bool:
        """Whether this CLI supports a --model flag."""
        return True

    def list_models_args(self) -> list[str] | None:
        """Return CLI args to list models, or None if unsupported."""
        return None

    def parse_models_output(self, stdout: str) -> list[dict]:
        """Parse list-models stdout into a list of model dicts.

        Expected dict keys: model_id, model_name, description,
        rate_multiplier (optional), rate_unit (optional).
        """
        return []

    def status_check_args(self) -> list[str]:
        """Return CLI args for a quick health check.

        Default: <cli> --version
        """
        return [self.config.cli_path, "--version"]

    def build_interactive_args(self, *, model: str | None = None) -> list[str] | None:
        """Return CLI args to start an interactive session.

        Returns None if this provider doesn't support interactive mode.
        Override in subclass to enable persistent sessions.
        """
        return None

    # ── Helpers available to subclasses ───────────────────────────

    def _base_env(self, base_env: dict[str, str]) -> dict[str, str]:
        """Common env vars that suppress color/interactive for all CLIs."""
        env = base_env.copy()
        env["NO_COLOR"] = "1"
        env["TERM"] = "dumb"
        env["FORCE_COLOR"] = "0"
        return env
