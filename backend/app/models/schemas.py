from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

class LocationInput(BaseModel):
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    name: Optional[str] = "Selected Location"
    state: Optional[str] = None

class ChatRequest(BaseModel):
    request_id: Optional[str] = Field(None, min_length=8, max_length=100)
    message: str = Field(..., min_length=1, max_length=6000, description="Farmer query in any Indian language or English")
    session_id: Optional[str] = Field(default=None, description="Optional existing session ID to continue history")
    language: Optional[str] = Field(default=None, description="Optional language hint; auto-detected if omitted")
    location: Optional[LocationInput] = None
    voice_output: bool = Field(default=True, description="Whether to synthesize audio TTS")

class ToolCallRecord(BaseModel):
    step: int
    tool: str
    inputs: Dict[str, Any]
    outputs: Any
    status: str = "success"
    duration_ms: Optional[int] = None
    summary: Optional[str] = None

class FarmerProfile(BaseModel):
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    state: Optional[str] = None
    district: Optional[str] = None
    land_size_acres: Optional[float] = None
    primary_crop: Optional[str] = None
    soil_type: Optional[str] = None

class ChatResponse(BaseModel):
    session_id: str
    response: str
    response_english: Optional[str] = None
    language: str
    audio_base64: Optional[str] = None
    advisory_id: Optional[str] = None
    tool_calls: List[ToolCallRecord] = []
    farmer_profile: Optional[FarmerProfile] = None
    iterations: int = 1
    truncated: bool = False

class ProgressEvent(BaseModel):
    type: str # 'thinking' | 'tool_start' | 'tool_end' | 'synthesizing' | 'translating' | 'speaking' | 'complete' | 'error'
    message: str
    tool: Optional[str] = None
    inputs: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None
    data: Optional[Any] = None

class SessionSummary(BaseModel):
    id: str
    language: str
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    state: Optional[str] = None
    district: Optional[str] = None
    land_size_acres: Optional[float] = None
    primary_crop: Optional[str] = None
    soil_type: Optional[str] = None
    created_at: str
    updated_at: str

class MessageRecord(BaseModel):
    advisory_id: Optional[str] = None
    id: str
    session_id: str
    role: str
    content: str
    content_english: Optional[str] = None
    language: str
    audio_url: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = []
    created_at: str

class AdvisorySummary(BaseModel):
    id: str
    session_id: Optional[str] = None
    crop_name: str
    crop_name_local: Optional[str] = None
    language: str
    season: Optional[str] = None
    location_name: Optional[str] = None
    sowing_window: Optional[str] = None
    harvesting_window: Optional[str] = None
    created_at: str

class AdvisoryDetail(BaseModel):
    evidence: Dict[str, Any] = {}
    id: str
    session_id: Optional[str] = None
    crop_name: str
    crop_name_local: Optional[str] = None
    language: str
    season: Optional[str] = None
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    sowing_window: Optional[str] = None
    harvesting_window: Optional[str] = None
    irrigation_schedule: Optional[Any] = None
    fertilizer_schedule: Optional[Any] = None
    protective_alerts: Optional[Any] = None
    soil_metrics: Optional[Any] = None
    weather_summary: Optional[Any] = None
    market_summary: Optional[Any] = None
    full_advisory_text: str
    created_at: str

class GeocodeResponse(BaseModel):
    name: str
    lat: float
    lon: float
    state: Optional[str] = None
    country: Optional[str] = None

class WeatherDaily(BaseModel):
    time: List[str]
    temperature_2m_max: List[Optional[float]]
    temperature_2m_min: List[Optional[float]]
    precipitation_sum: List[Optional[float]]
    precipitation_probability_max: Optional[List[Optional[int]]] = None

class WeatherAlert(BaseModel):
    date: str
    type: str
    message: str
    severity: str = "warning"

class WeatherResponse(BaseModel):
    source: Optional[str] = None
    retrieved_at: Optional[str] = None
    data_kind: Optional[str] = None
    note: Optional[str] = None
    location: Dict[str, Any]
    current: Dict[str, Any]
    daily: WeatherDaily
    alerts: List[WeatherAlert] = []

class SoilResponse(BaseModel):
    source: Optional[str] = None
    retrieved_at: Optional[str] = None
    data_kind: Optional[str] = None
    note: Optional[str] = None
    lat: float
    lon: float
    ph: float
    ph_interpretation: str
    soil_type: str
    sand_pct: float
    silt_pct: float
    clay_pct: float
    organic_carbon_g_kg: float
    nitrogen_g_kg: float
    summary: str

class MandiMarketItem(BaseModel):
    stale: bool = False
    market: str
    district: str
    state: str
    commodity: str
    variety: Optional[str] = ""
    min_price: float
    max_price: float
    modal_price: float
    date: str

class MandiResponse(BaseModel):
    source: Optional[str] = None
    retrieved_at: Optional[str] = None
    data_kind: Optional[str] = None
    status: str = "success"
    error: Optional[str] = None
    commodity: str
    state: str
    markets: List[MandiMarketItem]
    best_market: Optional[MandiMarketItem] = None
    total_found: int = 0
    note: Optional[str] = None

class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=6000)
    language: str = "hi"

class TTSResponse(BaseModel):
    audio_base64: Optional[str] = None
    format: str = "audio/wav"
    error: Optional[str] = None

class STTResponse(BaseModel):
    text: str
    language: str
    confidence: Optional[float] = None


class ProfileUpdate(BaseModel):
    location_name: Optional[str] = Field(None, max_length=200)
    latitude: Optional[float] = Field(None, ge=-90, le=90, allow_inf_nan=False)
    longitude: Optional[float] = Field(None, ge=-180, le=180, allow_inf_nan=False)
    state: Optional[str] = Field(None, max_length=100)
    district: Optional[str] = Field(None, max_length=100)
    land_size_acres: Optional[float] = Field(None, ge=0, le=100000, allow_inf_nan=False)
    primary_crop: Optional[str] = Field(None, max_length=200)
    soil_type: Optional[str] = Field(None, max_length=100)
    language: Optional[str] = Field(None, pattern=r"^[a-z]{2}$")
