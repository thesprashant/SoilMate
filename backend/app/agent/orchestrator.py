import time
import logging
import asyncio
from typing import Dict, Any, List, Optional, Callable, Awaitable
from google.genai import types

from app.agent.prompts import SOILMATE_SYSTEM_PROMPT
from app.agent.tools import AGENT_TOOLS, execute_tool
from app.agent.advisories import persist_advice, validate_schedule, schedule_references
from app.config import settings
from app.services.gemini_pool import key_manager
from app.services.language import (
    detect_language_from_text,
    normalize_language_code,
    resolve_spoken_language,
    SUPPORTED_INDIAN_LANGUAGES
)
from app.services.translation import translate_to_english, translate_from_english
from app.services.voice import text_to_speech
from app.models.schemas import ProfileUpdate, ChatResponse, ToolCallRecord, ProgressEvent, LocationInput, FarmerProfile
from app.db.repository import (
    create_or_update_session,
    update_session_profile,
    patch_profile,
    get_session,
    save_message,
    get_session_messages,
    save_advisory
)

logger = logging.getLogger(__name__)

def generate_tool_start_message(name: str, args: Dict[str, Any], location_name: Optional[str]) -> str:
    """Generate friendly progress description for live SSE streaming."""
    loc = location_name or "your area"
    if name == "get_weather":
        return f"Fetching live 7-day weather forecast and rain alerts for {loc}..."
    elif name == "get_soil_data":
        return f"Querying SoilGrids for soil texture, pH, and nitrogen metrics at {loc}..."
    elif name == "get_mandi_prices":
        comm = args.get("commodity", "crops")
        state = args.get("state", loc)
        return f"Checking APMC mandi modal prices for {comm} in {state}..."
    elif name == "query_crop_database":
        season = args.get("season", "current season")
        return "Fetching official crop reference and checking its regional scope..."
    elif name == "get_pest_and_disease_risk":
        crop = args.get("crop", "crop")
        return f"Analyzing pest and fungal disease risks for {crop} under forecast weather..."
    elif name == "get_government_schemes":
        return "Searching Central and State government agricultural subsidy and insurance schemes..."
    elif name == "update_farmer_profile":
        tgt = args.get("location_name") or "farmer"
        return f"Saving and remembering farm profile for {tgt}..."
    return f"Fetching data using {name}..."

def summarize_tool_output(name: str, output: Dict[str, Any]) -> str:
    """Create concise summary of tool results for UI traces."""
    if not output or output.get("error"):
        return output.get("error", "Failed to retrieve data.") if isinstance(output, dict) else "Done"

    if name == "get_weather":
        curr = output.get("current", {})
        temp = curr.get("temperature_2m", "N/A")
        rain = curr.get("precipitation", 0)
        alerts_count = len(output.get("alerts", []))
        return f"Current Temp: {temp}°C, Rain: {rain}mm. {alerts_count} agricultural alert(s) identified."

    elif name == "get_soil_data":
        ph = output.get("ph", "N/A")
        soil_type = output.get("soil_type", "Loamy")
        return f"Texture: {soil_type}, pH: {ph} ({output.get('ph_interpretation', '')[:40]})."

    elif name == "get_mandi_prices":
        total = output.get("total_found", 0)
        best = output.get("best_market")
        if best:
            return f"Found {total} mandi quotes. Best price: ₹{best.get('modal_price')}/quintal at {best.get('market')}."
        return f"Mandi quotes search complete ({total} found)."

    elif name == "query_crop_database":
        return f"Retrieved official {output.get('crop', 'crop')} reference. Check regional applicability."

    elif name == "get_pest_and_disease_risk":
        risks = output.get("identified_risks", [])
        return f"Identified {len(risks)} pest/disease management factors for {output.get('crop')}."

    elif name == "get_government_schemes":
        schemes = output.get("schemes", [])
        return f"Matched {len(schemes)} eligible agricultural welfare schemes."

    elif name == "update_farmer_profile":
        loc = output.get("location_name") or "Farm"
        lat = output.get("latitude")
        lon = output.get("longitude")
        st = output.get("state")
        coords = f" ({lat}, {lon})" if lat and lon else ""
        return f"Saved profile for {loc}{coords}{', ' + st if st else ''}."

    return "Data retrieved successfully."

async def run_agent_turn(
    message: str,
    session_id: Optional[str] = None,
    language_hint: Optional[str] = None,
    location: Optional[LocationInput] = None,
    voice_output: bool = True,
    progress_callback: Optional[Callable[[ProgressEvent], Awaitable[None]]] = None
) -> ChatResponse:
    """
    Execute a full turn of the SoilMate ReAct Agent:
    1. Detect language & translate to English.
    2. Run dynamic ReAct loop in English with Gemini 2.0 Flash.
    3. Stream real-time progress callbacks (for SSE).
    4. Auto-save history & crop advisories to SQLite.
    5. Translate response back to native language + generate TTS.
    """
    async def emit_progress(p_type: str, msg: str, tool: Optional[str] = None, dur: Optional[int] = None, data: Any = None, inputs: Any = None):
        if progress_callback:
            try:
                ev = ProgressEvent(type=p_type, message=msg, tool=tool, duration_ms=dur, data=data, inputs=inputs)
                await progress_callback(ev)
            except Exception as e:
                logger.warning(f"[run_agent_turn] progress_callback error: {e}")

    # Step 1: Ingestion & Language Identification
    # Requirement: Chat and all generated content MUST follow the language being spoken/typed!
    lang_code = resolve_spoken_language(message, spoken_hint=language_hint)
    lang_meta = SUPPORTED_INDIAN_LANGUAGES.get(lang_code, {"name": "Hindi", "native": "हिन्दी"})

    # Check for existing session and saved profile in DB (Conversational Memory)
    existing_session = None
    if session_id:
        existing_session = await get_session(session_id)

    saved_loc_name = existing_session.get("location_name") if existing_session else None
    saved_lat = existing_session.get("latitude") if existing_session else None
    saved_lon = existing_session.get("longitude") if existing_session else None
    saved_state = existing_session.get("state") if existing_session else None
    saved_district = existing_session.get("district") if existing_session else None
    saved_land = existing_session.get("land_size_acres") if existing_session else None
    saved_crop = existing_session.get("primary_crop") if existing_session else None
    saved_soil = existing_session.get("soil_type") if existing_session else None

    # Priority 1: User explicitly provided location in request (e.g. from UI search/dropdown)
    # Priority 2: Session already has saved profile from past conversation turns
    # Priority 3: Unknown
    if location and location.lat is not None and location.lon is not None and location.name and location.name not in ["Farm", "Selected Location"]:
        loc_name = location.name
        loc_lat = location.lat
        loc_lon = location.lon
        loc_state = location.state or saved_state
    elif saved_loc_name and saved_lat is not None and saved_lon is not None:
        loc_name = saved_loc_name
        loc_lat = saved_lat
        loc_lon = saved_lon
        loc_state = saved_state
    elif location and location.lat is not None and location.lon is not None:
        loc_name = location.name
        loc_lat = location.lat
        loc_lon = location.lon
        loc_state = location.state
    else:
        loc_name = None
        loc_lat = None
        loc_lon = None
        loc_state = None

    # Ensure Session exists in DB
    session = await create_or_update_session(
        session_id=session_id,
        language=lang_code,
        location_name=loc_name,
        latitude=loc_lat,
        longitude=loc_lon,
        state=loc_state
    )
    active_session_id = session.get("id")

    # Step 2: Translate User Query to English
    await emit_progress("thinking", f"Processing query in {lang_meta['name']} and standardizing to English...")
    user_english = await translate_to_english(message, source_lang=lang_code)

    # Save User Message to DB
    await save_message(
        session_id=active_session_id,
        role="user",
        content=message,
        content_english=user_english,
        language=lang_code
    )

    # Build Context & Previous Multi-Turn History
    past_messages = await get_session_messages(active_session_id)
    history_context = ""
    if len(past_messages) > 1:
        # Include last 3 exchanges in English
        recent = past_messages[-7:-1]
        history_lines = []
        for m in recent:
            role = "Farmer" if m["role"] == "user" else "SoilMate"
            txt = m.get("content_english") or m["content"]
            history_lines.append(f"{role}: {txt}")
        if history_lines:
            history_context = "\nConversation History:\n" + "\n".join(history_lines) + "\n"

    if loc_name and loc_lat is not None and loc_lon is not None:
        profile_context = (
            f"Current Farmer Profile:\n"
            f"- Location: {loc_name} (Coordinates: latitude={loc_lat}, longitude={loc_lon})\n"
            f"- State: {loc_state or 'Not specified'}\n"
            f"- District: {saved_district or 'Not specified'}\n"
            f"- Landholding: {saved_land or 'Not specified'} acres\n"
            f"- Primary Crops: {saved_crop or 'Not specified'}\n"
            f"- Soil Type: {saved_soil or 'Not specified'}\n"
            f"- Language: {lang_meta['name']}\n"
        )
    else:
        profile_context = (
            f"Current Farmer Profile:\n"
            f"- Location: UNKNOWN (Farmer has not specified village, district, or state yet)\n"
            f"- Landholding: {saved_land or 'Not specified'} acres\n"
            f"- Primary Crops: {saved_crop or 'Not specified'}\n"
            f"- Soil Type: {saved_soil or 'Not specified'}\n"
            f"- Language: {lang_meta['name']}\n"
        )

    prompt_content = f"{profile_context}{history_context}\nFarmer's Query: {user_english}"

    # Prepare Gemini Request
    gemini_messages = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt_content)]
        )
    ]

    config = types.GenerateContentConfig(
        system_instruction=SOILMATE_SYSTEM_PROMPT,
        tools=[AGENT_TOOLS],
        temperature=0.3
    )

    tool_traces: List[ToolCallRecord] = []
    max_iterations = 8
    iteration = 0
    final_english_response = ""

    # Step 3: Dynamic ReAct Agent Execution Loop
    while iteration < max_iterations:
        iteration += 1

        try:
            response = await key_manager.generate_with_fallback(
                model=settings.gemini_model,
                contents=gemini_messages,
                config=config
            )
        except Exception as e:
            logger.error(f"[AgentLoop] Gemini generation failed: {e}")
            raise RuntimeError("The language model is unavailable. Please retry; no advisory was generated.") from e
            break

        candidates = getattr(response, "candidates", [])
        if not candidates or not candidates[0].content or not candidates[0].content.parts:
            raise RuntimeError("The model returned no usable response.")
            break

        model_parts = candidates[0].content.parts
        function_calls = [p.function_call for p in model_parts if getattr(p, "function_call", None)]

        # If no tool calls, model provided final synthesis!
        if not function_calls:
            text_parts = [p.text for p in model_parts if getattr(p, "text", None)]
            final_english_response = "\n".join(text_parts).strip()
            break

        # Append model turn with function calls
        gemini_messages.append(types.Content(role="model", parts=model_parts))
        function_responses = []

        # Execute each requested tool dynamically
        for fc in function_calls:
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}

            # Inject location coordinates if omitted by model
            if tool_name in ["get_weather", "get_soil_data"]:
                if "latitude" not in tool_args and loc_lat is not None:
                    tool_args["latitude"] = loc_lat
                if "longitude" not in tool_args and loc_lon is not None:
                    tool_args["longitude"] = loc_lon
            elif tool_name == "get_mandi_prices":
                if "state" not in tool_args and loc_state:
                    tool_args["state"] = loc_state

            start_msg = generate_tool_start_message(tool_name, tool_args, loc_name)
            await emit_progress("tool_start", start_msg, tool=tool_name, inputs=tool_args)

            t0 = time.time()
            if tool_name == "record_crop_schedule":
                user_dates = " ".join((m.get("content", "") + " " + (m.get("content_english") or "")) for m in past_messages if m.get("role") == "user")
                references = await schedule_references(tool_args, [t.model_dump() for t in tool_traces], past_messages)
                tool_output = validate_schedule(tool_args, references, user_dates)
            else:
                tool_output = await execute_tool(tool_name, tool_args)
            dur_ms = int((time.time() - t0) * 1000)

            # If tool was update_farmer_profile, immediately update active location & DB!
            if tool_name == "update_farmer_profile" and isinstance(tool_output, dict) and not tool_output.get("error"):
                updates = {k: tool_output.get("primary_crops" if k == "primary_crop" else k) for k in ["location_name", "latitude", "longitude", "state", "district", "land_size_acres", "primary_crop", "soil_type"]}
                updates = {k: v for k, v in updates.items() if v is not None}
                if "location_name" in tool_args:
                    updates.update(latitude=tool_output.get("latitude"), longitude=tool_output.get("longitude"))
                profile = await patch_profile(active_session_id, ProfileUpdate(**updates).model_dump(exclude_unset=True))
                loc_name, loc_lat, loc_lon = profile["location_name"], profile["latitude"], profile["longitude"]
                loc_state, saved_district = profile["state"], profile["district"]
                saved_land, saved_crop, saved_soil = profile["land_size_acres"], profile["primary_crop"], profile["soil_type"]

            summary = summarize_tool_output(tool_name, tool_output)
            await emit_progress("tool_end", summary, tool=tool_name, dur=dur_ms, data=tool_output, inputs=tool_args)

            record = ToolCallRecord(
                step=iteration,
                tool=tool_name,
                inputs=tool_args,
                outputs=tool_output,
                status="error" if tool_output.get("error") else "success",
                duration_ms=dur_ms,
                summary=summary
            )
            tool_traces.append(record)

            function_responses.append(
                types.Part.from_function_response(
                    name=tool_name,
                    response={"result": tool_output}
                )
            )

        gemini_messages.append(types.Content(role="user", parts=function_responses))

    if not final_english_response:
        final_english_response = "The analysis reached its tool limit before a complete answer was available. Review the retrieved evidence or narrow your question."

    # Step 4: Translate Back to Farmer's Language
    await emit_progress("synthesizing", "Formulating complete agricultural advice and protective schedule...")
    await emit_progress("translating", f"Translating advisory to {lang_meta['name']}...")

    localized_response = await translate_from_english(final_english_response, target_lang=lang_code)

    # Step 5: Synthesize Voice Audio (TTS)
    audio_b64 = None
    if voice_output:
        await emit_progress("speaking", f"Generating audio voice response in {lang_meta['name']}...")
        audio_b64 = await text_to_speech(localized_response, language=lang_code)

    advisory_id = await persist_advice(active_session_id, lang_code, localized_response,
        {"location_name": loc_name, "latitude": loc_lat, "longitude": loc_lon, "primary_crop": saved_crop},
        [t.model_dump() for t in tool_traces], user_text=" ".join((m.get("content_english") or m.get("content") or "") for m in past_messages if m.get("role") == "user"))

    # Save Assistant Message & Tool Trace in DB
    tool_dicts = [t.model_dump() for t in tool_traces]
    await save_message(
        session_id=active_session_id,
        role="assistant",
        content=localized_response,
        content_english=final_english_response,
        language=lang_code,
        audio_url=None,
        tool_calls=tool_dicts,
        advisory_id=advisory_id
    )

    final_profile = FarmerProfile(
        location_name=loc_name,
        latitude=loc_lat,
        longitude=loc_lon,
        state=loc_state,
        district=saved_district,
        land_size_acres=saved_land,
        primary_crop=saved_crop,
        soil_type=saved_soil
    )

    final_result = ChatResponse(
        session_id=active_session_id,
        response=localized_response,
        response_english=final_english_response,
        language=lang_code,
        audio_base64=audio_b64,
        advisory_id=advisory_id,
        tool_calls=tool_traces,
        farmer_profile=final_profile,
        iterations=iteration,
        truncated=(iteration >= max_iterations)
    )

    await emit_progress("complete", "Analysis complete.", data=final_result.model_dump())
    return final_result

