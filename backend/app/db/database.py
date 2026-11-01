import os
import aiosqlite
from typing import AsyncGenerator
from app.config import settings

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    language TEXT NOT NULL DEFAULT 'hi',
    location_name TEXT,
    latitude REAL,
    longitude REAL,
    state TEXT,
    district TEXT,
    land_size_acres REAL,
    primary_crop TEXT,
    soil_type TEXT,
    profile_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    content_english TEXT,
    language TEXT NOT NULL,
    audio_url TEXT,
    tool_calls TEXT, -- JSON-serialized trace array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS advisories (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    crop_name TEXT NOT NULL,
    crop_name_local TEXT,
    language TEXT NOT NULL,
    season TEXT,
    location_name TEXT,
    latitude REAL,
    longitude REAL,
    sowing_window TEXT,
    harvesting_window TEXT,
    irrigation_schedule TEXT, -- JSON
    fertilizer_schedule TEXT, -- JSON
    protective_alerts TEXT,   -- JSON
    soil_metrics TEXT,        -- JSON
    weather_summary TEXT,     -- JSON
    market_summary TEXT,      -- JSON
    full_advisory_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_advisories_session ON advisories(session_id);
CREATE INDEX IF NOT EXISTS idx_advisories_crop ON advisories(crop_name);
"""

async def get_db_connection() -> aiosqlite.Connection:
    """Open an async connection to SQLite with row-factory enabled."""
    db_file = settings.db_path
    os.makedirs(os.path.dirname(os.path.abspath(db_file)), exist_ok=True)
    conn = await aiosqlite.connect(db_file, timeout=15)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON;")
    return conn

async def init_db() -> None:
    """Initialize database tables, columns, and indexes on application startup."""
    conn = await get_db_connection()
    try:
        await conn.executescript(CREATE_TABLES_SQL)
        # Migrate columns for existing database files safely
        columns_to_ensure = [
            ("owner_id", "TEXT NOT NULL DEFAULT 'local-demo'"),
            ("state", "TEXT"),
            ("district", "TEXT"),
            ("land_size_acres", "REAL"),
            ("primary_crop", "TEXT"),
            ("soil_type", "TEXT"),
            ("profile_data", "TEXT")
        ]
        for table, columns in [("sessions", columns_to_ensure), ("messages", [("advisory_id", "TEXT")]), ("advisories", [("evidence", "TEXT")])]:
            cursor = await conn.execute(f"PRAGMA table_info({table})")
            existing = {row["name"] for row in await cursor.fetchall()}
            for name, kind in columns:
                if name not in existing:
                    await conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
        await conn.execute("UPDATE advisories SET evidence = '{}' WHERE evidence IS NULL")
        await conn.commit()
    finally:
        await conn.close()
