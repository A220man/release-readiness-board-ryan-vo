# Changelog

## 1.2.0 — work-in-progress checkpoint

Partial code published for continued development. Known issues: STATUS.md.

## 1.1.0 — 2026-10-15

- Add in-app release notes preview modal for reviewing generated notes before export or release.
- Fetch and render structured release notes including criteria, blockers, approvals, and risk assessment.
- Add "Preview release notes" button to Insights panel with modal overlay and loading state.

- Add interactive release search and lifecycle status filtering to the workspace dashboard.
- Support keyword queries across release names and descriptions with reactive filter reset.
- Filter releases by lifecycle status (`draft`, `in_review`, `approved`, `released`, `cancelled`) with filter-aware pagination and empty states.
- Optimize criteria and blocker summary querying in backend release retrieval.
- Add comprehensive backend and frontend test suites for search, status filtering, and query combinations.

## [1.0.0] - 2026-10-09

- Track release criteria, reviewed evidence, blockers, owners, and risk acceptance.
- Require independent approval of the current evidence revision before approval or release.
- Freeze approved and released evidence; return approved releases to review before editing.
- Commit mutations, snapshots, and audit entries together; reject stale approval evidence.
- Provide deterministic risk diagnostics, keyword classification, bounded optional model advice, and JSON/Markdown/CSV exports.
- Add OIDC PKCE login with opaque cookie sessions, CSRF protection, role checks and local-only demo mode.
- Package the FastAPI backend and React/TypeScript frontend with Docker and CI.