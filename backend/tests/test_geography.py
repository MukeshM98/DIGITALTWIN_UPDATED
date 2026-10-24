import numpy as np
import pytest
from shapely.geometry import shape
from backend.flood_simulation import engine
from backend.routing import RoadRouter

def test_nodata_and_corner_barrier():
    original=engine.elevation_grid
    try:
        engine.elevation_grid=np.array([[1,9,9],[9,1,np.nan],[9,9,1]],dtype=float)
        d=engine.run_connectivity_flood(2,[(0,0)])
        assert d[0,0]==1
        assert np.count_nonzero(d)==1
        assert np.all(np.isfinite(d))
    finally: engine.elevation_grid=original

def test_outside_is_not_clamped():
    with pytest.raises(ValueError): engine.get_elevation(78.6,10.8)

def test_explicit_rise_independent_of_rainfall():
    assert engine.compute_wse(0,'rainfall',.5,2)==engine.compute_wse(250,'breach',.5,2)==71.5

def test_dry_scenario_has_no_inundation():
    result=engine.simulate(0,'dry',0)
    assert result['summary']['total_affected_buildings']==0
    assert all(not f['features'] for f in result['simulation_frames'])

def test_grade_separated_vertices_do_not_connect(monkeypatch):
    coords=[[78.69,10.87],[78.691,10.87],[78.692,10.87]]
    roads=[{'properties':{'node_ids':[1,2]},'geometry':{'type':'LineString','coordinates':coords[:2]}},
           {'properties':{'node_ids':[3,4]},'geometry':{'type':'LineString','coordinates':coords[1:]}}]
    router=RoadRouter(roads)
    monkeypatch.setattr(engine,'depth_at_stage',lambda w:np.zeros_like(engine.elevation_grid))
    assert router.route(coords[0],coords[-1],56)['status']=='no_available_route'

def test_polygonization_preserves_dry_holes_and_severity():
    d=np.zeros_like(engine.elevation_grid)
    d[10:13,10:13]=2; d[11,11]=0; d[10,12]=.2
    geo=engine.raster_to_geojson_polygons(d,72,0,0)
    point=__import__('shapely').geometry.Point(engine.grid_to_coord(11,11))
    assert not any(shape(f['geometry']).contains(point) for f in geo['features'])
    assert {f['properties']['severity'] for f in geo['features']}=={'high','low'}
    assert geo['properties']['flooded_cells']==8

def test_buildings_use_connected_depth_not_properties():
    d=np.zeros_like(engine.elevation_grid)
    count,impacts,_=engine.assess_building_impact(90,d)
    assert count==0 and all(b['water_depth_m']==0 for b in impacts)

def test_route_closes_interior_segment_and_no_route(monkeypatch):
    a,b,c=(78.69,10.87),(78.691,10.87),(78.692,10.87)
    roads=[{'properties':{},'geometry':{'type':'LineString','coordinates':[a,b,c]}}]
    router=RoadRouter(roads)
    dry=np.zeros_like(engine.elevation_grid)
    monkeypatch.setattr(engine,'depth_at_stage',lambda w:dry)
    assert router.route(a,c,69.5)['status']=='available_under_assumptions'
    r,col=engine.coord_to_grid(78.6905,10.87);dry[r,col]=1
    assert router.route(a,c,72)['status']=='no_available_route'
    assert router.route(a,c,69.5,closed_ids=[0,1])['status']=='no_available_route'

def test_water_and_buildings_within_prepared_extent():
    assert len(engine.buildings)>1000
    assert len(engine.get_river_seeds())>100
    assert np.isfinite(engine.elevation_grid).all()
