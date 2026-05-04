# Chati — Agent Context

## What Is This?

Chati — chat with any AI coding CLI from your phone. A Python bot that bridges messaging apps to AI CLIs (Kiro, Claude Code, Gemini, Codex) in headless mode. Standalone project.

## Architecture

```text
Chat App User -> Chati (python-telegram-bot)
  -> CliProvider.build_args() -> subprocess (streaming stdout)
  -> strip ANSI -> extract response -> Markdown to HTML -> chat reply
```

## File Structure

```text
chati.py                # Main entry: handlers, auth guard, streaming, command routing
chati                   # Bash management script (start/stop/restart/status/log)
config.py               # Config dataclass from .env (multi-CLI aware)
cli_runner.py           # CliRunner: subprocess wrapper, streaming, model listing
message_utils.py        # ANSI strip, response extraction, MD to HTML, message splitting

cli_providers/          # Pluggable CLI driver package (auto-discovery)
  __init__.py           # Re-exports: CliProvider, create_provider, get_available_providers
  base.py               # CliProvider ABC + CliProviderConfig dataclass
  registry.py           # Auto-scans cli_providers/*.py, registers by provider_id
  kiro.py               # Kiro CLI driver
  claude.py             # Claude Code driver
  gemini.py             # Gemini CLI driver
  codex.py              # OpenAI Codex driver

.env                    # Secrets (not committed)
.env.example            # Template
requirements.txt        # python-telegram-bot==21.10, python-dotenv==1.1.0
```

## How to Run

```bash
./chati start           # start in background
./chati restart         # kill + wait + start
./chati status          # check PID
./chati log             # tail -f chati.log
```

## Tech Stack

- Python 3.12+
- python-telegram-bot 21.10 (async)
- python-dotenv 1.1.0

## Key Design Decisions

1. **Pluggable CLI providers** -- cli_providers/ package with auto-discovery. Each driver is a single file with a CliProvider subclass. Registry scans on import via pkgutil.iter_modules. Adding a new CLI = one file, zero changes elsewhere.

2. **Streaming output** -- execute_stream() reads stdout line-by-line via asyncio.subprocess. Bot sends one message and edits it every 1.5s (respects Telegram rate limit of 30 edits/min). Tool activity shown as status line; response content shown as pre preview. Final formatted message sent after process exits.

3. **Response extraction** -- Some CLIs (e.g. Kiro) prefix the actual response with "> ". The extract_final_response() function finds this marker and strips everything before it (trust warnings, tool invocations, spawn logs, credits footer). Providers with no marker (Claude, Gemini, Codex) treat all output as response.

4. **Thread-based sessions** -- message_thread_id maps to session state. First message = new session; subsequent = --resume. /new resets. Tracked in _thread_sessions dict (in-memory, resets on restart).

5. **Model selection** -- /model fetches models via provider.list_models_args() + parse_models_output(). Inline keyboard, per-user storage in context.user_data["model"].

6. **Markdown to Telegram HTML** -- Pipeline: strip ANSI, extract response, convert MD to HTML (b, pre, code, i, blockquote, a). Falls back to plain text on parse error.

7. **subprocess stdin=DEVNULL** -- Prevents SIGTTIN (stopped) when bot runs via nohup.

8. **Auth guard** -- @authorized decorator checks update.effective_user.id against ALLOWED_USER_IDS whitelist.

9. **BMAD routing** -- Telegram commands use underscores (/bmad_create_prd), CLI skills use hyphens (/bmad-create-prd). Auto-converted.

10. **Management script** -- ./chati {start|stop|restart|status|log} with PID file tracking, graceful shutdown, polling release wait.

## Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| TELEGRAM_BOT_TOKEN | Yes | From @BotFather |
| ALLOWED_USER_IDS | Yes | Comma-separated Telegram user IDs |
| CLI_PROVIDER | No | kiro (default), claude, gemini, codex |
| CLI_PATH | No | Override CLI binary path |
| CLI_API_KEY | No | API key (only for headless/SSH machines) |
| CLI_TIMEOUT | No | Default: 300s |
| CLI_TRUST_ALL_TOOLS | No | Default: true |
| CLI_EXTRA_ARGS | No | Space-separated extra CLI flags |
| KIRO_API_KEY | No | Kiro auth (optional — prefers local login) |
| ANTHROPIC_API_KEY | No | Claude auth (optional — prefers local login) |
| GEMINI_API_KEY | No | Gemini auth (optional — prefers local login) |
| OPENAI_API_KEY | No | Codex auth (optional — prefers local login) |
| PROJECT_DIR | Yes | Working directory for CLI subprocess |
| LOG_LEVEL | No | Default: INFO |

## Adding a CLI Provider

Create cli_providers/newcli.py with a CliProvider subclass. Set provider_id, name, default_cli_path. Implement build_args() and build_env(). Registry auto-discovers it. Set CLI_PROVIDER=newcli in .env and restart.

## Known Issues

- Single project per instance
- Thread sessions are in-memory, reset on restart
- 409 Conflict if multiple instances poll same token
