"""Tests for release comparison and trending functionality."""

import pytest
import pytest_asyncio
from app.core.database import DatabaseManager
from app.services.comparison import ComparisonService
from .test_api_sessions import client, login


@pytest_asyncio.fixture
async def manager(tmp_path):
    m = DatabaseManager(str(tmp_path / "comparison_test.db"))
    await m.connect()
    await m.init_db()
    yield m
    await m.close()


@pytest.mark.asyncio
async def test_compare_releases(manager):
    async with manager.get_connection() as db:
        from app.services.release_service import ReleaseService
        from app.services.criteria_service import CriteriaService
        from app.services.blocker_service import BlockerService
        svc = ReleaseService(db)
        criteria_svc = CriteriaService(db)
        blocker_svc = BlockerService(db)

        r1 = await svc.create_release(
            {"name": "Alpha", "version": "1.0.0", "description": "First release"},
            "analyst", "reviewer"
        )
        r2 = await svc.create_release(
            {"name": "Beta", "version": "2.0.0", "description": "Second release"},
            "analyst", "reviewer"
        )

        # Add criteria to both
        await criteria_svc.add_criterion({"release_id": r1["id"], "name": "Security", "category": "security", "required": True}, "analyst")
        await criteria_svc.add_criterion({"release_id": r1["id"], "name": "Performance", "category": "performance", "required": True}, "analyst")
        await criteria_svc.add_criterion({"release_id": r2["id"], "name": "Security", "category": "security", "required": True}, "analyst")
        await criteria_svc.add_criterion({"release_id": r2["id"], "name": "Reliability", "category": "reliability", "required": True}, "analyst")

        # Add evidence and pass one criterion in r2
        criteria_r2 = await criteria_svc.list_criteria(r2["id"])
        sec_criterion = criteria_r2[0]
        await criteria_svc.update_criterion(sec_criterion["id"], {"evidence": "Security tests pass"}, "analyst")
        await criteria_svc.review_criterion(sec_criterion["id"], "analyst", "passed", "analyst")

        # Add blockers
        await blocker_svc.create_blocker({"release_id": r1["id"], "title": "Blocker A", "description": "Desc", "severity": "critical"}, "analyst")
        await blocker_svc.create_blocker({"release_id": r2["id"], "title": "Blocker B", "description": "Desc", "severity": "high"}, "analyst")

        comp_svc = ComparisonService(db)
        result = await comp_svc.compare_releases(r1["id"], r2["id"])

        assert result is not None
        assert result["release_a"]["name"] == "Alpha"
        assert result["release_b"]["name"] == "Beta"
        assert len(result["criteria_delta"]) == 3  # Security, Performance, Reliability
        assert len(result["blocker_changes"]) == 2
        assert result["approval_diff"]["release_a"]["total"] == 0
        assert result["approval_diff"]["release_b"]["total"] == 0


@pytest.mark.asyncio
async def test_get_risk_trend(manager):
    async with manager.get_connection() as db:
        from app.services.release_service import ReleaseService
        svc = ReleaseService(db)

        await svc.create_release(
            {"name": "Release 1", "version": "1.0.0", "description": "First"},
            "analyst", "reviewer"
        )
        await svc.create_release(
            {"name": "Release 2", "version": "2.0.0", "description": "Second"},
            "analyst", "reviewer"
        )

        comp_svc = ComparisonService(db)
        trend = await comp_svc.get_risk_trend(10)

        assert len(trend) == 2
        assert "risk_score" in trend[0]
        assert "criteria_pass_rate" in trend[0]
        assert "open_blockers" in trend[0]


def test_api_comparison_endpoints(client):
    login(client, "analyst")
    r1 = client.post("/api/releases/", json={"name": "Gamma", "version": "1.0.0", "description": "Test"}).json()
    r2 = client.post("/api/releases/", json={"name": "Delta", "version": "2.0.0", "description": "Test"}).json()

    # Test list for comparison
    resp = client.get("/api/releases/comparison/list")
    assert resp.status_code == 200
    releases = resp.json()
    assert len(releases) >= 2

    # Test trend
    resp = client.get("/api/releases/comparison/trend?limit=5")
    assert resp.status_code == 200
    trend = resp.json()
    assert isinstance(trend, list)

    # Test compare (GET)
    resp = client.get(f"/api/releases/comparison/compare?a={r1['id']}&b={r2['id']}")
    assert resp.status_code == 200
    comparison = resp.json()
    assert "release_a" in comparison
    assert "release_b" in comparison
    assert "criteria_delta" in comparison
    assert "blocker_changes" in comparison
    assert "approval_diff" in comparison
    assert "risk_delta" in comparison

    # Test compare with non-existent release
    resp = client.get("/api/releases/comparison/compare?a=nonexistent&b=" + r2["id"])
    assert resp.status_code == 404
