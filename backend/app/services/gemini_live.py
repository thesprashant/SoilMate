import json
import os
import asyncio
import logging
import time
from typing import Dict, Any, Optional
import websockets
from fastapi import WebSocket, WebSocketDisconnect

from app.config import settings
from app.services.gemini_pool import key_manager
from app.agent.prompts import SOILMATE_SYSTEM_PROMPT
from app.agent.tools import execute_tool, AGENT_TOOLS
from app.agent.advisories import persist_advice, validate_schedule, schedule_references
from app.agent.turns import turn_guard
from app.models.schemas import LocationInput, ProfileUpdate
from app.db.repository import patch_profile
from app.db.repository import (
    create_or_update_session,
    save_message,
    get_session,
    get_session_messages,
    save_advisory
)

logger = logging.getLogger(__name__)

# One declaration set for both typed chat and live voice.
GEMINI_LIVE_TOOLS = [AGENT_TOOLS.model_dump(mode="json", by_alias=True, exclude_none=True)]

async def safe_close_ws(ws):
    """Safely close a websocket connection without raising AttributeError or state errors."""
    if ws is not None:
        try:
            await ws.close()
        except Exception:
            pass

async def handle_gemini_live_websocket(client_ws: WebSocket):
    """
    Bidirectional WebSocket proxy connecting client browser directly to Google Gemini Multimodal Live API.
    Streams 16kHz PCM audio and text from the client to Gemini, and streams back 24kHz native audio
    and real-time tool traces to the client with sub-second conversational latency.
    """
    await client_ws.accept()
    logger.info("[GeminiLive] Client connected to live WebSocket.")

    api_key = key_manager.get_active_key()
    if not api_key:
        await client_ws.send_json({
            "type": "error",
            "message": "No Google Gemini API key configured. Please configure GEMINI_API_KEY in backend/.env"
        })
        await client_ws.close()
        return

    # Determine live model candidates from settings and available Google Live API models
    configured_live = (
        getattr(settings, "gemini_live_model", None) or
        os.getenv("GEMINI_LIVE_MODEL") or
        settings.gemini_model.strip() or
        "gemini-3.1-flash-live-preview"
    ).strip()

    # Context session metadata
    session_id = None
    ui_language = "hi"
    location_ctx = None
    farmer_profile = {}

    google_ws = None
    guard = None

    try:
        # 1. Wait for initial client handshake message
        init_raw = await asyncio.wait_for(client_ws.receive_text(), 15)
        if len(init_raw) > 10000:
            raise ValueError("Handshake too large")
        init_data = json.loads(init_raw)

        session_id = init_data.get("session_id")
        ui_language = init_data.get("language") or "hi"
        location_ctx = init_data.get("location")
        if location_ctx:
            location_ctx = LocationInput(**location_ctx).model_dump()
        from app.services.language import normalize_language_code
        ui_language = normalize_language_code(ui_language)
        candidate_guard = turn_guard(session_id)
        await candidate_guard.__aenter__()
        guard = candidate_guard

        # Load existing session from SQLite if available
        if session_id:
            sess = await get_session(session_id)
            if not sess:
                raise ValueError("Session not found")
            if sess:
                farmer_profile = {
                    "location_name": sess.get("location_name"),
                    "latitude": sess.get("latitude"),
                    "longitude": sess.get("longitude"),
                    "state": sess.get("state"),
                    "district": sess.get("district"),
                    "land_size_acres": sess.get("land_size_acres"),
                    "primary_crop": sess.get("primary_crop"),
                    "soil_type": sess.get("soil_type")
                }
        else:
            new_sess = await create_or_update_session(language=ui_language)
            session_id = new_sess.get("id")

        if location_ctx:
            farmer_profile.update(location_name=location_ctx["name"], latitude=location_ctx["lat"], longitude=location_ctx["lon"], state=location_ctx.get("state"))
            await patch_profile(session_id, farmer_profile)

        # Build dynamic context for Gemini System Instruction
        context_block = f"\n\nCURRENT SESSION CONTEXT:\n- Session ID: {session_id}\n- Farmer's UI/Spoken Language: {ui_language}\n"
        if location_ctx:
            context_block += f"- Active Farm Location: {location_ctx.get('name')} (lat: {location_ctx.get('lat')}, lon: {location_ctx.get('lon')})\n"
        if farmer_profile.get("location_name"):
            context_block += f"- Saved Farm Profile: {json.dumps(farmer_profile, ensure_ascii=False)}\n"

        system_instruction_text = (
            f"{SOILMATE_SYSTEM_PROMPT}\n{context_block}\n"
            f"IMPORTANT FOR REAL-TIME VOICE: Speak naturally, warmly, and in short 2-3 sentence conversational turns. "
            f"Address the farmer in {ui_language} with high respect and warmth (Priya persona). "
            f"Do not recite long bullet lists; ask engaging follow-up questions to converse like a real person."
        )

        # Candidate live model list: prioritize fastest, highest-quality Live API models
        candidate_models = []
        if configured_live:
            cand = configured_live if configured_live.startswith("models/") else f"models/{configured_live}"
            candidate_models.append(cand)

        for default_m in [
            "models/gemini-3.1-flash-live-preview",
            "models/gemini-2.5-flash-native-audio-latest",
            "models/gemini-2.5-flash-native-audio-preview-12-2025",
            "models/gemini-2.0-flash-exp",
            "models/gemini-2.0-flash"
        ]:
            if default_m not in candidate_models:
                candidate_models.append(default_m)

        # 2. Connect to Google Gemini BidiGenerateContent WebSocket
        google_url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={api_key}"

        setup_payload = {
            "setup": {
                "model": candidate_models[0],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": "Aoede" # Warm female voice for Priya
                            }
                        }
                    }
                },
                "systemInstruction": {
                    "parts": [{"text": system_instruction_text}]
                },
                "inputAudioTranscription": {},
                "outputAudioTranscription": {},
                "tools": GEMINI_LIVE_TOOLS
            }
        }

        connected = False
        active_model = None
        for cand_model in candidate_models:
            await safe_close_ws(google_ws)
            google_ws = None
            try:
                setup_payload["setup"]["model"] = cand_model
                google_ws = await websockets.connect(google_url, ping_interval=20, ping_timeout=20)
                await google_ws.send(json.dumps(setup_payload))
                init_resp = json.loads(await asyncio.wait_for(google_ws.recv(), timeout=7.0))
                if "setupComplete" not in init_resp:
                    raise RuntimeError("Gemini did not acknowledge Live API setup")
                logger.info(f"[GeminiLive] Connected successfully to Live API using model: {cand_model}")
                connected = True
                active_model = cand_model
                break
            except Exception as conn_err:
                logger.warning(f"[GeminiLive] Model {cand_model} failed for Live API: {conn_err}. Trying next fallback...")
                await safe_close_ws(google_ws)
                google_ws = None

        if not connected or not google_ws:
            raise RuntimeError(f"Could not connect to Google Gemini Live API with candidate models: {candidate_models}")

        logger.info("[GeminiLive] Connected to Live API with %s. Session %s ready.", active_model, session_id)

        # Notify client that connection is ready
        await client_ws.send_json({
            "type": "ready",
            "session_id": session_id,
            "model": active_model
        })

        # Track conversation turns for database persistence
        current_turn_user_text = []
        current_turn_model_text = []
        current_turn_tool_traces = []

        # ==========================================
        # TASK 1: Client -> Google Gemini
        # ==========================================
        async def client_to_google():
            nonlocal current_turn_user_text
            try:
                while True:
                    raw = await asyncio.wait_for(client_ws.receive_text(), 60)
                    if len(raw) > 256000:
                        raise ValueError("Voice frame too large")
                    data = json.loads(raw)
                    msg_type = data.get("type")

                    if msg_type == "audio":
                        # Raw base64 16kHz PCM audio chunk from farmer mic
                        b64_pcm = data.get("data")
                        if b64_pcm and google_ws:
                            media_chunk = {
                                "realtimeInput": {
                                    "audio": {
                                        "mimeType": "audio/pcm;rate=16000",
                                        "data": b64_pcm
                                    }
                                }
                            }
                            await google_ws.send(json.dumps(media_chunk))

                    elif msg_type == "text":
                        # Text query from farmer
                        text_str = data.get("text", "").strip()
                        if text_str and google_ws:
                            current_turn_user_text.append(text_str)
                            client_content = {
                                "clientContent": {
                                    "turns": [
                                        {
                                            "role": "user",
                                            "parts": [{"text": text_str}]
                                        }
                                    ],
                                    "turnComplete": True
                                }
                            }
                            await google_ws.send(json.dumps(client_content))

                    elif msg_type == "ping":
                        await client_ws.send_json({"type": "pong"})

                    elif msg_type == "interrupt":
                        # Client signal that user interrupted or tapped mic
                        logger.info("[GeminiLive] User interrupted active model turn.")

            except WebSocketDisconnect:
                logger.info("[GeminiLive] Browser disconnected.")

        # ==========================================
        # TASK 2: Google Gemini -> Client
        # ==========================================
        tool_tasks = set()
        tool_tasks_by_id = {}

        async def run_tool_calls(func_calls, traces):
            nonlocal farmer_profile
            try:
                function_responses = []

                for call in func_calls:
                    call_name = call.get("name")
                    call_id = call.get("id")
                    call_args = call.get("args", {})

                    t0 = time.time()
                    # Emit live progress to client UI monitor
                    await client_ws.send_json({
                        "type": "tool_start",
                        "tool": call_name,
                        "args": call_args,
                        "summary": f"Executing {call_name}..."
                    })

                    # Execute tool asynchronously in Python
                    if call_name == "record_crop_schedule":
                        history = await get_session_messages(session_id)
                        user_dates = " ".join((m.get("content", "") + " " + (m.get("content_english") or "")) for m in history if m.get("role") == "user") + " " + " ".join(current_turn_user_text)
                        references = await schedule_references(call_args, traces, history)
                        tool_result = validate_schedule(call_args, references, user_dates)
                    else:
                        tool_result = await asyncio.wait_for(execute_tool(call_name, call_args), 30)
                    dur_ms = int((time.time() - t0) * 1000)

                    # Handle farmer profile memory update
                    if call_name == "update_farmer_profile" and isinstance(tool_result, dict) and not tool_result.get("error"):
                        updates = {k: tool_result.get("primary_crops" if k == "primary_crop" else k) for k in ["location_name", "latitude", "longitude", "state", "district", "land_size_acres", "primary_crop", "soil_type"]}
                        updates = {k: v for k, v in updates.items() if v is not None}
                        if "location_name" in call_args:
                            updates.update(latitude=tool_result.get("latitude"), longitude=tool_result.get("longitude"))
                        validated = ProfileUpdate(**updates).model_dump(exclude_unset=True)
                        farmer_profile.update(validated)
                        await patch_profile(session_id, validated)

                    summary_msg = tool_result.get("error") or f"{call_name} completed in {dur_ms}ms"
                    traces.append({
                        "step": len(traces) + 1,
                        "tool": call_name,
                        "inputs": call_args,
                        "outputs": tool_result,
                        "duration_ms": dur_ms,
                        "status": "error" if tool_result.get("error") else "success",
                        "summary": summary_msg
                    })

                    await client_ws.send_json({
                        "type": "tool_end",
                        "tool": call_name,
                        "summary": summary_msg,
                        "data": tool_result,
                        "duration_ms": dur_ms,
                        "inputs": call_args,
                        "status": "error" if tool_result.get("error") else "success"
                    })

                    function_responses.append({
                        "name": call_name,
                        "response": {"output": tool_result},
                        "id": call_id
                    })

                # Send tool responses back to Gemini
                tool_resp_payload = {
                    "toolResponse": {
                        "functionResponses": function_responses
                    }
                }
                await google_ws.send(json.dumps(tool_resp_payload))
            except asyncio.CancelledError:
                raise
            except Exception:
                await client_ws.send_json({"type": "error", "message": "Live tool execution failed. Please reconnect and retry."})
                await safe_close_ws(google_ws)

        async def google_to_client():
            nonlocal current_turn_user_text, current_turn_model_text, current_turn_tool_traces, farmer_profile
            try:
                async for raw_msg in google_ws:
                    resp_json = json.loads(raw_msg)

                    # 1. Model Text & Audio Output
                    server_content = resp_json.get("serverContent")
                    if server_content:
                        input_text = server_content.get("inputTranscription", {}).get("text")
                        if input_text:
                            current_turn_user_text.append(input_text)
                            await client_ws.send_json({"type": "user_text", "text": input_text})
                        output_text = server_content.get("outputTranscription", {}).get("text")
                        if output_text:
                            current_turn_model_text.append(output_text)
                            await client_ws.send_json({"type": "text", "text": output_text})
                        model_turn = server_content.get("modelTurn")
                        if model_turn:
                            parts = model_turn.get("parts", [])
                            for p in parts:
                                # Stream text chunk
                                if "text" in p and p["text"] and not output_text and not p.get("thought"):
                                    chunk_text = p["text"]
                                    current_turn_model_text.append(chunk_text)
                                    await client_ws.send_json({
                                        "type": "text",
                                        "text": chunk_text
                                    })

                                # Stream raw 24kHz PCM audio chunk for instant playback
                                if "inlineData" in p:
                                    audio_chunk = p["inlineData"].get("data")
                                    if audio_chunk:
                                        await client_ws.send_json({
                                            "type": "audio",
                                            "data": audio_chunk
                                        })

                        # True real-time interruption signal
                        if server_content.get("interrupted"):
                            await client_ws.send_json({"type": "interrupted"})

                        # Turn completion: persist to SQLite database
                        if server_content.get("turnComplete"):
                            user_full = " ".join(current_turn_user_text).strip()
                            model_full = "".join(current_turn_model_text).strip()

                            history = await get_session_messages(session_id)
                            user_context = " ".join((m.get("content_english") or m.get("content") or "") for m in history if m.get("role") == "user") + " " + user_full
                            advisory_id = await persist_advice(session_id, ui_language, model_full, farmer_profile, current_turn_tool_traces, user_text=user_context)
                            if user_full or model_full:
                                # Save user message
                                await save_message(
                                    session_id=session_id,
                                    role="user",
                                    content=user_full,
                                    language=ui_language
                                )
                                # Save assistant message with tool traces
                                await save_message(
                                    session_id=session_id,
                                    role="assistant",
                                    content=model_full,
                                    language=ui_language,
                                    tool_calls=current_turn_tool_traces,
                                    advisory_id=advisory_id
                                )

                            await client_ws.send_json({
                                "type": "turn_complete",
                                "session_id": session_id,
                                "farmer_profile": farmer_profile,
                                "language": ui_language,
                                "user_content": user_full,
                                "content": model_full,
                                "tool_calls": current_turn_tool_traces,
                                "advisory_id": advisory_id
                            })

                            # Reset turn buffers
                            current_turn_user_text = []
                            current_turn_model_text = []
                            current_turn_tool_traces = []

                    # 2. Dynamic Autonomous Function / Tool Calling
                    tool_call = resp_json.get("toolCall")
                    if tool_call:
                        func_calls = tool_call.get("functionCalls", [])
                        task = asyncio.create_task(run_tool_calls(func_calls, current_turn_tool_traces))
                        tool_tasks.add(task)
                        def tool_done(done):
                            tool_tasks.discard(done)
                            for key in list(tool_tasks_by_id):
                                if tool_tasks_by_id[key] is done:
                                    del tool_tasks_by_id[key]
                            if not done.cancelled():
                                done.exception()
                        task.add_done_callback(tool_done)
                        for call in func_calls:
                            tool_tasks_by_id[call.get("id")] = task

                    for call_id in resp_json.get("toolCallCancellation", {}).get("ids", []):
                        pending_tool = tool_tasks_by_id.get(call_id)
                        if pending_tool:
                            pending_tool.cancel()

            except WebSocketDisconnect:
                logger.info("[GeminiLive] Browser disconnected while receiving output.")

        # Run both directions concurrently with prompt cleanup on first exit
        client_task = asyncio.create_task(client_to_google())
        google_task = asyncio.create_task(google_to_client())

        tasks = [client_task, google_task]
        try:
            done, pending = await asyncio.wait(
                tasks, timeout=900, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                raise TimeoutError("Live session reached its 15 minute limit; reconnect to continue.")
            # Surface provider failures instead of silently closing the browser socket.
            for task in done:
                task.result()
        finally:
            tasks.extend(tool_tasks)
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    except websockets.ConnectionClosed as e:
        close = e.rcvd
        code = close.code if close else 1006
        reason = close.reason if close else "Connection lost without a close frame"
        # Never expose the authenticated provider URL in client errors or logs.
        reason = reason.replace(api_key, "[redacted]")
        message = f"Gemini Live disconnected ({code}): {reason}"
        logger.warning("[GeminiLive] %s", message)
        try:
            await client_ws.send_json({"type": "error", "message": message})
        except Exception:
            pass
    except Exception as e:
        message = str(e).replace(api_key, "[redacted]")
        logger.error("[handle_gemini_live_websocket] Fatal: %s", message)
        try:
            await client_ws.send_json({"type": "error", "message": message})
        except Exception:
            pass
    finally:
        if guard:
            await guard.__aexit__(None, None, None)
        await safe_close_ws(google_ws)
        try:
            await client_ws.close()
        except Exception:
            pass
        logger.info("[GeminiLive] Session closed.")

