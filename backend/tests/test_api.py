import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_root_api():
    resp = client.get("/api")
    assert resp.status_code == 200
    data = resp.json()
    assert "Srirangam Island" in data["study_area"]
    assert data["focus_coordinates"]["latitude"] == 10.865
    assert data["focus_coordinates"]["longitude"] == 78.693

def test_health_check():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["dem_loaded"] is True

def test_metadata_endpoint():
    resp = client.get("/api/metadata")
    assert resp.status_code == 200
    data = resp.json()
    loc = data["location"]
    assert loc["district"] == "Tiruchirappalli"
    assert loc["state"] == "Tamil Nadu"
    assert loc["center"] == [78.693, 10.865]
    bbox = loc["bounding_box"]
    assert bbox["south"] <= 10.865 <= bbox["north"]
    assert bbox["west"] <= 78.693 <= bbox["east"]

def test_scenario_calculation():
    resp = client.post("/api/scenario", json={"rainfall_mm_24h": 90, "scenario": "rainfall"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["rainfall_mm_24h"] == 90
    assert "risk_index" in data
    assert data["risk_level"] in ["LOW", "MODERATE", "HIGH"]
    assert data["peak_wse_m"] >= 69.5

def test_simulate_endpoint():
    resp = client.post("/api/simulate", json={"rainfall_mm_24h": 60, "scenario": "rapid-rise"})
    assert resp.status_code == 200
    data = resp.json()
    assert "simulation_frames" in data
    assert len(data["simulation_frames"]) > 0
    assert "building_impacts" in data

def test_weather_endpoint():
    resp = client.get("/api/weather")
    assert resp.status_code == 200
    data = resp.json()
    assert "temperature_c" in data
    assert "relative_humidity_pct" in data

def test_elevation_point_query():
    resp = client.get("/api/elevation?lon=78.693&lat=10.865")
    assert resp.status_code == 200
    data = resp.json()
    assert "ground_elevation_m" in data
    assert data["vertical_datum"] == "EGM96 / MSL"
    assert 50.0 <= data["ground_elevation_m"] <= 100.0

def test_geojson_endpoints():
    river_resp = client.get("/api/river")
    assert river_resp.status_code == 200
    assert len(river_resp.json()["features"]) >= 2 # Cauvery and Kollidam

    stations_resp = client.get("/api/monitoring-points")
    assert stations_resp.status_code == 200
    assert len(stations_resp.json()["features"]) >= 4

    bld_resp = client.get("/api/buildings")
    assert bld_resp.status_code == 200
    assert len(bld_resp.json()["features"]) >= 8
