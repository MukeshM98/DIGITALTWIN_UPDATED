import pytest
import numpy as np
from pathlib import Path
import json

from backend.flood_simulation import FloodSimulationEngine

@pytest.fixture
def sim_engine():
    return FloodSimulationEngine()

def test_geographic_target_is_srirangam(sim_engine):
    """Verifies that geographic focus is Srirangam Island."""
    bounds = sim_engine.meta["bounds"]
    # Srirangam target coordinates: ~10.865 Lat, 78.693 Lon
    assert bounds["west"] <= 78.693 <= bounds["east"]
    assert bounds["south"] <= 10.865 <= bounds["north"]

def test_coordinate_order_is_lon_lat(sim_engine):
    """Verifies that coordinates in river and monitoring GeoJSON follow [lon, lat] convention."""
    for feature in sim_engine.rivers:
        coords = feature["geometry"]["coordinates"]
        for pt in coords:
            lon, lat = pt[0], pt[1]
            assert 78.0 <= lon <= 79.0, f"Expected longitude ~78.x, got {lon}"
            assert 10.0 <= lat <= 11.5, f"Expected latitude ~10.x, got {lat}"

def test_zero_rainfall_no_excess_flood(sim_engine):
    """Verifies that zero rainfall does not create an extreme rainfall surge."""
    wse_zero = sim_engine.compute_wse(0.0, "rainfall", 0.8)
    # Baseline dry stage is 69.5m
    assert wse_zero == 69.5, f"Expected dry river stage 69.5m, got {wse_zero}m"

def test_monotonic_wse_inundation(sim_engine):
    """
    Verifies that under identical static terrain conditions,
    higher WSE produces equal or greater inundation area.
    """
    seeds = sim_engine.get_river_seeds()
    depth_low = sim_engine.run_connectivity_flood(71.0, seeds)
    depth_high = sim_engine.run_connectivity_flood(73.5, seeds)
    
    count_low = np.count_nonzero(depth_low > 0.05)
    count_high = np.count_nonzero(depth_high > 0.05)
    assert count_high >= count_low, f"Higher WSE should produce >= flooded cells ({count_high} vs {count_low})"

def test_water_depth_never_negative(sim_engine):
    """Verifies that depth values are strictly >= 0."""
    seeds = sim_engine.get_river_seeds()
    depth_grid = sim_engine.run_connectivity_flood(73.0, seeds)
    assert np.all(depth_grid >= 0.0)

def test_disconnected_depression_not_flooded(sim_engine):
    """
    Verifies that a low depression physically isolated from river seeds
    is NOT inundated by the connectivity engine.
    """
    # Create synthetic test grid:
    # Row 0: river seeds at 70m
    # Row 1-3: high protective levee at 85m
    # Row 4: low isolated depression at 65m
    custom_engine = FloodSimulationEngine()
    test_grid = np.full((10, 10), 85.0, dtype=np.float32)
    test_grid[0, :] = 70.0 # river cells
    test_grid[8, 8] = 65.0 # deep low depression behind levee
    custom_engine.elevation_grid = test_grid
    
    river_seeds = [(0, c) for c in range(10)]
    wse = 72.0 # water reaches 72m: covers river cells (70m), but cannot cross levee (85m)
    
    depth_result = custom_engine.run_connectivity_flood(wse, river_seeds)
    # The depression at (8, 8) has ground elevation 65m <= WSE 72m, but is not connected!
    assert depth_result[8, 8] == 0.0, "Isolated depression without hydrological path should NOT be flooded!"

def test_simulation_produces_frames_and_summary(sim_engine):
    """Verifies full simulation output schema."""
    res = sim_engine.simulate(80.0, "rainfall")
    assert "metadata" in res
    assert "summary" in res
    assert "simulation_frames" in res
    assert len(res["simulation_frames"]) == 6
    assert res["summary"]["risk_level"] in ["LOW", "MODERATE", "HIGH"]
    assert res["summary"]["peak_wse_m"] >= 69.5
