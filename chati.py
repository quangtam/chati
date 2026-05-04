"""Chati — chat with any AI coding CLI from your phone.

Bridges messaging apps to AI CLIs (Kiro, Claude Code, Gemini, Codex)
in headless mode with streaming output.

Features:
- Thread-based sessions (each thread = separate conversation)
- Model selection via /model command with inline keyboard
- Pluggable CLI providers
- BMAD skill routing
"""

import logging
import re
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
from message_utils import format_output, split_message, strip_ansi, extract_final_response

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

    emoji = _model_emoji(model_id)
    await query.edit_message_text(
        f"{emoji} Model đã chuyển sang: <b>{model_id}</b>",
        parse_mode=ParseMode.HTML,
    )
    logger.info("User %s switched model to: %s", update.effective_user.id, model_id)


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


@authorized
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /cancel — kill running CLI process for this thread."""
    thread_id = _get_thread_id(update)
    cancelled = await runner.cancel(thread_id)
    if cancelled:
        await update.message.reply_text("✅ Cancelled running CLI process.")
    else:
        await update.message.reply_text("ℹ️ No active CLI process to cancel.")


@authorized
async def cmd_new_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /new — reset session for current thread."""
    thread_id = _get_thread_id(update)
    context.user_data["force_new_session"] = True
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
    """Handle free-form text messages → forward to CLI."""
    text = update.message.text
    if not text or not text.strip():
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
    """
    thread_id = _get_thread_id(update)

    # Notify if this thread is already busy (will queue behind the lock)
    if runner.is_busy(thread_id):
        await update.message.reply_text(
            "⏳ This thread has a running request — your message is queued.\n"
            "Use /cancel to stop the current one."
        )

    # The runner's per-thread lock handles queuing automatically
    await _execute_and_reply_inner(update, context, prompt, thread_id)


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

    # Collect all raw output + stream preview to Telegram
    raw_lines: list[str] = []
    preview_buffer = ""
    last_edit_time = 0.0
    last_typing_time = 0.0
    response_started = False
    response_marker = runner.provider.response_marker

    if not response_marker:
        response_started = True

    import time

    async for line in runner.execute_stream(prompt, thread_id=thread_id, model=model, resume=resume):
        raw_lines.append(line)
        now = time.monotonic()

        # Keep typing indicator alive
        if now - last_typing_time >= _TYPING_KEEPALIVE_INTERVAL:
            try:
                await update.message.reply_chat_action(ChatAction.TYPING)
                last_typing_time = now
            except Exception:
                pass

        # Strip ANSI for preview
        clean_line = strip_ansi(line).rstrip()
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

    # Model selection callback
    app.add_handler(CallbackQueryHandler(handle_model_callback, pattern=r"^model:"))

    # BMAD slash commands
    app.add_handler(MessageHandler(
        filters.Regex(r"^/bmad_\w+"),
        handle_bmad_command,
    ))

    # Free-form messages (must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Error handler
    app.add_error_handler(error_handler)

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
