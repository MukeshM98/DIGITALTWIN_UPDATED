from pathlib import Path
import json
import time
import urllib.request
import ssl
import os
from fastapi.middleware.gzip import GZipMiddleware
from backend.routing import router
from typing import Literal, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.flood_simulation import engine

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT.parent / "frontend"
DATA_DIR = ROOT / "data"

app = FastAPI(
    title="FloodSense DT — 3D Digital Twin API",
    version="2.0.0",
    description="Terrain-aware 3D flood digital twin simulation API for Srirangam Island, Tiruchirappalli, Tamil Nadu."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

class ScenarioRequest(BaseModel):
    rainfall_mm_24h: float = Field(default=80.0, ge=0.0, le=300.0, description="24-hour rainfall accumulation in mm")
    scenario: Literal["rainfall", "rapid-rise", "breach", "dry"] = Field(
        default="rainfall",
        description="Scenario profile: 'rainfall' (monsoon precipitation), 'rapid-rise' (upstream dam release surge), 'breach' (embankment breach)"
    )

    peak_rise_m: Optional[float] = Field(default=None, ge=0, le=10, description="Explicit illustrative peak stage rise above 69.5 m baseline")

# Cache for Open-Meteo weather
_weather_cache = {"timestamp": 0, "data": None}

@app.get("/api")
def root_api():
    return {
        "name": "FloodSense DT — 3D Digital Twin API",
        "version": "2.0.0",
        "study_area": "Srirangam Island, Tiruchirappalli, Tamil Nadu, India",
        "focus_coordinates": {"latitude": 10.865, "longitude": 78.693, "crs": "EPSG:4326"},
        "status": "operational",
        "terrain_engine": "Prepared Mapzen terrain / four-neighbour connectivity",
        "docs": "/docs"
    }

@app.get("/api/health")
def health():
    dem_loaded = engine.elevation_grid is not None
    return {
        "status": "ok",
        "study_area": "Srirangam Island, Tiruchirappalli",
        "dem_loaded": dem_loaded,
        "dem_shape": list(engine.elevation_grid.shape) if dem_loaded else None,
        "mode": "terrain-aware-simulation",
        "version": "2.0.0"
    }

@app.get("/api/metadata")
def metadata():
    return {
        "project": "FloodSense DT — AI-Powered Disaster Response Digital Twin",
        "location": {
            "name": "Srirangam Island",
            "district": "Tiruchirappalli",
            "state": "Tamil Nadu",
            "country": "India",
            "center": [78.693, 10.865],
            "recommended_camera": {
                "longitude": 78.693,
                "latitude": 10.865,
                "altitude_m": 2000,
                "pitch_deg": 58,
                "bearing_deg": -20
            },
            "bounding_box": engine.meta["bounds"]
        },
        "crs": "EPSG:4326 (WGS84)",
        "vertical_datum": engine.meta["vertical_datum"],
        "dem": engine.meta
    }

@app.get("/api/weather")
def weather():
    """
    Fetches real-time weather for Srirangam / Tiruchirappalli via Open-Meteo.
    Includes memory caching (10 min TTL) and reliable offline fallback.
    """
    now = time.time()
    if _weather_cache["data"] and (now - _weather_cache["timestamp"] < 600):
        return {**_weather_cache["data"], "status": "cached", "is_cached": True}

    url = "https://api.open-meteo.com/v1/forecast?latitude=10.865&longitude=78.693&current=temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m&forecast_days=1"
    try:
        if os.environ.get("FLOODSENSE_OFFLINE") == "1":
            raise ConnectionError("Offline configuration")
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "FloodSenseDT/2.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=4) as resp:
            data = json.loads(resp.read().decode())
            current = data.get("current", {})
            weather_payload = {
                "status": "live",
                "source": "Open-Meteo Weather API",
                "location": "Srirangam Island (10.865°N, 78.693°E)",
                "observation_time": current.get("time"),
                "temperature_c": current.get("temperature_2m", 29.0),
                "relative_humidity_pct": current.get("relative_humidity_2m", 75),
                "precipitation_mm": current.get("precipitation", 0.0),
                "wind_speed_kmh": current.get("wind_speed_10m", 8.5),
                "weather_code": current.get("weather_code", 1),
                "is_cached": False
            }
            _weather_cache["timestamp"] = now
            _weather_cache["data"] = weather_payload
            return weather_payload
    except Exception as e:
        fallback = {
            "status": "offline_fallback",
            "source": "Illustrative weather sample, not an observation",
            "location": "Srirangam Island (10.865°N, 78.693°E)",
            "observation_time": "Regional Fallback Estimate",
            "temperature_c": 29.5,
            "relative_humidity_pct": 74,
            "precipitation_mm": 0.0,
            "wind_speed_kmh": 9.2,
            "weather_code": 1,
            "note": f"Live meteorological service fallback ({type(e).__name__})"
        }
        return fallback

@app.post("/api/scenario")
def scenario(p: ScenarioRequest):
    """Calculates scenario risk score and peak hydrological indicators."""
    sim = engine.simulate(p.rainfall_mm_24h, p.scenario, p.peak_rise_m)
    summary = sim["summary"]
    return {
        "rainfall_mm_24h": p.rainfall_mm_24h,
        "scenario": p.scenario,
        "risk_index": summary["risk_index"],
        "risk_level": summary["risk_level"],
        "peak_wse_m": summary["peak_wse_m"],
        "water_level_change_m": summary["peak_water_level_change_m"],
        "inundated_sqkm": summary["max_inundated_sqkm"],
        "affected_buildings_count": summary["total_affected_buildings"],
        "highest_risk_sector": summary["highest_risk_sector"],
        "method": "Educational connected-stage scenario"
    }

@app.post("/api/simulate")
def simulate(p: ScenarioRequest):
    """
    Executes full multi-timestep terrain-aware flood simulation.
    Returns GeoJSON animation frames, building impact assessments, and simulation insights.
    """
    return engine.simulate(p.rainfall_mm_24h, p.scenario, p.peak_rise_m)

@app.get("/api/elevation")
def get_elevation_point(lon: float = Query(..., ge=78.60, le=78.80), lat: float = Query(..., ge=10.80, le=10.95)):
    """Returns sampled coarse grid elevation in metres MSL for a queried coordinate."""
    try:
        elev = engine.get_elevation(lon, lat)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {
        "longitude": lon,
        "latitude": lat,
        "ground_elevation_m": round(elev, 2),
        "vertical_datum": "EGM96 / MSL",
        "source": engine.meta["source"]
    }

@app.get("/api/river")
def river():
    p = DATA_DIR / "river.geojson"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"type": "FeatureCollection", "features": []}

@app.get("/api/monitoring-points")
def points():
    p = DATA_DIR / "monitoring-points.geojson"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"type": "FeatureCollection", "features": []}

@app.get("/api/buildings")
def buildings():
    p = FRONTEND_DIR / "data/buildings-osm.geojson"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"type": "FeatureCollection", "features": []}

app.add_middleware(GZipMiddleware, minimum_size=1000)

class RouteRequest(BaseModel):
    start: tuple[float, float]
    end: tuple[float, float]
    wse_m: float = Field(ge=50, le=100)

@app.post("/api/route")
def route(p: RouteRequest):
    if not engine.inside(*p.start) or not engine.inside(*p.end):
        raise HTTPException(422, "Route endpoints outside study area")
    return router.route(p.start, p.end, p.wse_m)

@app.get("/api/inspect")
def inspect(lon: float, lat: float, wse_m: float = Query(69.5, ge=50, le=100)):
    try:
        elevation = engine.get_elevation(lon,lat)
    except ValueError as exc:
        raise HTTPException(404,str(exc))
    r,c=engine.coord_to_grid(lon,lat)
    return {"ground_elevation_m": elevation, "depth_m": float(engine.depth_at_stage(wse_m)[r,c]), "baseline_water": bool(engine.water_mask[r,c]), "wse_m": wse_m, "datum": engine.meta["vertical_datum"]}

# Mount frontend static files so the digital twin runs seamlessly on port 8000
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
