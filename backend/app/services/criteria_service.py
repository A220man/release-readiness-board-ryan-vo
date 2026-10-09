"""Criteria management service with review workflows."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.services.audit_service import AuditService
from app.services.invariants import touch_release, release_row, require_ready, current_decisions


class CriteriaService:
    """Service for managing release criteria with evidence tracking."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def add_criterion(
        self, data: dict[str, Any], user_id: str, user_role: str = ""
    ) -> dict[str, Any]:
        """Add a new criterion to a release."""
        criterion_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        await touch_release(self.db,data["release_id"])

        # Verify release exists
        cursor = await self.db.execute(
            "SELECT id FROM releases WHERE id = ?", (data["release_id"],)
        )
        if not await cursor.fetchone():
            raise ValueError(f"Release {data['release_id']} not found")

        await self.db.execute(
            """INSERT INTO criteria
               (id, release_id, name, description, category, status,
                required, evidence, evidence_url, assigned_to,
                reviewed_by, reviewed_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                criterion_id, data["release_id"], data["name"],
                data.get("description", ""), data["category"], "pending",
                1 if data.get("required", True) else 0,
                "", "", "", "", None, now, now,
            ),
        )

        await AuditService.log_action(
            self.db, data["release_id"], "criterion", criterion_id,
            "created", "", "pending", user_id, user_role,
            f"Criterion '{data['name']}' added to release",
        )

        return await self.get_criterion(criterion_id)

    async def get_criterion(self, criterion_id: str) -> dict[str, Any]:
        """Get a single criterion by ID."""
        cursor = await self.db.execute(
            "SELECT * FROM criteria WHERE id = ?", (criterion_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise ValueError(f"Criterion {criterion_id} not found")
        result = dict(row)
        result["required"] = bool(result["required"])
        return result

    async def update_criterion(
        self, criterion_id: str, data: dict[str, Any],
        user_id: str, user_role: str = ""
    ) -> dict[str, Any]:
        """Update criterion fields."""
        current = await self.get_criterion(criterion_id)
        await touch_release(self.db,current["release_id"])
        if data.get('status') in {'passed','failed','waived'}:raise ValueError('Use the criterion review endpoint for review decisions')
        if current['status'] in {'passed','failed','waived'}:
            await self.db.execute("UPDATE criteria SET status='pending',reviewed_by='',reviewed_at=NULL WHERE id=?",(criterion_id,))
        now = datetime.now(timezone.utc).isoformat()

        updates: list[str] = []
        values: list[Any] = []
        for field in ("name", "description", "category", "status", "evidence",
                       "evidence_url", "assigned_to"):
            if field in data and data[field] is not None:
                old_val = current.get(field, "")
                updates.append(f"{field} = ?")
                values.append(data[field])
                if str(old_val) != str(data[field]):
                    await AuditService.log_action(
                        self.db, current["release_id"], "criterion", criterion_id,
                        f"updated_{field}", str(old_val), str(data[field]),
                        user_id, user_role,
                    )
        if "required" in data and data["required"] is not None:
            old_val = current.get("required", True)
            new_val = 1 if data["required"] else 0
            updates.append("required = ?")
            values.append(new_val)
            if old_val != bool(new_val):
                await AuditService.log_action(
                    self.db, current["release_id"], "criterion", criterion_id,
                    "updated_required", str(old_val), str(bool(new_val)),
                    user_id, user_role,
                )

        if updates:
            updates.append("updated_at = ?")
            values.append(now)
            values.append(criterion_id)
            await self.db.execute(
                f"UPDATE criteria SET {', '.join(updates)} WHERE id = ?",
                values,
            )

        return await self.get_criterion(criterion_id)

    async def review_criterion(
        self, criterion_id: str, reviewer: str,
        status: str, user_id: str, user_role: str = ""
    ) -> dict[str, Any]:
        """Review a criterion — mark it passed/failed/waived."""
        current = await self.get_criterion(criterion_id)
        await touch_release(self.db,current["release_id"])
        if status=='passed' and not current['evidence'].strip():raise ValueError('Passing review requires recorded evidence')
        now = datetime.now(timezone.utc).isoformat()
        old_status = current["status"]

        if status not in ("passed", "failed", "waived"):
            raise ValueError(f"Review status must be passed, failed, or waived, got '{status}'")

        await self.db.execute(
            """UPDATE criteria SET status = ?, reviewed_by = ?,
               reviewed_at = ?, updated_at = ? WHERE id = ?""",
            (status, reviewer, now, now, criterion_id),
        )

        await AuditService.log_action(
            self.db, current["release_id"], "criterion", criterion_id,
            "reviewed", old_status, status, user_id, user_role,
            f"Criterion reviewed by {reviewer}: {old_status} -> {status}",
        )

        return await self.get_criterion(criterion_id)

    async def list_criteria(
        self, release_id: str,
        category: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List criteria for a release with optional filters."""
        conditions = ["release_id = ?"]
        params: list[Any] = [release_id]

        if category:
            conditions.append("category = ?")
            params.append(category)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = " AND ".join(conditions)
        cursor = await self.db.execute(
            f"SELECT * FROM criteria WHERE {where} ORDER BY created_at ASC",
            params,
        )
        rows = await cursor.fetchall()
        results = [dict(row) for row in rows]
        for r in results:
            r["required"] = bool(r["required"])
        return results

    async def delete_criterion(
        self, criterion_id: str, user_id: str, user_role: str = ""
    ) -> bool:
        """Delete a criterion."""
        current = await self.get_criterion(criterion_id)
        await touch_release(self.db,current["release_id"])
        await self.db.execute("DELETE FROM criteria WHERE id = ?", (criterion_id,))

        await AuditService.log_action(
            self.db, current["release_id"], "criterion", criterion_id,
            "deleted", current["name"], "", user_id, user_role,
        )
        return True

    async def get_criteria_summary(self, release_id: str) -> dict[str, Any]:
        """Get aggregated criteria statistics for a release."""
        criteria = await self.list_criteria(release_id)
        summary: dict[str, Any] = {
            "total": len(criteria),
            "by_status": {},
            "by_category": {},
            "required_total": 0,
            "required_passed": 0,
        }
        for c in criteria:
            s = c["status"]
            summary["by_status"][s] = summary["by_status"].get(s, 0) + 1
            cat = c["category"]
            summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1
            if c["required"]:
                summary["required_total"] += 1
                if s == "passed":
                    summary["required_passed"] += 1
        return summary
