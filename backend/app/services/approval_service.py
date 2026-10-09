"""Approval management service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.services.audit_service import AuditService
from app.services.invariants import touch_release, release_row, require_ready, current_decisions


class ApprovalService:
    """Service for managing release approvals."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def create_approval(
        self, data: dict[str, Any], user_id: str, user_role: str
    ) -> dict[str, Any]:
        """Record an approval decision."""
        if user_role not in ("operator", "admin"):
            raise ValueError("Only operators and admins can approve releases")

        release=await release_row(self.db,data['release_id'])
        if release['status']!='in_review':raise ValueError('Approvals are only accepted during review')
        if release['created_by']==user_id:raise ValueError('The release creator cannot approve their own release')
        if data['decision']=='conditional' and not data.get('conditions','').strip():raise ValueError('Conditional approval needs explicit conditions')

        approval_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        await self.db.execute(
            """INSERT INTO approvals
               (id, release_id, approver, release_revision, role, decision, conditions, comment, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                approval_id, data["release_id"], user_id, release["revision"], user_role,
                data["decision"], data.get("conditions", ""),
                data.get("comment", ""), now,
            ),
        )

        await AuditService.log_action(
            self.db, data["release_id"], "approval", approval_id,
            "created", "", data["decision"], user_id, user_role,
            f"Approval '{data['decision']}' by {user_id}",
        )

        return await self.get_approval(approval_id)

    async def get_approval(self, approval_id: str) -> dict[str, Any]:
        """Get a single approval by ID."""
        cursor = await self.db.execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise ValueError(f"Approval {approval_id} not found")
        return dict(row)

    async def list_approvals(self, release_id: str) -> list[dict[str, Any]]:
        """List all approvals for a release."""
        cursor = await self.db.execute(
            "SELECT * FROM approvals WHERE release_id = ? ORDER BY created_at DESC",
            (release_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def revoke_approval(
        self, approval_id: str, user_id: str, user_role: str = ""
    ) -> bool:
        """Revoke an approval (admin only)."""
        current = await self.get_approval(approval_id)
        release=await release_row(self.db,current['release_id'])
        if release['status']=='released':raise ValueError('Released approvals cannot be revoked')
        if release['status']=='approved':
            await self.db.execute("UPDATE releases SET status='in_review',revision=revision+1 WHERE id=?",(current['release_id'],))
        await self.db.execute("DELETE FROM approvals WHERE id = ?", (approval_id,))

        await AuditService.log_action(
            self.db, current["release_id"], "approval", approval_id,
            "revoked", current["decision"], "", user_id, user_role,
            f"Approval revoked by {user_id}",
        )
        return True
