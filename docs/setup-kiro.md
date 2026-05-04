# Setup Chati with Kiro CLI

## Prerequisites

- [Kiro CLI](https://kiro.dev/docs/cli/) installed
- Kiro Pro, Pro+, or Power subscription (required for headless mode)

## Step 1: Install Kiro CLI

```bash
# macOS
brew install --cask kiro-cli

# Or download from https://kiro.dev/docs/cli/installation/
```

Verify:

```bash
kiro-cli --version
```

## Step 2: Get your API key

1. Go to [Kiro subscription settings](https://kiro.dev)
2. Find your **API Key** in account settings
3. Copy it

## Step 3: Configure Chati

Edit `.env`:

```env
CLI_PROVIDER=kiro
KIRO_API_KEY=your-kiro-api-key-here
PROJECT_DIR=/path/to/your/project
```

## Step 4: Verify

```bash
./chati start
```

Send `/status` in Telegram — you should see:

```text
✅ Kiro CLI ready

username: your-email@example.com
plan: Pro
```

## Notes

- Kiro is the only provider that **requires an API key** in `.env`
- Supports `--resume` for conversation continuity across messages
- Supports `/model` to switch between available models
- Supports BMAD skills via `/bmad-*` commands
