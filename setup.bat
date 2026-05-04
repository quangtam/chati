@echo off
setlocal enabledelayedexpansion

:: ── Chati Setup Wizard for Windows ──────────────────────────────

echo.
echo    ██████╗██╗  ██╗ █████╗ ████████╗██╗
echo   ██╔════╝██║  ██║██╔══██╗╚══██╔══╝██║
echo   ██║     ███████║███████║   ██║   ██║
echo   ██║     ██╔══██║██╔══██║   ██║   ██║
echo   ╚██████╗██║  ██║██║  ██║   ██║   ██║
echo    ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝  ╚═╝
echo.
echo         code from your pocket
echo.

:: ── Step 1: Check Python ────────────────────────────────────────

echo [*] Checking prerequisites...
echo.

set PYTHON=
for %%P in (python3 python py) do (
    where %%P >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=2" %%V in ('%%P --version 2^>^&1') do (
            for /f "tokens=1,2 delims=." %%A in ("%%V") do (
                if %%A geq 3 if %%B geq 12 (
                    set PYTHON=%%P
                    echo [OK] Python: %%V
                )
            )
        )
    )
)

if "%PYTHON%"=="" (
    echo [ERROR] Python 3.12+ is required but not found.
    echo.
    echo   Download from: https://www.python.org/downloads/
    echo   Make sure to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

:: ── Step 2: Create venv + install deps ──────────────────────────

if not exist ".venv" (
    echo [*] Creating virtual environment...
    %PYTHON% -m venv .venv
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment exists
)

echo [*] Installing dependencies...
.venv\Scripts\pip install -q -r requirements.txt
echo [OK] Dependencies installed
echo.

:: ── Step 3: Choose CLI provider ─────────────────────────────────

echo Which AI CLI do you want to use?
echo.
echo   1) Kiro CLI        (kiro-cli)
echo   2) Claude Code     (claude)
echo   3) Gemini CLI      (gemini)
echo   4) OpenAI Codex    (codex)
echo.
set /p CHOICE="Choose [1-4]: "

if "%CHOICE%"=="1" (set CLI_PROVIDER=kiro&   set CLI_BIN=kiro-cli)
if "%CHOICE%"=="2" (set CLI_PROVIDER=claude& set CLI_BIN=claude)
if "%CHOICE%"=="3" (set CLI_PROVIDER=gemini& set CLI_BIN=gemini)
if "%CHOICE%"=="4" (set CLI_PROVIDER=codex&  set CLI_BIN=codex)

if "%CLI_PROVIDER%"=="" (
    echo [ERROR] Invalid choice
    pause
    exit /b 1
)

where %CLI_BIN% >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] %CLI_BIN% found
) else (
    echo [WARN] %CLI_BIN% not found in PATH.
    if "%CLI_PROVIDER%"=="kiro"   echo   Install: https://kiro.dev/docs/cli/installation/
    if "%CLI_PROVIDER%"=="claude" echo   Install: npm install -g @anthropic-ai/claude-code
    if "%CLI_PROVIDER%"=="gemini" echo   Install: npm install -g @google/gemini-cli
    if "%CLI_PROVIDER%"=="codex"  echo   Install: npm install -g @openai/codex
    echo.
    set /p CONT="Continue anyway? [y/N]: "
    if /i not "!CONT!"=="y" exit /b 1
)
echo.

:: ── Step 4: Telegram bot token ──────────────────────────────────

echo Telegram Bot Setup
echo.
echo   1. Open Telegram, find @BotFather
echo   2. Send /newbot, follow the prompts
echo   3. Copy the bot token
echo.
set /p BOT_TOKEN="Paste your Telegram bot token: "

if "%BOT_TOKEN%"=="" (
    echo [ERROR] Bot token is required
    pause
    exit /b 1
)
echo.

:: ── Step 5: Telegram user ID ────────────────────────────────────

echo   To get your Telegram user ID:
echo   Open Telegram, find @userinfobot, send /start
echo.
set /p USER_IDS="Your Telegram user ID: "

if "%USER_IDS%"=="" (
    echo [ERROR] User ID is required
    pause
    exit /b 1
)
echo.

:: ── Step 6: Project directory ───────────────────────────────────

set /p PROJECT_DIR="Project directory [%CD%]: "
if "%PROJECT_DIR%"=="" set PROJECT_DIR=%CD%

if not exist "%PROJECT_DIR%" (
    echo [ERROR] Directory does not exist: %PROJECT_DIR%
    pause
    exit /b 1
)
echo [OK] Project: %PROJECT_DIR%
echo.

:: ── Step 7: Write .env ─────────────────────────────────────────

if exist ".env" (
    set /p OVERWRITE="[WARN] .env already exists. Overwrite? [y/N]: "
    if /i not "!OVERWRITE!"=="y" (
        echo [*] Keeping existing .env
        goto :done
    )
)

(
    echo TELEGRAM_BOT_TOKEN=%BOT_TOKEN%
    echo ALLOWED_USER_IDS=%USER_IDS%
    echo CLI_PROVIDER=%CLI_PROVIDER%
    echo PROJECT_DIR=%PROJECT_DIR%
    echo CLI_TIMEOUT=300
    echo CLI_TRUST_ALL_TOOLS=true
    echo LOG_LEVEL=INFO
) > .env

echo [OK] .env created

:: ── Done ────────────────────────────────────────────────────────

:done
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   Chati is ready!
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo   Make sure your CLI is logged in:
if "%CLI_PROVIDER%"=="kiro"   echo     kiro-cli login
if "%CLI_PROVIDER%"=="claude" echo     claude login
if "%CLI_PROVIDER%"=="gemini" echo     gemini auth
if "%CLI_PROVIDER%"=="codex"  echo     codex login
echo.
echo   Then start Chati:
echo     chati start
echo.
echo   Other commands:
echo     chati stop       # stop
echo     chati restart    # restart
echo     chati status     # check status
echo     chati log        # view logs
echo.
pause
