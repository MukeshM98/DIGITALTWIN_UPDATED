# Data Sources, Calibration, and Limitations

**Geographic Target:** Srirangam Island, Tiruchirappalli, Tamil Nadu, India  
**Bounding Box:**
- South: 10.8565°N
- West: 78.6820°E
- North: 10.8820°N
- East: 78.7050°E
- CRS: EPSG:4326 (WGS84)
- Vertical Datum: EGM96 / MSL

---

## Data Sources

1. **Elevation & Terrain:**
   - Source: SRTM 30m Digital Elevation Model published via AWS Terrarium elevation tiles.
   - Stored Local Grid: `backend/data/srirangam_dem.npz` (512x512 matrix, ~19.1m cell resolution).
   - Ground Elevation Range: 49.0 m to 94.0 m MSL (average ~69.1 m MSL). Riverbed depths at Kaveri and Kollidam channels are ~68.5–70.5 m MSL; central temple ridges are ~74.0–78.0 m MSL.

2. **Hydrographic Channels:**
   - Cauvery (Kaveri) River: Southern island river boundary (`river.geojson`).
   - Kollidam (Coleroon) River: Northern island flood carrier channel (`river.geojson`).

3. **Gauging Stations:**
   - Mukkombu (Upper Anicut) Regulator: Upstream division point between Kaveri and Kollidam.
   - Srirangam Cauvery Bridge (Amma Mandapam): South island monitoring point.
   - Kollidam Road Bridge & Regulator: North flood carrier discharge gauge.
   - Grand Anicut (Kallanai): Downstream delta division reference.

4. **Building Footprints & Infrastructure:**
   - 3D OpenStreetMap vector building layers + prominent landmarks in `buildings.geojson` (Sri Ranganathaswamy Temple Complex, Rajagopuram, Government Hospital, Railway Station, Melur Agricultural Settlement, Amma Mandapam riverfront community).

5. **Live Weather:**
   - Open-Meteo free meteorological API for coordinates (10.865°N, 78.693°E), with automatic caching and offline profile fallback.

---

## Hydrological Assumptions and Limitations

- **Connectivity Model:** The simulation engine employs an 8-neighbor surface elevation connectivity propagation (BFS) seeded from the river channels. It strictly prevents disconnected inland depressions with elevation $\le \text{WSE}$ from falsely inundating without an unbroken hydraulic path.
- **Physical Water Depth:** Calculated as:
  $$\text{Water Depth} = \max(0, \text{WSE} - \text{Ground Elevation})$$
- **Simplifications:**
  - Dynamic momentum, friction loss (Manning's $n$), and turbulent shallow-water Saint-Venant equations are not solved in real-time in this web prototype.
  - Infiltration and soil percolation are approximated through SCS Curve Number adjustments.
  - Culverts, underground stormwater drainage pipes, and localized sandbag levees are not represented in 30m DEM.
- **Disclaimer:** This tool is designed for educational, academic, and disaster preparedness research demonstration. Do not use for official emergency evacuations or civil defense directives.
