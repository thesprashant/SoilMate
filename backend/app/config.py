import os
from typing import List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    app_mode: str = Field(default_factory=lambda: os.getenv("APP_MODE", "local"))
    session_secret: str = Field(default_factory=lambda: os.getenv("SESSION_SECRET", ""))
    # Gemini API keys pool (split comma-separated keys)
    gemini_api_keys_raw: str = Field(
        default_factory=lambda: (os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY") or "").strip()
    )
    gemini_model: str = Field(
        default_factory=lambda: (os.getenv("GEMINI_MODEL") or "gemini-3.5-flash").strip()
    )
    gemini_live_model: str = Field(
        default_factory=lambda: (os.getenv("GEMINI_LIVE_MODEL") or "gemini-3.1-flash-live-preview").strip()
    )
    
    sarvam_api_key: str = Field(default_factory=lambda: (os.getenv("SARVAM_API_KEY") or "").strip())
    sarvam_speaker: str = Field(
        default_factory=lambda: (os.getenv("SARVAM_SPEAKER") or "priya").strip()
    )
    speaker_gender: str = Field(
        default_factory=lambda: (os.getenv("SPEAKER_GENDER") or "female").strip()
    )
    data_gov_api_key: str = Field(default_factory=lambda: (os.getenv("DATA_GOV_API_KEY") or "").strip())
    data_gov_resource_id: str = Field(
        default_factory=lambda: (os.getenv("DATA_GOV_RESOURCE_ID") or "35985678-0d79-46b4-9ed6-6f13308a1d24").strip()
    )
    
    db_path: str = Field(
        default_factory=lambda: os.getenv(
            "DB_PATH",
            os.path.join(os.path.dirname(__file__), "data", "soilmate.db")
        )
    )
    
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    frontend_url: str = Field(default_factory=lambda: os.getenv("FRONTEND_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:5173")
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    @property
    def gemini_api_keys(self) -> List[str]:
        """Extract sanitized list of non-empty Gemini API keys."""
        raw = self.gemini_api_keys_raw.strip()
        if not raw:
            raw = (os.getenv("GEMINI_API_KEY") or "").strip()
        if not raw:
            return []
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        return keys

settings = Settings()
