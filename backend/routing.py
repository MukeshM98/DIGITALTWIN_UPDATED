"""Road-node routing for educational scenarios; no certified evacuation destinations."""
import heapq
import json
import math
import numpy as np
from backend.flood_simulation import engine, GEO_DIR

def distance(a,b):
    return math.hypot((a[0]-b[0])*109300,(a[1]-b[1])*111320)

class RoadRouter:
    def __init__(self,features):
        self.nodes={}; self.edges=[]
        for f in features:
            p=f['properties']
            if p.get('access') in ('private','no') or p.get('highway') in ('motorway','motorway_link','construction'): continue
            coords=f['geometry']['coordinates']
            for i,(a,b) in enumerate(zip(coords,coords[1:])):
                if not engine.inside(*a) or not engine.inside(*b): continue
                # Only shared OSM vertices connect; geometrical crossings are not intersections.
                ids=p.get('node_ids',[])
                ka=tuple(a)+(str(ids[i]),) if ids else tuple(a)
                kb=tuple(b)+(str(ids[i+1]),) if ids else tuple(b)
                self.nodes[ka]=a; self.nodes[kb]=b
                samples=max(2,math.ceil(distance(a,b)/8)+1)
                cells=[engine.coord_to_grid(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t) for t in np.linspace(0,1,samples)]
                self.edges.append((ka,kb,distance(a,b),cells,p.get('bridge',False)))

    def route(self,start,end,wse,closed_ids=()):
        if not self.nodes: return {'status':'no_available_route','reason':'No road data'}
        src=min(self.nodes,key=lambda n:distance(n,start)); dst=min(self.nodes,key=lambda n:distance(n,end))
        if distance(src,start)>250 or distance(dst,end)>250:
            return {'status':'no_available_route','reason':'Endpoint more than 250 m from mapped accessible road'}
        depths=engine.depth_at_stage(wse); graph={}; closed=0
        for idx,(a,b,length,cells,bridge) in enumerate(self.edges):
            # Unknown deck elevations: conservatively close bridges when underlying grid floods.
            if idx in closed_ids or any(not np.isfinite(engine.elevation_grid[r,c]) or depths[r,c]>.15 for r,c in cells):
                closed+=1; continue
            graph.setdefault(a,[]).append((b,length)); graph.setdefault(b,[]).append((a,length))
        queue=[(0,src)]; costs={src:0}; previous={}
        while queue:
            cost,node=heapq.heappop(queue)
            if cost!=costs[node]: continue
            if node==dst and node in graph: break
            for nxt,length in graph.get(node,[]):
                new=cost+length
                if new<costs.get(nxt,float('inf')):
                    costs[nxt]=new; previous[nxt]=node; heapq.heappush(queue,(new,nxt))
        if dst not in costs or dst not in graph:
            return {'status':'no_available_route','reason':'Flood closures or disconnected mapped roads','closed_segments':closed}
        path=[dst]
        while path[-1]!=src: path.append(previous[path[-1]])
        path.reverse()
        return {'status':'available_under_assumptions','distance_m':round(costs[dst]),'closed_segments':closed,'geometry':{'type':'LineString','coordinates':[self.nodes[n] for n in path]},'note':'Walking network; 0.15 m closure threshold; unknown bridge decks conservatively closed; endpoint access and destination safety unverified'}

router=RoadRouter(json.loads((GEO_DIR/'roads-osm.geojson').read_text())['features'])
