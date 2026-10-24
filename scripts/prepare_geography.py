"""Bounded, cached public-data acquisition. Run from project root; --refresh to reacquire.
No Google content. One Overpass request; sequential terrain requests; no automatic retries.
"""
import argparse
import hashlib
import io
import json
import math
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from PIL import Image
from shapely.geometry import Polygon, LineString, mapping, box
from shapely.ops import polygonize, unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'frontend/data'
CACHE = ROOT / 'data/raw'
BOUNDS = [78.67, 10.845, 78.72, 10.90]  # west south east north; both river crossings
REFRESH = False
records = []

def acquire(url, path, data=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if REFRESH or not path.exists():
        req = urllib.request.Request(url, data=data, headers={'User-Agent': 'FloodSenseDT-educational-data-preparation/1.0'})
        with urllib.request.urlopen(req, timeout=180) as response:
            body = response.read()
        path.write_bytes(body)
        time.sleep(1)
    body = path.read_bytes()
    records.append({'url': url, 'path': str(path.relative_to(ROOT)),
                    'acquired_utc': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                    'sha256': hashlib.sha256(body).hexdigest()})
    return body

def save(name, features):
    (OUT / name).write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, separators=(',', ':')), encoding='utf8')

def feature(geom, props):
    return {'type': 'Feature', 'properties': props, 'geometry': mapping(geom)}

def osm():
    w,s,e,n = BOUNDS
    query = f'''[out:json][timeout:120];(way[building]({s},{w},{n},{e});way[highway]({s},{w},{n},{e});way[natural=water]({s},{w},{n},{e});relation[natural=water]({s},{w},{n},{e});way[landuse]({s},{w},{n},{e}););out geom;'''
    (CACHE / 'query.overpass').write_text(query)
    raw = json.loads(acquire('https://overpass-api.de/api/interpreter', CACHE/'osm.json', urllib.parse.urlencode({'data': query}).encode()))
    if 'remark' in raw:
        raise RuntimeError(raw['remark'])
    layers = {'buildings': [], 'roads': [], 'water': [], 'landcover': []}
    clip = box(*BOUNDS)
    for obj in raw['elements']:
        tags = obj.get('tags', {})
        props = {'id': f"osm/{obj['type']}/{obj['id']}", 'source': 'OpenStreetMap', **tags}
        try:
            if obj['type'] == 'relation':
                outer, inner = [], []
                for m in obj.get('members', []):
                    pts = [(p['lon'],p['lat']) for p in m.get('geometry', []) if p]
                    if len(pts)>1:
                        (inner if m.get('role') == 'inner' else outer).append(LineString(pts))
                geom = unary_union(list(polygonize(outer))).difference(unary_union(list(polygonize(inner))))
            else:
                pts = [(p['lon'], p['lat']) for p in obj.get('geometry', [])]
                if 'highway' in tags:
                    geom = LineString(pts)
                elif len(pts)>3 and pts[0] == pts[-1]:
                    geom = Polygon(pts)
                else:
                    continue
            if not geom.is_valid: geom = geom.buffer(0)
            if geom.is_empty or not geom.intersects(clip): continue
            if 'building' in tags:
                props['clipped_to_study_area'] = not clip.covers(geom)
                geom = geom.intersection(clip)
                try:
                    height = float(tags.get('height','').replace(' m',''))
                    method = 'OSM height tag (not independently surveyed)'
                except ValueError:
                    try:
                        height = float(tags['building:levels']) * 3
                        method = 'Estimated: OSM floor count × 3 m'
                    except (ValueError, KeyError):
                        height, method = 7.5, 'Estimated: 7.5 m fallback; no height/floors recorded'
                props.update(height=max(2, min(150, height)), height_source=method, type=tags['building'], name=tags.get('name', props['id']))
                layers['buildings'].append(feature(geom, props))
            elif 'highway' in tags:
                props['bridge'] = tags.get('bridge','no') != 'no'
                props['node_ids'] = obj.get('nodes', [])
                layers['roads'].append(feature(geom, props))
            elif tags.get('natural') == 'water':
                layers['water'].append(feature(geom.intersection(clip), props))
            elif 'landuse' in tags:
                layers['landcover'].append(feature(geom.intersection(clip), props))
        except (ValueError, TypeError):
            continue
    # Union river/lake polygons removes overlapping relation members and preserves holes.
    water = unary_union([__import__('shapely').geometry.shape(f['geometry']) for f in layers['water']])
    save('water.geojson', [feature(water, {'source':'OpenStreetMap','name':'Mapped water boundaries; not surveyed banks'})])
    save('rivers-osm.geojson', [f for f in layers['water'] if f['properties'].get('water') == 'river'])
    for name in ('buildings','roads','landcover'):
        save(f'{name}-osm.geojson', layers[name])
    return {k:len(v) for k,v in layers.items()}

def terrain():
    z = 12
    def tile(lon,lat):
        return (lon+180)/360*2**z, (1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*2**z
    w,s,e,n = BOUNDS
    x0,y0 = map(math.floor,tile(w,n)); x1,y1 = map(math.floor,tile(e,s))
    mosaic = np.zeros(((y1-y0+1)*256,(x1-x0+1)*256), dtype=np.float32)
    for x in range(x0,x1+1):
        for y in range(y0,y1+1):
            path = OUT/f'terrain/{z}/{x}/{y}.png'
            rgb = np.array(Image.open(io.BytesIO(acquire(f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png',path)))).astype(float)
            mosaic[(y-y0)*256:(y-y0+1)*256,(x-x0)*256:(x-x0+1)*256] = rgb[:,:,0]*256+rgb[:,:,1]+rgb[:,:,2]/256-32768
    # Explicit WGS84 cell-centred grid, resampled from Web Mercator pixels.
    size=320
    lons=w+(np.arange(size)+.5)/size*(e-w); lats=n-(np.arange(size)+.5)/size*(n-s)
    cols=((lons+180)/360*2**z*256-x0*256).astype(int)
    rows=((1-np.arcsinh(np.tan(np.radians(lats)))/np.pi)/2*2**z*256-y0*256).astype(int)
    grid=mosaic[rows[:,None],cols[None,:]]
    np.savez_compressed(ROOT/'backend/data/prepared_dem.npz',elevation=grid)
    meta={'bounds':dict(zip(['west','south','east','north'],BOUNDS)), 'grid_shape':[size,size], 'crs':'EPSG:4326', 'vertical_datum':'EGM96 assumed from global terrain source; unverified locally', 'units':'metres', 'resolution_m':(e-w)*111320*math.cos(math.radians((n+s)/2))/size, 'source_resolution_m':38, 'source':'Mapzen Terrain Tiles, zoom 12; mixed-source DEM, not bathymetry', 'terrain_tile_bounds':[x0,y0,x1,y1], 'min_elevation_m':float(grid.min()),'max_elevation_m':float(grid.max())}
    (ROOT/'backend/data/prepared_dem_meta.json').write_text(json.dumps(meta,indent=2))
    (OUT/'terrain-meta.json').write_text(json.dumps(meta,indent=2))

def main():
    global REFRESH
    parser=argparse.ArgumentParser(); parser.add_argument('--refresh',action='store_true'); args=parser.parse_args(); REFRESH=args.refresh
    CACHE.mkdir(parents=True,exist_ok=True); OUT.mkdir(parents=True,exist_ok=True)
    counts=osm(); terrain()
    for name in ('maplibre-gl.js','maplibre-gl.css'):
        acquire(f'https://unpkg.com/maplibre-gl@5.6.1/dist/{name}',ROOT/f'frontend/vendor/{name}')
    acquire('https://unpkg.com/maplibre-gl@5.6.1/LICENSE.txt',ROOT/'frontend/vendor/LICENSE.txt')
    manifest={'prepared_utc':datetime.now(timezone.utc).isoformat(),'coverage_wsen':BOUNDS,'crs':'EPSG:4326 GeoJSON lon,lat','units':'metres for elevations/heights; degrees for coordinates','counts':counts,'licenses':{'OSM':'ODbL 1.0 https://www.openstreetmap.org/copyright','terrain':'https://github.com/tilezen/joerd/blob/master/docs/attribution.md','MapLibre':'BSD-3-Clause; vendor/LICENSE.txt'},'limitations':['OSM completeness and heights unverified','Terrain ~38 m pixels at zoom 12; resampling adds no detail','No surveyed banks, bridge deck elevations, bathymetry or validated shelters','Raw OSM retained to reproduce preparation without requests'], 'acquisitions':records}
    (OUT/'sources.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(counts))

if __name__=='__main__': main()
