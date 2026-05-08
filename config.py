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
    # v2.0: Decision forwarding
    decision_idle_threshold: int = 12  # seconds before checking for prompt
    decision_reply_timeout: int = 1800  # 30min for user to reply to decision

    # v2.0 Growth: Voice features
    openai_api_key: str = ""  # Optional — if empty, local backends are used
    voice_enabled: bool = True   # Always enabled; backends auto-selected
    whisper_model: str = "gpt-4o-mini-transcribe"  # OpenAI model (when key present)
    whisper_timeout: int = 10
    whisper_local_model: str = "base"  # faster-whisper model: tiny/base/small

    # v2.0 Growth: TTS (voice output)
    tts_model: str = "gpt-4o-mini-tts"   # OpenAI model (when key present)
    tts_voice: str = "coral"              # OpenAI voice
    tts_speed: float = 1.5               # Playback speed: 0.25–4.0 (1.0 = normal)
    tts_timeout: int = 10
    tts_local_voice: str = "vi-VN-HoaiMyNeural"  # edge-tts voice (when no key)
    tts_local_rate: str = "+30%"         # edge-tts rate: +30% = 1.3x speed
    voice_output_enabled: bool = False    # Per-user default (toggle via /voice)
    voice_auto_send: bool = False         # Skip confirm — transcribe and send immediately

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

        # Voice (v2.0 Growth) — auto-select backend based on API key presence.
        # If OPENAI_API_KEY is set → use OpenAI cloud (Whisper + TTS).
        # Otherwise → use local backends (faster-whisper + edge-tts), no cost.
        openai_api_key = os.getenv("OPENAI_API_KEY", "")
        voice_enabled = True  # Always enabled — backend chosen automatically
        whisper_model = os.getenv("WHISPER_MODEL", "gpt-4o-mini-transcribe")
        whisper_timeout = int(os.getenv("WHISPER_TIMEOUT", "10"))
        whisper_local_model = os.getenv("WHISPER_LOCAL_MODEL", "base")

        # TTS (voice output)
        tts_model = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
        tts_voice = os.getenv("TTS_VOICE", "coral")
        tts_speed = float(os.getenv("TTS_SPEED", "1.5"))
        tts_timeout = int(os.getenv("TTS_TIMEOUT", "10"))
        tts_local_voice = os.getenv("TTS_LOCAL_VOICE", "vi-VN-HoaiMyNeural")
        tts_local_rate = os.getenv("TTS_LOCAL_RATE", "+30%")
        voice_output_enabled = os.getenv("VOICE_OUTPUT_ENABLED", "false").lower() == "true"
        voice_auto_send = os.getenv("VOICE_AUTO_SEND", "false").lower() == "true"

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
            decision_idle_threshold=int(os.getenv("DECISION_IDLE_THRESHOLD", "12")),
            decision_reply_timeout=int(os.getenv("DECISION_REPLY_TIMEOUT", "1800")),
            openai_api_key=openai_api_key,
            voice_enabled=voice_enabled,
            whisper_model=whisper_model,
            whisper_timeout=whisper_timeout,
            whisper_local_model=whisper_local_model,
            tts_model=tts_model,
            tts_voice=tts_voice,
            tts_speed=tts_speed,
            tts_timeout=tts_timeout,
            tts_local_voice=tts_local_voice,
            tts_local_rate=tts_local_rate,
            voice_output_enabled=voice_output_enabled,
            voice_auto_send=voice_auto_send,
        )
