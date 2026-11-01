import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from app.db.database import get_db_connection
from app.security import owner

def generate_id(prefix: str = "") -> str:
    """Generate a unique ID with an optional prefix."""
    raw = uuid.uuid4().hex[:12]
    return f"{prefix}_{raw}" if prefix else raw

# ==========================================
# SESSION OPERATIONS
# ==========================================

async def create_or_update_session(
    session_id: Optional[str] = None,
    language: Optional[str] = "hi",
    location_name: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    state: Optional[str] = None,
    district: Optional[str] = None,
    land_size_acres: Optional[float] = None,
    primary_crop: Optional[str] = None,
    soil_type: Optional[str] = None,
    profile_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a new session or update existing session metadata and farmer profile."""
    sid = session_id or generate_id("sess")
    now = datetime.now(timezone.utc).isoformat()
    prof_json = json.dumps(profile_data) if profile_data else None
    
    conn = await get_db_connection()
    try:
        # Check if session exists
        cursor = await conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,))
        existing = await cursor.fetchone()
        
        if existing and existing["owner_id"] != owner.get():
            raise PermissionError("Session not found")
        if existing:
            await conn.execute(
                """
                UPDATE sessions 
                SET language = COALESCE(?, language),
                    location_name = COALESCE(?, location_name),
                    latitude = COALESCE(?, latitude),
                    longitude = COALESCE(?, longitude),
                    state = COALESCE(?, state),
                    district = COALESCE(?, district),
                    land_size_acres = COALESCE(?, land_size_acres),
                    primary_crop = COALESCE(?, primary_crop),
                    soil_type = COALESCE(?, soil_type),
                    profile_data = COALESCE(?, profile_data),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    language, location_name, latitude, longitude,
                    state, district, land_size_acres, primary_crop,
                    soil_type, prof_json, now, sid
                )
            )
        else:
            await conn.execute(
                """
                INSERT INTO sessions (
                    id, language, location_name, latitude, longitude,
                    state, district, land_size_acres, primary_crop, soil_type,
                    profile_data, created_at, updated_at, owner_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid, language or "hi", location_name, latitude, longitude,
                    state, district, land_size_acres, primary_crop, soil_type,
                    prof_json, now, now, owner.get()
                )
            )
        await conn.commit()
        
        cursor = await conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,))
        row = await cursor.fetchone()
        return dict(row) if row else {}
    finally:
        await conn.close()

async def update_session_profile(
    session_id: str,
    location_name: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    state: Optional[str] = None,
    district: Optional[str] = None,
    land_size_acres: Optional[float] = None,
    primary_crop: Optional[str] = None,
    soil_type: Optional[str] = None,
    profile_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Persistently update farmer profile attributes for an existing session."""
    return await create_or_update_session(
        session_id=session_id,
        language=None,
        location_name=location_name,
        latitude=latitude,
        longitude=longitude,
        state=state,
        district=district,
        land_size_acres=land_size_acres,
        primary_crop=primary_crop,
        soil_type=soil_type,
        profile_data=profile_data
    )

async def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single session by ID."""
    conn = await get_db_connection()
    try:
        cursor = await conn.execute("SELECT * FROM sessions WHERE id = ? AND owner_id = ?", (session_id, owner.get()))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await conn.close()

async def list_sessions(limit: int = 50) -> List[Dict[str, Any]]:
    """List recent sessions ordered by last updated."""
    conn = await get_db_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM sessions WHERE owner_id = ? ORDER BY updated_at DESC LIMIT ?",
            (owner.get(), limit)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await conn.close()

# ==========================================
# MESSAGE OPERATIONS
# ==========================================

async def save_message(
    session_id: str,
    role: str,
    content: str,
    language: str,
    content_english: Optional[str] = None,
    audio_url: Optional[str] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    advisory_id: Optional[str] = None
) -> Dict[str, Any]:
    """Persist a chat message with tool execution trace."""
    if not await get_session(session_id):
        raise PermissionError("Session not found")
    msg_id = generate_id("msg")
    tool_calls_json = json.dumps(tool_calls) if tool_calls else None
    now = datetime.now(timezone.utc).isoformat()

    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            INSERT INTO messages (id, session_id, role, content, content_english, language, audio_url, tool_calls, created_at, advisory_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (msg_id, session_id, role, content, content_english, language, audio_url, tool_calls_json, now, advisory_id)
        )
        # Update session timestamp
        await conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        await conn.commit()

        return {
            "id": msg_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "content_english": content_english,
            "language": language,
            "audio_url": audio_url,
            "tool_calls": tool_calls or [],
            "created_at": now
        }
    finally:
        await conn.close()

async def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    """Retrieve full chronological conversation history for a session."""
    if not await get_session(session_id):
        return []
    conn = await get_db_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,)
        )
        rows = await cursor.fetchall()
        messages = []
        for r in rows:
            m = dict(r)
            if m.get("tool_calls"):
                try:
                    m["tool_calls"] = json.loads(m["tool_calls"])
                except Exception:
                    m["tool_calls"] = []
            else:
                m["tool_calls"] = []
            messages.append(m)
        return messages
    finally:
        await conn.close()

# ==========================================
# ADVISORY OPERATIONS
# ==========================================

async def save_advisory(
    crop_name: str,
    language: str,
    full_advisory_text: str,
    session_id: Optional[str] = None,
    crop_name_local: Optional[str] = None,
    season: Optional[str] = None,
    location_name: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    sowing_window: Optional[str] = None,
    harvesting_window: Optional[str] = None,
    irrigation_schedule: Optional[Any] = None,
    fertilizer_schedule: Optional[Any] = None,
    protective_alerts: Optional[Any] = None,
    soil_metrics: Optional[Any] = None,
    weather_summary: Optional[Any] = None,
    market_summary: Optional[Any] = None,
    evidence: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Persist structured crop protective advisory and schedules."""
    if not session_id or not await get_session(session_id):
        raise PermissionError("Session not found")
    adv_id = generate_id("adv")
    now = datetime.now(timezone.utc).isoformat()

    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            INSERT INTO advisories (
                id, session_id, crop_name, crop_name_local, language, season,
                location_name, latitude, longitude, sowing_window, harvesting_window,
                irrigation_schedule, fertilizer_schedule, protective_alerts,
                soil_metrics, weather_summary, market_summary, full_advisory_text, created_at, evidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                adv_id, session_id, crop_name, crop_name_local, language, season,
                location_name, latitude, longitude, sowing_window, harvesting_window,
                json.dumps(irrigation_schedule) if irrigation_schedule else None,
                json.dumps(fertilizer_schedule) if fertilizer_schedule else None,
                json.dumps(protective_alerts) if protective_alerts else None,
                json.dumps(soil_metrics) if soil_metrics else None,
                json.dumps(weather_summary) if weather_summary else None,
                json.dumps(market_summary) if market_summary else None,
                full_advisory_text,
                now, json.dumps(evidence or {})
            )
        )
        await conn.commit()
        return await get_advisory(adv_id) or {}
    finally:
        await conn.close()

async def list_advisories(session_id: Optional[str] = None, crop_name: Optional[str] = None, limit: int = 50, calendars_only: bool = False) -> List[Dict[str, Any]]:
    """List saved advisories with optional filtering."""
    conn = await get_db_connection()
    try:
        query = "SELECT * FROM advisories WHERE session_id IN (SELECT id FROM sessions WHERE owner_id = ?)"
        params: List[Any] = [owner.get()]
        if calendars_only:
            query += " AND json_valid(evidence) AND json_array_length(json_extract(evidence, '$.schedule')) > 0"
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        if crop_name:
            query += " AND LOWER(crop_name) LIKE ?"
            params.append(f"%{crop_name.lower().strip()}%")
        query += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params.append(limit)

        cursor = await conn.execute(query, tuple(params))
        rows = await cursor.fetchall()
        advisories = []
        for r in rows:
            adv = dict(r)
            for json_field in ["irrigation_schedule", "fertilizer_schedule", "protective_alerts", "soil_metrics", "weather_summary", "market_summary", "evidence"]:
                if adv.get(json_field):
                    try:
                        adv[json_field] = json.loads(adv[json_field])
                    except Exception:
                        pass
            advisories.append(adv)
        return advisories
    finally:
        await conn.close()

async def get_advisory(advisory_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve detailed advisory by ID."""
    conn = await get_db_connection()
    try:
        cursor = await conn.execute("SELECT * FROM advisories WHERE id = ? AND session_id IN (SELECT id FROM sessions WHERE owner_id = ?)", (advisory_id, owner.get()))
        row = await cursor.fetchone()
        if not row:
            return None
        adv = dict(row)
        for json_field in ["irrigation_schedule", "fertilizer_schedule", "protective_alerts", "soil_metrics", "weather_summary", "market_summary", "evidence"]:
            if adv.get(json_field):
                try:
                    adv[json_field] = json.loads(adv[json_field])
                except Exception:
                    pass
        return adv
    finally:
        await conn.close()

async def delete_session(session_id: str) -> bool:
    """Delete a session, cascading to messages and associated advisories."""
    if not await get_session(session_id):
        return False
    conn = await get_db_connection()
    try:
        await conn.execute("DELETE FROM advisories WHERE session_id = ?", (session_id,))
        await conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        cursor = await conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()

async def delete_advisory(advisory_id: str) -> bool:
    """Delete a specific crop advisory."""
    if not await get_advisory(advisory_id):
        return False
    conn = await get_db_connection()
    try:
        await conn.execute("UPDATE messages SET advisory_id = NULL WHERE advisory_id = ?", (advisory_id,))
        cursor = await conn.execute("DELETE FROM advisories WHERE id = ?", (advisory_id,))
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()



async def patch_profile(session_id, values):
    if not await get_session(session_id):
        return None
    allowed = {"location_name", "latitude", "longitude", "state", "district", "land_size_acres", "primary_crop", "soil_type", "language"}
    values = {k: v for k, v in values.items() if k in allowed}
    if "language" in values and not values["language"]:
        values.pop("language")
    if not values:
        return await get_session(session_id)
    conn = await get_db_connection()
    try:
        assignments = ", ".join(f"{key} = ?" for key in values)
        await conn.execute(f"UPDATE sessions SET {assignments}, updated_at = ? WHERE id = ?", (*values.values(), datetime.now(timezone.utc).isoformat(), session_id))
        await conn.commit()
    finally:
        await conn.close()
    return await get_session(session_id)
