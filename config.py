"""Chati configuration loader.

Supports multiple CLI providers: Kiro, Claude Code, Gemini, Codex.
"""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


@dataclass(frozen=True)
class Config:
    """Immutable bot configuration loaded from environment."""

    # Telegram
    telegram_token: str
    allowed_user_ids: frozenset[int]

    # CLI Provider
    cli_provider: str          # kiro, claude, gemini, codex
    cli_path: str              # Path to CLI binary
    cli_api_key: str           # API key for the CLI
    cli_extra_args: tuple[str, ...]  # Additional CLI arguments

    # Project
    project_dir: str
    cli_timeout: int
    trust_all_tools: bool
    log_level: str

    # v2.0: Resource limits
    max_sessions: int = 5
    idle_session_max_age: int = 1800  # 30 minutes
    cleanup_interval: int = 300  # 5 minutes

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required in .env")

        raw_ids = os.getenv("ALLOWED_USER_IDS", "")
        if not raw_ids:
            raise ValueError("ALLOWED_USER_IDS is required in .env")
        allowed = frozenset(
            int(uid.strip()) for uid in raw_ids.split(",") if uid.strip()
        )

        # CLI Provider — default to kiro for backward compatibility
        provider = os.getenv("CLI_PROVIDER", "kiro").lower().strip()

        # API key — optional, most CLIs use local login session
        api_key = (
            os.getenv("CLI_API_KEY")
            or os.getenv("KIRO_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        )

        # CLI path — check provider-specific first, then generic
        cli_path = (
            os.getenv("CLI_PATH")
            or os.getenv("KIRO_CLI_PATH")
            or ""
        )

        # Extra CLI arguments (space-separated)
        extra_args_raw = os.getenv("CLI_EXTRA_ARGS", "")
        extra_args = tuple(
            a.strip() for a in extra_args_raw.split() if a.strip()
        )

        project_dir = os.getenv("PROJECT_DIR", os.getcwd())
        if not Path(project_dir).is_dir():
            raise ValueError(f"PROJECT_DIR does not exist: {project_dir}")

        return cls(
            telegram_token=token,
            allowed_user_ids=allowed,
            cli_provider=provider,
            cli_path=cli_path,
            cli_api_key=api_key,
            cli_extra_args=extra_args,
            project_dir=project_dir,
            cli_timeout=int(os.getenv("CLI_TIMEOUT", os.getenv("KIRO_TIMEOUT", "600"))),
            trust_all_tools=os.getenv(
                "CLI_TRUST_ALL_TOOLS",
                os.getenv("KIRO_TRUST_ALL_TOOLS", "true"),
            ).lower() == "true",
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            max_sessions=int(os.getenv("MAX_SESSIONS", "5")),
            idle_session_max_age=int(os.getenv("IDLE_SESSION_MAX_AGE", "1800")),
            cleanup_interval=int(os.getenv("CLEANUP_INTERVAL", "300")),
        )
