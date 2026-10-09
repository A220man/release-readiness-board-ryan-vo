"""Audit log API endpoints."""

from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, Query

from app.core.auth import require_role
from app.core.database import get_db
from app.models.schemas import AuditLogResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/", response_model=AuditLogResponse)
async def get_audit_log(
    entity_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("operator")),
):
    """Get audit log with pagination and filtering."""
    items, total = await AuditService.get_audit_log(
        db, entity_type=entity_type, page=page, per_page=per_page,
    )
    return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.get("/release/{release_id}", response_model=AuditLogResponse)
async def get_release_audit_log(
    release_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("viewer")),
):
    """Get audit log for a specific release."""
    items, total = await AuditService.get_audit_log(
        db, release_id=release_id, page=page, per_page=per_page,
    )
    return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.get("/release/{release_id}/export")
async def export_release_audit_log(
    release_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("operator")),
):
    """Export complete audit log for a release."""
    items = await AuditService.export_audit_log(db, release_id)
    return {"items": items, "total": len(items)}
