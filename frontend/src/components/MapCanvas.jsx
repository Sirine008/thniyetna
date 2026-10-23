import React,{useEffect,useRef,useState} from 'react';
import {BIZERTE,demoBadge} from '../lib/constants';
let leafletPromise;
function loadLeaflet(){if(window.L)return Promise.resolve(window.L);if(leafletPromise)return leafletPromise;leafletPromise=new Promise((resolve,reject)=>{if(!document.querySelector('link[data-leaflet]')){const l=document.createElement('link');l.rel='stylesheet';l.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';l.dataset.leaflet='1';document.head.appendChild(l)}const s=document.createElement('script');s.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';s.onload=()=>resolve(window.L);s.onerror=reject;document.head.appendChild(s)});return leafletPromise;}
const icon=(L,type,label)=>L.divIcon({className:'th-marker-wrap',html:`<div class="th-marker ${type}"><span>${label}</span></div>`,iconSize:[34,34],iconAnchor:[17,17]});
export default function MapCanvas({data,selectedRoute=[],alternative=[],userPosition,destination,onMapClick,interactive=true,className=''}){
 const el=useRef(),map=useRef(),layer=useRef(),[offline,setOffline]=useState(false);
 useEffect(()=>{let alive=true;loadLeaflet().then(L=>{if(!alive)return;if(!map.current){map.current=L.map(el.current,{zoomControl:false,attributionControl:false,dragging:interactive,scrollWheelZoom:interactive,doubleClickZoom:interactive}).setView(BIZERTE,13);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map.current);L.control.zoom({position:'bottomright'}).addTo(map.current);if(onMapClick)map.current.on('click',e=>onMapClick([e.latlng.lat,e.latlng.lng]))}setTimeout(()=>map.current?.invalidateSize(),50)}).catch(()=>setOffline(true));return()=>{alive=false}},[]);
 useEffect(()=>{if(!map.current||!window.L)return;const L=window.L;layer.current?.remove();const group=L.layerGroup().addTo(map.current);layer.current=group;
   // Intentionally do NOT render official-route/risk-segment overlays here. They created the faint red/blue lines
   // that looked like navigation routes. Navigation geometry below comes only from OSRM.
   (data?.events||[]).filter(e=>e.status!=='closed').forEach(e=>L.marker([e.latitude,e.longitude],{icon:icon(L,'danger','!')}).addTo(group).bindPopup(`${demoBadge(e)}<b>${(e.event_type||'Défaut routier').replaceAll('_',' ')}</b><br/>Sévérité ${Math.round((e.severity||0)*100)}%<br/><small>Détection véhicule · ${e.status||'observed'}</small>`));
   (data?.complaints||[]).filter(c=>!['resolved','rejected'].includes(c.status)).forEach(c=>L.marker([c.latitude,c.longitude],{icon:icon(L,'claim','●')}).addTo(group).bindPopup(`${demoBadge(c)}<b>Signalement citoyen</b><br/>${c.description||'Dégradation routière'}<br/><small>${c.status||'open'}</small>`));
   if(selectedRoute.length)L.polyline(selectedRoute,{weight:8,opacity:.96,className:alternative.length?'route-danger':'route-active'}).addTo(group);
   if(alternative.length)L.polyline(alternative,{weight:8,opacity:.98,className:'route-safe'}).addTo(group);
   if(userPosition)L.marker(userPosition,{icon:icon(L,'user','⌖')}).addTo(group).bindTooltip('Départ · GPS actuel');
   if(destination)L.marker(destination,{icon:icon(L,'destination','◆')}).addTo(group).bindTooltip('Destination');
   const routePts=[...selectedRoute,...alternative];
   if(routePts.length>1)map.current.fitBounds(L.latLngBounds(routePts),{padding:[70,70],maxZoom:15});
   else if(userPosition)map.current.setView(userPosition,13);
 },[data,selectedRoute,alternative,userPosition,destination ]);
 return <div className={`map-shell ${className}`}><div ref={el} className="leaflet-host"/>{offline&&<div className="map-fallback"><div className="grid-city"/><b>Carte hors-ligne</b><span>Les données THNIYETNA restent disponibles.</span></div>}</div>
}
