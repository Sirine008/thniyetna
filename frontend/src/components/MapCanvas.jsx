import React,{useEffect,useRef,useState} from 'react';
import {BIZERTE,demoBadge} from '../lib/constants';
let leafletPromise;
export function loadLeaflet(){if(window.L)return Promise.resolve(window.L);if(leafletPromise)return leafletPromise;leafletPromise=new Promise((resolve,reject)=>{if(!document.querySelector('link[data-leaflet]')){const l=document.createElement('link');l.rel='stylesheet';l.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';l.dataset.leaflet='1';document.head.appendChild(l)}const s=document.createElement('script');s.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';s.onload=()=>resolve(window.L);s.onerror=reject;document.head.appendChild(s)});return leafletPromise;}
const icon=(L,type,label)=>L.divIcon({className:'th-marker-wrap',html:`<div class="th-marker ${type}"><span>${label}</span></div>`,iconSize:[34,34],iconAnchor:[17,17]});
const pt=p=>p?`${p[0].toFixed(5)},${p[1].toFixed(5)}`:'';
// focus: a [lat,lon] to centre on (e.g. a searched destination); the view only moves when the route, the
// start / destination or the focus change, not on every data refresh or map click.
// onMarkerDrag(which, [lat,lon]) makes the start ('start') and destination ('destination') markers draggable;
// centerOnStart=false keeps the view still when the start moves (the citizen picks it by clicking the map).
// fitPadding: Leaflet fitBounds padding options, to keep the route clear of the cards drawn over the map.
export default function MapCanvas({data,selectedRoute=[],alternative=[],userPosition,destination,onMapClick,onMarkerDrag,focus,dangerRoute=false,startLabel='Départ · GPS actuel',destinationLabel='Destination',startIcon='⌖',destinationIcon='◆',centerOnStart=true,fitPadding={padding:[70,70]},interactive=true,className=''}){
 const el=useRef(),map=useRef(),layer=useRef(),clickRef=useRef(onMapClick),dragRef=useRef(onMarkerDrag),viewKey=useRef(''),[offline,setOffline]=useState(false),[ready,setReady]=useState(false);
 clickRef.current=onMapClick;dragRef.current=onMarkerDrag;
 useEffect(()=>{let alive=true;loadLeaflet().then(L=>{if(!alive)return;if(!map.current){map.current=L.map(el.current,{zoomControl:false,attributionControl:false,dragging:interactive,scrollWheelZoom:interactive,doubleClickZoom:interactive}).setView(BIZERTE,13);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map.current);L.control.zoom({position:'bottomright'}).addTo(map.current);map.current.on('click',e=>clickRef.current?.([e.latlng.lat,e.latlng.lng]))}setReady(true);setTimeout(()=>map.current?.invalidateSize(),50)}).catch(()=>setOffline(true));
   // the citizen layout changes the map height (stacked fields on mobile): keep Leaflet's size in sync
   const ro=window.ResizeObserver?new ResizeObserver(()=>map.current?.invalidateSize()):null;ro?.observe(el.current);
   return()=>{alive=false;ro?.disconnect()}},[]);
 useEffect(()=>{if(!map.current||!window.L)return;const L=window.L;layer.current?.remove();const group=L.layerGroup().addTo(map.current);layer.current=group;
   // Intentionally do NOT render official-route/risk-segment overlays here. They created the faint red/blue lines
   // that looked like navigation routes. Navigation geometry below comes only from OSRM.
   (data?.events||[]).filter(e=>e.status!=='closed').forEach(e=>L.marker([e.latitude,e.longitude],{icon:icon(L,'danger','!')}).addTo(group).bindPopup(`${demoBadge(e)}<b>${(e.event_type||'Défaut routier').replaceAll('_',' ')}</b><br/>Sévérité ${Math.round((e.severity||0)*100)}%<br/><small>Détection véhicule · ${e.status||'observed'}</small>`));
   (data?.complaints||[]).filter(c=>!['resolved','rejected'].includes(c.status)).forEach(c=>L.marker([c.latitude,c.longitude],{icon:icon(L,'claim','●')}).addTo(group).bindPopup(`${demoBadge(c)}<b>Signalement citoyen</b><br/>${c.description||'Dégradation routière'}<br/><small>${c.status||'open'}</small>`));
   if(selectedRoute.length)L.polyline(selectedRoute,{weight:8,opacity:.96,className:alternative.length||dangerRoute?'route-danger':'route-active'}).addTo(group);
   if(alternative.length)L.polyline(alternative,{weight:8,opacity:.98,className:'route-safe'}).addTo(group);
   const point=(pos,which,type,label,tip)=>{const m=L.marker(pos,{icon:icon(L,type,label),draggable:!!onMarkerDrag,autoPan:true,keyboard:true,title:tip,alt:tip}).addTo(group).bindTooltip(tip);
     if(onMarkerDrag)m.on('dragend',e=>{const p=e.target.getLatLng();dragRef.current?.(which,[p.lat,p.lng])});};
   if(userPosition)point(userPosition,'start','user',startIcon,startLabel);
   if(destination)point(destination,'destination','destination',destinationIcon,destinationLabel);
   const routePts=[...selectedRoute,...alternative];
   const key=[routePts.length,pt(routePts[0]),pt(routePts.at(-1)),centerOnStart?pt(userPosition):'',pt(focus)].join('|');
   if(key===viewKey.current)return;
   viewKey.current=key;
   if(routePts.length>1)map.current.fitBounds(L.latLngBounds(routePts),{...fitPadding,maxZoom:15});
   else if(focus)map.current.setView(focus,Math.max(map.current.getZoom(),14));
   else if(userPosition&&centerOnStart)map.current.setView(userPosition,Math.max(map.current.getZoom(),13));
 },[ready,data,selectedRoute,alternative,dangerRoute,userPosition,destination,focus,startLabel,destinationLabel,startIcon,destinationIcon,centerOnStart,!!onMarkerDrag]);
 return <div className={`map-shell ${className}`}><div ref={el} className="leaflet-host"/>{offline&&<div className="map-fallback"><div className="grid-city"/><b>Carte hors-ligne</b><span>Les données THNIYETNA restent disponibles.</span></div>}</div>
}
