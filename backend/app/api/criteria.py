"""Criteria API endpoints."""

from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import require_role
from app.core.database import get_db
from app.models.schemas import (
    CriterionCreate,
    CriterionResponse,
    CriterionReview,
    CriterionUpdate,
)
from app.services.criteria_service import CriteriaService

router = APIRouter(prefix="/api/criteria", tags=["criteria"])


@router.post("/", response_model=CriterionResponse, status_code=status.HTTP_201_CREATED)
async def add_criterion(
    data: CriterionCreate,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("operator")),
):
    """Add a new criterion to a release."""
    svc = CriteriaService(db)
    try:
        criterion = await svc.add_criterion(data.model_dump(), user["sub"], user.get("role", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return criterion


@router.get("/release/{release_id}", response_model=list[CriterionResponse])
async def list_criteria(
    release_id: str,
    category: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("viewer")),
):
    """List criteria for a release."""
    svc = CriteriaService(db)
    return await svc.list_criteria(release_id, category, status_filter)


@router.get("/{criterion_id}", response_model=CriterionResponse)
async def get_criterion(
    criterion_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("viewer")),
):
    """Get a single criterion."""
    svc = CriteriaService(db)
    try:
        return await svc.get_criterion(criterion_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{criterion_id}", response_model=CriterionResponse)
async def update_criterion(
    criterion_id: str,
    data: CriterionUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("operator")),
):
    """Update a criterion."""
    svc = CriteriaService(db)
    try:
        return await svc.update_criterion(
            criterion_id, data.model_dump(exclude_none=True),
            user["sub"], user.get("role", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{criterion_id}/review", response_model=CriterionResponse)
async def review_criterion(
    criterion_id: str,
    data: CriterionReview,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("operator")),
):
    """Review a criterion (pass/fail/waive)."""
    svc = CriteriaService(db)
    try:
        return await svc.review_criterion(
            criterion_id, user["sub"], data.status.value,
            user["sub"], user.get("role", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{criterion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_criterion(
    criterion_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Delete a criterion (admin only)."""
    svc = CriteriaService(db)
    try:
        await svc.delete_criterion(criterion_id, user["sub"], user.get("role", ""))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
