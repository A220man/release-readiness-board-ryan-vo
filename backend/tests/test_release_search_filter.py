"""Tests for release search and status filtering functionality."""

import pytest
import pytest_asyncio
from app.core.database import DatabaseManager
from app.services.release_service import ReleaseService
from .test_api_sessions import client, login


@pytest_asyncio.fixture
async def manager(tmp_path):
    m = DatabaseManager(str(tmp_path / "filter_test.db"))
    await m.connect()
    await m.init_db()
    yield m
    await m.close()


@pytest.mark.asyncio
async def test_list_releases_status_filtering(manager):
    async with manager.get_connection() as db:
        svc = ReleaseService(db)
        r1 = await svc.create_release({"name": "Draft App", "version": "1.0.0"}, "analyst", "operator")
        r2 = await svc.create_release({"name": "Review App", "version": "2.0.0"}, "analyst", "operator")
        await svc.transition_release(r2["id"], "in_review", "analyst", "operator")

        # Filter by draft
        drafts, total_drafts = await svc.list_releases(status_filter="draft")
        assert total_drafts == 1
        assert len(drafts) == 1
        assert drafts[0]["id"] == r1["id"]

        # Filter by in_review
        reviews, total_reviews = await svc.list_releases(status_filter="in_review")
        assert total_reviews == 1
        assert len(reviews) == 1
        assert reviews[0]["id"] == r2["id"]

        # Filter by non-existent status
        empty, total_empty = await svc.list_releases(status_filter="released")
        assert total_empty == 0
        assert len(empty) == 0


@pytest.mark.asyncio
async def test_list_releases_search_query(manager):
    async with manager.get_connection() as db:
        svc = ReleaseService(db)
        await svc.create_release(
            {"name": "Payments Gateway", "version": "1.0.0", "description": "Core transaction processing"},
            "analyst",
            "operator",
        )
        await svc.create_release(
            {"name": "User Auth Service", "version": "2.0.0", "description": "Identity and session tokens"},
            "analyst",
            "operator",
        )

        # Search by name substring
        results, total = await svc.list_releases(search="Payments")
        assert total == 1
        assert results[0]["name"] == "Payments Gateway"

        # Search by description substring
        results, total = await svc.list_releases(search="tokens")
        assert total == 1
        assert results[0]["name"] == "User Auth Service"

        # Non-matching search
        results, total = await svc.list_releases(search="NonExistentModule")
        assert total == 0
        assert len(results) == 0


@pytest.mark.asyncio
async def test_list_releases_combined_filter_and_search(manager):
    async with manager.get_connection() as db:
        svc = ReleaseService(db)
        r1 = await svc.create_release({"name": "Core Engine", "version": "1.0.0"}, "analyst", "operator")
        r2 = await svc.create_release({"name": "Core Database", "version": "1.1.0"}, "analyst", "operator")
        await svc.transition_release(r2["id"], "in_review", "analyst", "operator")

        # Search 'Core' with status 'draft'
        results, total = await svc.list_releases(status_filter="draft", search="Core")
        assert total == 1
        assert results[0]["id"] == r1["id"]

        # Search 'Core' with status 'in_review'
        results, total = await svc.list_releases(status_filter="in_review", search="Core")
        assert total == 1
        assert results[0]["id"] == r2["id"]

        # Search 'Engine' with status 'in_review' (mismatch)
        results, total = await svc.list_releases(status_filter="in_review", search="Engine")
        assert total == 0
        assert len(results) == 0


def test_api_release_search_and_filter_endpoint(client):
    login(client, "analyst")
    client.post("/api/releases/", json={"name": "Alpha Service", "version": "1.0.0", "description": "Microservice A"})
    r2 = client.post("/api/releases/", json={"name": "Beta Pipeline", "version": "1.0.0", "description": "ETL worker"}).json()
    client.post(f"/api/releases/{r2['id']}/transition", json={"status": "in_review"})

    # Query with status filter
    resp = client.get("/api/releases/?status=in_review")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Beta Pipeline"

    # Query with search query
    resp = client.get("/api/releases/?search=Alpha")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Alpha Service"

    # Combined query with zero match
    resp = client.get("/api/releases/?status=draft&search=Beta")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
