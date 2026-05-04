# Chati

```
   ██████╗██╗  ██╗ █████╗ ████████╗██╗
  ██╔════╝██║  ██║██╔══██╗╚══██╔══╝██║
  ██║     ███████║███████║   ██║   ██║
  ██║     ██╔══██║██╔══██║   ██║   ██║
  ╚██████╗██║  ██║██║  ██║   ██║   ██║
   ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝  ╚═╝
        code from your pocket 💬→💻
```

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Chat with any AI coding CLI from your phone. No laptop needed.

<p align="center">
  <img src="assets/screenshot.jpg" alt="Chati screenshot" width="360" />
</p>

<p align="center">
  <video src="https://github.com/quangtam/chati/raw/main/assets/demo.mp4" width="360" controls>
    Video demo
  </video>
</p>

Chati bridges your favorite messaging app to AI coding CLIs (Kiro, Claude Code, Gemini, Codex) — send a message, get code back.

## Features

- **Multi-CLI** — pluggable drivers for Kiro, Claude Code, Gemini, OpenAI Codex
- **Streaming** — real-time response streaming with progressive message edits
- **Thread = Session** — each chat thread maps to a separate conversation
- **Model selection** — `/model` command with inline keyboard to switch AI models
- **BMAD workflow** — slash command routing for BMAD skills
- **Markdown → HTML** — CLI output converted to native chat formatting

## Supported CLIs

| Provider | Binary | Headless flag | Authentication | Setup guide |
| -------- | ------ | ------------- | -------------- | ----------- |
| Kiro | `kiro-cli` | `--no-interactive` | `kiro-cli login` on machine | [Setup Kiro](docs/setup-kiro.md) |
| Claude Code | `claude` | `-p` | `claude login` on machine | [Setup Claude](docs/setup-claude.md) |
| Gemini | `gemini` | `-p` | `gemini auth` on machine | [Setup Gemini](docs/setup-gemini.md) |
| Codex | `codex` | `exec` | `codex login` on machine | [Setup Codex](docs/setup-codex.md) |

> **Note:** All CLIs authenticate via browser login on the machine where Chati runs. Install the CLI, login once, and Chati uses that local session. No API keys needed.

## Prerequisites

- **Python 3.12+** — [download](https://www.python.org/downloads/) or `brew install python@3.12`
- **One AI CLI installed and logged in** — see [Supported CLIs](#supported-CLIs)
- **Telegram account** — to create a bot via [@BotFather](https://t.me/BotFather)

## Quick Start

```bash
git clone https://github.com/quangtam/chati.git
cd chati
bash setup.sh
```

The setup wizard will:

1. Check Python version
2. Create virtual environment and install dependencies
3. Ask which AI CLI you want to use
4. Configure Telegram bot token and user ID
5. Set your project directory
6. Generate `.env`

After setup, login your CLI and start:

```bash
# Login your CLI (one time only)
kiro-cli login    # or: claude login / gemini auth / codex login

# Start Chati
./chati start
```

## Manual Setup

If you prefer to configure manually:

### 1. Create a chat bot

Currently supports Telegram. Create a bot via [@BotFather](https://t.me/BotFather):
1. Open Telegram, find `@BotFather`
2. Send `/newbot`, set name and username
3. Copy the **BOT_TOKEN**

### 2. Get your Telegram User ID

1. Find `@userinfobot` on Telegram
2. Send `/start` — it returns your User ID

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=your-bot-token
ALLOWED_USER_IDS=123456789

# Pick your CLI provider: kiro, claude, gemini, codex
CLI_PROVIDER=kiro

PROJECT_DIR=/path/to/your/project
```

> **Auth:** Just login your CLI once on the machine (`kiro-cli login`, `claude login`, etc.). Chati uses that local session. No API keys needed in `.env`.

### 4. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5. Run

```bash
./chati start      # start in background
./chati stop       # stop
./chati restart    # restart
./chati status     # check if running
./chati log        # tail -f logs
```

## Usage

### Commands

| Command | Description |
| ------- | ----------- |
| `/start` | Show welcome message |
| `/help` | Usage guide |
| `/model` | Select AI model (inline keyboard) |
| `/skills` | List available BMAD skills |
| `/status` | Check CLI availability |
| `/cancel` | Kill running CLI process |
| `/new` | Reset session for current thread |
| `/resume` | Resume previous session |

### Chat

Send any message — Chati forwards it to the configured CLI:

```text
You: Check sprint status
Chati: [streaming response from CLI]
```

### Thread-based sessions

- First message in a thread → new session
- Subsequent messages → auto-resume conversation
- `/new` in a thread → reset that thread's session

### BMAD skills

```text
/bmad-sprint-status
/bmad-create-prd
/bmad-code-review
```

## Adding a new CLI provider

Create a file in `cli_providers/`, e.g. `cli_providers/my_cli.py`:

```python
from cli_providers.base import CliProvider

class MyCLIProvider(CliProvider):
    provider_id = "mycli"
    name = "My CLI"
    default_cli_path = "mycli"

    def build_args(self, prompt, *, model=None, resume=False):
        args = [self.config.cli_path, "--prompt", prompt]
        if model:
            args.extend(["--model", model])
        return args

    def build_env(self, base_env):
        env = self._base_env(base_env)
        if self.config.api_key:
            env["MYCLI_KEY"] = self.config.api_key
        return env
```

Then set `CLI_PROVIDER=mycli` in `.env`. No other changes needed.

## Limitations

- Telegram message limit: 4096 chars (auto-split for longer output)
- Single project directory per bot instance
- Only one bot instance can poll the same token at a time

## License

[MIT](LICENSE) — free to use, modify, and distribute.
