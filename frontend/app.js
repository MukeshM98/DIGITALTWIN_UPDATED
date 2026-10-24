/* FloodSense DT: local-first MapLibre geography and explicit educational stage scenarios. */
const INITIAL_VIEW={center:[78.693,10.865],zoom:13.8,pitch:58,bearing:-20};
const $=id=>document.getElementById(id);
const empty=()=>({type:'FeatureCollection',features:[]});
const state={rain:80,scenario:'rainfall',rise:2,exaggeration:1,layers:{terrain:true,buildings:true,flood:true,depth:true,river:true,riskZones:true,roads:true},frames:[],frame:0,speed:1,playing:false,selected:null,offline:false};
let map,popup,timer,inspection=0,routeVersion=0;
const api=location.port==='5173'||location.port==='5174'?'http://127.0.0.1:8000':'';
const escapeHTML=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function json(url,options={}){const r=await fetch(url,{...options,signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error(url+': '+r.status);return r.json();}
function status(message){$('mapStatus').textContent=message;}
function showError(message){$('mapError').textContent=message;$('mapError').hidden=false;}
const riskColor=['case',['>', ['coalesce',['feature-state','depth'],0],1.5],'#d8484b',['>',['coalesce',['feature-state','depth'],0],.5],'#e8a43c',['>',['coalesce',['feature-state','depth'],0],.05],'#50bfc3','#e0c8a4'];
async function initMap(){
 const started=performance.now();
 try{
  const [buildings,water,roads,land,meta]=await Promise.all(['buildings-osm.geojson','water.geojson','roads-osm.geojson','landcover-osm.geojson','terrain-meta.json'].map(f=>json('./data/'+f)));
  state.buildings=buildings;state.meta=meta;state.byId=new Map(buildings.features.map(f=>[f.properties.id,f]));
  map=new maplibregl.Map({container:'map',style:{version:8,sources:{},layers:[{id:'ground',type:'background',paint:{'background-color':'#d9dfce'}}]},...INITIAL_VIEW,maxPitch:70,minZoom:12,maxZoom:18,maxBounds:[[78.655,10.83],[78.735,10.915]],antialias:true});
  map.addControl(new maplibregl.NavigationControl({visualizePitch:true}),'bottom-right');
  map.addControl(new maplibregl.ScaleControl({unit:'metric'}),'bottom-right');
  map.on('error',e=>{showError('Map resource unavailable: '+(e.error?.message||'unknown error'));});
  map.on('load',()=>{
   map.addSource('dem',{type:'raster-dem',tiles:[location.origin+location.pathname.replace(/[^/]*$/,'')+'data/terrain/{z}/{x}/{y}.png'],tileSize:256,encoding:'terrarium',minzoom:12,maxzoom:12,bounds:[78.662109,10.833306,78.75,10.919618],attribution:'Terrain: <a href="https://registry.opendata.aws/terrain-tiles/">Mapzen Terrain Tiles</a>'});
   map.addSource('shade-dem',{type:'raster-dem',tiles:[location.origin+location.pathname.replace(/[^/]*$/,'')+'data/terrain/{z}/{x}/{y}.png'],tileSize:256,encoding:'terrarium',minzoom:12,maxzoom:12,bounds:[78.662109,10.833306,78.75,10.919618]});
   map.addSource('land',{type:'geojson',data:land});
   map.addLayer({id:'land',type:'fill',source:'land',paint:{'fill-color':['match',['get','landuse'],'forest','#779b78','farmland','#a9bf85','orchard','#91b28b','residential','#e4dfd1','industrial','#c4c0b6','#b7cba0'],'fill-opacity':.8}});
   map.addLayer({id:'shade',type:'hillshade',source:'shade-dem',paint:{'hillshade-exaggeration':.35,'hillshade-shadow-color':'#67735c','hillshade-highlight-color':'#fff5db','hillshade-illumination-direction':315}});
   map.addSource('water',{type:'geojson',data:water,attribution:'<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors (ODbL)</a>'});
   map.addLayer({id:'water',type:'fill',source:'water',paint:{'fill-color':'#368c9b','fill-opacity':.95}});
   map.addLayer({id:'banks',type:'line',source:'water',paint:{'line-color':'#f2dc9b','line-width':['interpolate',['linear'],['zoom'],12,1,16,3],'line-opacity':.9}});
   map.addSource('floodsrc',{type:'geojson',data:empty()});
   map.addLayer({id:'floodfill',type:'fill',source:'floodsrc',paint:{'fill-color':['match',['get','severity'],'high','#ce536b','moderate','#5481d4','#56bec5'],'fill-opacity':.38}});
   map.addLayer({id:'floodline',type:'line',source:'floodsrc',paint:{'line-color':'#405d9d','line-width':.7,'line-opacity':.45}});
   map.addSource('roads',{type:'geojson',data:roads});
   map.addLayer({id:'road-casing',type:'line',source:'roads',paint:{'line-color':['case',['==',['get','bridge'],true],'#425568','#8f8c7f'],'line-width':['interpolate',['linear'],['zoom'],12,1.5,16,6]}});
   map.addLayer({id:'roads',type:'line',source:'roads',paint:{'line-color':['case',['==',['get','bridge'],true],'#fff3ba','#faf5e9'],'line-width':['interpolate',['linear'],['zoom'],12,.7,16,3.8]}});
   map.addSource('buildings',{type:'geojson',data:buildings,promoteId:'id'});
   map.addLayer({id:'buildings',type:'fill-extrusion',source:'buildings',minzoom:12.5,paint:{'fill-extrusion-color':riskColor,'fill-extrusion-height':['get','height'],'fill-extrusion-base':0,'fill-extrusion-opacity':1,'fill-extrusion-vertical-gradient':true}});
   map.addSource('selection',{type:'geojson',data:empty()});
   map.addLayer({id:'selection',type:'line',source:'selection',paint:{'line-color':'#122a35','line-width':3}});
   map.addSource('route',{type:'geojson',data:empty()});
   map.addLayer({id:'route',type:'line',source:'route',paint:{'line-color':'#812ce0','line-width':5}});
   map.addSource('boundary',{type:'geojson',data:{type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[[[78.67,10.845],[78.72,10.845],[78.72,10.9],[78.67,10.9],[78.67,10.845]]]}}});
   map.addLayer({id:'boundary',type:'line',source:'boundary',paint:{'line-color':'#66745a','line-width':1.5,'line-dasharray':[4,3]}});
   state.labels=[];
   for(const [name,coords] of [['KOLLIDAM',[78.69773,10.87115]],['KAVERI',[78.67673,10.85520]],['SRIRANGAM TEMPLE',[78.6915,10.8625]]]){
    const el=document.createElement('span');el.className='geo-label';el.textContent=name;
    state.labels.push(new maplibregl.Marker({element:el}).setLngLat(coords).addTo(map));
   }
   map.setLight({anchor:'map',color:'#fff7e6',intensity:.48,position:[1.5,225,35]});
   map.setTerrain({source:'dem',exaggeration:1});
   setupControls();
   map.on('click',onMapClick);
   map.on('mousemove',e=>{$('inspectorCoord').textContent=e.lngLat.lng.toFixed(4)+'°E, '+e.lngLat.lat.toFixed(4)+'°N · click to inspect';});
   map.once('idle',()=>{$('loadTime').textContent='Scene ready '+((performance.now()-started)/1000).toFixed(2)+' s (load + render)';});
   status('LOCAL GEOGRAPHY · 1× TERRAIN');
   updateSimulation(); fetchWeather();
  });
 }catch(e){showError('Geography could not load. Run scripts/prepare_geography.py and serve over HTTP. '+e.message);}
}
function visible(id,on){if(map.getLayer(id))map.setLayoutProperty(id,'visibility',on?'visible':'none');}
function syncLayers(){
 const l=state.layers;
 visible('buildings',l.buildings);visible('selection',l.buildings);
 visible('water',l.river);visible('banks',l.river);state.labels?.slice(0,2).forEach(m=>m.getElement().hidden=!l.river);
 visible('roads',l.roads);visible('road-casing',l.roads);
 visible('floodfill',l.flood);visible('floodline',l.flood&&l.depth);
 map.setPaintProperty('floodfill','fill-color',l.depth?['match',['get','severity'],'high','#ce536b','moderate','#5481d4','#56bec5']:'#5481d4');
 map.setPaintProperty('buildings','fill-extrusion-color',l.riskZones?riskColor:'#e0c8a4');
 visible('shade',l.terrain);
 map.setTerrain(l.terrain?{source:'dem',exaggeration:state.exaggeration}:null);
}
async function updateSimulation(){
 pauseAnimation(); $('update').disabled=true;$('update').querySelector('.btn-text').textContent='Computing connected flood…';
 $('mapError').hidden=true;status('COMPUTING SCENARIO…');
 const started=performance.now();let result;
 try{
  if(new URLSearchParams(location.search).has('offline'))throw Error('Offline demo requested');
  result=await json(api+'/api/simulate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rainfall_mm_24h:state.rain,scenario:state.rise==='dry'?'dry':state.scenario,peak_rise_m:state.rise==='dry'?0:state.rise})});
  state.offline=false;status('LOCAL DATA · API SCENARIO');
 }catch(e){
  try{
   result=await json('./data/demo-'+state.rise+'.json');state.offline=true;
   status('PRERECORDED '+(state.rise==='dry'?'DRY TEST':state.rise+' m RISE')+' · OFFLINE DEMO');
  }catch(_){showError('Simulation unavailable. Start the API or select a bundled 0, 2 or 6 m rise demo.');$('update').disabled=false;$('update').querySelector('.btn-text').textContent='▶ Update Simulation';return;}
 }
 state.frames=result.simulation_frames;state.result=result;
 $('computeTime').textContent='Scenario response '+((performance.now()-started)/1000).toFixed(2)+' s (compute + transfer)';
 const s=result.summary;
 $('water').innerHTML=s.peak_wse_m.toFixed(1)+' <i>m</i>';
 $('waterDiff').textContent=state.rise==='dry'?'Dry test: below terrain minimum':'+'+s.peak_water_level_change_m.toFixed(1)+' m above assumed baseline';
 $('rainMetric').innerHTML=state.rain+' <i>mm</i>';
 $('score').innerHTML=s.risk_index+'<small>%</small>';$('bar').style.width=s.risk_index+'%';
 $('level').textContent='EDUCATIONAL';$('level').className='tag low';
 $('insSector').textContent='No validated sector assessment';
 $('insightTitle').textContent='Connected-stage scenario';
 $('insight').textContent='Mapped water seeds a level-surface flood. Rainfall is context only; peak rise is selected independently. No surveyed banks, drainage or validated warning thresholds.';
 $('timelineSlider').max=state.frames.length-1;
 renderFrame(0);
 $('update').disabled=false;$('update').querySelector('.btn-text').textContent='▶ Update Simulation';
}
function renderFrame(index){
 const frame=state.frames[index];if(!frame)return;
 state.frame=index;const p=frame.properties;
 map.getSource('floodsrc').setData({type:'FeatureCollection',features:frame.features});
 map.removeFeatureState({source:'buildings'});
 for(const [id,depth] of Object.entries(frame.impacts||{}))map.setFeatureState({source:'buildings',id},{depth});
 $('timelineTime').textContent='t = '+p.time_hours+'h / 24h';$('timelineSlider').value=index;
 $('insWse').textContent=p.wse_m.toFixed(2)+' m (assumed datum)';
 $('inundatedArea').innerHTML=p.inundated_sqkm.toFixed(2)+' <i>km²</i>';
 $('affectedBld').innerHTML=(p.affected_buildings||0)+' <i>/ '+state.buildings.features.length+'</i>';
 renderBuildingList();
 routeVersion++;map.getSource('route').setData(empty());$('routeStatus').textContent='Select a building, then request a route for this frame.';
}
function renderBuildingList(){
 const impacts=state.frames[state.frame]?.impacts||{};
 const sorted=state.buildings.features.filter(f=>impacts[f.properties.id]||f.properties.name!==f.properties.id).sort((a,b)=>(impacts[b.properties.id]||0)-(impacts[a.properties.id]||0)).slice(0,35);
 $('buildingList').replaceChildren();
 for(const f of sorted){
  const card=document.createElement('button');card.className='bld-card';
  card.textContent=f.properties.name+' · '+(impacts[f.properties.id]||0).toFixed(2)+' m';
  card.onclick=()=>selectBuilding(f,true);$('buildingList').appendChild(card);
 }
 $('stations').textContent='No live gauge feed connected. Legacy gauge coordinates and thresholds are unverified and are not displayed as observations.';
}
function selectBuilding(f,fly=false){
 state.selected=f;map.getSource('selection').setData(f);
 const coords=f.geometry.type==='Polygon'?f.geometry.coordinates[0][0]:f.geometry.coordinates[0][0][0];
 if(fly)map.flyTo({center:coords,zoom:16,pitch:58,duration:700});
 const p=f.properties;const depth=state.frames[state.frame]?.impacts?.[p.id]||0;
 if(popup)popup.remove();
 popup=new maplibregl.Popup().setLngLat(coords).setHTML('<strong>'+escapeHTML(p.name)+'</strong><p>Height: '+p.height+' m<br>'+escapeHTML(p.height_source)+'</p><p>Connected model depth: '+depth.toFixed(2)+' m<br>OSM footprint; flat roof approximation<br>Coarse terrain; not a structural assessment</p>').addTo(map);
 $('routeStatus').textContent='Selected '+p.name+'. Destination: mapped Vignesh Sri Ranga School; not a verified shelter.';
}
async function onMapClick(e){
 const buildings=map.queryRenderedFeatures(e.point,{layers:['buildings']});
 if(buildings.length){selectBuilding(state.byId.get(buildings[0].properties.id));return;}
 const version=++inspection;const wse=state.frames[state.frame]?.properties.wse_m??69.5;
 try{
  const p=await json(api+'/api/inspect?lon='+e.lngLat.lng+'&lat='+e.lngLat.lat+'&wse_m='+wse);
  if(version!==inspection)return;
  $('inspectorElev').textContent='Grid ground '+p.ground_elevation_m.toFixed(1)+' m';
  if(popup)popup.remove();
  popup=new maplibregl.Popup().setLngLat(e.lngLat).setHTML('<strong>Scenario grid inspection</strong><p>Ground: '+p.ground_elevation_m.toFixed(2)+' m<br>WSE: '+wse.toFixed(2)+' m<br>Connected depth: '+p.depth_m.toFixed(2)+' m<br>'+(p.baseline_water?'Mapped baseline water':'Land cell')+'</p><small>Assumed EGM96; no bathymetry. Display exaggeration does not change these values.</small>').addTo(map);
 }catch(_){$('inspectorElev').textContent='Grid inspection unavailable';}
}
async function routeSelected(){
 if(!state.selected){$('routeStatus').textContent='Select a mapped building first.';return;}
 const version=++routeVersion;
 const f=state.selected;const start=f.geometry.type==='Polygon'?f.geometry.coordinates[0][0]:f.geometry.coordinates[0][0][0];
 $('routeStatus').textContent='Checking road segments…';
 try{
  const r=await json(api+'/api/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({start,end:[78.6878967,10.8563813],wse_m:state.frames[state.frame].properties.wse_m})});
  if(version!==routeVersion)return;
  map.getSource('route').setData(r.geometry?{type:'Feature',properties:{},geometry:r.geometry}:empty());
  $('routeStatus').textContent=r.status==='no_available_route'?'No available route: '+r.reason:'Available under simulation assumptions: '+r.distance_m+' m; '+r.closed_segments+' closed segments. To mapped Vignesh Sri Ranga School. Safety and access unverified.';
 }catch(_){$('routeStatus').textContent='Routing unavailable: API required.';}
}
function pauseAnimation(){clearInterval(timer);state.playing=false;$('playBtn').disabled=false;$('pauseBtn').disabled=true;}
function playAnimation(){if(!state.frames.length)return;pauseAnimation();state.playing=true;$('playBtn').disabled=true;$('pauseBtn').disabled=false;timer=setInterval(()=>renderFrame((state.frame+1)%state.frames.length),1200/state.speed);}
function setupControls(){
 $('rain').oninput=e=>{state.rain=+e.target.value;$('rainLabel').textContent=state.rain+' mm / 24h';};
 $('rise').onchange=e=>{state.rise=e.target.value==='dry'?'dry':+e.target.value;};
 $('scenario').onchange=e=>{state.scenario=e.target.value;};
 $('update').onclick=updateSimulation;
 $('exaggeration').oninput=e=>{state.exaggeration=+e.target.value;$('exagLabel').textContent=state.exaggeration.toFixed(1)+'× (visual only)';syncLayers();};
 for(const [id,key] of Object.entries({terrain:'terrain',buildings:'buildings',flood:'flood',depthLayer:'depth',river:'river',riskZones:'riskZones',roads:'roads'}))$(id).onchange=e=>{state.layers[key]=e.target.checked;syncLayers();};
 $('camRotLeft').onclick=()=>map.rotateTo(map.getBearing()-30);$('camRotRight').onclick=()=>map.rotateTo(map.getBearing()+30);
 $('camTiltUp').onclick=()=>map.easeTo({pitch:Math.min(70,map.getPitch()+10)});$('camTiltDown').onclick=()=>map.easeTo({pitch:Math.max(0,map.getPitch()-10)});
 $('camZoomIn').onclick=()=>map.zoomIn();$('camZoomOut').onclick=()=>map.zoomOut();
 $('extent').onclick=()=>map.fitBounds([[78.67,10.845],[78.72,10.89]],{padding:60,pitch:40,bearing:0,duration:900});
 $('camNorth').onclick=()=>map.easeTo({bearing:0});
 $('camReset').onclick=()=>map.flyTo({...INITIAL_VIEW,duration:700});$('reset').onclick=$('camReset').onclick;
 $('flat').onclick=()=>map.easeTo({pitch:0,bearing:0});$('tilt').onclick=()=>map.easeTo({pitch:58,bearing:-20});
 map.on('pitchend',()=>{const three=map.getPitch()>15;$('modeBadge').textContent=three?'3D':'2D';$('tilt').classList.toggle('chosen',three);$('flat').classList.toggle('chosen',!three);});
 $('playBtn').onclick=playAnimation;$('pauseBtn').onclick=pauseAnimation;$('resetAnimBtn').onclick=()=>{pauseAnimation();renderFrame(0);};
 $('timelineSlider').oninput=e=>{pauseAnimation();renderFrame(+e.target.value);};
 document.querySelectorAll('.speed-btn').forEach(b=>b.onclick=()=>{state.speed=+b.dataset.speed;document.querySelectorAll('.speed-btn').forEach(x=>x.classList.toggle('active',x===b));if(state.playing)playAnimation();});
 $('insightsToggle').onclick=()=>{$('insightsContent').hidden=!$('insightsContent').hidden;};
 $('routeBtn').onclick=routeSelected;
}
async function fetchWeather(){
 if(new URLSearchParams(location.search).has('offline')){$('weatherSource').textContent='OFFLINE';return;}
 try{
  const w=await json(api+'/api/weather');
  if(w.status==='offline_fallback'){$('weatherSource').textContent='UNAVAILABLE';return;}
  $('tempVal').textContent=w.temperature_c.toFixed(1)+'°C';$('rainVal').textContent='Precipitation: '+w.precipitation_mm+' mm';$('humidVal').textContent='Humidity: '+w.relative_humidity_pct+'%';$('weatherSource').textContent=w.is_cached?'CACHED':'LIVE';
 }catch(_){$('weatherSource').textContent='UNAVAILABLE';}
}
document.addEventListener('DOMContentLoaded',initMap);

