"""SQLite persistence layer for Chati v2.0.

Repository pattern with async context manager. Per-operation connections
with WAL mode for concurrent-safe reads/writes.

Schema:
    thread_config (
        thread_id INTEGER PK, project_dir TEXT NOT NULL,
        cli_provider, model, timeout_seconds, last_active_at,
        created_at, updated_at
    )
"""

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = "chati.db"
DEFAULT_THREAD_ID = 0  # sentinel for "main chat" (no message_thread_id)


@dataclass(frozen=True)
class ThreadConfig:
    """Immutable per-thread configuration."""

    thread_id: int
    project_dir: str
    cli_provider: str | None = None
    model: str | None = None
    timeout_seconds: int | None = None
    last_active_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ─── Connection context manager ──────────────────────────────────────────────


@asynccontextmanager
async def get_db(path: str = DB_PATH) -> AsyncIterator[aiosqlite.Connection]:
    """Async context manager for SQLite connections.

    Auto-commits on successful exit, rolls back on exception.
    WAL mode and busy_timeout applied per connection.
    """
    db = await aiosqlite.connect(path, timeout=30)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    try:
        yield db
        await db.commit()
    finally:
        await db.close()


# ─── Schema migration ────────────────────────────────────────────────────────


async def init_db(path: str = DB_PATH, default_project_dir: str = "") -> None:
    """Create schema if not exists. Insert default thread row if table is empty.

    Idempotent: safe to call on every startup.
    """
    async with get_db(path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS thread_config (
                thread_id       INTEGER PRIMARY KEY,
                project_dir     TEXT NOT NULL,
                cli_provider    TEXT,
                model           TEXT,
                timeout_seconds INTEGER,
                last_active_at  TEXT,
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now'))
            )
            """
        )

        # Insert default row only if table is empty AND default path provided
        if default_project_dir:
            cursor = await db.execute(
                "SELECT COUNT(*) as c FROM thread_config WHERE thread_id = ?",
                (DEFAULT_THREAD_ID,),
            )
            row = await cursor.fetchone()
            if row["c"] == 0:
                await db.execute(
                    "INSERT INTO thread_config (thread_id, project_dir) VALUES (?, ?)",
                    (DEFAULT_THREAD_ID, default_project_dir),
                )
                logger.info(
                    f"[db] init_db: created default thread row with project_dir={default_project_dir}"
                )


# ─── Repository functions ────────────────────────────────────────────────────


def _row_to_config(row: aiosqlite.Row) -> ThreadConfig:
    """Convert SQLite Row to ThreadConfig dataclass."""
    return ThreadConfig(
        thread_id=row["thread_id"],
        project_dir=row["project_dir"],
        cli_provider=row["cli_provider"],
        model=row["model"],
        timeout_seconds=row["timeout_seconds"],
        last_active_at=row["last_active_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def get_thread_config(
    thread_id: int, path: str = DB_PATH
) -> ThreadConfig | None:
    """Fetch config for a specific thread. Returns None if not found."""
    async with get_db(path) as db:
        cursor = await db.execute(
            "SELECT * FROM thread_config WHERE thread_id = ?", (thread_id,)
        )
        row = await cursor.fetchone()
        return _row_to_config(row) if row else None


async def upsert_thread_config(
    thread_id: int,
    *,
    project_dir: str | None = None,
    cli_provider: str | None = None,
    model: str | None = None,
    timeout_seconds: int | None = None,
    path: str = DB_PATH,
) -> None:
    """Insert or update thread config. Only non-None fields are written.

    For inserts, project_dir is required (schema enforces NOT NULL).
    For updates, unchanged fields are preserved.
    """
    async with get_db(path) as db:
        # Check if row exists
        cursor = await db.execute(
            "SELECT thread_id FROM thread_config WHERE thread_id = ?", (thread_id,)
        )
        exists = await cursor.fetchone() is not None

        if exists:
            # Update: only set fields that were explicitly provided
            updates: list[str] = []
            values: list[object] = []
            if project_dir is not None:
                updates.append("project_dir = ?")
                values.append(project_dir)
            if cli_provider is not None:
                updates.append("cli_provider = ?")
                values.append(cli_provider)
            if model is not None:
                updates.append("model = ?")
                values.append(model)
            if timeout_seconds is not None:
                updates.append("timeout_seconds = ?")
                values.append(timeout_seconds)

            if not updates:
                return  # nothing to update

            updates.append("updated_at = datetime('now')")
            values.append(thread_id)
            await db.execute(
                f"UPDATE thread_config SET {', '.join(updates)} WHERE thread_id = ?",
                values,
            )
        else:
            # Insert: project_dir required
            if project_dir is None:
                raise ValueError(
                    f"[db] upsert_thread_config: project_dir required for new thread {thread_id}"
                )
            await db.execute(
                """
                INSERT INTO thread_config
                    (thread_id, project_dir, cli_provider, model, timeout_seconds)
                VALUES (?, ?, ?, ?, ?)
                """,
                (thread_id, project_dir, cli_provider, model, timeout_seconds),
            )
        logger.debug(
            f"[db] upsert_thread_config: thread_id={thread_id} ({'UPDATE' if exists else 'INSERT'})"
        )


async def list_all_threads(path: str = DB_PATH) -> list[ThreadConfig]:
    """Return all thread configurations, ordered by thread_id."""
    async with get_db(path) as db:
        cursor = await db.execute(
            "SELECT * FROM thread_config ORDER BY thread_id"
        )
        rows = await cursor.fetchall()
        return [_row_to_config(r) for r in rows]


async def update_last_active(thread_id: int, path: str = DB_PATH) -> None:
    """Update last_active_at to current timestamp. No-op if thread not found."""
    async with get_db(path) as db:
        await db.execute(
            "UPDATE thread_config SET last_active_at = datetime('now'), updated_at = datetime('now') WHERE thread_id = ?",
            (thread_id,),
        )


async def list_distinct_project_dirs(path: str = DB_PATH) -> list[str]:
    """Return unique project directories, most-recently-active first.

    Deduplicates by project_dir and orders by the latest activity
    (last_active_at if present, else updated_at).
    """
    async with get_db(path) as db:
        cursor = await db.execute(
            """
            SELECT project_dir, MAX(COALESCE(last_active_at, updated_at)) as last_used
            FROM thread_config
            GROUP BY project_dir
            ORDER BY last_used DESC
            """
        )
        rows = await cursor.fetchall()
        return [r["project_dir"] for r in rows]



@dataclass(frozen=True)
class ResolvedConfig:
    """Fully-resolved per-thread configuration (no None where a value is required)."""

    thread_id: int
    project_dir: str
    cli_provider: str
    model: str | None  # None if no model default — provider handles it
    timeout_seconds: int


async def resolve_thread_config(
    thread_id: int,
    *,
    env_project_dir: str,
    env_cli_provider: str,
    env_model: str | None = None,
    env_timeout_seconds: int = 600,
    path: str = DB_PATH,
) -> ResolvedConfig:
    """Resolve thread configuration using 3-layer fallback chain.

    Precedence per field:
      1. thread_config row (SQLite) if value is not None
      2. env_* parameter (from .env via Config)
      3. Hardcoded defaults in function signature

    Args:
        thread_id: Thread to resolve config for
        env_project_dir: Default project dir from .env (PROJECT_DIR)
        env_cli_provider: Default provider from .env (CLI_PROVIDER)
        env_model: Optional default model (no .env key by default)
        env_timeout_seconds: Default timeout from .env (CLI_TIMEOUT)
        path: DB path (for testability)

    Returns:
        ResolvedConfig with all fields filled (model may be None).
    """
    row = await get_thread_config(thread_id, path=path)

    if row:
        project_dir = row.project_dir  # NOT NULL in schema
        cli_provider = row.cli_provider or env_cli_provider
        model = row.model if row.model is not None else env_model
        timeout_seconds = row.timeout_seconds or env_timeout_seconds
    else:
        project_dir = env_project_dir
        cli_provider = env_cli_provider
        model = env_model
        timeout_seconds = env_timeout_seconds

    return ResolvedConfig(
        thread_id=thread_id,
        project_dir=project_dir,
        cli_provider=cli_provider,
        model=model,
        timeout_seconds=timeout_seconds,
    )
