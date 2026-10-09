"""Blocker management service with NLP auto-classification."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.core.risk_engine import risk_engine
from app.services.audit_service import AuditService
from app.services.invariants import touch_release, release_row, require_ready, current_decisions


class BlockerService:
    """Service for managing release blockers with automatic classification."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def create_blocker(
        self, data: dict[str, Any], user_id: str, user_role: str = ""
    ) -> dict[str, Any]:
        """Create a new blocker with auto-classification."""
        blocker_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        await touch_release(self.db,data["release_id"])

        # Verify release exists
        cursor = await self.db.execute(
            "SELECT id FROM releases WHERE id = ?", (data["release_id"],)
        )
        if not await cursor.fetchone():
            raise ValueError(f"Release {data['release_id']} not found")

        # NLP auto-classification
        classification = risk_engine.classify_blocker(
            data["title"], data["description"]
        )
        auto_category = classification["category"]

        await self.db.execute(
            """INSERT INTO blockers
               (id, release_id, title, description, severity, status,
                category, assigned_to, resolution, created_by,
                created_at, updated_at, resolved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                blocker_id, data["release_id"], data["title"],
                data["description"], data.get("severity", "medium"),
                "open", auto_category, "", "", user_id, now, now, None,
            ),
        )

        await AuditService.log_action(
            self.db, data["release_id"], "blocker", blocker_id,
            "created", "", "open", user_id, user_role,
            f"Blocker '{data['title']}' created (auto-classified: {auto_category})",
        )

        result = await self.get_blocker(blocker_id)
        result["auto_category"] = classification
        return result

    async def get_blocker(self, blocker_id: str) -> dict[str, Any]:
        """Get a single blocker by ID."""
        cursor = await self.db.execute(
            "SELECT * FROM blockers WHERE id = ?", (blocker_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise ValueError(f"Blocker {blocker_id} not found")
        result = dict(row)
        # Add auto-classification
        classification = risk_engine.classify_blocker(
            result["title"], result["description"]
        )
        result["auto_category"] = classification
        return result

    async def update_blocker(
        self, blocker_id: str, data: dict[str, Any],
        user_id: str, user_role: str = ""
    ) -> dict[str, Any]:
        """Update blocker fields."""
        current = await self.get_blocker(blocker_id)
        await touch_release(self.db,current["release_id"])
        final_status=data.get('status') or current['status']
        if final_status in {'resolved','accepted','mitigated'} and len((data.get('resolution') or current['resolution']).strip())<5:
            raise ValueError('A resolution or risk acceptance rationale is required')
        now = datetime.now(timezone.utc).isoformat()

        updates: list[str] = []
        values: list[Any] = []
        for field in ("title", "description", "severity", "status",
                       "category", "assigned_to", "resolution"):
            if field in data and data[field] is not None:
                old_val = current.get(field, "")
                updates.append(f"{field} = ?")
                values.append(data[field])
                if str(old_val) != str(data[field]):
                    await AuditService.log_action(
                        self.db, current["release_id"], "blocker", blocker_id,
                        f"updated_{field}", str(old_val), str(data[field]),
                        user_id, user_role,
                    )

        if updates:
            updates.append("updated_at = ?")
            values.append(now)
            values.append(blocker_id)
            await self.db.execute(
                f"UPDATE blockers SET {', '.join(updates)} WHERE id = ?",
                values,
            )

        return await self.get_blocker(blocker_id)

    async def resolve_blocker(
        self, blocker_id: str, resolution: str,
        user_id: str, user_role: str = ""
    ) -> dict[str, Any]:
        """Resolve a blocker."""
        if len(resolution.strip())<5:raise ValueError('Provide a substantive resolution')
        current = await self.get_blocker(blocker_id)
        await touch_release(self.db,current["release_id"])
        now = datetime.now(timezone.utc).isoformat()
        old_status = current["status"]

        await self.db.execute(
            """UPDATE blockers SET status = ?, resolution = ?,
               resolved_at = ?, updated_at = ? WHERE id = ?""",
            ("resolved", resolution, now, now, blocker_id),
        )

        await AuditService.log_action(
            self.db, current["release_id"], "blocker", blocker_id,
            "resolved", old_status, "resolved", user_id, user_role,
            f"Blocker resolved: {resolution}",
        )

        return await self.get_blocker(blocker_id)

    async def list_blockers(
        self, release_id: str,
        severity: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List blockers for a release with optional filters."""
        conditions = ["release_id = ?"]
        params: list[Any] = [release_id]

        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = " AND ".join(conditions)
        cursor = await self.db.execute(
            f"SELECT * FROM blockers WHERE {where} ORDER BY created_at DESC",
            params,
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["auto_category"] = risk_engine.classify_blocker(
                item["title"], item["description"]
            )
            results.append(item)
        return results

    async def delete_blocker(
        self, blocker_id: str, user_id: str, user_role: str = ""
    ) -> bool:
        """Delete a blocker."""
        current = await self.get_blocker(blocker_id)
        await touch_release(self.db,current["release_id"])
        await self.db.execute("DELETE FROM blockers WHERE id = ?", (blocker_id,))

        await AuditService.log_action(
            self.db, current["release_id"], "blocker", blocker_id,
            "deleted", current["title"], "", user_id, user_role,
        )
        return True

    async def get_blocker_summary(self, release_id: str) -> dict[str, Any]:
        """Get aggregated blocker statistics for a release."""
        blockers = await self.list_blockers(release_id)
        summary: dict[str, Any] = {
            "total": len(blockers),
            "by_status": {},
            "by_severity": {},
            "by_category": {},
        }
        for b in blockers:
            s = b["status"]
            summary["by_status"][s] = summary["by_status"].get(s, 0) + 1
            sev = b["severity"]
            summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + 1
            cat = b.get("category", "uncategorized")
            summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1
        return summary
