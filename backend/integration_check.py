"""Bounded real-provider checks. Uses a temporary database, never real chat records.

Run from backend: .venv/Scripts/python.exe integration_check.py
Calls configured Gemini and public data providers; may consume API quota.
"""
import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path


async def main():
    with tempfile.TemporaryDirectory(prefix="soilmate-check-") as directory:
        os.environ["DB_PATH"] = str(Path(directory) / "check.db")
        from app.config import settings
        settings.db_path = os.environ["DB_PATH"]
        from app.db.database import init_db
        from app.db.repository import get_session_messages
        from app.services.references import crop_reference
        from app.services.weather import get_weather_forecast
        from app.services.soil import get_soil_properties
        from app.services.mandi import get_mandi_prices
        from app.services.gemini_live import handle_gemini_live_websocket
        from app.agent.orchestrator import run_agent_turn
        from fastapi import WebSocketDisconnect
        logging.getLogger("httpx").setLevel(logging.WARNING)
        await init_db()
        async def inspect(name, fn):
            try:
                data = await asyncio.wait_for(fn, 30)
                print(name, json.dumps({"status": data.get("status", "success"), "error": data.get("error"), "source": data.get("source"), "retrieved_at": data.get("retrieved_at")}, ensure_ascii=True))
            except Exception as exc:
                print(name, type(exc).__name__)
        await asyncio.gather(
            inspect("weather", get_weather_forecast(26.91, 75.79)),
            inspect("soil", get_soil_properties(26.91, 75.79)),
            inspect("wheat_reference", crop_reference("wheat")),
            inspect("rice_reference", crop_reference("rice")),
            inspect("mandi", get_mandi_prices("Rajasthan", "Wheat")),
        )
        try:
            from app.models.schemas import LocationInput
            result = await asyncio.wait_for(run_agent_turn("What is the weather forecast here? Use the weather tool and briefly mention the data source.", language_hint="en", location=LocationInput(name="Jaipur", lat=26.91, lon=75.79), voice_output=False), 120)
            history = await get_session_messages(result.session_id)
            print("typed_turn", json.dumps({"has_response": bool(result.response), "tools": [t.tool for t in result.tool_calls], "advisory_saved": bool(result.advisory_id), "messages_saved": len(history)}))
        except Exception as exc:
            print("typed_turn", type(exc).__name__)

        class BrowserProbe:
            def __init__(self):
                self.initial = True
                self.submitted = False
                self.finished = asyncio.Event()
                self.audio = 0
                self.text = 0
                self.complete = None
                self.error = None
            async def accept(self): pass
            async def receive_text(self):
                if self.initial:
                    self.initial = False
                    return json.dumps({"language": "en"})
                if not self.submitted:
                    self.submitted = True
                    return json.dumps({"type": "text", "text": "Say hello in one short sentence in English."})
                await self.finished.wait()
                raise WebSocketDisconnect(1000)
            async def send_json(self, message):
                kind = message["type"]
                if kind == "audio": self.audio += 1
                if kind == "text": self.text += 1
                if kind == "turn_complete":
                    self.complete = message
                    self.finished.set()
                if kind == "error":
                    self.error = message["message"]
                    self.finished.set()
            async def close(self): pass
        browser = BrowserProbe()
        try:
            await asyncio.wait_for(handle_gemini_live_websocket(browser), 60)
            print("live_turn", json.dumps({"audio_chunks": browser.audio, "transcript_chunks": browser.text, "completed": bool(browser.complete), "error": browser.error}))
            if browser.complete:
                print("live_history_messages", len(await get_session_messages(browser.complete["session_id"])))
        except Exception as exc:
            print("live_turn", type(exc).__name__)


if __name__ == "__main__":
    asyncio.run(main())
