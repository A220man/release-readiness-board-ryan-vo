"""Pydantic v2 schemas for API request/response models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime


# Enums
class ReleaseStatus(str, Enum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"
    released = "released"
    cancelled = "cancelled"


class CriterionCategory(str, Enum):
    testing = "testing"
    security = "security"
    performance = "performance"
    documentation = "documentation"
    compliance = "compliance"
    infrastructure = "infrastructure"


class CriterionStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    passed = "passed"
    failed = "failed"
    waived = "waived"


class BlockerSeverity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class BlockerStatus(str, Enum):
    open = "open"
    investigating = "investigating"
    mitigated = "mitigated"
    resolved = "resolved"
    accepted = "accepted"


class ApprovalDecision(str, Enum):
    approved = "approved"
    rejected = "rejected"
    conditional = "conditional"


class ExportFormat(str, Enum):
    json = "json"
    markdown = "markdown"
    csv = "csv"


# Release schemas
class ReleaseDate(BaseModel):
    @field_validator('target_date',check_fields=False)
    @classmethod
    def date_valid(cls,value):
        if value is not None:
            try:datetime.fromisoformat(value.replace('Z','+00:00'))
            except ValueError:raise ValueError('target_date must be ISO 8601')
        return value

class ReleaseCreate(ReleaseDate):
    name: str = Field(..., min_length=1, max_length=200)
    version: str = Field(..., min_length=1, max_length=50)
    description: str = Field(default="", max_length=2000)
    target_date: str | None = None


class ReleaseUpdate(ReleaseDate):
    model_config=ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    version: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    target_date: str | None = None


class ReleaseTransition(BaseModel):
    status: ReleaseStatus


class CriteriaSummary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    pending: int = 0
    in_progress: int = 0
    waived: int = 0
    required_total: int = 0
    required_passed: int = 0


class BlockerSummaryModel(BaseModel):
    total: int = 0
    open: int = 0
    investigating: int = 0
    mitigated: int = 0
    resolved: int = 0
    accepted: int = 0
    critical: int = 0
    high: int = 0


class ReleaseResponse(BaseModel):
    revision: int
    id: str
    name: str
    version: str
    description: str
    status: str
    target_date: str | None
    created_by: str
    created_at: str
    updated_at: str
    criteria_summary: CriteriaSummary | None = None
    blocker_summary: BlockerSummaryModel | None = None
    risk_score: float | None = None


class ReleaseListResponse(BaseModel):
    items: list[ReleaseResponse]
    total: int
    page: int
    per_page: int


# Criterion schemas
class CriterionCreate(BaseModel):
    release_id: str
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    category: CriterionCategory
    required: bool = True


class CriterionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: CriterionCategory | None = None
    status: CriterionStatus | None = None
    required: bool | None = None
    evidence: str | None = Field(default=None, max_length=5000)
    evidence_url: str | None = Field(default=None, max_length=500)
    assigned_to: str | None = Field(default=None, max_length=100)


class CriterionReview(BaseModel):
    status: CriterionStatus
    comment: str = Field(default="", max_length=2000)


class CriterionResponse(BaseModel):
    id: str
    release_id: str
    name: str
    description: str
    category: str
    status: str
    required: bool
    evidence: str
    evidence_url: str
    assigned_to: str
    reviewed_by: str
    reviewed_at: str | None
    created_at: str
    updated_at: str


# Blocker schemas
class BlockerCreate(BaseModel):
    release_id: str
    title: str = Field(..., min_length=1, max_length=300)
    description: str = Field(..., min_length=1, max_length=5000)
    severity: BlockerSeverity = BlockerSeverity.medium


class BlockerUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    severity: BlockerSeverity | None = None
    status: BlockerStatus | None = None
    category: str | None = Field(default=None, max_length=100)
    assigned_to: str | None = Field(default=None, max_length=100)
    resolution: str | None = Field(default=None, max_length=2000)


class BlockerResolve(BaseModel):
    resolution: str = Field(..., min_length=1, max_length=2000)


class BlockerResponse(BaseModel):
    id: str
    release_id: str
    title: str
    description: str
    severity: str
    status: str
    category: str
    assigned_to: str
    resolution: str
    created_by: str
    created_at: str
    updated_at: str
    resolved_at: str | None
    auto_category: dict[str, Any] | None = None


# Approval schemas
class ApprovalCreate(BaseModel):
    release_id: str
    decision: ApprovalDecision
    conditions: str = Field(default="", max_length=2000)
    comment: str = Field(default="", max_length=2000)


class ApprovalResponse(BaseModel):
    release_revision: int
    id: str
    release_id: str
    approver: str
    role: str
    decision: str
    conditions: str
    comment: str
    created_at: str


# Audit log schemas
class AuditLogEntry(BaseModel):
    id: str
    release_id: str | None
    entity_type: str
    entity_id: str
    action: str
    old_value: str
    new_value: str
    user_id: str
    user_role: str
    timestamp: str
    details: str


class AuditLogResponse(BaseModel):
    items: list[AuditLogEntry]
    total: int
    page: int
    per_page: int


# Risk assessment schemas
class RiskAssessmentResponse(BaseModel):
    risk_score: float
    risk_level: str
    features: dict[str, float]
    risk_factors: list[str]
    recommendations: list[str]
    patterns: list[dict[str, Any]] | None = None
    ready_for_release: bool


# Release notes schemas
class ReleaseNotesResponse(BaseModel):
    release_name: str
    version: str
    date: str
    summary: str
    criteria_results: list[dict[str, Any]]
    blockers_resolved: list[dict[str, Any]]
    approvals: list[dict[str, Any]]
    risk_assessment: dict[str, Any]
    generated_at: str


# LLM analysis schemas
class LLMAnalysisResponse(BaseModel):
    analysis: str
    suggestions: list[str]
    confidence: str
    advisory: str = "AI-generated analysis — advisory only, verify independently"
    provider: str = ""


class ErrorResponse(BaseModel):
    detail: str
