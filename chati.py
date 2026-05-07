"""Chati — chat with any AI coding CLI from your phone.

Bridges messaging apps to AI CLIs (Kiro, Claude Code, Gemini, Codex)
in headless mode with streaming output.

Features:
- Thread-based sessions (each thread = separate conversation)
- Model selection via /model command with inline keyboard
- Pluggable CLI providers
- BMAD skill routing
"""

import asyncio
import logging
import os
import re
import time
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import Config
from cli_runner import CliRunner
from cli_providers import get_available_providers
from message_utils import format_output, split_message, strip_ansi, extract_final_response, strip_streaming_noise
from session_manager import DecisionPrompt, PtyState, SessionManager
import db
from db import DEFAULT_THREAD_ID, DB_PATH

# ── Globals ──────────────────────────────────────────────────────

config = Config.from_env()
runner = CliRunner(config)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=getattr(logging, config.log_level, logging.INFO),
)
logger = logging.getLogger(__name__)

# Track which threads have had at least one message processed.
# Key: thread_id (int or None for non-thread), Value: message count.
_thread_sessions: dict[int | None, int] = {}

# Track the currently-running asyncio task per thread, so /cancel can
# abort the task (not just kill the PTY process). Set in _execute_and_reply,
# cleared in finally, cancelled in cmd_cancel.
_thread_tasks: dict[int | None, asyncio.Task] = {}

MAX_MSG_LEN = 4096


# ── Auth Guard ───────────────────────────────────────────────────

def authorized(func):
    """Decorator to restrict bot access to allowed user IDs."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id not in config.allowed_user_ids:
            uid = user.id if user else "unknown"
            logger.warning("Unauthorized access attempt from user %s", uid)
            if update.message:
                await update.message.reply_text(
                    "⛔ Unauthorized. Your user ID is not in the allowed list."
                )
            return
        return await func(update, context)
    return wrapper


# ── Session Helpers ──────────────────────────────────────────────

def _get_thread_id(update: Update) -> int | None:
    """Extract thread ID from a Telegram message.

    Returns message_thread_id if in a topic/thread, else None.
    """
    if update.message and update.message.message_thread_id:
        return update.message.message_thread_id
    return None


def _should_resume(thread_id: int | None, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Determine if this message should resume an existing session.

    - If user explicitly requested /new → don't resume.
    - If this thread has had previous messages → resume.
    - First message in a thread → don't resume (fresh session).
    """
    if context.user_data.get("force_new_session"):
        context.user_data["force_new_session"] = False
        # Reset thread counter
        _thread_sessions[thread_id] = 0
        return False

    count = _thread_sessions.get(thread_id, 0)
    return count > 0


def _track_thread(thread_id: int | None) -> None:
    """Increment message count for a thread."""
    _thread_sessions[thread_id] = _thread_sessions.get(thread_id, 0) + 1


def _get_model(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """Get the user's selected model, or None for default."""
    model = context.user_data.get("model")
    if model == "auto":
        return None  # auto = let CLI decide
    return model


# ── Command Handlers ─────────────────────────────────────────────

@authorized
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    model = context.user_data.get("model", "auto")
    await update.message.reply_text(
        f"🚀 <b>Chati</b> — {_escape_html(runner.provider.name)}\n\n"
        "Gửi tin nhắn bất kỳ → CLI xử lý trong project:\n"
        f"<code>{config.project_dir}</code>\n\n"
        "<b>Commands:</b>\n"
        "/help — Hướng dẫn sử dụng\n"
        "/model — Chọn AI model\n"
        "/skills — Liệt kê BMAD skills\n"
        "/status — Kiểm tra CLI\n"
        "/cancel — Hủy lệnh đang chạy\n"
        "/new — Tạo session mới\n\n"        "<b>💡 Thread = Session:</b>\n"
        "Mỗi thread riêng biệt = 1 conversation session.\n"
        "Tin nhắn tiếp theo trong cùng thread sẽ tự động resume.\n\n"
        f"<b>Model:</b> <code>{model}</code>",
        parse_mode=ParseMode.HTML,
    )


@authorized
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    model = context.user_data.get("model", "auto")
    await update.message.reply_text(
        "📖 <b>Hướng dẫn sử dụng</b>\n\n"
        "<b>Chat tự do:</b>\n"
        "Gõ bất kỳ câu hỏi/yêu cầu → CLI xử lý\n\n"
        "<b>Thread = Session:</b>\n"
        "• Tin nhắn đầu tiên trong thread → session mới\n"
        "• Tin nhắn tiếp theo → tự động resume session\n"
        "• /new trong thread → reset session\n"
        "• Ngoài thread → mỗi tin nhắn cũng resume\n\n"
        "<b>Model:</b>\n"
        "/model — Chọn AI model (inline keyboard)\n"
        f"Đang dùng: <code>{model}</code>\n\n"
        "<b>BMAD Workflow:</b>\n"
        "<code>/bmad-create-prd</code> — Tạo PRD\n"
        "<code>/bmad-create-architecture</code> — Thiết kế architecture\n"
        "<code>/bmad-sprint-planning</code> — Sprint planning\n"
        "<code>/bmad-dev-story</code> — Implement story\n"
        "<code>/bmad-code-review</code> — Code review\n\n"
        "<b>Quản lý:</b>\n"
        "/status — Kiểm tra CLI\n"
        "/cancel — Hủy lệnh đang chạy\n"
        "/new — Tạo session mới\n"
        "/resume — Resume session trước\n\n"
        f"<b>Project:</b> <code>{Path(config.project_dir).name}</code>\n"
        f"<b>Timeout:</b> {config.cli_timeout}s",
        parse_mode=ParseMode.HTML,
    )


# ── Model Selection ──────────────────────────────────────────────

# Emoji indicators for model tiers
_MODEL_EMOJI = {
    "auto": "🔄",
    "claude-opus": "🟣",
    "claude-sonnet": "🔵",
    "claude-haiku": "🟢",
    "deepseek": "🟠",
    "minimax": "🟡",
    "glm": "🟤",
    "qwen": "⚪",
}


def _model_emoji(model_id: str) -> str:
    """Get emoji for a model based on its family."""
    for prefix, emoji in _MODEL_EMOJI.items():
        if model_id.startswith(prefix):
            return emoji
    return "⚙️"


@authorized
async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /model — show model selection keyboard."""
    await update.message.reply_chat_action(ChatAction.TYPING)

    models = await runner.list_models()
    if not models:
        await update.message.reply_text("⚠️ Could not fetch models from CLI.")
        return

    current = context.user_data.get("model", "auto")

    # Build inline keyboard — 2 columns
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for m in models:
        mid = m["model_id"]
        name = m["model_name"]
        rate = m.get("rate_multiplier", 1.0)
        emoji = _model_emoji(mid)
        check = " ✓" if mid == current else ""
        label = f"{emoji} {name} ({rate}x){check}"

        row.append(InlineKeyboardButton(label, callback_data=f"model:{mid}"))
        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    await update.message.reply_text(
        f"🤖 <b>Chọn AI Model</b>\n\n"
        f"Đang dùng: <code>{current}</code>\n"
        f"Giá hiển thị là credit multiplier (thấp = rẻ hơn).",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@authorized
async def handle_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard callback for model selection."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data or not data.startswith("model:"):
        return

    model_id = data.removeprefix("model:")
    context.user_data["model"] = model_id

    # Persist to SQLite (per-thread) so it survives bot restart
    thread_id = _get_thread_id(update) or DEFAULT_THREAD_ID
    try:
        await db.upsert_thread_config(thread_id, model=model_id, path=DB_PATH)
    except ValueError:
        # Thread has no row yet (no project_dir) — only store in user_data
        pass

    emoji = _model_emoji(model_id)
    await query.edit_message_text(
        f"{emoji} Model đã chuyển sang: <b>{model_id}</b>",
        parse_mode=ParseMode.HTML,
    )
    logger.info("User %s switched model to: %s (thread=%s)", update.effective_user.id, model_id, thread_id)


# ── Other Commands ───────────────────────────────────────────────

@authorized
async def cmd_skills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /skills — list available BMAD skills."""
    skills_dir = Path(config.project_dir) / ".kiro" / "skills"
    if not skills_dir.is_dir():
        await update.message.reply_text("⚠️ No .kiro/skills/ directory found in project.")
        return

    bmad_skills = sorted(
        d.name for d in skills_dir.iterdir()
        if d.is_dir() and d.name.startswith("bmad-")
    )

    if not bmad_skills:
        await update.message.reply_text("⚠️ No BMAD skills found.")
        return

    agents = [s for s in bmad_skills if "agent-" in s]
    workflows = [s for s in bmad_skills if s not in agents]

    lines = ["🧠 <b>BMAD Skills Available</b>\n"]
    if workflows:
        lines.append("<b>Workflows:</b>")
        for skill in workflows:
            lines.append(f"  <code>/{skill}</code>")
    if agents:
        lines.append("\n<b>Agents:</b>")
        for skill in agents:
            lines.append(f"  <code>/{skill}</code>")
    lines.append(f"\n📊 Total: {len(bmad_skills)} skills")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@authorized
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status — check CLI availability."""
    await update.message.reply_chat_action(ChatAction.TYPING)
    model = context.user_data.get("model", "auto")
    thread_id = _get_thread_id(update)
    thread_count = _thread_sessions.get(thread_id, 0)

    status = await runner.check_status()
    status += f"\n\n🤖 Model: {model}"
    status += f"\n💬 Thread messages: {thread_count}"
    await update.message.reply_text(status)


def _format_duration(seconds: float) -> str:
    """Format elapsed seconds as human-readable duration.

    Examples: 45s → "45s", 3660s → "1h 1m", 125s → "2m 5s"
    """
    total = int(seconds) if seconds > 0 else 0
    if total < 60:
        return f"{total}s"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {secs}s"


@authorized
async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /info — show current session details (read-only).

    Layout prioritizes what users care most on mobile:
      1. Project (bold, top — "where am I working")
      2. Status (emoji + state)
      3. Pending-decision alert (if any)
      4. Provider + model
      5. Duration / last activity / messages
      6. Technical details (thread, timeout, PID, binary, pool, usage)

    Never shells out to CLI (must be instant). Never mutates session state.
    """
    await update.message.reply_chat_action(ChatAction.TYPING)

    thread_id = _get_thread_id(update)
    lookup_id = thread_id if thread_id is not None else DEFAULT_THREAD_ID

    # Thread config from SQLite (best-effort)
    try:
        thread_config = await db.get_thread_config(lookup_id, path=DB_PATH)
    except Exception as exc:
        logger.warning("[cmd_info] failed to load thread config: %s", exc)
        thread_config = None

    provider = runner.provider
    provider_name = provider.name
    cli_path = provider.config.cli_path
    user_model = context.user_data.get("model")
    model = (thread_config.model if thread_config and thread_config.model else None) or user_model or "default"
    project_dir = (thread_config.project_dir if thread_config else None) or config.project_dir
    project_name = Path(project_dir).name if project_dir else "—"
    timeout_s = (
        thread_config.timeout_seconds
        if thread_config and thread_config.timeout_seconds
        else config.cli_timeout
    )
    thread_provider = (
        thread_config.cli_provider if thread_config and thread_config.cli_provider else config.cli_provider
    )

    # Session pool stats
    session_mgr = runner._session_mgr
    active_total = session_mgr.active_count()
    max_slots = session_mgr.max_sessions
    thread_label = str(thread_id) if thread_id is not None else "main"

    # Active session info (from memory, no CLI shell-out)
    session = session_mgr.get(thread_id)

    # ── Branch A: no active session ──────────────────────────────
    if session is None or session.state == PtyState.DEAD:
        lines = [
            f"📁 <b>{project_name}</b>",
            f"   <code>{project_dir}</code>",
            "",
            "💤 <b>No active session</b>",
            "",
            f"📡 {provider_name}  |  🤖 <code>{model}</code>",
            "",
            "<i>Send a message to start a session.</i>",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🧵 Thread: <code>{thread_label}</code>  |  "
            f"⚙️ Timeout: {timeout_s}s  |  "
            f"⚡ Pool: {active_total}/{max_slots}",
            f"🛠 Binary: <code>{cli_path}</code>",
        ]
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return

    # ── Branch B: active session ─────────────────────────────────
    now = time.monotonic()
    duration = _format_duration(now - session.created_at)
    idle_for = _format_duration(now - session.last_active_at)
    msg_count = _thread_sessions.get(thread_id, 0)
    status_emoji = SessionManager.get_status_emoji(session.state)
    state_name = session.state.value
    ready_mark = "ready" if session.ready else "warming up"
    usage_text = provider.parse_usage_output("") or "not available"

    lines = [
        # 1. Project — top priority, bold
        f"📁 <b>{project_name}</b>",
        f"   <code>{project_dir}</code>",
        "",
        # 2. Status — what's happening right now
        f"{status_emoji} <b>{state_name}</b>  ({ready_mark})",
    ]

    # 3. Pending-decision alert — if applicable, right after status
    if session.state == PtyState.WAITING_FOR_USER:
        elapsed = now - session.last_active_at
        remaining = max(0, config.decision_reply_timeout - int(elapsed))
        lines.append(
            f"⚠️ <b>Waiting for your reply</b> — expires in {_format_duration(remaining)}"
        )

    lines.extend([
        "",
        # 4. Provider + model — who you're talking to
        f"📡 {provider_name}  |  🤖 <code>{model}</code>",
        "",
        # 5. Session usage — duration, activity, messages
        f"⏱️ Duration: <b>{duration}</b>  (last activity: {idle_for} ago)",
        f"💬 Messages: <b>{msg_count}</b>",
        f"💳 Usage: {usage_text}",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        # 6. Technical details — debug row
        f"🧵 Thread: <code>{thread_label}</code>  |  "
        f"⚙️ Timeout: {timeout_s}s  |  "
        f"⚡ Pool: {active_total}/{max_slots}",
        f"🔢 PID: <code>{session.pid}</code>  |  "
        f"🛠 Binary: <code>{cli_path}</code>",
    ])

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@authorized
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /cancel — kill running CLI process for this thread.

    Three things happen:
    1. Pending decision state is cleared (if any)
    2. The registered asyncio task (if any) is cancelled — this releases
       the per-thread lock so the next message isn't queued behind it.
    3. The PTY session is killed (via runner.cancel) — this also handles
       the case where /cancel is sent before a task is registered
       (e.g. session is idle but user wants to free resources).
    4. Thread message counter is reset so the next message starts fresh.
    """
    thread_id = _get_thread_id(update)

    # Clear any pending decision state for this thread
    context.bot_data.pop(f"thread:{thread_id}:pending_decision", None)

    # Cancel the running task (releases per-thread lock)
    task = _thread_tasks.pop(thread_id, None)
    task_cancelled = False
    if task is not None and not task.done():
        task.cancel()
        task_cancelled = True
        logger.info("[cmd_cancel] cancelled task [thread=%s]", thread_id)

    # Kill the PTY session
    cancelled = await runner.cancel(thread_id)

    # Reset thread counter so next message starts fresh (no stale resume)
    if cancelled or task_cancelled:
        _thread_sessions[thread_id] = 0
        await update.message.reply_text("✅ Cancelled running CLI process.")
    else:
        await update.message.reply_text("ℹ️ No active CLI process to cancel.")


@authorized
async def cmd_new_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /new — reset session for current thread."""
    thread_id = _get_thread_id(update)
    context.user_data["force_new_session"] = True
    context.bot_data.pop(f"thread:{thread_id}:pending_decision", None)
    _thread_sessions[thread_id] = 0

    thread_label = f"thread {thread_id}" if thread_id else "main chat"
    await update.message.reply_text(
        f"🆕 Session reset cho {thread_label}.\n"
        "Tin nhắn tiếp theo sẽ bắt đầu conversation mới."
    )


@authorized
async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /resume — explicitly resume previous session."""
    await _execute_and_reply(update, context, "")


@authorized
async def cmd_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /project <path> — bind current thread to a project directory."""
    text = update.message.text or ""
    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        await update.message.reply_text(
            "⚠️ Usage: <code>/project &lt;path&gt;</code>\n\n"
            "Example: <code>/project /home/user/myapp</code>\n"
            "Use <code>/projects</code> to see previously-used projects.",
            parse_mode=ParseMode.HTML,
        )
        return

    path = parts[1].strip()
    if not os.path.isdir(path):
        await update.message.reply_text(
            f"⚠️ Path not found or not a directory:\n<code>{_escape_html(path)}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    thread_id = _get_thread_id(update) or DEFAULT_THREAD_ID
    await db.upsert_thread_config(thread_id, project_dir=path, path=DB_PATH)

    thread_label = f"thread {thread_id}" if thread_id != DEFAULT_THREAD_ID else "main chat"
    await update.message.reply_text(
        f"✅ Bound {thread_label} to project:\n<code>{_escape_html(path)}</code>",
        parse_mode=ParseMode.HTML,
    )
    logger.info("[cmd_project] thread=%s → %s", thread_id, path)


@authorized
async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /projects — show inline keyboard of previously-used projects."""
    projects = await db.list_distinct_project_dirs(path=DB_PATH)
    if not projects:
        await update.message.reply_text(
            "No previous projects found. Use <code>/project &lt;path&gt;</code> to bind a project.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Store full paths for callback lookup (callback_data has 64-byte limit)
    context.chat_data["_projects_list"] = projects

    # Mark current thread's binding if any
    thread_id = _get_thread_id(update) or DEFAULT_THREAD_ID
    current_config = await db.get_thread_config(thread_id, path=DB_PATH)
    current_path = current_config.project_dir if current_config else None

    keyboard = []
    for idx, path in enumerate(projects):
        marker = "✓ " if path == current_path else ""
        display = path if len(path) <= 55 else "..." + path[-52:]
        label = f"{marker}{display}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"project:{idx}")])

    await update.message.reply_text(
        "📂 Select a project to bind this thread to:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_projects_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle project selection from the /projects inline keyboard."""
    query = update.callback_query
    await query.answer()

    try:
        idx = int(query.data.split(":", 1)[1])
        projects = context.chat_data.get("_projects_list", [])
        path = projects[idx]
    except (ValueError, IndexError, KeyError):
        await query.edit_message_text(
            "⚠️ Invalid selection. Try /projects again."
        )
        return

    thread_id = _get_thread_id(update) or DEFAULT_THREAD_ID
    await db.upsert_thread_config(thread_id, project_dir=path, path=DB_PATH)

    thread_label = f"thread {thread_id}" if thread_id != DEFAULT_THREAD_ID else "main chat"
    await query.edit_message_text(
        f"✅ Bound {thread_label} to:\n<code>{_escape_html(path)}</code>",
        parse_mode=ParseMode.HTML,
    )
    logger.info("[cmd_projects] thread=%s → %s (from history)", thread_id, path)


@authorized
async def cmd_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /provider <name> — switch CLI provider for current thread."""
    text = update.message.text or ""
    parts = text.split(maxsplit=1)

    available = get_available_providers()

    if len(parts) < 2:
        await update.message.reply_text(
            f"⚠️ Usage: <code>/provider &lt;name&gt;</code>\n\n"
            f"Available: <code>{', '.join(sorted(available.keys()))}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    name = parts[1].strip().lower()
    if name not in available:
        await update.message.reply_text(
            f"⚠️ Unknown provider: <code>{_escape_html(name)}</code>\n\n"
            f"Available: <code>{', '.join(sorted(available.keys()))}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    thread_id = _get_thread_id(update) or DEFAULT_THREAD_ID

    # Guard: reject switch if an active session exists for this thread
    session = runner._sessions.get(thread_id)
    if session and session.alive:
        await update.message.reply_text(
            "⚠️ Active process running. Use /cancel first, then try again.",
        )
        return

    try:
        await db.upsert_thread_config(thread_id, cli_provider=name, path=DB_PATH)
    except ValueError:
        # No row yet and no project_dir — must bind project first
        await update.message.reply_text(
            "⚠️ No project bound yet. Use <code>/project &lt;path&gt;</code> first.",
            parse_mode=ParseMode.HTML,
        )
        return

    thread_label = f"thread {thread_id}" if thread_id != DEFAULT_THREAD_ID else "main chat"
    provider_class = available[name]
    await update.message.reply_text(
        f"✅ {thread_label} provider switched to <b>{provider_class.name}</b> "
        f"(<code>{name}</code>)",
        parse_mode=ParseMode.HTML,
    )
    logger.info("[cmd_provider] thread=%s → %s", thread_id, name)


# ── BMAD Slash Command Handler ───────────────────────────────────

@authorized
async def handle_bmad_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /bmad_* commands → forward as CLI slash commands."""
    text = update.message.text.strip()
    command = text.split()[0]
    extra = text[len(command):].strip()

    kiro_command = command.replace("_", "-")
    prompt = kiro_command if not extra else f"{kiro_command} {extra}"

    await _execute_and_reply(update, context, prompt)


# ── Free-form Message Handler ────────────────────────────────────

@authorized
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle free-form text messages → forward to CLI (or pipe as decision reply)."""
    text = update.message.text
    if not text or not text.strip():
        return

    thread_id = _get_thread_id(update)
    pending_key = f"thread:{thread_id}:pending_decision"

    # If a decision is pending, treat this message as the reply
    if context.bot_data.get(pending_key):
        context.bot_data.pop(pending_key, None)
        await _pipe_decision_reply(update, context, text.strip(), thread_id)
        return

    await _execute_and_reply(update, context, text.strip())


# ── Core Execute + Reply (Streaming) ─────────────────────────────

# Telegram rate limits: ~30 edits/min/chat → update every ~2s
_STREAM_UPDATE_INTERVAL = 1.5

# Max chars to show in streaming preview (keep it readable)
_STREAM_PREVIEW_MAX = 3000

# Send typing indicator every N seconds to keep Telegram alive
_TYPING_KEEPALIVE_INTERVAL = 4.0


async def _execute_and_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
) -> None:
    """Execute a prompt via CLI with streaming output.

    Features:
    - Per-thread parallel execution (different threads run concurrently)
    - Same-thread messages queue sequentially (shared session)
    - Progressive message edits (ChatGPT-like streaming)
    - Typing indicator keepalive
    - Idle watchdog (kills stuck processes)
    - Sends partial output if process dies mid-stream
    - Task is registered in _thread_tasks so /cancel can abort it
    """
    thread_id = _get_thread_id(update)

    # Notify if this thread is already busy (will queue behind the lock)
    if runner.is_busy(thread_id):
        await update.message.reply_text(
            "⏳ This thread has a running request — your message is queued.\n"
            "Use /cancel to stop the current one."
        )

    # Register current task so /cancel can abort it
    task = asyncio.current_task()
    if task is not None:
        _thread_tasks[thread_id] = task

    try:
        # The runner's per-thread lock handles queuing automatically
        await _execute_and_reply_inner(update, context, prompt, thread_id)
    except asyncio.CancelledError:
        logger.info("[execute_and_reply] cancelled [thread=%s]", thread_id)
        # Re-raise so asyncio knows we honored the cancellation
        raise
    finally:
        # Only unregister if our task is still the registered one
        if _thread_tasks.get(thread_id) is task:
            _thread_tasks.pop(thread_id, None)


async def _handle_decision_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    decision: DecisionPrompt,
    thread_id: int | None,
) -> None:
    """Forward a detected CLI decision prompt to the user via Telegram.

    Sets pending_decision flag in bot_data so the next user message is
    treated as a reply to this prompt (see handle_message).
    """
    context_text = "\n".join(decision.context_lines[-5:])
    msg = (
        "⚠️ <b>CLI is waiting for input</b>\n\n"
        f"<pre>{_escape_html(context_text)}</pre>\n\n"
        "Reply to proceed, or /cancel to abort."
    )
    try:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    except Exception as exc:
        logger.exception("[decision] failed to forward prompt: %s", exc)
        await update.message.reply_text(
            "⚠️ CLI is waiting for input. Reply to proceed or /cancel to abort."
        )
    logger.info(
        "[decision] forwarded to user [thread=%s]: %s",
        thread_id, decision.prompt_text[:80],
    )


async def _pipe_decision_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    reply: str,
    thread_id: int | None,
) -> None:
    """Pipe user's reply to the waiting CLI session and stream remaining output."""
    logger.info("[pipe_reply] routing user message as decision reply [thread=%s]", thread_id)

    # Resolve per-thread config for timeout
    try:
        resolved = await db.resolve_thread_config(
            thread_id if thread_id is not None else DEFAULT_THREAD_ID,
            env_project_dir=config.project_dir,
            env_cli_provider=config.cli_provider,
            env_timeout_seconds=config.cli_timeout,
            path=DB_PATH,
        )
        resolved_timeout = resolved.timeout_seconds
    except Exception:
        resolved_timeout = config.cli_timeout

    await _stream_to_telegram(
        update, context, thread_id,
        stream=runner.pipe_reply_stream(
            thread_id=thread_id, reply=reply, timeout_seconds=resolved_timeout,
        ),
    )


async def _stream_to_telegram(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    thread_id: int | None,
    stream,
) -> None:
    """Shared stream-to-Telegram helper for both execute and pipe_reply paths.

    Handles DecisionPrompt yields, preview edits, final response formatting.
    """
    chat_id = update.effective_chat.id

    try:
        preview_msg = await update.message.reply_text("⏳ Connecting...")
    except Exception as exc:
        logger.exception("Failed to send preview message: %s", exc)
        return

    typing_active = True

    async def _typing_keepalive():
        while typing_active:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                pass
            await asyncio.sleep(_TYPING_KEEPALIVE_INTERVAL)

    typing_task = asyncio.create_task(_typing_keepalive())

    raw_lines: list[str] = []
    preview_buffer = ""
    last_edit_time = 0.0
    response_started = False
    response_marker = runner.provider.response_marker
    if not response_marker:
        response_started = True

    import time as _t

    try:
        async for line in stream:
            if isinstance(line, DecisionPrompt):
                context.bot_data[f"thread:{thread_id}:pending_decision"] = True
                await _handle_decision_prompt(update, context, line, thread_id)
                typing_active = False
                if not typing_task.done():
                    typing_task.cancel()
                # Delete preview placeholder (decision prompt sent separately)
                try:
                    await preview_msg.delete()
                except Exception:
                    pass
                return

            raw_lines.append(line)
            now = _t.monotonic()
            clean_line = strip_streaming_noise(strip_ansi(line)).rstrip()
            if not clean_line:
                continue

            if response_marker and not response_started and clean_line.startswith(response_marker):
                response_started = True

            if response_started:
                preview_buffer += clean_line + "\n"
                if now - last_edit_time >= _STREAM_UPDATE_INTERVAL:
                    preview = preview_buffer[-_STREAM_PREVIEW_MAX:]
                    if len(preview_buffer) > _STREAM_PREVIEW_MAX:
                        preview = "...\n" + preview
                    try:
                        await preview_msg.edit_text(f"<pre>{_escape_html(preview)}</pre>", parse_mode=ParseMode.HTML)
                        last_edit_time = now
                    except Exception:
                        pass
            else:
                if now - last_edit_time >= _STREAM_UPDATE_INTERVAL:
                    status_line = clean_line[:100]
                    try:
                        await preview_msg.edit_text(f"🔧 {_escape_html(status_line)}", parse_mode=ParseMode.HTML)
                        last_edit_time = now
                    except Exception:
                        pass
    finally:
        typing_active = False
        if not typing_task.done():
            typing_task.cancel()

    # Compose final response
    raw_output = "".join(raw_lines)
    final = format_output(raw_output)
    if not final.strip():
        final = "(CLI returned no output)"

    # Delete preview, send final
    try:
        await preview_msg.delete()
    except Exception:
        pass

    for chunk in split_message(final):
        await _send_html_with_fallback(update, chunk)


async def _execute_and_reply_inner(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    thread_id: int | None,
) -> None:
    """Inner implementation of execute and reply."""
    model = _get_model(context)
    resume = _should_resume(thread_id, context)

    await update.message.reply_chat_action(ChatAction.TYPING)

    model_label = model or "auto"
    session_label = "resume" if resume else "new"
    provider_name = runner.provider.name

    # Send initial streaming message
    stream_msg = await update.message.reply_text(
        f"⏳ <i>Connecting to {_escape_html(provider_name)}...</i>"
        f" [{model_label} · {session_label}]",
        parse_mode=ParseMode.HTML,
    )

    # Background typing keepalive — runs independently of stream loop
    typing_active = True

    async def _typing_keepalive():
        while typing_active:
            try:
                await update.message.reply_chat_action(ChatAction.TYPING)
            except Exception:
                pass
            await asyncio.sleep(_TYPING_KEEPALIVE_INTERVAL)

    typing_task = asyncio.create_task(_typing_keepalive())

    # Collect all raw output + stream preview to Telegram
    raw_lines: list[str] = []
    preview_buffer = ""
    last_edit_time = 0.0
    response_started = False
    response_marker = runner.provider.response_marker

    if not response_marker:
        response_started = True

    import time

    # Resolve per-thread config (provider, model, timeout, project_dir from SQLite with .env fallback)
    try:
        resolved = await db.resolve_thread_config(
            thread_id if thread_id is not None else DEFAULT_THREAD_ID,
            env_project_dir=config.project_dir,
            env_cli_provider=config.cli_provider,
            env_model=model,
            env_timeout_seconds=config.cli_timeout,
            path=DB_PATH,
        )
        resolved_timeout = resolved.timeout_seconds
        resolved_model = resolved.model or model
        resolved_project_dir = resolved.project_dir
    except Exception as exc:
        logger.warning("[resolve_thread_config] fallback to defaults: %s", exc)
        resolved_timeout = config.cli_timeout
        resolved_model = model
        resolved_project_dir = config.project_dir

    try:
        async for line in runner.execute_stream(
            prompt,
            thread_id=thread_id,
            model=resolved_model,
            resume=resume,
            timeout_seconds=resolved_timeout,
            project_dir=resolved_project_dir,
        ):
            # Handle DecisionPrompt — CLI is waiting for user input
            if isinstance(line, DecisionPrompt):
                context.bot_data[f"thread:{thread_id}:pending_decision"] = True
                await _handle_decision_prompt(update, context, line, thread_id)
                typing_active = False
                if not typing_task.done():
                    typing_task.cancel()
                return  # Exit the handler; next user message will trigger pipe_reply

            raw_lines.append(line)
            now = time.monotonic()

            # Strip ANSI and spinner/thinking noise for preview
            clean_line = strip_streaming_noise(strip_ansi(line)).rstrip()
            if not clean_line:
                continue

            # Detect response start
            if response_marker and not response_started and clean_line.startswith(response_marker):
                response_started = True
                clean_line = clean_line[len(response_marker):]

            if response_started:
                preview_buffer += clean_line + "\n"

                if now - last_edit_time >= _STREAM_UPDATE_INTERVAL:
                    preview = preview_buffer[-_STREAM_PREVIEW_MAX:]
                    if len(preview_buffer) > _STREAM_PREVIEW_MAX:
                        nl = preview.find("\n")
                        if nl > 0:
                            preview = preview[nl + 1:]
                        preview = "...\n" + preview

                    try:
                        await stream_msg.edit_text(
                            f"✍️ <i>Streaming...</i>\n\n"
                            f"<pre>{_escape_html(preview.rstrip())}</pre>",
                            parse_mode=ParseMode.HTML,
                        )
                        last_edit_time = now
                    except Exception:
                        pass
            else:
                if now - last_edit_time >= _STREAM_UPDATE_INTERVAL:
                    status_line = clean_line[:100]
                    try:
                        await stream_msg.edit_text(
                            f"⚙️ <i>{_escape_html(status_line)}</i>",
                            parse_mode=ParseMode.HTML,
                        )
                        last_edit_time = now
                    except Exception:
                        pass
    finally:
        # Stop typing keepalive
        typing_active = False
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    # Track this thread for future resume
    _track_thread(thread_id)

    # Delete the streaming preview message
    try:
        await stream_msg.delete()
    except Exception:
        pass

    # Format and send final result
    full_output = "".join(raw_lines)
    is_error = runner.get_exit_code(thread_id) != 0
    output = format_output(full_output, is_error)
    chunks = split_message(output)

    if not chunks or all(not c.strip() for c in chunks):
        # No meaningful output — send a notice
        await update.message.reply_text(
            "⚠️ CLI returned no output. The process may have been stuck.\n"
            "Try /cancel then send your message again."
        )
        return

    for chunk in chunks:
        await _send_html_with_fallback(update, chunk)


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _send_html_with_fallback(update: Update, text: str) -> None:
    """Send a message as HTML, falling back to plain text on parse error."""
    try:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as exc:
        logger.warning("HTML parse failed, falling back to plain text: %s", exc)
        plain = re.sub(r"<[^>]+>", "", text)
        try:
            await update.message.reply_text(plain[:MAX_MSG_LEN])
        except Exception as exc2:
            logger.error("Failed to send even plain text: %s", exc2)


# ── Error Handler ────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and notify user."""
    logger.error("Exception while handling update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            f"❌ Bot error: {context.error}\n\nTry again or use /cancel."
        )


# ── Main ─────────────────────────────────────────────────────────

def main() -> None:
    """Start Chati."""
    logger.info("Starting Chati")
    logger.info("Project: %s", config.project_dir)
    logger.info("Allowed users: %s", config.allowed_user_ids)
    logger.info("CLI Provider: %s", config.cli_provider)
    logger.info("Timeout: %ds", config.cli_timeout)

    # Initialize SQLite schema + default row (v2.0)
    asyncio.get_event_loop().run_until_complete(
        db.init_db(DB_PATH, default_project_dir=config.project_dir)
    )
    logger.info("SQLite initialized: %s", DB_PATH)

    app = (
        Application.builder()
        .token(config.telegram_token)
        .concurrent_updates(True)
        .build()
    )

    # Built-in commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("skills", cmd_skills))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("new", cmd_new_session))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("project", cmd_project))
    app.add_handler(CommandHandler("projects", cmd_projects))
    app.add_handler(CommandHandler("provider", cmd_provider))
    app.add_handler(CommandHandler("info", cmd_info))

    # Model selection callback
    app.add_handler(CallbackQueryHandler(handle_model_callback, pattern=r"^model:"))

    # Project selection callback (/projects)
    app.add_handler(CallbackQueryHandler(handle_projects_callback, pattern=r"^project:"))

    # BMAD slash commands
    app.add_handler(MessageHandler(
        filters.Regex(r"^/bmad_\w+"),
        handle_bmad_command,
    ))

    # Free-form messages (must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Error handler
    app.add_error_handler(error_handler)

    # Background: idle session cleanup (runs every N seconds)
    async def _post_init(app_):
        async def _cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(config.cleanup_interval)
                    killed = runner._session_mgr.cleanup_idle(
                        max_age_seconds=config.idle_session_max_age
                    )
                    if killed:
                        logger.info("[cleanup_idle] killed %d idle sessions", killed)
                    orphans = runner._session_mgr.cleanup_orphans()
                    if orphans:
                        logger.warning("[cleanup_orphans] killed %d orphan sessions", orphans)

                    # Expired decision replies
                    expired = runner._session_mgr.expired_decisions(
                        max_wait_seconds=config.decision_reply_timeout
                    )
                    for tid in expired:
                        logger.warning("[decision] reply timeout [thread=%s]", tid)
                        app_.bot_data.pop(f"thread:{tid}:pending_decision", None)
                        # Kill session — state may transition to DEAD
                        runner._session_mgr.kill(tid)
                        # Notify user via bot
                        try:
                            # Notify the last known chat for this thread
                            # We don't know chat_id without explicit tracking;
                            # the next user message in this thread will get "session expired"
                            logger.info(
                                "[decision] auto-killed thread %s — user will be notified on next message",
                                tid,
                            )
                        except Exception as exc:
                            logger.exception("[decision] notify failed: %s", exc)
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.exception("[cleanup_loop] error: %s", exc)

        app_.bot_data["_cleanup_task"] = asyncio.create_task(_cleanup_loop())
        logger.info(
            "Started background cleanup task (interval=%ds, idle_max=%ds, decision_timeout=%ds)",
            config.cleanup_interval, config.idle_session_max_age,
            config.decision_reply_timeout,
        )

    async def _post_shutdown(app_):
        task = app_.bot_data.get("_cleanup_task")
        if task:
            task.cancel()
        runner._session_mgr.shutdown()
        logger.info("Session manager shut down")

    app.post_init = _post_init
    app.post_shutdown = _post_shutdown

    # Start polling
    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    main()
