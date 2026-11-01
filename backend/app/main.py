import json
import asyncio
import logging
import time
from pathlib import Path
from collections import deque
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
from typing import Optional, List
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app.security import owner, identity, new_identity, allowed_origins, origin_is_allowed, validate_deployment
from app.agent.turns import turn_guard, active
from app.db.repository import create_or_update_session, patch_profile
from app.models.schemas import ProfileUpdate
from app.services.references import crop_reference

from app.config import settings
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
from app.db.database import init_db
from app.db.repository import (
    list_sessions,
    get_session,
    get_session_messages,
    list_advisories,
    get_advisory,
    delete_session,
    delete_advisory
)
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ProgressEvent,
    SessionSummary,
    MessageRecord,
    AdvisorySummary,
    AdvisoryDetail,
    WeatherResponse,
    SoilResponse,
    MandiResponse,
    GeocodeResponse,
    TTSRequest,
    TTSResponse,
    STTResponse
)
from app.services.gemini_pool import key_manager
from app.services.weather import get_weather_forecast, geocode_location
from app.services.soil import get_soil_properties
from app.services.mandi import get_mandi_prices
from app.services.voice import speech_to_text, text_to_speech
from app.services.gemini_live import handle_gemini_live_websocket
from app.agent.tools import load_crops_data, load_schemes_data
from app.agent.orchestrator import run_agent_turn

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite tables on startup
    validate_deployment()
    await init_db()
    yield

app = FastAPI(
    title="SoilMate API",
    description="Multilingual AI Agronomic Advisory & Protective Planning Backend for Indian Farmers",
    version="1.0.0",
    lifespan=lifespan
)

# CORS setup: allows explicit origins, all vercel preview/prod apps, and headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_origin_regex=r"https://.*(\.vercel\.app|\.onrender\.com)",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Soilmate-Owner", "Content-Length", "Content-Type"],
)

request_times = {}

@app.middleware("http")
async def browser_scope(request: Request, call_next):
    # Allow preflight OPTIONS requests to pass through cleanly to CORS middleware
    if request.method == "OPTIONS":
        return await call_next(request)

    if settings.app_mode == "local" and request.client and request.client.host not in {"127.0.0.1", "::1", "localhost", "test", "testclient"}:
        return JSONResponse({"detail": "Local demo accepts loopback clients only"}, status_code=403)

    origin = request.headers.get("origin")
    if origin and not origin_is_allowed(origin):
        return JSONResponse({"detail": "Origin not allowed"}, status_code=403)

    try:
        content_length = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        return JSONResponse({"detail": "Invalid content length"}, status_code=400)
    if content_length > 12 * 1024 * 1024:
        return JSONResponse({"detail": "Upload too large"}, status_code=413)

    if request.method in {"POST", "PATCH", "DELETE"}:
        now = time.monotonic()
        ip = request.client.host if request.client else "unknown"
        for key in list(request_times):
            if not request_times[key] or request_times[key][-1] < now - 60:
                del request_times[key]
        recent = request_times.setdefault(ip, deque())
        while recent and recent[0] < now - 60:
            recent.popleft()
        if len(recent) >= 60 or len(request_times) > 5000:
            return JSONResponse({"detail": "Too many requests; retry in a minute"}, status_code=429)
        recent.append(now)

    owner_raw = request.headers.get("x-soilmate-owner") or request.cookies.get("soilmate_owner")
    who = identity(owner_raw)
    cookie = None
    if not who:
        who, cookie = new_identity()
    token = owner.set(who)
    try:
        response = await call_next(request)
        token_to_send = cookie or owner_raw
        if cookie:
            response.set_cookie(
                "soilmate_owner",
                cookie,
                httponly=True,
                secure=True,
                samesite="none",
                max_age=2592000
            )
        if token_to_send:
            response.headers["X-Soilmate-Owner"] = token_to_send
        return response
    finally:
        owner.reset(token)


async def require_session(session_id):
    if session_id and not await get_session(session_id):
        raise HTTPException(404, "Session not found")


@app.post("/api/sessions", response_model=SessionSummary)
async def new_session():
    return await create_or_update_session()


@app.patch("/api/sessions/{session_id}", response_model=SessionSummary)
async def edit_profile(session_id: str, req: ProfileUpdate):
    await require_session(session_id)
    if (owner.get(), session_id) in active:
        raise HTTPException(409, "End the current conversation before editing the profile")
    values = req.model_dump(exclude_unset=True)
    if "location_name" in values and not {"latitude", "longitude"}.issubset(values):
        loc = await geocode_location(values["location_name"]) if values["location_name"] else None
        if values["location_name"] and not loc:
            raise HTTPException(422, "Location could not be resolved. Enter coordinates or use a more specific place name.")
        values.update(latitude=loc["lat"] if loc else None, longitude=loc["lon"] if loc else None, state=loc.get("state") if loc else None)
    if (values.get("latitude") is None) != (values.get("longitude") is None):
        raise HTTPException(422, "Supply latitude and longitude together")
    return await patch_profile(session_id, values)


# ==========================================
# SYSTEM & HEALTH
# ==========================================

@app.get("/api/health")
async def health_check():
    """Verify backend health, database connection, and API key configurations."""
    return {
        "status": "ok",
        "service": "SoilMate Agritech Engine",
        "gemini_pool": {
            "total_keys": key_manager.total_keys,
            "has_active_key": key_manager.get_active_key() is not None
        },
        "sarvam_configured": bool(settings.sarvam_api_key),
        "data_gov_configured": bool(settings.data_gov_api_key)
    }

# ==========================================
# CHAT & STREAMING (RE-ACT AGENT)
# ==========================================

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """
    Synchronous turn with SoilMate ReAct Agent:
    Translates Indic query to English, autonomously calls tools, records trace,
    and returns localized response + TTS voice audio.
    """
    await require_session(req.session_id)
    async with turn_guard(req.session_id, req.request_id):
        try:
            return await asyncio.wait_for(run_agent_turn(message=req.message, session_id=req.session_id, language_hint=req.language, location=req.location, voice_output=req.voice_output), 150)
        except asyncio.TimeoutError:
            raise HTTPException(504, "Analysis timed out. Review history before retrying.")
        except Exception:
            raise HTTPException(502, "Analysis could not be completed. Please retry later.")

@app.post("/api/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    """
    Server-Sent Events (SSE) streaming endpoint:
    Streams live progress notifications (e.g. 'Fetching live weather for Jaipur...',
    'Analyzing SoilGrids...', 'Translating to Telugu...') followed by the final completion event.
    """
    await require_session(req.session_id)
    guard = turn_guard(req.session_id, req.request_id)
    await guard.__aenter__()
    queue = asyncio.Queue(maxsize=64)
    async def on_progress(event):
        if event.type != "complete":
            await queue.put(event)
    async def event_generator():
        task = asyncio.create_task(asyncio.wait_for(run_agent_turn(message=req.message, session_id=req.session_id, language_hint=req.language, location=req.location, voice_output=req.voice_output, progress_callback=on_progress), 150))
        try:
            while not task.done() or not queue.empty():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1)
                    yield f"event: progress\ndata: {json.dumps(event.model_dump())}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
            result = task.result()
            yield f"event: complete\ndata: {json.dumps(result.model_dump())}\n\n"
        except Exception:
            yield 'event: error\ndata: {"message":"Analysis failed or timed out. Review history before retrying."}\n\n'
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await guard.__aexit__(None, None, None)
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ==========================================
# GEMINI MULTIMODAL LIVE WEBSOCKET
# ==========================================

@app.websocket("/api/ws/live")
@app.websocket("/ws/live")
async def gemini_live_endpoint(websocket: WebSocket):
    """
    Direct Gemini Multimodal Live WebSocket endpoint.
    Streams 16kHz PCM audio bidirectionally with sub-second latency,
    native emotional voice synthesis, real-time barge-in, and autonomous tool calling.
    """
    origin = websocket.headers.get("origin")
    if origin and not origin_is_allowed(origin):
        logger.warning(f"[GeminiLive] Origin {origin} rejected")
        await websocket.close(code=1008)
        return

    # Extract owner from query param, header, or cookie
    owner_token = (
        websocket.query_params.get("owner") or
        websocket.headers.get("x-soilmate-owner") or
        websocket.cookies.get("soilmate_owner")
    )
    who = identity(owner_token)
    if not who:
        who, _ = new_identity()

    token = owner.set(who)
    try:
        await handle_gemini_live_websocket(websocket)
    finally:
        owner.reset(token)


# ==========================================
# HISTORY & SESSIONS
# ==========================================

@app.get("/api/sessions", response_model=List[SessionSummary])
async def get_sessions(limit: int = Query(50, ge=1, le=100)):
    """List recent conversation sessions."""
    sessions = await list_sessions(limit=limit)
    return [SessionSummary(**s) for s in sessions]

@app.get("/api/sessions/{session_id}", response_model=SessionSummary)
async def get_session_by_id(session_id: str):
    """Retrieve session metadata and persistent farmer profile by ID."""
    sess = await get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionSummary(**sess)

@app.get("/api/chat/history/{session_id}", response_model=List[MessageRecord])
async def get_chat_history(session_id: str):
    """Retrieve full chronological chat history with tool execution traces."""
    await require_session(session_id)
    msgs = await get_session_messages(session_id)
    return [MessageRecord(**m) for m in msgs]

@app.delete("/api/sessions/{session_id}")
async def remove_session(session_id: str):
    """Delete a conversation session, cascading to its messages and related advisories."""
    if (owner.get(), session_id) in active:
        raise HTTPException(409, "End the current conversation before deleting it")
    success = await delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "success", "message": f"Session {session_id} deleted successfully"}

# ==========================================
# CROP ADVISORIES & SCHEDULES
# ==========================================

@app.get("/api/advisories", response_model=List[AdvisorySummary])
async def get_advisories(
    session_id: Optional[str] = None,
    crop: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100)
):
    """List saved crop protective advisories and planting schedules."""
    advs = await list_advisories(session_id=session_id, crop_name=crop, limit=limit)
    return [AdvisorySummary(**a) for a in advs]

@app.get("/api/calendars", response_model=List[AdvisoryDetail])
async def get_calendars(limit: int = Query(50, ge=1, le=100)):
    """List saved agent-generated calendars, newest first, for the current owner."""
    return await list_advisories(limit=limit, calendars_only=True)


@app.get("/api/advisories/{advisory_id}", response_model=AdvisoryDetail)
async def get_advisory_by_id(advisory_id: str):
    """Retrieve a specific crop advisory with complete schedules and metrics."""
    adv = await get_advisory(advisory_id)
    if not adv:
        raise HTTPException(status_code=404, detail="Advisory not found")
    return AdvisoryDetail(**adv)

@app.delete("/api/advisories/{advisory_id}")
async def remove_advisory(advisory_id: str):
    """Delete a specific crop advisory."""
    success = await delete_advisory(advisory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Advisory not found")
    return {"status": "success", "message": f"Advisory {advisory_id} deleted successfully"}


# ==========================================
# VOICE & MULTILINGUAL UTILITIES
# ==========================================

@app.post("/api/voice/stt", response_model=STTResponse)
async def stt_endpoint(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None)
):
    """Transcribe speech audio file to text."""
    audio_bytes = await file.read(10 * 1024 * 1024 + 1)
    if len(audio_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, "Audio must be under 10 MB")
    res = await speech_to_text(audio_bytes, filename=file.filename or "audio.wav", language_hint=language)
    if "error" in res and not res.get("text"):
        raise HTTPException(status_code=502, detail=res["error"])
    return STTResponse(**res)

@app.post("/api/voice/tts", response_model=TTSResponse)
async def tts_endpoint(req: TTSRequest):
    """Synthesize text into target Indian language voice audio."""
    audio_b64 = await text_to_speech(req.text, language=req.language)
    if not audio_b64:
        return TTSResponse(audio_base64=None, error="TTS synthesis failed or key not configured")
    return TTSResponse(audio_base64=audio_b64)

# ==========================================
# DIRECT DATA INSPECTION ENDPOINTS
# ==========================================

@app.get("/api/weather", response_model=WeatherResponse)
async def weather_endpoint(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)):
    """Get live 7-day agricultural weather forecast and alerts."""
    try:
        data = await get_weather_forecast(lat, lon)
        return WeatherResponse(**data)
    except Exception:
        logger.exception("Open-Meteo query failed")
        raise HTTPException(status_code=502, detail="Weather provider is unavailable or returned invalid data")

@app.get("/api/soil", response_model=SoilResponse)
async def soil_endpoint(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)):
    """Get live SoilGrids physical and chemical soil properties."""
    try:
        data = await get_soil_properties(lat, lon)
        if data.get("error"):
            return JSONResponse(data, status_code=503)
        return SoilResponse(**data)
    except Exception:
        logger.exception("SoilGrids query failed")
        raise HTTPException(status_code=502, detail="Soil provider is unavailable or returned invalid data")

@app.get("/api/mandi", response_model=MandiResponse)
async def mandi_endpoint(state: str = Query(""), commodity: str = Query(...)):
    """Get live APMC mandi commodity prices from Agmarknet."""
    try:
        data = await get_mandi_prices(state, commodity)
        return MandiResponse(**data)
    except Exception:
        logger.exception("Mandi price fetch failed")
        raise HTTPException(status_code=502, detail="Mandi provider is unavailable or returned invalid data")

@app.get("/api/geocode", response_model=GeocodeResponse)
async def geocode_endpoint(query: str = Query(...)):
    """Search place coordinates via Open-Meteo Geocoding."""
    loc = await geocode_location(query)
    if not loc:
        raise HTTPException(status_code=404, detail=f"Location '{query}' not found")
    return GeocodeResponse(**loc)

@app.get("/api/crops")
async def crops_catalog(crop: str = ""):
    return await crop_reference(crop)

@app.get("/api/schemes")
async def schemes_catalog():
    return {"status": "unavailable", "schemes": [], "total": 0, "note": "Live eligibility verification is not connected.", "source": "https://www.myscheme.gov.in/"}


# ============================================================================
# SINGLE-SERVICE HOSTING (Render Web Service / Docker / Production)
# Serves the compiled Vite React frontend alongside FastAPI on a single domain.
# ============================================================================
frontend_dist = None
for candidate in [
    Path(__file__).resolve().parents[2] / "frontend" / "dist",
    Path("/app/frontend/dist"),
    Path(__file__).resolve().parents[1] / "frontend" / "dist",
    Path.cwd() / "frontend" / "dist",
    Path.cwd() / "dist",
]:
    if candidate.is_dir() and (candidate / "index.html").is_file():
        frontend_dist = candidate
        break

if frontend_dist:
    logger.info("Serving built SoilMate frontend from %s", frontend_dist)
    assets_dir = frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_html = frontend_dist / "index.html"

    # Catch-all route for Single-Page Application (SPA) client-side routing
    @app.get("/{full_path:path}")
    async def serve_spa_app(full_path: str):
        # Do not catch backend API routes or documentation
        if full_path.startswith("api/") or full_path in {"docs", "redoc", "openapi.json"}:
            raise HTTPException(status_code=404, detail="Not Found")

        # If a specific static asset was requested from root (e.g. favicon.svg, vite.svg, manifest.json)
        asset_file = (frontend_dist / full_path).resolve()
        if str(asset_file).startswith(str(frontend_dist.resolve())) and asset_file.is_file():
            return FileResponse(asset_file)

        # Fallback to index.html for all SPA routes (e.g. /, /advisories, /calendar, etc.)
        return FileResponse(index_html)
