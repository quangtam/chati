"""Smoke tests verifying all conftest fixtures are functional."""

import os
import select

import pytest


class TestInMemoryDb:
    """Verify in_memory_db fixture creates schema correctly."""

    async def test_fixture_returns_connection(self, in_memory_db):
        assert in_memory_db is not None

    async def test_thread_config_table_exists(self, in_memory_db):
        cursor = await in_memory_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='thread_config'"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["name"] == "thread_config"

    async def test_insert_and_read(self, in_memory_db):
        await in_memory_db.execute(
            "INSERT INTO thread_config (thread_id, project_dir) VALUES (?, ?)",
            (42, "/tmp/test"),
        )
        await in_memory_db.commit()
        cursor = await in_memory_db.execute(
            "SELECT project_dir FROM thread_config WHERE thread_id = ?", (42,)
        )
        row = await cursor.fetchone()
        assert row["project_dir"] == "/tmp/test"

    async def test_schema_columns(self, in_memory_db):
        cursor = await in_memory_db.execute("PRAGMA table_info(thread_config)")
        columns = [row[1] for row in await cursor.fetchall()]
        expected = [
            "thread_id", "project_dir", "cli_provider", "model",
            "timeout_seconds", "last_active_at", "created_at", "updated_at",
        ]
        assert columns == expected


class TestMockProvider:
    """Verify mock_provider fixture returns usable CliProvider."""

    def test_factory_returns_provider(self, mock_provider):
        provider = mock_provider()
        assert provider is not None
        assert provider.provider_id == "mock"
        assert provider.name == "Mock CLI"

    def test_build_args(self, mock_provider):
        provider = mock_provider()
        args = provider.build_args("hello world", model="sonnet")
        assert args == ["echo", "hello world"]
        assert provider.calls == [("build_args", "hello world", "sonnet", False)]

    def test_build_env(self, mock_provider):
        provider = mock_provider()
        env = provider.build_env({"PATH": "/usr/bin"})
        assert env == {"PATH": "/usr/bin"}

    def test_custom_responses(self, mock_provider):
        provider = mock_provider(responses=["custom1", "custom2"])
        assert provider.responses == ["custom1", "custom2"]


class TestPtyProcess:
    """Verify pty_process fixture spawns and cleans up."""

    async def test_fixture_returns_pid_and_fd(self, pty_process):
        assert "pid" in pty_process
        assert "fd" in pty_process
        assert pty_process["pid"] > 0
        assert pty_process["fd"] >= 0

    async def test_process_is_alive(self, pty_process):
        # Process should be alive during test
        try:
            os.kill(pty_process["pid"], 0)
            alive = True
        except OSError:
            alive = False
        assert alive

    async def test_pty_echoes_input(self, pty_process):
        fd = pty_process["fd"]
        os.write(fd, b"hello\n")
        # Wait for echo
        r, _, _ = select.select([fd], [], [], 2.0)
        assert r, "PTY should have data available"
        data = os.read(fd, 4096)
        assert b"hello" in data


class TestSessionContext:
    """Verify session_context fixture provides seeded data."""

    async def test_fixture_returns_context(self, session_context):
        assert "db" in session_context
        assert "thread_ids" in session_context
        assert session_context["thread_ids"] == [1001, 1002]

    async def test_seeded_data_readable(self, session_context):
        db = session_context["db"]
        cursor = await db.execute(
            "SELECT project_dir, cli_provider FROM thread_config WHERE thread_id = ?",
            (1001,),
        )
        row = await cursor.fetchone()
        assert row["project_dir"] == "/home/test/project-a"
        assert row["cli_provider"] == "kiro"

    async def test_second_thread_has_defaults(self, session_context):
        db = session_context["db"]
        cursor = await db.execute(
            "SELECT cli_provider, model FROM thread_config WHERE thread_id = ?",
            (1002,),
        )
        row = await cursor.fetchone()
        assert row["cli_provider"] is None
        assert row["model"] is None


class TestTelegramUpdateFactory:
    """Verify telegram_update_factory creates proper mock objects."""

    def test_default_update(self, telegram_update_factory):
        update = telegram_update_factory()
        assert update.effective_user.id == 123456789
        assert update.effective_chat.id == 123456789
        assert update.message.text == "/start"
        assert update.message.message_thread_id is None

    def test_custom_update(self, telegram_update_factory):
        update = telegram_update_factory(
            user_id=999,
            chat_id=888,
            text="hello",
            message_thread_id=42,
        )
        assert update.effective_user.id == 999
        assert update.effective_chat.id == 888
        assert update.message.text == "hello"
        assert update.message.message_thread_id == 42

    def test_reply_text_is_async(self, telegram_update_factory):
        update = telegram_update_factory()
        # reply_text should be AsyncMock (awaitable)
        assert hasattr(update.message.reply_text, "__call__")
        assert hasattr(update.message.reply_text, "assert_awaited")
