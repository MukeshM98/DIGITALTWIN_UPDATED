"""Educational connected-stage inundation; not a rainfall-runoff or forecasting model."""
import json
import math
from collections import deque
from functools import lru_cache
from pathlib import Path
import numpy as np
from shapely import contains_xy
from shapely.geometry import shape, box, mapping
from shapely.ops import unary_union

DATA_DIR = Path(__file__).resolve().parent / 'data'
GEO_DIR = DATA_DIR.parents[1] / 'frontend/data'
BASE_STAGE = 69.5  # Illustrative baseline, NOT a measured river gauge.

class FloodSimulationEngine:
    def __init__(self, dem_path=None, meta_path=None):
        self.dem_path = dem_path or DATA_DIR/'prepared_dem.npz'
        self.meta_path = meta_path or DATA_DIR/'prepared_dem_meta.json'
        self.load_data()

    def load_data(self):
        self.elevation_grid = np.load(self.dem_path)['elevation']
        self.meta = json.loads(self.meta_path.read_text())
        self.buildings = json.loads((GEO_DIR/'buildings-osm.geojson').read_text())['features']
        self.rivers = json.loads((DATA_DIR/'river.geojson').read_text())['features'] # legacy references only
        self.water = shape(json.loads((GEO_DIR/'water.geojson').read_text())['features'][0]['geometry'])
        h,w=self.elevation_grid.shape; b=self.meta['bounds']
        self.lons=b['west']+(np.arange(w)+.5)/w*(b['east']-b['west'])
        self.lats=b['north']-(np.arange(h)+.5)/h*(b['north']-b['south'])
        self.water_mask=contains_xy(self.water,self.lons[None,:],self.lats[:,None])
        self.cell_area=(b['east']-b['west'])*111320*math.cos(math.radians((b['north']+b['south'])/2))/w*(b['north']-b['south'])*111320/h
        self.building_cells=[]
        for f in self.buildings:
            geom=shape(f['geometry']); west,south,east,north=geom.bounds
            r0,c0=self.coord_to_grid(west,north); r1,c1=self.coord_to_grid(east,south)
            rr,cc=np.mgrid[r0:r1+1,c0:c1+1]
            mask=contains_xy(geom,self.lons[cc],self.lats[rr])
            cells=list(zip(rr[mask].tolist(),cc[mask].tolist()))
            if not cells:
                p=geom.representative_point(); cells=[self.coord_to_grid(p.x,p.y)]
            self.building_cells.append(cells)

    def inside(self,lon,lat):
        b=self.meta['bounds']; return b['west']<=lon<=b['east'] and b['south']<=lat<=b['north']

    def coord_to_grid(self,lon,lat):
        b=self.meta['bounds']; h,w=self.elevation_grid.shape
        return max(0,min(h-1,int((b['north']-lat)/(b['north']-b['south'])*h))),max(0,min(w-1,int((lon-b['west'])/(b['east']-b['west'])*w)))

    def grid_to_coord(self,row,col):
        b=self.meta['bounds']; h,w=self.elevation_grid.shape
        return b['west']+(col+.5)/w*(b['east']-b['west']),b['north']-(row+.5)/h*(b['north']-b['south'])

    def get_elevation(self,lon,lat):
        if not self.inside(lon,lat): raise ValueError('Outside prepared terrain coverage')
        value=float(self.elevation_grid[self.coord_to_grid(lon,lat)])
        if not np.isfinite(value): raise ValueError('Terrain no-data cell')
        return value

    def get_river_seeds(self):
        rivers=unary_union([shape(f['geometry']) for f in json.loads((GEO_DIR/'rivers-osm.geojson').read_text())['features']])
        mask=contains_xy(rivers,self.lons[None,:],self.lats[:,None])
        return list(zip(*np.where(mask)))

    def compute_wse(self,rainfall_mm,scenario,timestep_ratio,peak_rise_m=None):
        if scenario == 'dry':
            return float(np.nanmin(self.elevation_grid)) - 1
        # Legacy presets remain backward compatible, but are not a calibrated model.
        rise=peak_rise_m if peak_rise_m is not None else (rainfall_mm/60)**1.15*1.5*{'rainfall':1,'rapid-rise':1.25,'breach':1.45}.get(scenario,1)
        return round(BASE_STAGE+rise*math.sin(math.pi*timestep_ratio),2)

    def run_connectivity_flood(self,wse,river_seeds,max_distance_cells=None):
        h,w=self.elevation_grid.shape
        wet=np.isfinite(self.elevation_grid)&(self.elevation_grid<wse)
        visited=np.zeros((h,w),bool); queue=deque()
        for r,c in river_seeds:
            if 0<=r<h and 0<=c<w and wet[r,c] and not visited[r,c]:
                visited[r,c]=True; queue.append((r,c,0))
        # Four neighbours prevent diagonal leakage across barriers.
        while queue:
            r,c,d=queue.popleft()
            if max_distance_cells is not None and d>=max_distance_cells: continue
            for nr,nc in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)):
                if 0<=nr<h and 0<=nc<w and wet[nr,nc] and not visited[nr,nc]:
                    visited[nr,nc]=True; queue.append((nr,nc,d+1))
        return np.where(visited,wse-self.elevation_grid,0).astype(np.float32)

    def raster_to_geojson_polygons(self,depth_grid,wse,step_idx,time_h):
        h,w=depth_grid.shape; b=self.meta['bounds']
        classes=np.where(depth_grid>1.5,3,np.where(depth_grid>.5,2,np.where(depth_grid>.05,1,0)))
        features=[]
        for tier,name in ((1,'low'),(2,'moderate'),(3,'high')):
            rects=[]
            for r in range(h):
                edges=np.diff(np.pad((classes[r]==tier).astype(int),(1,1)))
                for c0,c1 in zip(np.where(edges==1)[0],np.where(edges==-1)[0]):
                    rects.append(box(b['west']+c0/w*(b['east']-b['west']),b['north']-(r+1)/h*(b['north']-b['south']),b['west']+c1/w*(b['east']-b['west']),b['north']-r/h*(b['north']-b['south'])))
            if rects:
                features.append({'type':'Feature','properties':{'severity':name,'depth_m':round(float(depth_grid[classes==tier].mean()),2),'wse_m':wse},'geometry':mapping(unary_union(rects))})
        values=depth_grid[depth_grid>.05]
        return {'type':'FeatureCollection','properties':{'step':step_idx,'time_hours':time_h,'wse_m':wse,'flooded_cells':int(len(values)),'inundated_sqkm':round(len(values)*self.cell_area/1e6,3),'mean_depth_m':round(float(values.mean()),2) if len(values) else 0,'max_depth_m':round(float(values.max()),2) if len(values) else 0},'features':features}

    def assess_building_impact(self,wse,depth_grid=None):
        if depth_grid is None: depth_grid=self.run_connectivity_flood(wse,self.get_river_seeds())
        impacts=[]; counts=dict(safe=0,minor=0,moderate=0,severe=0)
        for f,cells in zip(self.buildings,self.building_cells):
            p=f['properties']; depth=max(float(depth_grid[r,c]) for r,c in cells)
            elev=float(np.nanmin([self.elevation_grid[r,c] for r,c in cells]))
            category='severe' if depth>1.5 else 'moderate' if depth>.5 else 'minor' if depth>.05 else 'safe'
            counts[category]+=1
            impacts.append({'id':p['id'],'name':p['name'],'type':p['type'],'height_m':p['height'],'height_source':p['height_source'],'ground_elevation_m':round(elev,2),'water_depth_m':round(depth,2),'risk_category':category.upper()})
        return len(impacts)-counts['safe'],impacts,counts

    @lru_cache(maxsize=8)
    def depth_at_stage(self,wse):
        return self.run_connectivity_flood(wse,self.get_river_seeds())

    @lru_cache(maxsize=8)
    def simulate(self,rainfall_mm_24h,scenario,peak_rise_m=None):
        frames=[]; peak=BASE_STAGE; peak_depth=None
        for idx,hour in enumerate([0.,3.,6.,12.,18.,24.]):
            wse=self.compute_wse(rainfall_mm_24h,scenario,hour/24,peak_rise_m)
            depth=self.depth_at_stage(wse).copy()
            depth[self.water_mask]=0 # Baseline water is a distinct map layer.
            frame=self.raster_to_geojson_polygons(depth,wse,idx,hour)
            count,impacts,_=self.assess_building_impact(wse,depth)
            frame['properties']['affected_buildings']=count
            # Sparse state: absent buildings have zero connected depth.
            frame['impacts']={p['id']:p['water_depth_m'] for p in impacts if p['water_depth_m']>.05}
            frames.append(frame)
            if peak_depth is None or wse>=peak: peak=wse; peak_depth=depth
        count,impacts,tiers=self.assess_building_impact(peak,peak_depth)
        risk=round(100*count/max(1,len(self.buildings)))
        return {'metadata':{'model':'Four-neighbour connected stage scenario','baseline_wse_m':BASE_STAGE,'vertical_datum':self.meta['vertical_datum'],'rainfall_stage_link':'None when peak_rise_m supplied; otherwise legacy illustrative preset, not calibrated','disclaimer':'Educational only; no validated forecast, surveyed banks, barriers or bathymetry'},'inputs':{'rainfall_mm_24h':rainfall_mm_24h,'scenario':scenario,'peak_rise_m':peak_rise_m},'summary':{'risk_index':risk,'risk_level':'HIGH' if risk>=65 else 'MODERATE' if risk>=35 else 'LOW','peak_wse_m':peak,'peak_water_level_change_m':round(peak-BASE_STAGE,2),'max_inundated_sqkm':max(f['properties']['inundated_sqkm'] for f in frames),'total_affected_buildings':count,'building_risk_breakdown':tiers,'highest_risk_sector':'Not assessed; no validated sector boundaries','timesteps_count':6},'building_impacts':[{k:p[k] for k in ('id','water_depth_m','risk_category')} for p in impacts if p['water_depth_m']>.05],'simulation_frames':frames}

engine=FloodSimulationEngine()

