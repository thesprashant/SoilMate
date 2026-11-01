import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "gemini_pool" in data

@pytest.mark.asyncio
async def test_crops_catalog_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/crops?season=rabi")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"
        assert "supported_crops" in data

@pytest.mark.asyncio
async def test_schemes_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/schemes?query=kisan")
        assert resp.status_code == 200
        data = resp.json()
        assert "schemes" in data
        assert data["status"] == "unavailable"
        assert data["schemes"] == []

@pytest.mark.asyncio
async def test_sessions_and_history_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

@pytest.mark.asyncio
async def test_delete_endpoints():
    from app.db.repository import create_or_update_session, save_advisory
    sess = await create_or_update_session(language="hi", location_name="Rohtak")
    sid = sess["id"]
    adv = await save_advisory(crop_name="Mustard", language="hi", full_advisory_text="सरसों की खेती सलाह", session_id=sid)
    adv_id = adv["id"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Delete advisory
        del_adv = await client.delete(f"/api/advisories/{adv_id}")
        assert del_adv.status_code == 200
        assert del_adv.json()["status"] == "success"

        # Delete session
        del_sess = await client.delete(f"/api/sessions/{sid}")
        assert del_sess.status_code == 200
        assert del_sess.json()["status"] == "success"


