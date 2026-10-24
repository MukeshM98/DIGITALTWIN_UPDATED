# FloodSense DT — AI-Powered Disaster Response Digital Twin

**Study Area:** Srirangam Island, Tiruchirappalli, Tamil Nadu, India  
**Geographic Coordinates:** Center `[78.693°E, 10.865°N]`, Viewing Altitude: ~2,000m  
**CRS:** EPSG:4326 (WGS84) | **Vertical Datum:** EGM96 / Mean Sea Level (MSL)  

FloodSense DT is an interactive, terrain-aware 3D flood disaster response digital twin. It models surface water inundation across Srirangam Island—the river delta bounded by the **Kaveri (Cauvery) River** to the south and the **Kollidam (Coleroon) River** to the north.

---

## Key Features

1. **Full 3D Camera Controls:**
   - Smooth horizontal 360° rotation (`Rot L`, `Rot R`)
   - Vertical tilt control up to 75° pitch (`Tilt Up`, `Tilt Down`)
   - Zoom in/out, North-up compass alignment, and Srirangam overview reset
   - One-click toggle between 2D Top-Down and 3D Perspective views
   - Intuitive mouse & touch gestures (left drag to pan, right drag or Ctrl+drag to rotate/tilt, scroll to zoom)

2. **Terrain-Aware Hydrological Simulation:**
   - 8-neighbor surface elevation connectivity algorithm using real SRTM 30m DEM
   - Prevents disconnected inland depressions from falsely flooding without a hydraulic river connection
   - Water Depth calculation: `Water Depth = max(0, Water Surface Elevation - Ground Elevation)`
   - Multi-timestep flood spreading timeline (`t = 0h` to `24h`)
   - Interactive timeline scrubber with Play, Pause, Reset, and Speed multipliers (1x, 2x, 4x)

3. **3D Terrain & Building Detail:**
   - Real-time elevation tiles via AWS Terrarium encoding
   - 3D extruded OpenStreetMap vector buildings and designated Srirangam landmark structures (Sri Ranganathaswamy Temple, Rajagopuram, Government Hospital, Railway Station, Melur agricultural settlement, Amma Mandapam riverfront)
   - Real-time Pointer Elevation Inspector: move mouse or click anywhere on the map to inspect ground elevation and estimated water depth

4. **Vulnerability & Infrastructure Risk Assessment:**
   - Prototype building damage risk tiers:
     - **Safe:** Depth $\le 0.05$ m
     - **Minor:** Depth $0.05$ m – $0.5$ m
     - **Moderate:** Depth $0.5$ m – $1.5$ m
     - **Severe:** Depth $> 1.5$ m
   - Interactive building cards in sidebar: click to fly camera to the structure and view its risk profile

5. **Live Meteorological Conditions:**
   - Integrated Open-Meteo API feed for Tiruchirappalli / Srirangam (temperature, humidity, precipitation, wind speed) with offline caching and graceful fallback

6. **FastAPI Backend & Test Suite:**
   - Modular Python simulation engine in `backend/flood_simulation.py`
   - Complete REST endpoints for metadata, health, weather, scenario, simulation, and elevation query
   - Automated pytest suite verifying geographic bounds, coordinate ordering, monotonic inundation, depth validity, and isolated depression rejection

---

## Quickstart (Windows)

### 1. Run Frontend Only
```powershell
cd frontend
py -m http.server 5173
```
Open **http://localhost:5173** in your browser (or double-click `RUN_FRONTEND.bat`).

### 2. Run API Backend & Full Integrated Digital Twin
```powershell
# From project root:
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.main:app --reload --port 8000
```
- Digital Twin Web Application: **http://localhost:8000**
- Interactive Swagger API Documentation: **http://localhost:8000/docs**

---

## Running Automated Tests

Run the full pytest suite from the project root:
```powershell
py -m pytest backend/tests -v
```

---

## Hydrological Model & Limitations

- **Inundation Solver:** The current prototype implements an 8-neighbor surface connectivity elevation inundation engine. While it strictly enforces hydraulic connectivity from river channels and physical DEM constraints, it is not a 2D hydrodynamic Saint-Venant shallow water numerical solver (such as HEC-RAS 2D or LISFLOOD-FP).
- **DEM Resolution:** SRTM elevation raster is approx 30m resolution (~19m raster cell). Small localized storm drains, roadside gutters, and micro-levees may not be resolved in 30m data.
- **Damage Risk Tiers:** Risk categories (Minor, Moderate, Severe) are academic prototype thresholds, not official structural engineering certifications.
- **Disclaimer:** This system is an academic research and demonstration digital twin. It must not be used as an official emergency warning or disaster evacuation directive without calibration and endorsement by civil defense authorities.
