"""Local computation and serialization benchmark; not an FPS or network benchmark."""
import gzip
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.flood_simulation import engine
rows=[]
for name,rise in [('dry',0),('rainfall',2),('rainfall',6)]:
    start=time.perf_counter();result=engine.simulate(80,name,rise);compute=time.perf_counter()-start
    start=time.perf_counter();body=json.dumps(result,separators=(',',':')).encode();serialize=time.perf_counter()-start
    start=time.perf_counter();engine.simulate(80,name,rise);cached=time.perf_counter()-start
    rows.append(dict(scenario=name,rise=rise,compute_s=round(compute,3),serialize_s=round(serialize,3),cached_s=round(cached,6),json_bytes=len(body),gzip_bytes=len(gzip.compress(body)),summary=result['summary']))
path=Path(__file__).resolve().parents[1]/'docs/benchmark.json'
path.write_text(json.dumps(rows,indent=2));print(path.read_text())
