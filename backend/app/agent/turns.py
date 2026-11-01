"""Bound concurrent turns. Same request ID is never executed twice in a session."""
import asyncio
from contextlib import asynccontextmanager
from fastapi import HTTPException
from app.security import owner

active = set()
seen = {}  # bounded process-local duplicate guard; single-worker deployment


@asynccontextmanager
async def turn_guard(session_id, request_id=None):
    key = (owner.get(), session_id or "new")
    request_key = (owner.get(), request_id) if request_id else None
    if request_key and request_key in seen:
        raise HTTPException(409, "This request was already accepted. Reload history before retrying.")
    if key in active or len(active) >= 8:
        raise HTTPException(409, "A conversation is already running. End it before starting another turn.")
    if request_key:
        seen[request_key] = True
        while len(seen) > 10000:
            seen.pop(next(iter(seen)))
    active.add(key)
    try:
        yield
    finally:
        active.discard(key)
