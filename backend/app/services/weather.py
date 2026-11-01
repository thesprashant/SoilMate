from typing import Dict, Any, List, Optional
import logging
import httpx
from app.services.references import timestamp

logger = logging.getLogger(__name__)

async def geocode_location(query: str) -> Optional[Dict[str, Any]]:
    """Convert city/village/district name to coordinates using Open-Meteo Geocoding API."""
    if not query or not query.strip():
        return None

    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": query.strip(),
        "count": 1,
        "language": "en",
        "format": "json"
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params, timeout=8.0)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results")
                if results and len(results) > 0:
                    r = results[0]
                    return {
                        "name": r.get("name", query),
                        "lat": float(r.get("latitude")),
                        "lon": float(r.get("longitude")),
                        "state": r.get("admin1"),
                        "country": r.get("country")
                    }
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            logger.warning("Geocoding provider unavailable or returned invalid data")
    return None

def compute_weather_alerts(daily: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Derive agricultural alert notifications from weather forecast."""
    alerts = []
    times = daily.get("time", [])
    max_temps = daily.get("temperature_2m_max", [])
    min_temps = daily.get("temperature_2m_min", [])
    precip_sums = daily.get("precipitation_sum", [])
    
    consecutive_dry_days = 0

    for i in range(len(times)):
        date = times[i]
        t_max = max_temps[i] if i < len(max_temps) else None
        t_min = min_temps[i] if i < len(min_temps) else None
        rain = precip_sums[i] if i < len(precip_sums) else None

        if t_max is not None and t_max >= 40.0:
            alerts.append({
                "date": date,
                "type": "HEATWAVE_WARNING",
                "message": f"High heat ({t_max}°C). Mulch soil and schedule morning/evening irrigation to reduce evapotranspiration.",
                "severity": "high" if t_max >= 43.0 else "medium"
            })

        if t_min is not None and t_min <= 4.0:
            alerts.append({
                "date": date,
                "type": "FROST_WARNING",
                "message": f"Near-freezing temperature ({t_min}°C). Check local extension guidance for protecting sensitive seedlings.",
                "severity": "high"
            })

        if rain is not None and rain >= 40.0:
            alerts.append({
                "date": date,
                "type": "HEAVY_RAIN_ALERT",
                "message": f"Heavy rainfall expected ({rain} mm). Clear field drains immediately. Avoid pesticide/fertilizer spraying.",
                "severity": "high" if rain >= 65.0 else "medium"
            })

        if rain is not None and rain < 1.0:
            consecutive_dry_days += 1
        else:
            consecutive_dry_days = 0

    if consecutive_dry_days >= 5:
        alerts.append({
            "date": times[0] if times else "upcoming",
            "type": "DRY_SPELL",
            "message": f"Dry conditions ahead for {consecutive_dry_days}+ days. Plan supplemental irrigation cycles.",
            "severity": "low"
        })

    return alerts

async def get_weather_forecast(lat: float, lon: float) -> Dict[str, Any]:
    """Fetch 7-day agricultural weather forecast from Open-Meteo."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation",
            "weather_code",
            "wind_speed_10m"
        ],
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "precipitation_probability_max",
            "wind_speed_10m_max"
        ],
        "timezone": "Asia/Kolkata",
        "forecast_days": 7
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=12.0)
        resp.raise_for_status()
        data = resp.json()

    daily = data.get("daily", {})
    alerts = compute_weather_alerts(daily)

    return {
        "location": {"lat": lat, "lon": lon},
        "current": data.get("current", {}),
        "daily": daily,
        "alerts": alerts,
        "source": url, "retrieved_at": timestamp(), "data_kind": "weather_model_forecast",
        "note": "Seven-day model forecast; alerts are heuristic weather thresholds, not official crop diagnoses."
    }

