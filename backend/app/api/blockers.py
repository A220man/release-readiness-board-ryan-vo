"""Blocker API endpoints."""

from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import require_role
from app.core.database import get_db
from app.models.schemas import (
    BlockerCreate,
    BlockerResolve,
    BlockerResponse,
    BlockerUpdate,
)
from app.services.blocker_service import BlockerService

router = APIRouter(prefix="/api/blockers", tags=["blockers"])


@router.post("/", response_model=BlockerResponse, status_code=status.HTTP_201_CREATED)
async def create_blocker(
    data: BlockerCreate,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("operator")),
):
    """Create a new blocker with NLP auto-classification."""
    svc = BlockerService(db)
    try:
        blocker = await svc.create_blocker(data.model_dump(), user["sub"], user.get("role", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return blocker


@router.get("/release/{release_id}", response_model=list[BlockerResponse])
async def list_blockers(
    release_id: str,
    severity: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("viewer")),
):
    """List blockers for a release."""
    svc = BlockerService(db)
    return await svc.list_blockers(release_id, severity, status_filter)


@router.get("/{blocker_id}", response_model=BlockerResponse)
async def get_blocker(
    blocker_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("viewer")),
):
    """Get a single blocker."""
    svc = BlockerService(db)
    try:
        return await svc.get_blocker(blocker_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{blocker_id}", response_model=BlockerResponse)
async def update_blocker(
    blocker_id: str,
    data: BlockerUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("operator")),
):
    """Update a blocker."""
    svc = BlockerService(db)
    try:
        return await svc.update_blocker(
            blocker_id, data.model_dump(exclude_none=True),
            user["sub"], user.get("role", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{blocker_id}/resolve", response_model=BlockerResponse)
async def resolve_blocker(
    blocker_id: str,
    data: BlockerResolve,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("operator")),
):
    """Resolve a blocker."""
    svc = BlockerService(db)
    try:
        return await svc.resolve_blocker(
            blocker_id, data.resolution, user["sub"], user.get("role", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{blocker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blocker(
    blocker_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Delete a blocker (admin only)."""
    svc = BlockerService(db)
    try:
        await svc.delete_blocker(blocker_id, user["sub"], user.get("role", ""))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
