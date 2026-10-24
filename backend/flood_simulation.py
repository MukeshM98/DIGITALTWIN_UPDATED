"""
FloodSense DT — Hydrological Simulation Engine
Terrain-Aware Inundation Modeling for Srirangam Island, Tiruchirappalli, Tamil Nadu

Features:
- Real SRTM DEM elevation grid loading (512x512 matrix, ~19m cell resolution)
- River channel seed extraction (Cauvery and Kollidam corridors)
- Scenario-based Water Surface Elevation (WSE) computation
- 8-neighbor spatial flood-connectivity algorithm (BFS flood propagation)
- Prevents disconnected low-lying depression inundation
- Timestep simulation progression (t=0h to t=24h)
- Building vulnerability and depth-based damage risk classification
- GeoJSON polygonization for 3D map rendering
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import numpy as np

DATA_DIR = Path(__file__).resolve().parent / "data"

class FloodSimulationEngine:
    def __init__(self, dem_path: Optional[Path] = None, meta_path: Optional[Path] = None):
        self.dem_path = dem_path or (DATA_DIR / "srirangam_dem.npz")
        self.meta_path = meta_path or (DATA_DIR / "srirangam_dem_meta.json")
        self.buildings_path = DATA_DIR / "buildings.geojson"
        self.river_path = DATA_DIR / "river.geojson"
        
        self.elevation_grid: Optional[np.ndarray] = None
        self.meta: Dict[str, Any] = {}
        self.buildings: List[Dict[str, Any]] = []
        self.rivers: List[Dict[str, Any]] = []
        
        self.load_data()

    def load_data(self) -> None:
        """Loads elevation grid, metadata, river vectors, and building footprints."""
        if self.dem_path.exists():
            npz = np.load(self.dem_path)
            self.elevation_grid = npz["elevation"]
        else:
            # Fallback synthetic grid for Srirangam if DEM file is missing
            self.elevation_grid = np.full((512, 512), 72.0, dtype=np.float32)

        if self.meta_path.exists():
            with open(self.meta_path, "r", encoding="utf-8") as f:
                self.meta = json.load(f)
        else:
            self.meta = {
                "bounds": {"west": 78.662109, "south": 10.833306, "east": 78.750000, "north": 10.919618},
                "grid_shape": [512, 512],
                "resolution_m": 19.11
            }

        if self.buildings_path.exists():
            with open(self.buildings_path, "r", encoding="utf-8") as f:
                self.buildings = json.load(f).get("features", [])

        if self.river_path.exists():
            with open(self.river_path, "r", encoding="utf-8") as f:
                self.rivers = json.load(f).get("features", [])

    def coord_to_grid(self, lon: float, lat: float) -> Tuple[int, int]:
        """Converts geographic longitude and latitude to (row, col) grid indices."""
        b = self.meta["bounds"]
        h, w = self.elevation_grid.shape
        col = int((lon - b["west"]) / (b["east"] - b["west"]) * w)
        row = int((b["north"] - lat) / (b["north"] - b["south"]) * h)
        return max(0, min(h - 1, row)), max(0, min(w - 1, col))

    def grid_to_coord(self, row: int, col: int) -> Tuple[float, float]:
        """Converts grid (row, col) to geographic (lon, lat)."""
        b = self.meta["bounds"]
        h, w = self.elevation_grid.shape
        lon = b["west"] + (col + 0.5) / w * (b["east"] - b["west"])
        lat = b["north"] - (row + 0.5) / h * (b["north"] - b["south"])
        return round(lon, 6), round(lat, 6)

    def get_elevation(self, lon: float, lat: float) -> float:
        """Returns ground elevation in metres MSL for a given coordinate."""
        r, c = self.coord_to_grid(lon, lat)
        return float(self.elevation_grid[r, c])

    def get_river_seeds(self) -> List[Tuple[int, int]]:
        """Extracts grid cells along the Cauvery and Kollidam river courses as flood seeds."""
        seeds = []
        for feature in self.rivers:
            coords = feature["geometry"]["coordinates"]
            for i in range(len(coords) - 1):
                p1 = coords[i]
                p2 = coords[i + 1]
                # Interpolate points along river segments
                steps = 15
                for s in range(steps + 1):
                    lon = p1[0] + (p2[0] - p1[0]) * (s / steps)
                    lat = p1[1] + (p2[1] - p1[1]) * (s / steps)
                    r, c = self.coord_to_grid(lon, lat)
                    seeds.append((r, c))
        # Remove duplicates
        return list(set(seeds))

    def compute_wse(self, rainfall_mm: float, scenario: str, timestep_ratio: float) -> float:
        """
        Computes Water Surface Elevation (WSE in metres MSL) based on:
        - Base river stage: ~69.5m MSL
        - Rainfall runoff contribution (SCS Curve Number adaptation for Srirangam delta)
        - Scenario surge multipliers:
          * rainfall: baseline precipitation runoff
          * rapid-rise: upstream Mukkombu barrage discharge surge
          * breach: Kollidam embankment breach scenario
        - Timestep progression factor (hydrograph rise and fall)
        """
        base_stage = 69.5  # Normal dry-season river water level in Srirangam

        # Scenario multiplier for river surge
        multiplier = {
            "rainfall": 1.0,
            "rapid-rise": 1.25,
            "breach": 1.45
        }.get(scenario, 1.0)

        # Non-linear runoff stage rise: P in mm converted to stage increase in metres
        # Zero rainfall yields zero rainfall stage rise
        if rainfall_mm <= 0:
            stage_rise = 0.0
        else:
            # 50mm -> ~1.2m rise, 100mm -> ~2.8m rise, 200mm -> ~5.2m rise
            stage_rise = (rainfall_mm / 60.0) ** 1.15 * 1.5 * multiplier

        if scenario == "rapid-rise":
            # Upstream inflow adds base surge even at lower local rain
            stage_rise += 1.8 * timestep_ratio

        # Hydrograph curve: peaks around timestep_ratio ~ 0.6 to 0.8
        # Shape: sin wave from 0 to pi
        hydrograph = np.sin(timestep_ratio * np.pi * 0.85) if timestep_ratio > 0 else 0.0
        current_wse = base_stage + stage_rise * hydrograph
        return round(float(current_wse), 2)

    def run_connectivity_flood(
        self,
        wse: float,
        river_seeds: List[Tuple[int, int]],
        max_distance_cells: int = 120
    ) -> np.ndarray:
        """
        Computes connected inundation using 8-connected Breadth-First Search (BFS).
        Only cells hydrologically connected to the river channel where elevation <= WSE
        are marked as inundated. Disconnected depressions are rejected.
        
        Returns depth_grid where 0 = dry/disconnected, >0 = water depth in metres.
        """
        h, w = self.elevation_grid.shape
        depth_grid = np.zeros((h, w), dtype=np.float32)
        
        # If water surface elevation is below the minimum riverbed, no overbank flooding occurs
        if wse <= 69.0 or not river_seeds:
            return depth_grid

        visited = np.zeros((h, w), dtype=bool)
        from collections import deque
        queue = deque()

        # Seed with river channel cells that are below WSE
        for r, c in river_seeds:
            if 0 <= r < h and 0 <= c < w:
                if self.elevation_grid[r, c] <= wse:
                    visited[r, c] = True
                    depth = max(0.0, wse - self.elevation_grid[r, c])
                    depth_grid[r, c] = depth
                    queue.append((r, c, 0))

        # 8-connected neighbors
        neighbors = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

        while queue:
            r, c, dist = queue.popleft()
            if dist >= max_distance_cells:
                continue

            for dr, dc in neighbors:
                nr, nc = r + dr, c + dc
                if 0 <= nr < h and 0 <= nc < w and not visited[nr, nc]:
                    ground_elev = self.elevation_grid[nr, nc]
                    if ground_elev <= wse:
                        visited[nr, nc] = True
                        depth = max(0.0, wse - ground_elev)
                        depth_grid[nr, nc] = depth
                        queue.append((nr, nc, dist + 1))

        return depth_grid

    def raster_to_geojson_polygons(self, depth_grid: np.ndarray, wse: float, step_idx: int, time_h: float) -> Dict[str, Any]:
        """
        Converts the inundated depth grid into simplified GeoJSON polygons categorized
        by severity tiers:
        - Low (0.05m - 0.5m)
        - Moderate (0.5m - 1.5m)
        - High (> 1.5m)
        """
        h, w = depth_grid.shape
        b = self.meta["bounds"]
        cell_res = self.meta["resolution_m"]
        
        # Subsample grid for lightweight vector transfer (4x downsampling -> 128x128)
        downsample = 4
        sub_depth = depth_grid[::downsample, ::downsample]
        sh, sw = sub_depth.shape
        
        features = []
        
        # Inundation mask
        flooded_mask = sub_depth > 0.05
        flooded_count = int(np.count_nonzero(depth_grid > 0.05))
        inundated_sqkm = round(flooded_count * (cell_res * cell_res) / 1e6, 3)
        
        if flooded_count == 0:
            return {
                "type": "FeatureCollection",
                "properties": {
                    "step": step_idx,
                    "time_hours": time_h,
                    "wse_m": wse,
                    "flooded_cells": 0,
                    "inundated_sqkm": 0.0,
                    "mean_depth_m": 0.0,
                    "max_depth_m": 0.0,
                    "severity": "safe"
                },
                "features": []
            }

        valid_depths = depth_grid[depth_grid > 0.05]
        mean_depth = round(float(valid_depths.mean()), 2) if len(valid_depths) > 0 else 0.0
        max_depth = round(float(valid_depths.max()), 2) if len(valid_depths) > 0 else 0.0

        # Cluster flooded blocks into rectangular quad polygons for fast client rendering
        visited = np.zeros((sh, sw), dtype=bool)
        
        for r in range(sh):
            for c in range(sw):
                if flooded_mask[r, c] and not visited[r, c]:
                    # Find width of continuous flooded segment
                    c_end = c
                    while c_end < sw and flooded_mask[r, c_end] and not visited[r, c_end]:
                        c_end += 1
                    
                    # Mark visited
                    visited[r, c:c_end] = True
                    
                    d_val = float(sub_depth[r, c])
                    severity = "high" if d_val > 1.5 else "moderate" if d_val > 0.5 else "low"
                    
                    # Map to geographic coordinates
                    orig_r1 = r * downsample
                    orig_r2 = min(h, (r + 1) * downsample)
                    orig_c1 = c * downsample
                    orig_c2 = min(w, c_end * downsample)
                    
                    lon1 = b["west"] + orig_c1 / w * (b["east"] - b["west"])
                    lon2 = b["west"] + orig_c2 / w * (b["east"] - b["west"])
                    lat1 = b["north"] - orig_r2 / h * (b["north"] - b["south"])
                    lat2 = b["north"] - orig_r1 / h * (b["north"] - b["south"])
                    
                    poly = [
                        [round(lon1, 6), round(lat1, 6)],
                        [round(lon2, 6), round(lat1, 6)],
                        [round(lon2, 6), round(lat2, 6)],
                        [round(lon1, 6), round(lat2, 6)],
                        [round(lon1, 6), round(lat1, 6)]
                    ]
                    
                    features.append({
                        "type": "Feature",
                        "properties": {
                            "depth_m": round(d_val, 2),
                            "severity": severity
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [poly]
                        }
                    })

        overall_sev = "high" if max_depth > 1.5 else "moderate" if max_depth > 0.5 else "low"
        
        return {
            "type": "FeatureCollection",
            "properties": {
                "step": step_idx,
                "time_hours": time_h,
                "wse_m": wse,
                "flooded_cells": flooded_count,
                "inundated_sqkm": inundated_sqkm,
                "mean_depth_m": mean_depth,
                "max_depth_m": max_depth,
                "severity": overall_sev
            },
            "features": features
        }

    def assess_building_impact(self, wse: float) -> Tuple[int, List[Dict[str, Any]], Dict[str, int]]:
        """
        Assesses flood depth and risk for all designated buildings in Srirangam.
        Thresholds (prototype damage classification):
        - Safe: depth <= 0.05m
        - Minor: 0.05m - 0.5m
        - Moderate: 0.5m - 1.5m
        - Severe: > 1.5m
        """
        affected_count = 0
        impacts = []
        counts_by_tier = {"safe": 0, "minor": 0, "moderate": 0, "severe": 0}

        for bld in self.buildings:
            props = bld["properties"]
            elev = props.get("ground_elevation_m", 72.0)
            depth = max(0.0, wse - elev)
            
            if depth > 1.5:
                category = "severe"
                counts_by_tier["severe"] += 1
                affected_count += 1
            elif depth > 0.5:
                category = "moderate"
                counts_by_tier["moderate"] += 1
                affected_count += 1
            elif depth > 0.05:
                category = "minor"
                counts_by_tier["minor"] += 1
                affected_count += 1
            else:
                category = "safe"
                counts_by_tier["safe"] += 1

            impacts.append({
                "id": props.get("id"),
                "name": props.get("name"),
                "type": props.get("type"),
                "ground_elevation_m": elev,
                "water_depth_m": round(depth, 2),
                "risk_category": category.upper()
            })

        return affected_count, impacts, counts_by_tier

    def simulate(self, rainfall_mm_24h: float, scenario: str) -> Dict[str, Any]:
        """
        Runs the full 6-step time progression simulation:
        t = [0h, 3h, 6h, 12h, 18h, 24h]
        """
        river_seeds = self.get_river_seeds()
        timesteps = [0.0, 3.0, 6.0, 12.0, 18.0, 24.0]
        timestep_ratios = [0.0, 0.25, 0.55, 0.85, 0.95, 0.70] # hydrograph curve
        
        frames = []
        max_inundated_sqkm = 0.0
        peak_wse = 0.0
        
        for idx, (t_hours, ratio) in enumerate(zip(timesteps, timestep_ratios)):
            wse = self.compute_wse(rainfall_mm_24h, scenario, ratio)
            if wse > peak_wse:
                peak_wse = wse
                
            depth_grid = self.run_connectivity_flood(wse, river_seeds)
            geojson_frame = self.raster_to_geojson_polygons(depth_grid, wse, idx, t_hours)
            
            inundated_sqkm = geojson_frame["properties"]["inundated_sqkm"]
            if inundated_sqkm > max_inundated_sqkm:
                max_inundated_sqkm = inundated_sqkm
                
            frames.append(geojson_frame)

        # Peak impact assessment
        affected_buildings_count, building_impacts, counts_by_tier = self.assess_building_impact(peak_wse)
        
        # Risk index score (0 - 100)
        risk_multiplier = {"rainfall": 1.0, "rapid-rise": 1.18, "breach": 1.32}.get(scenario, 1.0)
        risk_index = min(98, max(5, int((rainfall_mm_24h / 2.3 + 10) * risk_multiplier)))
        risk_level = "HIGH" if risk_index >= 65 else "MODERATE" if risk_index >= 35 else "LOW"

        # Determine highest risk sector
        if scenario == "breach" or rainfall_mm_24h >= 140:
            highest_risk_sector = "Melur Lowlands & North Kollidam Embankment"
        elif scenario == "rapid-rise" or rainfall_mm_24h >= 80:
            highest_risk_sector = "Amma Mandapam Riverfront Ghats & Mambalasalai"
        else:
            highest_risk_sector = "Immediate Unprotected Riverbed Channels"

        return {
            "metadata": {
                "study_area": "Srirangam Island, Tiruchirappalli, Tamil Nadu, India",
                "center": [78.693, 10.865],
                "crs": "EPSG:4326 (WGS84)",
                "vertical_datum": "EGM96 / MSL (Metres)",
                "dem_source": "SRTM 30m / Terrarium Elevation Raster",
                "model": "8-Neighbor Surface Connectivity Elevation Inundation Engine",
                "disclaimer": "Prototype hydrological digital twin for academic/disaster risk assessment demonstration."
            },
            "inputs": {
                "rainfall_mm_24h": rainfall_mm_24h,
                "scenario": scenario
            },
            "summary": {
                "risk_index": risk_index,
                "risk_level": risk_level,
                "peak_wse_m": peak_wse,
                "peak_water_level_change_m": round(peak_wse - 69.5, 2),
                "max_inundated_sqkm": max_inundated_sqkm,
                "total_affected_buildings": affected_buildings_count,
                "building_risk_breakdown": counts_by_tier,
                "highest_risk_sector": highest_risk_sector,
                "timesteps_count": len(frames)
            },
            "building_impacts": building_impacts,
            "simulation_frames": frames
        }

# Global singleton instance
engine = FloodSimulationEngine()
