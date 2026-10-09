"""Approval API endpoints."""

from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import require_role
from app.core.database import get_db
from app.models.schemas import ApprovalCreate, ApprovalResponse
from app.services.approval_service import ApprovalService

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.post("/", response_model=ApprovalResponse, status_code=status.HTTP_201_CREATED)
async def create_approval(
    data: ApprovalCreate,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("operator")),
):
    """Record an approval decision."""
    svc = ApprovalService(db)
    try:
        approval = await svc.create_approval(
            data.model_dump(), user["sub"], user.get("role", "operator"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return approval


@router.get("/release/{release_id}", response_model=list[ApprovalResponse])
async def list_approvals(
    release_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("viewer")),
):
    """List approvals for a release."""
    svc = ApprovalService(db)
    return await svc.list_approvals(release_id)


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(
    approval_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("viewer")),
):
    """Get a single approval."""
    svc = ApprovalService(db)
    try:
        return await svc.get_approval(approval_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{approval_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_approval(
    approval_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Revoke an approval (admin only)."""
    svc = ApprovalService(db)
    try:
        await svc.revoke_approval(approval_id, user["sub"], user.get("role", ""))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
