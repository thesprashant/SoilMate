import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from app.services import gemini_live


class BrowserSocket:
    def __init__(self, messages=()):
        self.messages = iter(messages)
        self.sent = []
        self.closed = False
        self.initial = True

    async def accept(self):
        pass

    async def receive_text(self):
        if self.initial:
            self.initial = False
            return json.dumps({"language": "en"})
        return json.dumps(await self.receive_json())

    async def receive_json(self):
        await asyncio.sleep(0)
        try:
            return next(self.messages)
        except StopIteration:
            raise WebSocketDisconnect(code=1000)

    async def send_json(self, message):
        self.sent.append(message)

    async def close(self):
        self.closed = True


class ProviderSocket:
    def __init__(self, handshake=None, fail_audio=False):
        self.handshake = {"setupComplete": {}} if handshake is None else handshake
        self.fail_audio = fail_audio
        self.sent = []
        self.closed = False
        self.receiver_stopped = False

    async def send(self, raw):
        message = json.loads(raw)
        self.sent.append(message)
        if self.fail_audio and "realtimeInput" in message:
            raise ConnectionClosedError(Close(1007, "Invalid audio payload"), None)

    async def recv(self):
        return json.dumps(self.handshake)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            await asyncio.Future()
        finally:
            self.receiver_stopped = True

    async def close(self):
        self.closed = True


@pytest.fixture
def live_dependencies(monkeypatch):
    monkeypatch.setattr(gemini_live.key_manager, "get_active_key", lambda: "test-key")
    monkeypatch.setattr(
        gemini_live, "create_or_update_session", AsyncMock(return_value={"id": "test-session"})
    )


@pytest.mark.asyncio
async def test_audio_and_interrupt_keep_same_live_connection(monkeypatch, live_dependencies):
    provider = ProviderSocket()
    connect = AsyncMock(return_value=provider)
    monkeypatch.setattr(gemini_live.websockets, "connect", connect)
    browser = BrowserSocket([
        {"type": "audio", "data": "AAAA"},
        {"type": "interrupt"},
        {"type": "ping"},
        {"type": "audio", "data": "BBBB"},
    ])

    await asyncio.wait_for(gemini_live.handle_gemini_live_websocket(browser), 2)

    assert connect.await_count == 1
    frames = [m["realtimeInput"] for m in provider.sent if "realtimeInput" in m]
    assert frames == [
        {"audio": {"mimeType": "audio/pcm;rate=16000", "data": "AAAA"}},
        {"audio": {"mimeType": "audio/pcm;rate=16000", "data": "BBBB"}},
    ]
    assert [m["type"] for m in browser.sent] == ["ready", "pong"]
    assert provider.closed and browser.closed and provider.receiver_stopped


@pytest.mark.asyncio
async def test_provider_close_reason_reaches_browser(monkeypatch, live_dependencies):
    provider = ProviderSocket(fail_audio=True)
    monkeypatch.setattr(gemini_live.websockets, "connect", AsyncMock(return_value=provider))
    browser = BrowserSocket([{"type": "audio", "data": "AAAA"}])

    await asyncio.wait_for(gemini_live.handle_gemini_live_websocket(browser), 2)

    error = next(m for m in browser.sent if m["type"] == "error")
    assert "1007" in error["message"]
    assert "Invalid audio payload" in error["message"]
    assert provider.closed and provider.receiver_stopped


@pytest.mark.asyncio
async def test_rejected_setup_never_reports_ready(monkeypatch, live_dependencies):
    provider = ProviderSocket(handshake={"error": {"message": "Invalid setup"}})
    monkeypatch.setattr(gemini_live.websockets, "connect", AsyncMock(return_value=provider))
    browser = BrowserSocket()

    await asyncio.wait_for(gemini_live.handle_gemini_live_websocket(browser), 2)

    assert not any(m["type"] == "ready" for m in browser.sent)
    assert any(m["type"] == "error" for m in browser.sent)
    assert provider.closed and browser.closed


@pytest.mark.asyncio
async def test_live_barge_in_is_forwarded_while_tool_is_running(monkeypatch, live_dependencies):
    tool_started = asyncio.Event()
    tool_cancelled = asyncio.Event()
    interrupted = asyncio.Event()
    async def slow_tool(*args):
        tool_started.set()
        try:
            await asyncio.Future()
        finally:
            tool_cancelled.set()
    class WaitingBrowser(BrowserSocket):
        async def receive_json(self):
            await interrupted.wait()
            raise WebSocketDisconnect(1000)
        async def send_json(self, message):
            await super().send_json(message)
            if message["type"] == "interrupted":
                interrupted.set()
    class ToolProvider(ProviderSocket):
        def __init__(self):
            super().__init__()
            self.index = 0
        async def __anext__(self):
            self.index += 1
            if self.index == 1:
                return json.dumps({"toolCall": {"functionCalls": [{"id": "call1", "name": "get_weather", "args": {"latitude": 20, "longitude": 70}}]}})
            if self.index == 2:
                await tool_started.wait()
                return json.dumps({"serverContent": {"interrupted": True}})
            return await super().__anext__()
    provider = ToolProvider()
    browser = WaitingBrowser()
    monkeypatch.setattr(gemini_live, "execute_tool", slow_tool)
    monkeypatch.setattr(gemini_live.websockets, "connect", AsyncMock(return_value=provider))
    await asyncio.wait_for(gemini_live.handle_gemini_live_websocket(browser), 2)
    assert interrupted.is_set()
    assert tool_cancelled.is_set()
