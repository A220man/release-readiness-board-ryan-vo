"""Release management service with state machine transitions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.services.audit_service import AuditService
from app.services.invariants import touch_release, release_row, require_ready, current_decisions


# Valid release status transitions
_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["in_review", "cancelled"],
    "in_review": ["approved", "draft", "cancelled"],
    "approved": ["released", "in_review", "cancelled"],
    "released": [],
    "cancelled": ["draft"],
}


class ReleaseService:
    """Service for managing releases with auditable state transitions."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def create_release(
        self, data: dict[str, Any], user_id: str, user_role: str = ""
    ) -> dict[str, Any]:
        """Create a new release."""
        release_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        await self.db.execute(
            """INSERT INTO releases
               (id, name, version, description, status, target_date, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                release_id, data["name"], data["version"],
                data.get("description", ""), "draft",
                data.get("target_date"), user_id, now, now,
            ),
        )

        await AuditService.log_action(
            self.db, release_id, "release", release_id,
            "created", "", "draft", user_id, user_role,
            f"Release '{data['name']}' v{data['version']} created",
        )

        return await self.get_release(release_id)

    async def get_release(self, release_id: str) -> dict[str, Any]:
        """Get a release by ID with criteria and blocker summaries."""
        cursor = await self.db.execute(
            "SELECT * FROM releases WHERE id = ?", (release_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise ValueError(f"Release {release_id} not found")

        release = dict(row)

        # Criteria summary
        crit_cursor = await self.db.execute(
            "SELECT status, required FROM criteria WHERE release_id = ?",
            (release_id,),
        )
        criteria_rows = await crit_cursor.fetchall()
        criteria_summary = {
            "total": 0, "passed": 0, "failed": 0, "pending": 0,
            "in_progress": 0, "waived": 0, "required_total": 0, "required_passed": 0,
        }
        for cr in criteria_rows:
            criteria_summary["total"] += 1
            status = cr["status"]
            if status in criteria_summary:
                criteria_summary[status] += 1
            if cr["required"]:
                criteria_summary["required_total"] += 1
                if status == "passed":
                    criteria_summary["required_passed"] += 1
        release["criteria_summary"] = criteria_summary

        # Blocker summary
        block_cursor = await self.db.execute(
            "SELECT status, severity FROM blockers WHERE release_id = ?",
            (release_id,),
        )
        blocker_rows = await block_cursor.fetchall()
        blocker_summary = {
            "total": 0, "open": 0, "investigating": 0, "mitigated": 0,
            "resolved": 0, "accepted": 0, "critical": 0, "high": 0,
        }
        for br in blocker_rows:
            blocker_summary["total"] += 1
            bstatus = br["status"]
            if bstatus in blocker_summary:
                blocker_summary[bstatus] += 1
            sev = br["severity"]
            if sev in ("critical", "high"):
                if br["status"] in ("open", "investigating"):
                    blocker_summary[sev] += 1
        release["blocker_summary"] = blocker_summary

        # Risk score
        from app.core.risk_engine import risk_engine

        all_criteria = []
        full_crit_cursor = await self.db.execute(
            "SELECT * FROM criteria WHERE release_id = ?", (release_id,),
        )
        for cr in await full_crit_cursor.fetchall():
            all_criteria.append(dict(cr))

        all_blockers = []
        full_block_cursor = await self.db.execute(
            "SELECT * FROM blockers WHERE release_id = ?", (release_id,),
        )
        for br in await full_block_cursor.fetchall():
            all_blockers.append(dict(br))

        all_approvals = await current_decisions(self.db,release_id)

        days_to_target = 30
        if release.get("target_date"):
            try:
                target = datetime.fromisoformat(release["target_date"])
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                days_to_target = (target - datetime.now(timezone.utc)).days
            except (ValueError, TypeError):
                pass

        release_data = {
            "criteria": all_criteria,
            "blockers": all_blockers,
            "approvals": all_approvals,
            "days_to_target": days_to_target,
        }
        assessment = risk_engine.assess_readiness(release_data)
        release["risk_score"] = assessment["risk_score"]

        return release

    async def list_releases(
        self,
        page: int = 1,
        per_page: int = 20,
        status_filter: str | None = None,
        search: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List releases with pagination and filtering."""
        conditions: list[str] = []
        params: list[Any] = []

        if status_filter:
            conditions.append("status = ?")
            params.append(status_filter)
        if search:
            conditions.append("(name LIKE ? OR description LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        count_cursor = await self.db.execute(
            f"SELECT COUNT(*) FROM releases {where}", params,
        )
        count_row = await count_cursor.fetchone()
        total = count_row[0] if count_row else 0

        offset = (page - 1) * per_page
        cursor = await self.db.execute(
            f"""SELECT * FROM releases {where}
                ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
            params + [per_page, offset],
        )
        rows = await cursor.fetchall()

        items = []
        for row in rows:
            release = await self.get_release(row["id"])
            items.append(release)

        return items, total

    async def update_release(
        self, release_id: str, data: dict[str, Any], user_id: str, user_role: str = ""
    ) -> dict[str, Any]:
        """Update release fields."""
        current = await self.get_release(release_id)
        await touch_release(self.db,release_id)
        now = datetime.now(timezone.utc).isoformat()

        updates: list[str] = []
        values: list[Any] = []
        for field in ("name", "version", "description", "target_date"):
            if field in data and data[field] is not None:
                old_val = current.get(field, "")
                updates.append(f"{field} = ?")
                values.append(data[field])
                if str(old_val) != str(data[field]):
                    await AuditService.log_action(
                        self.db, release_id, "release", release_id,
                        f"updated_{field}", str(old_val), str(data[field]),
                        user_id, user_role,
                    )

        if updates:
            updates.append("updated_at = ?")
            values.append(now)
            values.append(release_id)
            await self.db.execute(
                f"UPDATE releases SET {', '.join(updates)} WHERE id = ?",
                values,
            )

        return await self.get_release(release_id)

    async def transition_release(
        self, release_id: str, new_status: str, user_id: str, user_role: str = ""
    ) -> dict[str, Any]:
        """Transition release to a new status with validation."""
        current = await self.get_release(release_id)
        old_status = current["status"]

        valid_targets = _TRANSITIONS.get(old_status, [])
        if new_status not in valid_targets:
            raise ValueError(
                f"Cannot transition from '{old_status}' to '{new_status}'. "
                f"Valid transitions: {valid_targets}"
            )

        if new_status in {"approved","released"}:
            await require_ready(self.db,release_id)
        if old_status=='approved' and new_status=='in_review':
            await self.db.execute('UPDATE releases SET revision=revision+1 WHERE id=?',(release_id,))

        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE releases SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, release_id),
        )

        if new_status in {'in_review','released'}:
            import json
            from app.services.export_service import ExportService
            snapshot=await ExportService._gather_release_data(release_id,self.db)
            assessment=await self.get_release(release_id)
            await self.db.execute('INSERT INTO release_snapshots(id,release_id,snapshot_data,risk_score,created_at) VALUES(?,?,?,?,?)',
                (str(uuid.uuid4()),release_id,json.dumps(snapshot),assessment['risk_score'],now))

        await AuditService.log_action(
            self.db, release_id, "release", release_id,
            "status_transition", old_status, new_status,
            user_id, user_role,
            f"Release transitioned from {old_status} to {new_status}",
        )

        return await self.get_release(release_id)

    async def delete_release(
        self, release_id: str, user_id: str, user_role: str = ""
    ) -> bool:
        """Delete a release and all associated data."""
        current=await self.get_release(release_id)
        if current["status"]=="released":raise ValueError("Released records cannot be deleted")

        await self.db.execute("DELETE FROM criteria WHERE release_id = ?", (release_id,))
        await self.db.execute("DELETE FROM blockers WHERE release_id = ?", (release_id,))
        await self.db.execute("DELETE FROM approvals WHERE release_id = ?", (release_id,))
        await self.db.execute("DELETE FROM release_snapshots WHERE release_id = ?", (release_id,))
        await self.db.execute("DELETE FROM releases WHERE id = ?", (release_id,))

        await AuditService.log_action(
            self.db, release_id, "release", release_id,
            "deleted", "", "", user_id, user_role,
        )

        return True
