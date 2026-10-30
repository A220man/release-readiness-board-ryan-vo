# Product development plan

Each round completes one feature or repair. Future items are planned, not implemented claims.

## Current round

release-comparison-and-trending

## Roadmap

### evidence-backed-releases — Evidence-backed release lifecycle and state machine

Status: done

Acceptance:
- Create release drafts, record criteria with evidence and owners, enforce passing reviews for required criteria, and freeze approved evidence.

Implementation: `backend/app/api/releases.py`, `backend/app/services/release_service.py`, `backend/app/services/invariants.py`, `frontend/src/App.tsx`, `frontend/src/CriteriaPanel.tsx`

Tests: `backend/tests/test_release_invariants.py`, `backend/tests/test_api_sessions.py`, `frontend/src/workflows.test.tsx`

### independent-approvals-and-blockers — Independent revision-bound approvals and blocker resolution

Status: done

Acceptance:
- Track blockers with severity and auto-categorization; reject approval by release creator; tie approval decisions strictly to current evidence revision.

Implementation: `backend/app/api/approvals.py`, `backend/app/api/blockers.py`, `backend/app/services/approval_service.py`, `backend/app/services/blocker_service.py`, `frontend/src/ApprovalsPanel.tsx`, `frontend/src/BlockersPanel.tsx`

Tests: `backend/tests/test_release_invariants.py`, `backend/tests/test_api_sessions.py`, `frontend/src/workflows.test.tsx`

### deterministic-risk-and-exports — Deterministic risk scoring, evaluation diagnostics, and audit export

Status: done

Acceptance:
- Calculate deterministic risk index with feature weights and NLP classification; export release notes in JSON/Markdown/CSV; provide reproducible evaluation corpus.

Implementation: `backend/app/core/risk_engine.py`, `backend/app/services/evaluation.py`, `backend/app/services/export_service.py`, `frontend/src/InsightsPanel.tsx`

Tests: `backend/tests/test_diagnostics_providers.py`, `frontend/src/workflows.test.tsx`

### release-search-and-filtering — Interactive release search and lifecycle status filtering

Status: done

Acceptance:
- Filter releases by lifecycle status (draft, in_review, approved, released, cancelled) and search by keyword across name and description with filter-aware pagination and empty states in both API and UI.

Implementation: `backend/app/services/release_service.py`, `backend/app/api/releases.py`, `frontend/src/App.tsx`

Tests: `backend/tests/test_release_search_filter.py`, `frontend/src/workflows.test.tsx`

### in-app-release-notes-preview — In-app structured release notes preview modal

Status: done

Acceptance:
- Preview generated release notes directly in the UI before exporting or releasing.

Implementation: `frontend/src/ReleaseNotesPreview.tsx`, `frontend/src/InsightsPanel.tsx`

Tests: `frontend/src/workflows.test.tsx`

### release-comparison-and-trending — Cross-release comparison and risk trending

Status: done

Acceptance:
- Compare two releases side-by-side showing criteria delta, blocker changes, risk score evolution, and approval history differences.
- Display risk trend across recent releases with sparklines for risk score, blocker count, and criteria pass rate.
- Enable release-to-release diff view for audit trail analysis.

Implementation: `backend/app/api/releases.py`, `backend/app/services/comparison.py`, `frontend/src/ComparisonPanel.tsx`, `frontend/src/App.tsx`

Tests: `backend/tests/test_release_comparison.py`, `frontend/src/workflows.test.tsx`

