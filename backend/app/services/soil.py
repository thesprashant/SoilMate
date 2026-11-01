import asyncio
from io import BytesIO
import math
from typing import Any, Dict

import httpx
from PIL import Image, UnidentifiedImageError

from app.services.references import timestamp


SOILGRIDS_WCS = "https://maps.isric.org/mapserv"
SOIL_PROPERTIES = ("phh2o", "clay", "sand", "silt", "soc", "nitrogen")


def classify_soil_texture(sand: float, silt: float, clay: float) -> str:
    """Classify soil texture based on USDA soil triangle approximations."""
    if sand >= 85.0 and (silt + 1.5 * clay) < 15.0:
        return "Sandy"
    if sand >= 70.0 and (silt + 2.0 * clay) < 30.0:
        return "Loamy Sand"
    if 7.0 <= clay <= 27.0 and 28.0 <= silt <= 50.0 and sand <= 52.0:
        return "Loam"
    if clay >= 40.0:
        return "Clayey"
    if 27.0 <= clay < 40.0 and sand <= 45.0:
        return "Clay Loam"
    if sand >= 43.0 and clay < 20.0 and silt < 50.0:
        return "Sandy Loam"
    if silt >= 80.0:
        return "Silty"
    if silt >= 50.0 and 12.0 <= clay < 27.0:
        return "Silt Loam"
    return "Loamy"


def interpret_soil_ph(ph: float) -> str:
    """Provide agricultural interpretation of soil pH."""
    if ph < 5.0:
        return "Extremely acidic — heavy liming (agricultural lime/dolomite) required to restore nutrient uptake."
    if ph < 5.8:
        return "Strongly to moderately acidic — suitable for acid-tolerant crops (tea, potato, rice); apply lime for pulses."
    if ph < 6.5:
        return "Slightly acidic — favorable for most cereals, millets, and pulses."
    if ph <= 7.5:
        return "Neutral (optimal) — ideal pH range with maximum availability of N, P, K, and micronutrients."
    if ph <= 8.5:
        return "Moderately alkaline — common in arid/black soils; watch for iron and zinc deficiency; avoid over-liming."
    return "Strongly alkaline / saline — gypsum application and drainage leaching needed to reduce sodicity."


def _nearest_valid_pixel(payload: bytes) -> tuple[float, float]:
    """Return the nearest non-zero coverage value and its approximate offset."""
    with Image.open(BytesIO(payload)) as image:
        image.load()
        width, height = image.size
        pixels = list(image.getdata())
    cx, cy = (width - 1) / 2, (height - 1) / 2
    candidates = []
    for index, value in enumerate(pixels):
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric) or numeric <= 0:
            continue
        x, y = index % width, index // width
        candidates.append((math.hypot(x - cx, y - cy), numeric))
    if not candidates:
        raise ValueError("Coverage contains no valid pixels")
    distance, value = min(candidates)
    # The request spans 0.04 degrees (about 4.45 km north/south).
    offset_km = distance * (4.45 / max(width - 1, height - 1, 1))
    return value, offset_km


async def _fetch_property(client: httpx.AsyncClient, name: str, lat: float, lon: float) -> tuple[str, float, float]:
    radius = 0.02
    params = [
        ("map", f"/map/{name}.map"), ("SERVICE", "WCS"), ("VERSION", "2.0.1"),
        ("REQUEST", "GetCoverage"), ("COVERAGEID", f"{name}_0-5cm_mean"),
        ("SUBSET", f"x({lon - radius:.6f},{lon + radius:.6f})"),
        ("SUBSET", f"y({lat - radius:.6f},{lat + radius:.6f})"),
        ("SUBSETTINGCRS", "http://www.opengis.net/def/crs/EPSG/0/4326"),
        ("FORMAT", "image/tiff"),
    ]
    response = await client.get(SOILGRIDS_WCS, params=params)
    response.raise_for_status()
    value, offset_km = await asyncio.to_thread(_nearest_valid_pixel, response.content)
    return name, value, offset_km


async def get_soil_properties(lat: float, lon: float) -> Dict[str, Any]:
    """Fetch SoilGrids topsoil estimates through the supported WCS endpoint."""
    try:
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "SoilMate/1.0"}) as client:
            rows = await asyncio.gather(*(_fetch_property(client, p, lat, lon) for p in SOIL_PROPERTIES))
        properties = {name: value for name, value, _ in rows}
        max_offset_km = max(offset for _, _, offset in rows)

        ph = round(properties["phh2o"] / 10.0, 1)
        sand_pct = round(properties["sand"] / 10.0, 1)
        silt_pct = round(properties["silt"] / 10.0, 1)
        clay_pct = round(properties["clay"] / 10.0, 1)
        soc = round(properties["soc"] / 10.0, 1)
        nitrogen = round(properties["nitrogen"] / 100.0, 2)
        if not 0 < ph <= 14 or not 95 <= sand_pct + silt_pct + clay_pct <= 105:
            raise ValueError("Invalid SoilGrids values")

        soil_type = classify_soil_texture(sand_pct, silt_pct, clay_pct)
        ph_interp = interpret_soil_ph(ph)
        summary = (f"Texture: {soil_type} ({sand_pct}% sand, {silt_pct}% silt, {clay_pct}% clay). "
                   f"pH: {ph} ({ph_interp}). Organic carbon: {soc} g/kg.")
        proximity = (f" Nearest valid model pixels were within approximately {max_offset_km:.1f} km."
                     if max_offset_km >= 0.1 else "")
        return {
            "source": SOILGRIDS_WCS, "retrieved_at": timestamp(), "data_kind": "gridded_prediction",
            "note": "SoilGrids 250 m mean model estimate for 0-5 cm depth, not a field laboratory measurement."
                    + proximity + " Local soil testing is needed for input prescriptions.",
            "lat": lat, "lon": lon, "ph": ph, "ph_interpretation": ph_interp,
            "soil_type": soil_type, "sand_pct": sand_pct, "silt_pct": silt_pct,
            "clay_pct": clay_pct, "organic_carbon_g_kg": soc,
            "nitrogen_g_kg": nitrogen, "summary": summary,
        }
    except (httpx.HTTPError, OSError, UnidentifiedImageError, ValueError, TypeError, KeyError):
        return {"status": "unavailable", "error": "SoilGrids has no usable model coverage for these coordinates. Obtain a local soil test; no measurements have been substituted.",
                "lat": lat, "lon": lon, "source": SOILGRIDS_WCS, "retrieved_at": timestamp()}
