"""Release comparison service for cross-release analysis."""

from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone
from typing import Any

from app.core.risk_engine import risk_engine


class ComparisonService:
    """Service for comparing releases and tracking risk trends."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def _compute_summaries_and_risk(self, release: dict[str, Any]) -> dict[str, Any]:
        """Compute criteria_summary, blocker_summary, and risk_score for a release."""
        # Criteria summary
        criteria = release.get("criteria", [])
        criteria_summary = {
            "total": len(criteria),
            "passed": 0,
            "failed": 0,
            "pending": 0,
            "in_progress": 0,
            "waived": 0,
            "required_total": 0,
            "required_passed": 0,
        }
        for c in criteria:
            st = c["status"]
            if st in criteria_summary:
                criteria_summary[st] += 1
            if c["required"]:
                criteria_summary["required_total"] += 1
                if st == "passed":
                    criteria_summary["required_passed"] += 1
        release["criteria_summary"] = criteria_summary

        # Blocker summary
        blockers = release.get("blockers", [])
        blocker_summary = {
            "total": len(blockers),
            "open": 0,
            "investigating": 0,
            "mitigated": 0,
            "resolved": 0,
            "accepted": 0,
            "critical": 0,
            "high": 0,
        }
        for b in blockers:
            bst = b["status"]
            if bst in blocker_summary:
                blocker_summary[bst] += 1
            sev = b["severity"]
            if sev in ("critical", "high") and bst in ("open", "investigating"):
                blocker_summary[sev] += 1
        release["blocker_summary"] = blocker_summary

        # Risk score
        approvals = release.get("approvals", [])
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
            "criteria": criteria,
            "blockers": blockers,
            "approvals": approvals,
            "days_to_target": days_to_target,
        }
        assessment = risk_engine.assess_readiness(release_data)
        release["risk_score"] = assessment["risk_score"]

        return release

    async def get_release_full(self, release_id: str) -> dict[str, Any] | None:
        """Get a complete release with all related data and computed summaries."""
        cursor = await self.db.execute(
            "SELECT * FROM releases WHERE id = ?", (release_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        release = dict(row)

        # Get criteria
        cursor = await self.db.execute(
            "SELECT * FROM criteria WHERE release_id = ? ORDER BY created_at", (release_id,)
        )
        release["criteria"] = [dict(r) for r in await cursor.fetchall()]

        # Get blockers
        cursor = await self.db.execute(
            "SELECT * FROM blockers WHERE release_id = ? ORDER BY created_at", (release_id,)
        )
        release["blockers"] = [dict(r) for r in await cursor.fetchall()]

        # Get approvals
        cursor = await self.db.execute(
            "SELECT * FROM approvals WHERE release_id = ? ORDER BY created_at", (release_id,)
        )
        release["approvals"] = [dict(r) for r in await cursor.fetchall()]

        # Get risk snapshots
        cursor = await self.db.execute(
            "SELECT * FROM release_snapshots WHERE release_id = ? ORDER BY created_at", (release_id,)
        )
        release["snapshots"] = [dict(r) for r in await cursor.fetchall()]

        # Compute summaries and risk score
        return await self._compute_summaries_and_risk(release)

    async def compare_releases(
        self, release_id_a: str, release_id_b: str
    ) -> dict[str, Any] | None:
        """Compare two releases side by side."""
        release_a = await self.get_release_full(release_id_a)
        release_b = await self.get_release_full(release_id_b)

        if not release_a or not release_b:
            return None

        # Compare criteria
        criteria_a = {c["id"]: c for c in release_a["criteria"]}
        criteria_b = {c["id"]: c for c in release_b["criteria"]}

        # Match criteria by name (since IDs differ across releases)
        criteria_by_name_a = {c["name"]: c for c in release_a["criteria"]}
        criteria_by_name_b = {c["name"]: c for c in release_b["criteria"]}
        all_criteria_names = set(criteria_by_name_a.keys()) | set(criteria_by_name_b.keys())

        criteria_delta = []
        for name in sorted(all_criteria_names):
            ca = criteria_by_name_a.get(name)
            cb = criteria_by_name_b.get(name)
            if ca and cb:
                criteria_delta.append({
                    "name": name,
                    "status_a": ca["status"],
                    "status_b": cb["status"],
                    "required": ca["required"],
                    "changed": ca["status"] != cb["status"],
                })
            elif ca:
                criteria_delta.append({
                    "name": name,
                    "status_a": ca["status"],
                    "status_b": "missing",
                    "required": ca["required"],
                    "changed": True,
                })
            else:
                criteria_delta.append({
                    "name": name,
                    "status_a": "missing",
                    "status_b": cb["status"],
                    "required": cb["required"],
                    "changed": True,
                })

        # Compare blockers
        blockers_a = {b["id"]: b for b in release_a["blockers"]}
        blockers_b = {b["id"]: b for b in release_b["blockers"]}
        all_blocker_ids = set(blockers_a.keys()) | set(blockers_b.keys())

        blocker_changes = []
        for bid in sorted(all_blocker_ids):
            ba = blockers_a.get(bid)
            bb = blockers_b.get(bid)
            if ba and bb:
                blocker_changes.append({
                    "id": bid,
                    "title_a": ba["title"],
                    "title_b": bb["title"],
                    "severity_a": ba["severity"],
                    "severity_b": bb["severity"],
                    "status_a": ba["status"],
                    "status_b": bb["status"],
                    "changed": ba["status"] != bb["status"] or ba["severity"] != bb["severity"],
                })
            elif ba:
                blocker_changes.append({
                    "id": bid,
                    "title_a": ba["title"],
                    "title_b": "removed",
                    "severity_a": ba["severity"],
                    "severity_b": "N/A",
                    "status_a": ba["status"],
                    "status_b": "removed",
                    "changed": True,
                })
            else:
                blocker_changes.append({
                    "id": bid,
                    "title_a": "new",
                    "title_b": bb["title"],
                    "severity_a": "N/A",
                    "severity_b": bb["severity"],
                    "status_a": "new",
                    "status_b": bb["status"],
                    "changed": True,
                })

        # Compare approvals
        approvals_a = {a["id"]: a for a in release_a["approvals"]}
        approvals_b = {a["id"]: a for a in release_b["approvals"]}

        approval_diff = {
            "release_a": {
                "total": len(release_a["approvals"]),
                "approved": sum(1 for a in release_a["approvals"] if a["decision"] == "approved"),
                "rejected": sum(1 for a in release_a["approvals"] if a["decision"] == "rejected"),
                "conditional": sum(1 for a in release_a["approvals"] if a["decision"] == "conditional"),
            },
            "release_b": {
                "total": len(release_b["approvals"]),
                "approved": sum(1 for a in release_b["approvals"] if a["decision"] == "approved"),
                "rejected": sum(1 for a in release_b["approvals"] if a["decision"] == "rejected"),
                "conditional": sum(1 for a in release_b["approvals"] if a["decision"] == "conditional"),
            },
        }

        # Risk comparison
        risk_a = release_a.get("risk_score", 0)
        risk_b = release_b.get("risk_score", 0)

        return {
            "release_a": {
                "id": release_a["id"],
                "name": release_a["name"],
                "version": release_a["version"],
                "status": release_a["status"],
                "revision": release_a["revision"],
                "risk_score": risk_a,
                "criteria_summary": release_a.get("criteria_summary"),
                "blocker_summary": release_a.get("blocker_summary"),
            },
            "release_b": {
                "id": release_b["id"],
                "name": release_b["name"],
                "version": release_b["version"],
                "status": release_b["status"],
                "revision": release_b["revision"],
                "risk_score": risk_b,
                "criteria_summary": release_b.get("criteria_summary"),
                "blocker_summary": release_b.get("blocker_summary"),
            },
            "criteria_delta": criteria_delta,
            "blocker_changes": blocker_changes,
            "approval_diff": approval_diff,
            "risk_delta": risk_b - risk_a,
        }


    async def get_releases_for_comparison(self) -> list[dict[str, Any]]:
        """Get all releases available for comparison."""
        cursor = await self.db.execute(
            "SELECT id, name, version, status, updated_at FROM releases ORDER BY updated_at DESC"
        )
        return [dict(r) for r in await cursor.fetchall()]



    async def get_risk_trend(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get risk trend across recent releases."""
        cursor = await self.db.execute(
            """
            SELECT r.id, r.name, r.version, r.status, r.updated_at,
                   (SELECT COUNT(*) FROM criteria WHERE release_id = r.id) as total_criteria,
                   (SELECT COUNT(*) FROM criteria WHERE release_id = r.id AND status = 'passed') as passed_criteria,
                   (SELECT COUNT(*) FROM blockers WHERE release_id = r.id AND status = 'open') as open_blockers
            FROM releases r
            ORDER BY r.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        trend = []
        for row in rows:
            d = dict(row)
            d["criteria_pass_rate"] = (
                d["passed_criteria"] / d["total_criteria"] if d["total_criteria"] > 0 else 0
            )
            # Get latest risk score from snapshots
            snap_cursor = await self.db.execute(
                "SELECT risk_score FROM release_snapshots WHERE release_id = ? ORDER BY created_at DESC LIMIT 1",
                (d["id"],),
            )
            snap_row = await snap_cursor.fetchone()
            d["risk_score"] = snap_row["risk_score"] if snap_row else 0.0
            trend.append(d)
        return list(reversed(trend))  # Oldest first for charting
