"""SQLite database manager with async support via aiosqlite."""

from __future__ import annotations

import aiosqlite
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.core.config import get_settings

_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS releases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    revision INTEGER NOT NULL DEFAULT 1,
    target_date TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS criteria (
    id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    category TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    required INTEGER NOT NULL DEFAULT 1,
    evidence TEXT DEFAULT '',
    evidence_url TEXT DEFAULT '',
    assigned_to TEXT DEFAULT '',
    reviewed_by TEXT DEFAULT '',
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (release_id) REFERENCES releases(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS blockers (
    id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'open',
    category TEXT DEFAULT '',
    assigned_to TEXT DEFAULT '',
    resolution TEXT DEFAULT '',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (release_id) REFERENCES releases(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL,
    approver TEXT NOT NULL,
    release_revision INTEGER NOT NULL DEFAULT 1,
    role TEXT NOT NULL,
    decision TEXT NOT NULL,
    conditions TEXT DEFAULT '',
    comment TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (release_id) REFERENCES releases(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    release_id TEXT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    old_value TEXT DEFAULT '',
    new_value TEXT DEFAULT '',
    user_id TEXT NOT NULL,
    user_role TEXT DEFAULT '',
    timestamp TEXT NOT NULL,
    details TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS release_snapshots (
    id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL,
    snapshot_data TEXT NOT NULL,
    risk_score REAL,
    risk_factors TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (release_id) REFERENCES releases(id) ON DELETE CASCADE
);
"""


def _get_db_path(settings=None) -> str:
    """Extract file path from SQLite URL."""
    if settings is None:
        settings = get_settings()
    url = settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    if url == ":memory:" or url == "sqlite://" or url == "sqlite:///:memory:":
        return ":memory:"
    return url


class DatabaseManager:
    """Async SQLite database manager."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _get_db_path()
        self._lock = asyncio.Lock()
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> aiosqlite.Connection:
        """Open the database connection."""
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True,exist_ok=True)
        self._connection = await aiosqlite.connect(self._db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        return self._connection

    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def init_db(self) -> None:
        """Create all tables."""
        if not self._connection:
            await self.connect()
        assert self._connection is not None
        await self._connection.executescript(_TABLES_SQL)
        await self._connection.commit()

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Get a database connection as async context manager."""
        if not self._connection:
            await self.connect()
        assert self._connection is not None
        async with self._lock:
            await self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
                await self._connection.commit()
            except BaseException:
                await self._connection.rollback()
                raise


_manager: DatabaseManager | None = None


async def get_database_manager(db_path: str | None = None) -> DatabaseManager:
    """Get or create the singleton database manager."""
    global _manager
    if _manager is None:
        _manager = DatabaseManager(db_path)
        await _manager.connect()
        await _manager.init_db()
    return _manager


async def reset_database_manager() -> None:
    """Reset the singleton (for testing)."""
    global _manager
    if _manager:
        await _manager.close()
    _manager = None


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """FastAPI dependency that yields a database connection."""
    manager = await get_database_manager()
    async with manager.get_connection() as conn:
        yield conn
