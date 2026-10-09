"""Audit logging service for tracking all state changes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite


class AuditService:
    """Service for creating and querying audit log entries."""

    @staticmethod
    async def log_action(
        db: aiosqlite.Connection,
        release_id: str | None,
        entity_type: str,
        entity_id: str,
        action: str,
        old_value: str,
        new_value: str,
        user_id: str,
        user_role: str = "",
        details: str = "",
    ) -> dict[str, Any]:
        """Record an audit log entry."""
        entry_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        await db.execute(
            """INSERT INTO audit_log
               (id, release_id, entity_type, entity_id, action,
                old_value, new_value, user_id, user_role, timestamp, details)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry_id, release_id, entity_type, entity_id, action,
                old_value, new_value, user_id, user_role, timestamp, details,
            ),
        )

        return {
            "id": entry_id,
            "release_id": release_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "old_value": old_value,
            "new_value": new_value,
            "user_id": user_id,
            "user_role": user_role,
            "timestamp": timestamp,
            "details": details,
        }

    @staticmethod
    async def get_audit_log(
        db: aiosqlite.Connection,
        release_id: str | None = None,
        entity_type: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query audit log with optional filters and pagination."""
        conditions: list[str] = []
        params: list[Any] = []

        if release_id:
            conditions.append("release_id = ?")
            params.append(release_id)
        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        count_cursor = await db.execute(
            f"SELECT COUNT(*) FROM audit_log {where}", params
        )
        count_row = await count_cursor.fetchone()
        total = count_row[0] if count_row else 0

        offset = (page - 1) * per_page
        cursor = await db.execute(
            f"""SELECT * FROM audit_log {where}
                ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
            params + [per_page, offset],
        )
        rows = await cursor.fetchall()

        items = [dict(row) for row in rows]
        return items, total

    @staticmethod
    async def export_audit_log(
        db: aiosqlite.Connection,
        release_id: str,
    ) -> list[dict[str, Any]]:
        """Export all audit entries for a release."""
        cursor = await db.execute(
            "SELECT * FROM audit_log WHERE release_id = ? ORDER BY timestamp ASC",
            (release_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
