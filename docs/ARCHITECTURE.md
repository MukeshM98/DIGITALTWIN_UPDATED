# Architecture — FloodSense DT

```mermaid
flowchart TD
  subgraph Data Sources
    A[OpenFreeMap Vector Tiles]
    B[AWS Terrarium SRTM 30m DEM Tiles]
    C[Open-Meteo Meteorological API]
    D[Srirangam GeoJSON & Buildings Footprints]
  end

  subgraph Backend Service [FastAPI & Hydrological Engine]
    E[FastAPI Endpoints: /api/simulate, /api/weather, /api/elevation]
    F[FloodSimulationEngine]
    G[8-Neighbor BFS Surface Connectivity Solver]
    H[Building Vulnerability & Risk Tier Classifier]
  end

  subgraph Frontend 3D Digital Twin [MapLibre GL JS]
    I[MapLibre 3D Terrain & Building Extrusions]
    J[3D Camera Controls Toolbar: Rotate, Tilt, Zoom, 2D/3D]
    K[Timeline Player & Flood Inundation Animator]
    L[Live Pointer Elevation & Depth Inspector]
    M[Simulation Insights & Infrastructure Impact Panel]
  end

  A --> I
  B --> I
  C --> E
  D --> F
  B --> F
  E --> F
  F --> G
  G --> H
  H --> E
  E --> Frontend
  Frontend --> E
```

### Component Details
1. **Frontend:** Single-page application built with vanilla HTML5, CSS3, and modern JavaScript, powered by MapLibre GL JS v5.6.1. Supports full camera degree-of-freedom rotations, vertical pitch up to 75°, live elevation sampling, and multi-timestep animated inundation playback.
2. **Hydrological Simulation Engine:** Implemented in `backend/flood_simulation.py`. Samples the real SRTM 30m DEM grid (512x512 matrix), detects river channel seed coordinates along the Kaveri and Kollidam rivers, computes Water Surface Elevation (WSE) from scenario rainfall and surge parameters, and traverses surface elevation via 8-connected BFS.
3. **API Layer:** FastAPI with Pydantic validation, CORS middleware, in-memory caching for meteorological conditions, and full static file hosting.
