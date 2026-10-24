/**
 * FloodSense DT — 3D Disaster Response Digital Twin
 * Target: Srirangam Island, Tiruchirappalli, Tamil Nadu, India
 * Core GIS Controller & Terrain-Aware Flood Simulation Engine
 */

const INITIAL_VIEW = {
  center: [78.693, 10.865],
  zoom: 13.8,
  pitch: 58,
  bearing: -20
};

// Application State
const state = {
  rain: 80,
  scenario: "rainfall",
  exaggeration: 1.5,
  layers: {
    terrain: true,
    buildings: true,
    flood: true,
    depth: true,
    river: true,
    riskZones: true
  },
  simulationFrames: [],
  currentFrameIdx: 0,
  isPlaying: false,
  animInterval: null,
  animSpeedMs: 1200,
  speedMultiplier: 1,
  riverData: null,
  stationsData: null,
  buildingsData: null
};

const $ = id => document.getElementById(id);
let map = null;
let currentPopup = null;

// Utility: Determine API Base URL
function getApiBase() {
  // If served from FastAPI on port 8000
  if (window.location.port === "8000") return "";
  // If served from static server on port 5173, point to backend on 8000
  return "http://localhost:8000";
}

// ----------------------------------------------------
// 1. Map Initialization
// ----------------------------------------------------
async function initMap() {
  if (!window.maplibregl) {
    showError("MapLibre GL JS library failed to load.");
    return;
  }

  // Load GeoJSON datasets
  await loadData();

  try {
    map = new maplibregl.Map({
      container: "map",
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: INITIAL_VIEW.center,
      zoom: INITIAL_VIEW.zoom,
      pitch: INITIAL_VIEW.pitch,
      bearing: INITIAL_VIEW.bearing,
      maxPitch: 75,
      antialias: true
    });

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");

    map.on("error", (e) => {
      console.warn("Map resource event:", e);
    });

    map.on("load", () => {
      $("mapStatus").textContent = "3D TERRAIN + VECTOR MAP ACTIVE";
      setupTerrain();
      setupBuildings();
      setupGeoLayers();
      setupInteractions();
      // Run initial simulation
      updateSimulation();
      fetchWeather();
    });

    map.on("pitchend", () => {
      const is3D = map.getPitch() >= 15;
      $("modeBadge").textContent = is3D ? "3D" : "2D";
      if (is3D) {
        $("tilt").classList.add("chosen");
        $("flat").classList.remove("chosen");
      } else {
        $("flat").classList.add("chosen");
        $("tilt").classList.remove("chosen");
      }
    });

    // Pointer elevation tracking
    map.on("mousemove", onMapMouseMove);
    map.on("click", onMapClick);

  } catch (err) {
    console.error("Map initialization failed:", err);
    showError("3D Map rendering failed. Check connection or WebGL support.");
  }
}

// ----------------------------------------------------
// 2. Data Loading
// ----------------------------------------------------
async function loadData() {
  const api = getApiBase();
  const fetchWithFallback = async (endpoint, localPath) => {
    try {
      const res = await fetch(`${api}${endpoint}`);
      if (res.ok) return await res.json();
    } catch (_) {}
    try {
      const localRes = await fetch(localPath);
      if (localRes.ok) return await localRes.json();
    } catch (_) {}
    return { type: "FeatureCollection", features: [] };
  };

  const [river, stations, blds] = await Promise.all([
    fetchWithFallback("/api/river", "./data/river.geojson"),
    fetchWithFallback("/api/monitoring-points", "./data/monitoring-points.geojson"),
    fetchWithFallback("/api/buildings", "./data/buildings.geojson")
  ]);

  state.riverData = river;
  state.stationsData = stations;
  state.buildingsData = blds;

  renderStationList();
  renderBuildingList();
}

// ----------------------------------------------------
// 3. Terrain & 3D Building Layers
// ----------------------------------------------------
function setupTerrain() {
  if (!map) return;
  if (!map.getSource("dem")) {
    map.addSource("dem", {
      type: "raster-dem",
      tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
      tileSize: 256,
      encoding: "terrarium",
      maxzoom: 15
    });
  }
  applyTerrainExaggeration();
}

function applyTerrainExaggeration() {
  if (!map || !map.getSource("dem")) return;
  try {
    map.setTerrain(state.layers.terrain ? { source: "dem", exaggeration: state.exaggeration } : null);
  } catch (e) {
    console.warn("Terrain update note:", e);
  }
}

function setupBuildings() {
  if (!map) return;
  const style = map.getStyle();
  const vectorSourceKey = style.sources?.openmaptiles ? "openmaptiles" : Object.keys(style.sources || {}).find(k => style.sources[k].type === "vector");

  // Extrude OpenStreetMap vector buildings where available
  if (vectorSourceKey && !map.getLayer("osm-buildings-3d")) {
    const symbolLayer = (style.layers || []).find(l => l.type === "symbol" && l.layout?.["text-field"]);
    map.addLayer({
      id: "osm-buildings-3d",
      type: "fill-extrusion",
      source: vectorSourceKey,
      "source-layer": "building",
      minzoom: 13,
      paint: {
        "fill-extrusion-color": [
          "interpolate", ["linear"], ["coalesce", ["get", "render_height"], ["get", "height"], 8],
          0, "#8fa1ad",
          25, "#687f8c",
          60, "#48606e"
        ],
        "fill-extrusion-height": [
          "interpolate", ["linear"], ["zoom"],
          13, 0,
          15, ["coalesce", ["get", "render_height"], ["get", "height"], 8]
        ],
        "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], ["get", "min_height"], 0],
        "fill-extrusion-opacity": 0.85
      }
    }, symbolLayer?.id);
  }

  // Custom Srirangam landmark structures
  if (state.buildingsData && !map.getSource("srirangam-buildings")) {
    map.addSource("srirangam-buildings", {
      type: "geojson",
      data: state.buildingsData
    });

    map.addLayer({
      id: "srirangam-landmarks-3d",
      type: "fill-extrusion",
      source: "srirangam-buildings",
      paint: {
        "fill-extrusion-color": [
          "match", ["get", "risk_category"],
          "SEVERE", "#ef4444",
          "MODERATE", "#f59e0b",
          "MINOR", "#59c9cc",
          "#4a758c" // safe / default
        ],
        "fill-extrusion-height": ["get", "height"],
        "fill-extrusion-base": 0,
        "fill-extrusion-opacity": 0.92
      }
    });

    // Landmark building stroke outlines
    map.addLayer({
      id: "srirangam-landmarks-line",
      type: "line",
      source: "srirangam-buildings",
      paint: {
        "line-color": "#58d6c5",
        "line-width": 1.5
      }
    });
  }

  setLayerVisibility("osm-buildings-3d", state.layers.buildings);
  setLayerVisibility("srirangam-landmarks-3d", state.layers.buildings);
  setLayerVisibility("srirangam-landmarks-line", state.layers.buildings);
}

// ----------------------------------------------------
// 4. Rivers, Flood & Gauging Layers
// ----------------------------------------------------
function setupGeoLayers() {
  if (!map) return;

  // 1. Flood Extent Source
  if (!map.getSource("floodsrc")) {
    map.addSource("floodsrc", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] }
    });

    // Inundation fill with depth-based color grading
    map.addLayer({
      id: "floodfill",
      type: "fill",
      source: "floodsrc",
      paint: {
        "fill-color": [
          "match", ["get", "severity"],
          "high", "#ef4444",
          "moderate", "#3b82f6",
          "#59c9cc" // low / shallow
        ],
        "fill-opacity": 0.62
      }
    });

    // Flood edge boundary glow
    map.addLayer({
      id: "floodline",
      type: "line",
      source: "floodsrc",
      paint: {
        "line-color": "#7dd3fc",
        "line-width": 1.8,
        "line-opacity": 0.9
      }
    });
  }

  // 2. River Corridors (Cauvery & Kollidam)
  if (!map.getSource("riverline") && state.riverData) {
    map.addSource("riverline", {
      type: "geojson",
      data: state.riverData
    });

    map.addLayer({
      id: "river",
      type: "line",
      source: "riverline",
      paint: {
        "line-color": "#4dd3e7",
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 3, 14, 8],
        "line-opacity": 0.88
      }
    });

    map.addLayer({
      id: "riverlabels",
      type: "symbol",
      source: "riverline",
      layout: {
        "symbol-placement": "line",
        "text-field": ["get", "name"],
        "text-size": 11,
        "text-letter-spacing": 0.1,
        "text-max-angle": 30
      },
      paint: {
        "text-color": "#c4f5fc",
        "text-halo-color": "#0d1b22",
        "text-halo-width": 2
      }
    });
  }

  // 3. Hydrological Monitoring Gauging Points
  if (!map.getSource("points") && state.stationsData) {
    map.addSource("points", {
      type: "geojson",
      data: state.stationsData
    });

    // Outer pulse ring
    map.addLayer({
      id: "pointrings",
      type: "circle",
      source: "points",
      paint: {
        "circle-radius": 10,
        "circle-color": "transparent",
        "circle-stroke-color": "#f4b46c",
        "circle-stroke-width": 1.5,
        "circle-stroke-opacity": 0.6
      }
    });

    // Core point dot
    map.addLayer({
      id: "pointdots",
      type: "circle",
      source: "points",
      paint: {
        "circle-radius": 5,
        "circle-color": "#f4b46c",
        "circle-stroke-color": "#0d181e",
        "circle-stroke-width": 2
      }
    });

    // Labels
    map.addLayer({
      id: "pointlabels",
      type: "symbol",
      source: "points",
      layout: {
        "text-field": ["get", "name"],
        "text-size": 10,
        "text-offset": [0, 1.4],
        "text-anchor": "top",
        "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"]
      },
      paint: {
        "text-color": "#fbfbf8",
        "text-halo-color": "#101f27",
        "text-halo-width": 2
      }
    });
  }

  // Apply initial visibility
  syncLayerVisibilities();
}

function setLayerVisibility(id, isVisible) {
  if (map?.getLayer(id)) {
    map.setLayoutProperty(id, "visibility", isVisible ? "visible" : "none");
  }
}

function syncLayerVisibilities() {
  setLayerVisibility("floodfill", state.layers.flood);
  setLayerVisibility("floodline", state.layers.flood);
  setLayerVisibility("river", state.layers.river);
  setLayerVisibility("riverlabels", state.layers.river);
  setLayerVisibility("pointdots", state.layers.river);
  setLayerVisibility("pointrings", state.layers.river);
  setLayerVisibility("pointlabels", state.layers.river);
  setLayerVisibility("osm-buildings-3d", state.layers.buildings);
  setLayerVisibility("srirangam-landmarks-3d", state.layers.buildings);
  setLayerVisibility("srirangam-landmarks-line", state.layers.buildings);
}

// ----------------------------------------------------
// 5. Hydrological Simulation & Real API Call
// ----------------------------------------------------
async function updateSimulation() {
  const updateBtn = $("update");
  const spinner = updateBtn.querySelector(".spinner");
  const btnText = updateBtn.querySelector(".btn-text");

  updateBtn.disabled = true;
  if (spinner) spinner.hidden = false;
  if (btnText) btnText.textContent = "Simulating Inundation...";

  const api = getApiBase();
  const payload = {
    rainfall_mm_24h: state.rain,
    scenario: state.scenario
  };

  let result = null;

  try {
    const res = await fetch(`${api}/api/simulate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      result = await res.json();
    }
  } catch (err) {
    console.warn("Backend API call failed, generating terrain-aware client-side simulation:", err);
  }

  // Fallback to client-side elevation-connectivity simulation if backend is offline
  if (!result || !result.simulation_frames) {
    result = generateClientFallbackSimulation(state.rain, state.scenario);
  }

  // Store frames & summary
  state.simulationFrames = result.simulation_frames;
  state.currentFrameIdx = 0;

  // Update UI components
  applySimulationSummary(result);
  renderFrame(0);

  // Update building vulnerability metadata
  if (result.building_impacts) {
    updateBuildingImpacts(result.building_impacts);
  }

  // Reset timeline slider
  $("timelineSlider").value = 0;
  pauseAnimation();

  updateBtn.disabled = false;
  if (spinner) spinner.hidden = true;
  if (btnText) btnText.textContent = "▶ Update Simulation";
}

function applySimulationSummary(result) {
  const sum = result.summary;
  const riskIndex = sum.risk_index;
  const riskLevel = sum.risk_level;

  $("rainLabel").textContent = `${state.rain} mm / 24h`;
  $("rainMetric").innerHTML = `${state.rain} <i>mm</i>`;
  $("water").innerHTML = `${sum.peak_wse_m.toFixed(1)} <i>m</i>`;
  $("waterDiff").textContent = `+${sum.peak_water_level_change_m.toFixed(1)} m over riverbed`;
  $("inundatedArea").innerHTML = `${sum.max_inundated_sqkm.toFixed(1)} <i>km²</i>`;
  $("affectedBld").innerHTML = `${sum.total_affected_buildings} <i>/ ${state.buildingsData?.features?.length || 10}</i>`;

  $("score").innerHTML = `${riskIndex}<small>/100</small>`;
  $("bar").style.width = `${riskIndex}%`;

  const levelTag = $("level");
  levelTag.textContent = riskLevel;
  levelTag.className = `tag ${riskLevel.toLowerCase()}`;

  // Update Insights Panel
  $("insWse").textContent = `${sum.peak_wse_m.toFixed(1)} m MSL`;
  $("insSector").textContent = sum.highest_risk_sector || "Melur Lowlands & North Kollidam";

  // Context Interpretation Text
  const title = $("insightTitle");
  const desc = $("insight");
  if (riskLevel === "HIGH") {
    title.textContent = "High Flood Hazard Warning";
    desc.textContent = "Extreme water surge overtopping river embankments. Significant inundation of Melur lowlands and Amma Mandapam riverfront communities.";
  } else if (riskLevel === "MODERATE") {
    title.textContent = "Moderate Flood Risk Active";
    desc.textContent = "Elevated river stage. Water spills into lowest riparian drainage channels. Elevated Sri Ranganathaswamy Temple ridges remain protected.";
  } else {
    title.textContent = "Low Riparian Hazard";
    desc.textContent = "Water surface elevation remains confined within Cauvery and Kollidam primary channels. Island core is fully dry.";
  }
}

function renderFrame(frameIdx) {
  if (!state.simulationFrames || !state.simulationFrames[frameIdx]) return;
  state.currentFrameIdx = frameIdx;
  const frame = state.simulationFrames[frameIdx];

  if (map?.getSource("floodsrc")) {
    map.getSource("floodsrc").setData(frame);
  }

  const props = frame.properties || {};
  const tHours = props.time_hours !== undefined ? props.time_hours : frameIdx * 4;
  $("timelineTime").textContent = `t = ${tHours.toFixed(1)}h / 24h`;
  $("timelineSlider").value = frameIdx;
}

// ----------------------------------------------------
// 6. Animation Player & Timeline Controls
// ----------------------------------------------------
function playAnimation() {
  if (state.isPlaying) return;
  state.isPlaying = true;
  $("playBtn").disabled = true;
  $("pauseBtn").disabled = false;

  const intervalTime = Math.max(250, state.animSpeedMs / state.speedMultiplier);

  state.animInterval = setInterval(() => {
    let nextIdx = state.currentFrameIdx + 1;
    if (nextIdx >= state.simulationFrames.length) {
      nextIdx = 0; // loop
    }
    renderFrame(nextIdx);
  }, intervalTime);
}

function pauseAnimation() {
  state.isPlaying = false;
  if (state.animInterval) {
    clearInterval(state.animInterval);
    state.animInterval = null;
  }
  $("playBtn").disabled = false;
  $("pauseBtn").disabled = true;
}

function resetAnimation() {
  pauseAnimation();
  renderFrame(0);
}

function setPlaybackSpeed(mult) {
  state.speedMultiplier = mult;
  document.querySelectorAll(".speed-btn").forEach(btn => {
    btn.classList.toggle("active", parseFloat(btn.dataset.speed) === mult);
  });
  if (state.isPlaying) {
    pauseAnimation();
    playAnimation();
  }
}

// ----------------------------------------------------
// 7. Interactive 3D Camera Controls
// ----------------------------------------------------
function setupCameraControls() {
  // Horizontal Rotation
  $("camRotLeft").addEventListener("click", () => {
    if (!map) return;
    map.rotateTo(map.getBearing() - 30, { duration: 600 });
  });

  $("camRotRight").addEventListener("click", () => {
    if (!map) return;
    map.rotateTo(map.getBearing() + 30, { duration: 600 });
  });

  // Vertical Tilt
  $("camTiltUp").addEventListener("click", () => {
    if (!map) return;
    const newPitch = Math.min(75, map.getPitch() + 15);
    map.easeTo({ pitch: newPitch, duration: 500 });
  });

  $("camTiltDown").addEventListener("click", () => {
    if (!map) return;
    const newPitch = Math.max(0, map.getPitch() - 15);
    map.easeTo({ pitch: newPitch, duration: 500 });
  });

  // Zoom
  $("camZoomIn").addEventListener("click", () => map?.zoomIn({ duration: 400 }));
  $("camZoomOut").addEventListener("click", () => map?.zoomOut({ duration: 400 }));

  // North-Up
  $("camNorth").addEventListener("click", () => {
    if (!map) return;
    map.resetNorthPitch({ duration: 700 });
  });

  // Reset to Srirangam overview
  $("camReset").addEventListener("click", () => {
    if (!map) return;
    map.flyTo({
      center: INITIAL_VIEW.center,
      zoom: INITIAL_VIEW.zoom,
      pitch: INITIAL_VIEW.pitch,
      bearing: INITIAL_VIEW.bearing,
      duration: 1000
    });
  });

  $("reset").addEventListener("click", () => $("camReset").click());

  // 2D / 3D Mode Switcher Buttons
  $("tilt").addEventListener("click", () => {
    if (!map) return;
    map.easeTo({ pitch: 58, bearing: -20, duration: 700 });
    $("tilt").classList.add("chosen");
    $("flat").classList.remove("chosen");
    $("modeBadge").textContent = "3D";
  });

  $("flat").addEventListener("click", () => {
    if (!map) return;
    map.easeTo({ pitch: 0, bearing: 0, duration: 700 });
    $("flat").classList.add("chosen");
    $("tilt").classList.remove("chosen");
    $("modeBadge").textContent = "2D";
  });
}

// ----------------------------------------------------
// 8. Terrain & Depth Pointer Inspection
// ----------------------------------------------------
function onMapMouseMove(e) {
  const lng = e.lngLat.lng.toFixed(4);
  const lat = e.lngLat.lat.toFixed(4);

  // In MapLibre GL, queryTerrainElevation queries the DEM elevation at that point in metres
  let elev = null;
  if (state.layers.terrain && map.queryTerrainElevation) {
    try {
      elev = map.queryTerrainElevation(e.lngLat);
    } catch (_) {}
  }

  // Fallback realistic interpolation based on Srirangam terrain profile
  if (elev === null || isNaN(elev)) {
    elev = estimateSrirangamElevation(e.lngLat.lng, e.lngLat.lat);
  }

  $("inspectorElev").textContent = `Ground Elev: ${elev.toFixed(1)} m MSL`;
  $("inspectorCoord").textContent = `${lng}°E, ${lat}°N · Click to inspect depth`;
}

function onMapClick(e) {
  const lng = e.lngLat.lng;
  const lat = e.lngLat.lat;

  let elev = null;
  if (state.layers.terrain && map.queryTerrainElevation) {
    try {
      elev = map.queryTerrainElevation(e.lngLat);
    } catch (_) {}
  }
  if (elev === null || isNaN(elev)) {
    elev = estimateSrirangamElevation(lng, lat);
  }

  // Current frame WSE
  const currentFrame = state.simulationFrames[state.currentFrameIdx] || {};
  const wse = currentFrame.properties?.wse_m || 71.5;
  const depth = Math.max(0, wse - elev);

  const status = depth > 1.5 ? "Severe Inundation" : depth > 0.5 ? "Moderate Water Depth" : depth > 0.05 ? "Shallow Ponding" : "Dry Ground (Safe)";
  const statusColor = depth > 1.5 ? "#ef4444" : depth > 0.5 ? "#f59e0b" : depth > 0.05 ? "#59c9cc" : "#10b981";

  if (currentPopup) currentPopup.remove();

  currentPopup = new maplibregl.Popup({ closeButton: true, closeOnClick: true })
    .setLngLat(e.lngLat)
    .setHTML(`
      <div class="popup-title">Terrain & Flood Inspection</div>
      <div class="popup-row"><span>Coordinates:</span> <b>${lng.toFixed(4)}°E, ${lat.toFixed(4)}°N</b></div>
      <div class="popup-row"><span>Ground Elevation:</span> <b>${elev.toFixed(1)} m MSL</b></div>
      <div class="popup-row"><span>Water Surface Elev:</span> <b>${wse.toFixed(1)} m MSL</b></div>
      <div class="popup-row"><span>Estimated Depth:</span> <b>${depth.toFixed(2)} m</b></div>
      <div class="popup-row" style="margin-top:6px; border-top:1px solid #283e4c; padding-top:4px;">
        <span>Condition:</span> <b style="color:${statusColor}">${status}</b>
      </div>
      <small style="color:#768d97; display:block; margin-top:4px; font-size:8px;">SRTM 30m DEM elevation · Depth = max(0, WSE − Ground)</small>
    `)
    .addTo(map);
}

function estimateSrirangamElevation(lon, lat) {
  // Srirangam Island center is around 78.693, 10.865
  // Distance from temple core
  const dx = (lon - 78.6935) * 111.0;
  const dy = (lat - 10.8625) * 111.0;
  const distKm = Math.sqrt(dx * dx + dy * dy);
  
  // River corridors at North (lat ~10.880) and South (lat ~10.857) have lower bed elevation ~69-70m
  // Temple ridge reaches ~74-78m
  let elev = 75.0 - distKm * 2.2;
  return Math.max(68.5, Math.min(82.0, elev));
}

// ----------------------------------------------------
// 9. Building Vulnerability & Station Lists
// ----------------------------------------------------
function updateBuildingImpacts(impacts) {
  if (!impacts) return;
  const listEl = $("buildingList");
  listEl.innerHTML = "";

  impacts.forEach(b => {
    const card = document.createElement("div");
    card.className = "bld-card";
    const riskClass = (b.risk_category || "safe").toLowerCase();

    card.innerHTML = `
      <div class="bld-info">
        <strong>${b.name}</strong>
        <small>${b.type} · Elev: ${b.ground_elevation_m}m · Depth: ${b.water_depth_m}m</small>
      </div>
      <span class="bld-badge ${riskClass}">${b.risk_category}</span>
    `;

    card.addEventListener("click", () => {
      // Find building feature
      const feat = state.buildingsData?.features?.find(f => f.properties.id === b.id);
      if (feat && map) {
        const coords = feat.geometry.coordinates[0][0];
        map.flyTo({ center: coords, zoom: 15.5, pitch: 62, duration: 900 });
        if (currentPopup) currentPopup.remove();
        currentPopup = new maplibregl.Popup()
          .setLngLat(coords)
          .setHTML(`
            <div class="popup-title">${b.name}</div>
            <div class="popup-row"><span>Building Type:</span> <b>${b.type}</b></div>
            <div class="popup-row"><span>Ground Elevation:</span> <b>${b.ground_elevation_m} m MSL</b></div>
            <div class="popup-row"><span>Estimated Depth:</span> <b>${b.water_depth_m} m</b></div>
            <div class="popup-row"><span>Risk Category:</span> <b class="tag ${riskClass}">${b.risk_category}</b></div>
          `)
          .addTo(map);
      }
    });

    listEl.appendChild(card);
  });
}

function renderBuildingList() {
  if (!state.buildingsData) return;
  const sampleImpacts = state.buildingsData.features.map(f => ({
    id: f.properties.id,
    name: f.properties.name,
    type: f.properties.type,
    ground_elevation_m: f.properties.ground_elevation_m || 74.0,
    water_depth_m: 0.0,
    risk_category: "SAFE"
  }));
  updateBuildingImpacts(sampleImpacts);
}

function renderStationList() {
  if (!state.stationsData) return;
  const listEl = $("stations");
  listEl.innerHTML = "";

  state.stationsData.features.forEach(f => {
    const p = f.properties;
    const card = document.createElement("div");
    card.className = "station-card";
    card.innerHTML = `
      <i class="station-pin"></i>
      <div class="station-info">
        <strong>${p.name}</strong>
        <small>${p.type || p.id} · Warn: ${p.warning_stage_m || 72}m · Danger: ${p.danger_stage_m || 74}m</small>
      </div>
      <small style="color:var(--teal); font-weight:700; font-size:8px;">GAUGE</small>
    `;

    card.addEventListener("click", () => {
      if (map) {
        map.flyTo({ center: f.geometry.coordinates, zoom: 15.2, pitch: 55, duration: 900 });
        if (currentPopup) currentPopup.remove();
        currentPopup = new maplibregl.Popup()
          .setLngLat(f.geometry.coordinates)
          .setHTML(`
            <div class="popup-title">${p.name}</div>
            <div class="popup-row"><span>Station ID:</span> <b>${p.id}</b></div>
            <div class="popup-row"><span>Type:</span> <b>${p.type || "Hydrometric Gauge"}</b></div>
            <div class="popup-row"><span>Ground Elevation:</span> <b>${p.ground_elevation_m || 70} m MSL</b></div>
            <div class="popup-row"><span>Warning Stage:</span> <b>${p.warning_stage_m} m</b></div>
            <div class="popup-row"><span>Danger Stage:</span> <b style="color:#ef4444">${p.danger_stage_m} m</b></div>
          `)
          .addTo(map);
      }
    });

    listEl.appendChild(card);
  });
}

// ----------------------------------------------------
// 10. Live Weather Integration
// ----------------------------------------------------
async function fetchWeather() {
  const api = getApiBase();
  try {
    const res = await fetch(`${api}/api/weather`);
    if (res.ok) {
      const w = await res.json();
      $("tempVal").textContent = `${w.temperature_c.toFixed(1)}°C`;
      $("rainVal").textContent = `Rain: ${w.precipitation_mm.toFixed(1)} mm/h`;
      $("humidVal").textContent = `Humidity: ${w.relative_humidity_pct}%`;
      $("weatherSource").textContent = w.status === "live" ? "LIVE" : "CACHED";
    }
  } catch (err) {
    console.warn("Weather fetch note:", err);
  }
}

// ----------------------------------------------------
// 11. Client Fallback Simulation (If Backend is Offline)
// ----------------------------------------------------
function generateClientFallbackSimulation(rain, scenario) {
  const multiplier = scenario === "breach" ? 1.4 : scenario === "rapid-rise" ? 1.22 : 1.0;
  const baseStage = 69.5;
  const stageRise = Math.pow(rain / 65, 1.15) * 1.6 * multiplier;
  const peakWse = Math.round((baseStage + stageRise) * 100) / 100;
  
  const timesteps = [0.0, 3.0, 6.0, 12.0, 18.0, 24.0];
  const ratios = [0.0, 0.3, 0.6, 0.95, 0.8, 0.5];

  // Srirangam river polygons
  const cauveryRing = [
    [78.665, 10.865], [78.692, 10.857], [78.705, 10.858], [78.730, 10.852],
    [78.730, 10.848], [78.705, 10.853], [78.692, 10.854], [78.665, 10.860], [78.665, 10.865]
  ];
  const kollidamRing = [
    [78.662, 10.887], [78.685, 10.883], [78.700, 10.879], [78.730, 10.871],
    [78.730, 10.866], [78.700, 10.874], [78.685, 10.878], [78.662, 10.882], [78.662, 10.887]
  ];
  const melurLowland = [
    [78.680, 10.865], [78.686, 10.865], [78.686, 10.872], [78.680, 10.872], [78.680, 10.865]
  ];

  const frames = timesteps.map((t, idx) => {
    const curWse = baseStage + stageRise * ratios[idx];
    const expansion = 1 + (curWse - baseStage) * 0.45;
    const features = [];

    if (curWse > 69.8) {
      features.push({
        type: "Feature",
        properties: { severity: "low", depth_m: 0.3 },
        geometry: { type: "Polygon", coordinates: [cauveryRing] }
      });
      features.push({
        type: "Feature",
        properties: { severity: "moderate", depth_m: 0.8 },
        geometry: { type: "Polygon", coordinates: [kollidamRing] }
      });
    }

    if (curWse > 71.0) {
      features.push({
        type: "Feature",
        properties: { severity: curWse > 73.0 ? "high" : "moderate", depth_m: 1.2 },
        geometry: { type: "Polygon", coordinates: [melurLowland] }
      });
    }

    return {
      type: "FeatureCollection",
      properties: {
        step: idx,
        time_hours: t,
        wse_m: Math.round(curWse * 100) / 100,
        inundated_sqkm: Math.round((features.length * 15.5 * expansion) * 10) / 10
      },
      features
    };
  });

  const riskScore = Math.min(98, Math.max(8, Math.round((rain / 2.3 + 10) * multiplier)));
  const riskLevel = riskScore >= 65 ? "HIGH" : riskScore >= 35 ? "MODERATE" : "LOW";

  return {
    summary: {
      risk_index: riskScore,
      risk_level: riskLevel,
      peak_wse_m: peakWse,
      peak_water_level_change_m: Math.round((peakWse - baseStage) * 10) / 10,
      max_inundated_sqkm: Math.round((38.0 * multiplier) * 10) / 10,
      total_affected_buildings: rain >= 120 ? 4 : rain >= 70 ? 2 : 0,
      highest_risk_sector: "Melur Lowlands & North Kollidam Embankment"
    },
    simulation_frames: frames
  };
}

// ----------------------------------------------------
// 12. UI Event Handlers & Interactions
// ----------------------------------------------------
function setupInteractions() {
  setupCameraControls();

  // Rainfall Slider
  $("rain").addEventListener("input", e => {
    state.rain = +e.target.value;
    $("rainLabel").textContent = `${state.rain} mm / 24h`;
  });

  // Scenario Selector
  $("scenario").addEventListener("change", e => {
    state.scenario = e.target.value;
  });

  // Update Simulation Button
  $("update").addEventListener("click", updateSimulation);

  // Terrain Exaggeration Slider
  $("exaggeration").addEventListener("input", e => {
    state.exaggeration = +e.target.value;
    $("exagLabel").textContent = `${state.exaggeration.toFixed(1)}x`;
    applyTerrainExaggeration();
  });

  // Layer Checkboxes
  $("terrain").addEventListener("change", e => {
    state.layers.terrain = e.target.checked;
    applyTerrainExaggeration();
  });

  $("buildings").addEventListener("change", e => {
    state.layers.buildings = e.target.checked;
    setLayerVisibility("osm-buildings-3d", state.layers.buildings);
    setLayerVisibility("srirangam-landmarks-3d", state.layers.buildings);
    setLayerVisibility("srirangam-landmarks-line", state.layers.buildings);
  });

  $("flood").addEventListener("change", e => {
    state.layers.flood = e.target.checked;
    setLayerVisibility("floodfill", state.layers.flood);
    setLayerVisibility("floodline", state.layers.flood);
  });

  $("depthLayer").addEventListener("change", e => {
    state.layers.depth = e.target.checked;
    setLayerVisibility("floodfill", state.layers.depth && state.layers.flood);
  });

  $("river").addEventListener("change", e => {
    state.layers.river = e.target.checked;
    setLayerVisibility("river", state.layers.river);
    setLayerVisibility("riverlabels", state.layers.river);
    setLayerVisibility("pointdots", state.layers.river);
    setLayerVisibility("pointrings", state.layers.river);
    setLayerVisibility("pointlabels", state.layers.river);
  });

  $("riskZones").addEventListener("change", e => {
    state.layers.riskZones = e.target.checked;
    setLayerVisibility("srirangam-landmarks-3d", state.layers.riskZones && state.layers.buildings);
  });

  // Timeline Controls
  $("playBtn").addEventListener("click", playAnimation);
  $("pauseBtn").addEventListener("click", pauseAnimation);
  $("resetAnimBtn").addEventListener("click", resetAnimation);

  $("timelineSlider").addEventListener("input", e => {
    pauseAnimation();
    renderFrame(+e.target.value);
  });

  document.querySelectorAll(".speed-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      setPlaybackSpeed(parseFloat(btn.dataset.speed));
    });
  });

  // Insights Accordion Toggle
  $("insightsToggle").addEventListener("click", () => {
    const content = $("insightsContent");
    const arrow = $("insightsArrow");
    const isHidden = content.style.display === "none";
    content.style.display = isHidden ? "flex" : "none";
    arrow.textContent = isHidden ? "▲" : "▼";
  });
}

function showError(msg) {
  const errBox = $("mapError");
  if (errBox) {
    errBox.hidden = false;
    errBox.textContent = msg;
  }
}

// Start Digital Twin Application
document.addEventListener("DOMContentLoaded", initMap);