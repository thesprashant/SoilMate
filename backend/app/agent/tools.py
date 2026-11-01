import json
import os
import time
from typing import Dict, Any, List
from google.genai import types

from app.services.weather import get_weather_forecast, geocode_location
from app.services.soil import get_soil_properties
from app.services.mandi import get_mandi_prices
from app.services.references import crop_reference
from app.models.schemas import LocationInput, ProfileUpdate
from app.agent.advisories import schedule_decl

# Define tool schemas for Gemini Function Calling
weather_decl = types.FunctionDeclaration(
    name="get_weather",
    description="Fetch live 7-day weather forecast, temperature, rainfall, humidity, and agro-weather alerts for a location.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "latitude": types.Schema(type="NUMBER", description="Latitude coordinate of the farm/village"),
            "longitude": types.Schema(type="NUMBER", description="Longitude coordinate of the farm/village")
        },
        required=["latitude", "longitude"]
    )
)

soil_decl = types.FunctionDeclaration(
    name="get_soil_data",
    description="Fetch live soil properties (pH, texture, sand/silt/clay %, organic carbon, nitrogen) from ISRIC SoilGrids.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "latitude": types.Schema(type="NUMBER", description="Latitude coordinate"),
            "longitude": types.Schema(type="NUMBER", description="Longitude coordinate")
        },
        required=["latitude", "longitude"]
    )
)

mandi_decl = types.FunctionDeclaration(
    name="get_mandi_prices",
    description="Fetch live commodity prices across APMC mandis from Agmarknet (data.gov.in) with price comparisons.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "state": types.Schema(type="STRING", description="Indian state name (e.g. 'Rajasthan', 'Madhya Pradesh', 'Maharashtra')"),
            "commodity": types.Schema(type="STRING", description="Crop/commodity name in English (e.g. 'Wheat', 'Mustard', 'Soybean', 'Onion')")
        },
        required=["state", "commodity"]
    )
)

crops_decl = types.FunctionDeclaration(
    name="query_crop_database",
    description="Fetch an official TNAU crop reference for wheat, rice/paddy or potato. Specify the crop. Regional applicability must be checked.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "crop": types.Schema(type="STRING", description="Crop name, required for official reference lookup"),
            "season": types.Schema(type="STRING", description="Farming season: 'kharif' (monsoon), 'rabi' (winter), or 'zaid' (summer)"),
            "soil_type": types.Schema(type="STRING", description="Soil texture type (e.g. 'Loamy', 'Sandy Loam', 'Clayey', 'Clay Loam')"),
            "state": types.Schema(type="STRING", description="Optional state name to filter regional crops")
        }, required=["crop"]
    )
)

pest_decl = types.FunctionDeclaration(
    name="get_pest_and_disease_risk",
    description="Analyze pest and disease vulnerability for a specific crop under current temperature, humidity, and rainfall conditions.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "crop": types.Schema(type="STRING", description="Crop name (e.g. 'Paddy', 'Cotton', 'Wheat', 'Soybean')"),
            "temp_max": types.Schema(type="NUMBER", description="Maximum temperature in Celsius"),
            "humidity": types.Schema(type="NUMBER", description="Relative humidity percentage"),
            "rainfall": types.Schema(type="NUMBER", description="Precipitation in mm")
        },
        required=["crop"]
    )
)

schemes_decl = types.FunctionDeclaration(
    name="get_government_schemes",
    description="Look up eligible Central and State Government agricultural subsidy, insurance (PMFBY), and income support (PM-KISAN) schemes.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "query": types.Schema(type="STRING", description="Keywords such as 'income', 'insurance', 'soil test', 'drip irrigation', 'loan'")
        }
    )
)

profile_decl = types.FunctionDeclaration(
    name="update_farmer_profile",
    description="Save or update the farmer's profile, location (village, district, or state), land size, soil type, and primary crops. Automatically geocodes location coordinates.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "location_name": types.Schema(type="STRING", description="Name of village, town, district or state mentioned by the farmer (e.g. 'Nashik', 'Sehore, MP', 'Guntur, AP', 'Punjab')"),
            "state": types.Schema(type="STRING", description="Indian state name if recognized (e.g. 'Maharashtra', 'Madhya Pradesh', 'Punjab')"),
            "district": types.Schema(type="STRING", description="District name if recognized"),
            "land_size_acres": types.Schema(type="NUMBER", description="Size of farmer's landholding in acres if mentioned"),
            "primary_crops": types.Schema(type="STRING", description="Crop(s) currently cultivated or planned (e.g. 'Wheat', 'Mustard', 'Cotton')"),
            "soil_type": types.Schema(type="STRING", description="Soil texture/type described by farmer (e.g. 'Black soil', 'Sandy loam', 'Clayey')")
        }
    )
)

AGENT_TOOLS = types.Tool(function_declarations=[schedule_decl,
    weather_decl,
    soil_decl,
    mandi_decl,
    crops_decl,
    pest_decl,
    schemes_decl,
    profile_decl
])

# Legacy unverified catalogs are intentionally not loaded.
def load_crops_data():
    return []

def load_schemes_data():
    return []

async def execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Central async tool dispatcher."""
    t0 = time.time()
    try:
        if name == "get_weather":
            lat = LocationInput(lat=args["latitude"], lon=args["longitude"]).lat
            lon = float(args["longitude"])
            res = await get_weather_forecast(lat, lon)
            return res

        elif name == "get_soil_data":
            lat = LocationInput(lat=args["latitude"], lon=args["longitude"]).lat
            lon = float(args["longitude"])
            res = await get_soil_properties(lat, lon)
            return res

        elif name == "get_mandi_prices":
            state = str(args.get("state", ""))
            commodity = str(args.get("commodity", ""))
            res = await get_mandi_prices(state, commodity)
            return res

        elif name == "query_crop_database":
            return await crop_reference(**args)

        elif name == "get_pest_and_disease_risk":
            return {"status": "unavailable", "error": "No validated crop-specific pest forecasting model is connected. Weather alone cannot diagnose an outbreak. Seek local extension advice; no pesticide dosage is inferred."}

        elif name == "get_government_schemes":
            return {"status": "unavailable", "error": "Live eligibility verification is not connected. Consult the official scheme portal; no eligibility or benefit amounts are inferred.", "source": "https://www.myscheme.gov.in/"}

        elif name == "update_farmer_profile":
            loc = args.get("location_name")
            geocoded = None
            if loc:
                geocoded = await geocode_location(loc)
                if not geocoded:
                    return {
                        "status": "unavailable",
                        "error": "Location could not be resolved. Ask for a more specific village, district, or coordinates. The saved location was not changed."
                    }

            lat = geocoded["lat"] if geocoded else None
            lon = geocoded["lon"] if geocoded else None
            norm_name = geocoded["name"] if geocoded else loc
            state = geocoded.get("state") if (geocoded and geocoded.get("state")) else args.get("state")

            ProfileUpdate(location_name=norm_name, latitude=lat, longitude=lon, land_size_acres=args.get("land_size_acres"), primary_crop=args.get("primary_crops"), soil_type=args.get("soil_type"))
            return {
                "status": "profile_updated",
                "location_name": norm_name,
                "latitude": lat,
                "longitude": lon,
                "state": state,
                "district": args.get("district"),
                "land_size_acres": args.get("land_size_acres"),
                "primary_crops": args.get("primary_crops"),
                "soil_type": args.get("soil_type"),
                "message": f"Successfully updated and remembered profile for {norm_name or 'farmer'}."
            }

        else:
            return {"error": f"Unknown tool '{name}'"}

    except Exception as e:
        return {"status": "unavailable", "error": f"Tool {name} failed ({type(e).__name__}). Check inputs or retry later."}

