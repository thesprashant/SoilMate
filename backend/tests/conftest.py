import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


import pytest_asyncio
from app.config import settings
from app.db.database import init_db
from app.security import owner
from app.agent.turns import active, seen

@pytest_asyncio.fixture(autouse=True)
async def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "app_mode", "local")
    from app.main import request_times
    request_times.clear()
    active.clear(); seen.clear()
    token = owner.set("local-demo")
    await init_db()
    yield
    owner.reset(token)
