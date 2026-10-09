"""Release API endpoints."""

from __future__ import annotations

from typing import Any

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import get_current_user, require_role
from app.core.database import get_db
from app.core.risk_engine import risk_engine
from app.models.schemas import (
    ExportFormat,
    ReleaseCreate,
    ReleaseListResponse,
    ReleaseResponse,
    ReleaseTransition,
    ReleaseUpdate,
    RiskAssessmentResponse,
)
from app.services.export_service import ExportService
from app.services.release_service import ReleaseService

router = APIRouter(prefix="/api/releases", tags=["releases"])


def _release_to_response(release: dict[str, Any]) -> dict[str, Any]:
    """Convert release dict to response format."""
    return {
        "id": release["id"],
        "name": release["name"],
        "version": release["version"],
        "description": release.get("description", ""),
        "status": release["status"],
        "revision": release["revision"],
        "target_date": release.get("target_date"),
        "created_by": release["created_by"],
        "created_at": release["created_at"],
        "updated_at": release["updated_at"],
        "criteria_summary": release.get("criteria_summary"),
        "blocker_summary": release.get("blocker_summary"),
        "risk_score": release.get("risk_score"),
    }


@router.post("/", response_model=ReleaseResponse, status_code=status.HTTP_201_CREATED)
async def create_release(
    data: ReleaseCreate,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("operator")),
):
    """Create a new release."""
    svc = ReleaseService(db)
    release = await svc.create_release(data.model_dump(), user["sub"], user.get("role", ""))
    return _release_to_response(release)


@router.get("/", response_model=ReleaseListResponse)
async def list_releases(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None),
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("viewer")),
):
    """List releases with pagination and filtering."""
    svc = ReleaseService(db)
    items, total = await svc.list_releases(page, per_page, status_filter, search)
    return {
        "items": [_release_to_response(r) for r in items],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/{release_id}", response_model=ReleaseResponse)
async def get_release(
    release_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("viewer")),
):
    """Get a release by ID."""
    svc = ReleaseService(db)
    try:
        release = await svc.get_release(release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _release_to_response(release)


@router.put("/{release_id}", response_model=ReleaseResponse)
async def update_release(
    release_id: str,
    data: ReleaseUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("operator")),
):
    """Update a release."""
    svc = ReleaseService(db)
    try:
        update_data = data.model_dump(exclude_none=True)
        if "status" in update_data:
            del update_data["status"]
        release = await svc.update_release(release_id, update_data, user["sub"], user.get("role", ""))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _release_to_response(release)


@router.post("/{release_id}/transition", response_model=ReleaseResponse)
async def transition_release(
    release_id: str,
    data: ReleaseTransition,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("operator")),
):
    """Transition release status."""
    if data.status.value == "approved" and user.get("role") != "admin":
        raise HTTPException(
            status_code=403, detail="Only admins can approve releases"
        )
    svc = ReleaseService(db)
    try:
        release = await svc.transition_release(
            release_id, data.status.value, user["sub"], user.get("role", "")
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _release_to_response(release)


@router.delete("/{release_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_release(
    release_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Delete a release (admin only)."""
    svc = ReleaseService(db)
    try:
        await svc.delete_release(release_id, user["sub"], user.get("role", ""))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{release_id}/risk-assessment", response_model=RiskAssessmentResponse)
async def get_risk_assessment(
    release_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("viewer")),
):
    """Get ML-powered risk assessment for a release."""
    svc = ReleaseService(db)
    try:
        release = await svc.get_release(release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Gather full data for assessment
    from app.services.criteria_service import CriteriaService
    from app.services.blocker_service import BlockerService
    from app.services.approval_service import ApprovalService

    criteria = await CriteriaService(db).list_criteria(release_id)
    blockers = await BlockerService(db).list_blockers(release_id)
    from app.services.invariants import current_decisions
    approvals = await current_decisions(db,release_id)

    from datetime import datetime, timezone
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

    # Get historical snapshots for pattern detection
    snap_cursor = await db.execute(
        "SELECT snapshot_data, risk_score FROM release_snapshots WHERE release_id = ? ORDER BY created_at",
        (release_id,),
    )
    history = []
    for row in await snap_cursor.fetchall():
        try:
            import json
            snap = json.loads(row["snapshot_data"])
            snap["risk_score"] = row["risk_score"]
            history.append(snap)
        except (json.JSONDecodeError, TypeError):
            pass

    assessment = risk_engine.assess_readiness(release_data, history or None)
    from app.services.invariants import require_ready
    try:await require_ready(db,release_id);assessment['ready_for_release']=True
    except ValueError as exc:
        assessment['ready_for_release']=False;assessment['risk_factors'].append(str(exc))
    return assessment


@router.get("/{release_id}/release-notes")
async def get_release_notes(
    release_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("viewer")),
):
    """Get generated release notes."""
    try:
        notes = await ExportService.generate_release_notes(release_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return notes


@router.get("/{release_id}/export/{fmt}")
async def export_release(
    release_id: str,
    fmt: ExportFormat,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("viewer")),
):
    """Export release in the specified format."""
    from fastapi.responses import Response

    try:
        if fmt == ExportFormat.json:
            content = await ExportService.export_json(release_id, db)
            return Response(content=content, media_type="application/json")
        elif fmt == ExportFormat.markdown:
            content = await ExportService.export_markdown(release_id, db)
            return Response(content=content, media_type="text/markdown")
        elif fmt == ExportFormat.csv:
            content = await ExportService.export_csv(release_id, db)
            return Response(content=content, media_type="text/csv")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
