"""Rebuild explicitly prerecorded offline scenarios from the current prepared terrain."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.flood_simulation import engine, GEO_DIR
for rise in ('dry',0,2,6):
    result=engine.simulate(80,'dry' if rise == 'dry' else 'rainfall',0 if rise == 'dry' else rise)
    result['metadata']['offline_demo']='Prerecorded scenario; 80 mm contextual input; stage rise is independent'
    (GEO_DIR/f'demo-{rise}.json').write_text(json.dumps(result,separators=(',',':')))
    print(rise,result['summary'])
