import asyncio
import json
from unittest.mock import AsyncMock
import httpx
import pytest
from fastapi import HTTPException
from app.main import app, chat_stream_endpoint
from app.models.schemas import ChatRequest, ChatResponse
from app.db.repository import create_or_update_session, get_session, get_advisory, get_session_messages, delete_session, list_sessions, save_message
from app.agent.advisories import validate_schedule, persist_advice
from app.agent.turns import active, turn_guard
from app.security import owner
from app.config import settings
from app.services import soil


def reference():
    return {"tool": "query_crop_database", "inputs": {"crop": "wheat"}, "outputs": {
        "crop": "wheat", "source": "https://agritech.tnau.ac.in/test", "retrieved_at": "2026-11-01T00:00:00Z",
        "reference_text": "Irrigate immediately after sowing and at 20 days.", "coverage": "Regional reference"}}


def schedule():
    return {"crop": "wheat", "entries": [{"stage": "irrigation", "source": reference()["outputs"]["source"],
        "quote": reference()["outputs"]["reference_text"], "guidance": "Irrigate at 20 days."}]}


def test_schedule_rejects_fabricated_evidence_and_numbers():
    assert validate_schedule(schedule(), [reference()])["status"] == "success"
    wrong = schedule(); wrong["entries"][0]["guidance"] = "Irrigate at 30 days."
    assert "error" in validate_schedule(wrong, [reference()])
    wrong = schedule(); wrong["entries"][0]["source"] = "https://example.com"
    assert "error" in validate_schedule(wrong, [reference()])
    assert "error" in validate_schedule(schedule(), [])


def test_calendar_dates_require_user_anchor_and_source_interval():
    plan = schedule()
    plan["sowing_date"] = "2026-11-01"
    plan["entries"][0]["days_after_sowing"] = 20
    refs = [reference()]
    refs[0]["outputs"]["reference_text"] = "Irrigate 20 days after sowing."
    plan["entries"][0]["quote"] = refs[0]["outputs"]["reference_text"]
    assert validate_schedule(plan, refs, "I sowed on 01/11/2026")["entries"][0]["date"] == "2026-11-21"
    assert "date" not in validate_schedule(plan, refs, "I grow wheat")["entries"][0]
    plan["entries"][0]["days_after_sowing"] = 30
    assert "date" not in validate_schedule(plan, refs, "2026-11-01")["entries"][0]


def test_calendar_keeps_supported_entries_when_other_quotes_are_invalid():
    source = "https://agritech.tnau.ac.in/horticulture/horti_vegetables_potato.html"
    quote = "Irrigate the crop 10 days after planting."
    refs = [{"tool": "query_crop_database", "outputs": {"crop": "potato", "source": source,
             "reference_text": quote + " Take up the first hoeing on 45th day.", "retrieved_at": "2026-11-01", "coverage": "regional"}}]
    plan = {"crop": "potato", "sowing_date": "2026-11-01", "entries": [
        {"stage": "sowing", "quote": "Prepare the land to fine tilth.", "guidance": "Prepare the land.", "source": source},
        {"stage": "irrigation", "quote": quote, "guidance": "Irrigate 10 days after planting.", "source": source},
        {"stage": "irrigation", "quote": "Take up the first hoeing on 45th day.", "guidance": "Hoe on day 45.", "source": source},
    ]}
    result = validate_schedule(plan, refs, "I planted on 2026-11-01")
    assert result["status"] == "partial" and result["rejected_count"] == 2
    assert len(result["entries"]) == 1 and result["entries"][0]["date"] == "2026-11-11"


def test_wheat_irrigation_rows_use_their_source_heading_and_keep_ranges():
    source = "https://agritech.tnau.ac.in/agriculture/agri_irrigationmgt_wheat.html"
    quote = "II – Crown root intiation : 15-20 DAS"
    ref = {"tool": "query_crop_database", "outputs": {"crop": "wheat", "source": source,
           "reference_text": "Wheat crop requires minimum of 5 irrigations at the following critical stages. " + quote + " Crown root initiation and flowering are the most critical stages.",
           "retrieved_at": "2026-11-01", "coverage": "regional"}}
    plan = {"crop": "wheat", "sowing_date": "2026-11-01", "entries": [
        {"stage": "irrigation", "quote": quote, "guidance": "Irrigate 15-20 days after sowing.", "source": source}]}
    relative = validate_schedule(plan, [ref], "No sowing date yet")
    assert relative["status"] == "success"
    assert relative["entries"][0]["days_after_sowing_end"] == 20
    assert "date" not in relative["entries"][0]
    dated = validate_schedule(plan, [ref], "Sowing date 2026-11-01")
    assert dated["entries"][0]["date"] == "2026-11-16"
    assert dated["entries"][0]["date_end"] == "2026-11-21"


@pytest.mark.asyncio
async def test_advisory_message_schedule_round_trip():
    sess = await create_or_update_session(primary_crop="wheat")
    refs = [reference(), {"tool": "record_crop_schedule", "outputs": validate_schedule(schedule(), [reference()])}]
    aid = await persist_advice(sess["id"], "en", "Check the regional guidance.", sess, refs)
    await save_message(sess["id"], "assistant", "Check guidance", "en", advisory_id=aid, tool_calls=refs)
    adv = await get_advisory(aid)
    assert adv["irrigation_schedule"][0]["quote"] == reference()["outputs"]["reference_text"]
    assert adv["sowing_window"] is None
    assert adv["evidence"]["tools"] == refs
    assert (await get_session_messages(sess["id"]))[0]["advisory_id"] == aid


@pytest.mark.asyncio
async def test_calendar_list_ignores_newer_noncalendar_advice():
    sess = await create_or_update_session(primary_crop="wheat")
    refs = [reference(), {"tool": "record_crop_schedule", "outputs": validate_schedule(schedule(), [reference()])}]
    calendar_id = await persist_advice(sess["id"], "en", "Schedule", sess, refs)
    await persist_advice(sess["id"], "en", "Weather", sess, [{"tool": "get_weather", "outputs": {}}])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        result = await client.get("/api/calendars?limit=1")
    assert result.status_code == 200
    assert result.json()[0]["id"] == calendar_id
    assert result.json()[0]["evidence"]["schedule"][0]["stage"] == "irrigation"


@pytest.mark.asyncio
async def test_reference_without_schedule_does_not_generate_navigation_tasks():
    sess = await create_or_update_session(primary_crop="wheat")
    refs = [reference()]
    refs[0]["outputs"]["reference_text"] = "Sowing should be done after preparing the field. Irrigate 20 days after sowing."
    aid = await persist_advice(sess["id"], "en", "Here is your crop plan.", sess, refs, user_text="Please make a wheat calendar")
    assert (await get_advisory(aid))["evidence"]["schedule"] == []


@pytest.mark.asyncio
async def test_schedule_resolves_reference_from_session_history(monkeypatch):
    from app.agent import advisories
    fetch = AsyncMock(side_effect=AssertionError("history should be reused"))
    monkeypatch.setattr(advisories, "crop_reference", fetch)
    refs = await advisories.schedule_references({"crop": "wheat"}, [], [{"role": "assistant", "tool_calls": [reference()]}])
    assert validate_schedule(schedule(), refs)["status"] == "success"
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_schedule_fetches_reference_when_missing(monkeypatch):
    from app.agent import advisories
    fetch = AsyncMock(return_value=reference()["outputs"])
    monkeypatch.setattr(advisories, "crop_reference", fetch)
    refs = await advisories.schedule_references({"crop": "wheat"}, [], [])
    assert validate_schedule(schedule(), refs)["status"] == "success"
    fetch.assert_awaited_once_with(crop="wheat")


@pytest.mark.asyncio
async def test_other_browser_cannot_read_or_delete_records():
    token = owner.set("browser-a")
    sess = await create_or_update_session()
    aid = await persist_advice(sess["id"], "en", "Reference", sess, [reference()])
    owner.set("browser-b")
    assert await get_session(sess["id"]) is None
    assert await get_advisory(aid) is None
    assert await get_session_messages(sess["id"]) == []
    assert await list_sessions() == []
    assert not await delete_session(sess["id"])
    with pytest.raises(PermissionError):
        await create_or_update_session(session_id=sess["id"])
    owner.reset(token)


@pytest.mark.asyncio
async def test_profile_edits_validate_and_allow_clearing():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as c:
        sid = (await c.post("/api/sessions")).json()["id"]
        assert (await c.patch(f"/api/sessions/{sid}", json={"latitude": 100, "longitude": 20})).status_code == 422
        result = await c.patch(f"/api/sessions/{sid}", json={"location_name": "Test field", "latitude": 0, "longitude": 0, "primary_crop": "wheat"})
        assert result.json()["latitude"] == 0
        result = await c.patch(f"/api/sessions/{sid}", json={"primary_crop": None})
        assert result.json()["primary_crop"] is None


@pytest.mark.asyncio
async def test_duplicate_turns_never_execute_twice():
    async with turn_guard("session", "request-123"):
        with pytest.raises(HTTPException):
            async with turn_guard("session", "request-456"):
                pass
    assert not active
    with pytest.raises(HTTPException):
        async with turn_guard("session", "request-123"):
            pass


@pytest.mark.asyncio
async def test_stream_completion_and_error(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "run_agent_turn", AsyncMock(return_value=ChatResponse(session_id="s", response="Done", language="en")))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as c:
        result = await c.post("/api/chat/stream", json={"message": "hello", "request_id": "request-123"})
        assert "event: complete" in result.text
        assert (await c.post("/api/chat/stream", json={"message": "hello", "request_id": "request-123"})).status_code == 409
        monkeypatch.setattr(main, "run_agent_turn", AsyncMock(side_effect=RuntimeError("private-provider-error")))
        result = await c.post("/api/chat/stream", json={"message": "hello"})
        assert "event: error" in result.text
        assert "private-provider-error" not in result.text
    assert not active


@pytest.mark.asyncio
async def test_stream_disconnect_cancels_agent_and_releases_turn(monkeypatch):
    import app.main as main
    cancelled = asyncio.Event()
    async def run(**kwargs):
        try:
            from app.models.schemas import ProgressEvent
            await kwargs["progress_callback"](ProgressEvent(type="thinking", message="Working"))
            await asyncio.Future()
        finally:
            cancelled.set()
    monkeypatch.setattr(main, "run_agent_turn", run)
    response = await chat_stream_endpoint(ChatRequest(message="test"))
    await anext(response.body_iterator)
    await response.body_iterator.aclose()
    assert cancelled.is_set()
    assert not active


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [True, False])
async def test_soil_missing_data_is_never_fabricated(monkeypatch, fail):
    response = httpx.Response(200, json={"properties": {"layers": []}}, request=httpx.Request("GET", "https://test"))
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get = AsyncMock(side_effect=httpx.ConnectError("offline")) if fail else AsyncMock(return_value=response)
    monkeypatch.setattr(soil.httpx, "AsyncClient", lambda **kw: client)
    data = await soil.get_soil_properties(20, 70)
    assert data["status"] == "unavailable"
    assert "ph" not in data and "nitrogen_g_kg" not in data


@pytest.mark.asyncio
async def test_origins_and_hosted_cookie_isolation(monkeypatch):
    monkeypatch.setattr(settings, "app_mode", "hosted")
    monkeypatch.setattr(settings, "session_secret", "test-only-secret-" * 4)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://test") as a, httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://test") as b:
        assert (await a.post("/api/sessions", headers={"Origin": "https://evil.example"})).status_code == 403
        sid = (await a.post("/api/sessions")).json()["id"]
        assert (await a.get(f"/api/sessions/{sid}")).status_code == 200
        assert (await b.get(f"/api/sessions/{sid}")).status_code == 404
        assert (await b.delete(f"/api/sessions/{sid}")).status_code == 404


@pytest.mark.asyncio
async def test_typed_agent_saves_validated_schedule_and_history(monkeypatch):
    from google.genai import types
    from types import SimpleNamespace
    from app.agent import orchestrator
    def response(part):
        return SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(role="model", parts=[part]))])
    replies = [
        response(types.Part.from_function_call(name="query_crop_database", args={"crop": "wheat"})),
        response(types.Part.from_function_call(name="record_crop_schedule", args=schedule())),
        response(types.Part.from_text(text="Review the cited regional irrigation reference.")),
    ]
    monkeypatch.setattr(orchestrator.key_manager, "generate_with_fallback", AsyncMock(side_effect=replies))
    monkeypatch.setattr(orchestrator, "execute_tool", AsyncMock(return_value=reference()["outputs"]))
    result = await orchestrator.run_agent_turn("Give me the wheat reference schedule", language_hint="en", voice_output=False)
    assert result.advisory_id
    assert [t.tool for t in result.tool_calls] == ["query_crop_database", "record_crop_schedule"]
    assert (await get_advisory(result.advisory_id))["evidence"]["schedule"][0]["stage"] == "irrigation"
    assert (await get_session_messages(result.session_id))[-1]["advisory_id"] == result.advisory_id
