import React, { useEffect, useRef, useState } from 'react';
import { BIZERTE } from '../lib/constants';
import { geoLines } from '../lib/segments';
import { riskLevel } from '../lib/risk';
import { riskLabel } from '../lib/labels';
import { RISK_STYLE, UNSCORED_STYLE, MapLegend } from '../ui/MapLegend';
import { loadLeaflet } from './MapCanvas';

const TILES = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const ATTRIBUTION = '© contributeurs OpenStreetMap';

/** Creates one Leaflet map in `ref` (muted basemap, zoom bottom-right, OSM attribution). */
function useLeafletMap(ref, { zoom = 11, center = BIZERTE, interactive = true } = {}) {
  const [state, setState] = useState({ map: null, L: null, offline: false });
  useEffect(() => {
    let alive = true, map;
    loadLeaflet().then(L => {
      if (!alive || !ref.current) return;
      map = L.map(ref.current, { zoomControl: false, attributionControl: true, dragging: interactive, scrollWheelZoom: false, doubleClickZoom: interactive, keyboard: interactive }).setView(center, zoom);
      map.attributionControl.setPrefix(false);
      L.tileLayer(TILES, { maxZoom: 19, attribution: ATTRIBUTION }).addTo(map);
      if (interactive) L.control.zoom({ position: 'bottomright', zoomInTitle: 'Zoom avant', zoomOutTitle: 'Zoom arrière' }).addTo(map);
      setTimeout(() => map.invalidateSize(), 50);
      setState({ map, L, offline: false });
    }).catch(() => alive && setState(s => ({ ...s, offline: true })));
    const ro = window.ResizeObserver ? new ResizeObserver(() => map?.invalidateSize()) : null;
    if (ref.current) ro?.observe(ref.current);
    return () => { alive = false; ro?.disconnect(); map?.remove(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return state;
}

const Offline = () => <div className="map-fallback"><b>Carte indisponible</b><span className="t-sm">Le fond de carte n’a pas pu être chargé ; les données restent dans le tableau.</span></div>;

const styleFor = (segment, selected) => {
  const level = riskLevel(segment);
  const s = RISK_STYLE[level] || UNSCORED_STYLE;
  return { color: s.hex, weight: s.weight + (selected ? 3 : 0), dashArray: s.dash, opacity: selected ? 1 : 0.9, lineCap: 'round' };
};

/**
 * Road segments coloured by M2 risk level (line style differs per level, see MapLegend).
 * Clicking a segment calls onSelect(segment); `selectedCode` is highlighted and brought into view.
 */
export function SegmentMap({ segments, selectedCode, onSelect, height = 420, label = 'Carte des segments', legend = ['risk'] }) {
  const ref = useRef();
  const { map, L, offline } = useLeafletMap(ref);
  const layers = useRef(new Map());
  const fitted = useRef('');

  useEffect(() => {
    if (!map) return undefined;
    const group = L.featureGroup().addTo(map);
    layers.current = new Map();
    segments.forEach(segment => {
      const lines = geoLines(segment.geometry);
      if (!lines.length) return;
      const casing = L.polyline(lines, { color: '#141a21', weight: 0, opacity: 0, interactive: false }).addTo(group);
      const line = L.polyline(lines, styleFor(segment, false)).addTo(group);
      line.bindTooltip(`${segment.name || segment.segment_code} · ${riskLabel(riskLevel(segment))}`, { sticky: true });
      if (onSelect) line.on('click', () => onSelect(segment));
      layers.current.set(segment.segment_code, { line, casing, segment });
    });
    const key = segments.map(s => s.segment_code).join('|');
    if (key !== fitted.current && group.getLayers().length) { fitted.current = key; map.fitBounds(group.getBounds(), { padding: [24, 24], maxZoom: 14 }); }
    return () => group.remove();
  }, [map, segments]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!map) return;
    layers.current.forEach(({ line, casing, segment }, code) => {
      const on = code === selectedCode;
      line.setStyle(styleFor(segment, on));
      casing.setStyle(on ? { weight: styleFor(segment, true).weight + 4, opacity: 0.85 } : { weight: 0, opacity: 0 });
      if (on) { casing.bringToFront(); line.bringToFront(); map.fitBounds(line.getBounds(), { padding: [48, 48], maxZoom: 15 }); }
    });
  }, [map, selectedCode, segments]);

  return <figure className="map-figure" style={{ margin: 0 }}>
    <div className="map-shell" style={{ blockSize: height }} role="region" aria-label={label}><div ref={ref} className="leaflet-host"/>{offline && <Offline/>}</div>
    {legend && <figcaption className="map-caption"><MapLegend show={legend}/></figcaption>}
  </figure>;
}

/** Small map centred on one point (citizen report, detection). */
export function PointMap({ lat, lon, kind = 'claim', height = 180, label = 'Position' }) {
  const ref = useRef();
  const { map, L, offline } = useLeafletMap(ref, { zoom: 15, center: [lat, lon], interactive: true });
  useEffect(() => {
    if (!map) return undefined;
    map.setView([lat, lon], 15);
    const icon = L.divIcon({ className: 'th-marker-wrap', html: `<div class="th-marker ${kind === 'event' ? 'danger' : 'claim'}"><span></span></div>`, iconSize: [34, 34], iconAnchor: [17, 17] });
    const marker = L.marker([lat, lon], { icon, keyboard: false }).addTo(map);
    return () => marker.remove();
  }, [map, lat, lon, kind]);
  return <div className="map-shell" style={{ blockSize: height, borderRadius: 'var(--radius-sm)', border: 'var(--border)' }} role="img" aria-label={label}><div ref={ref} className="leaflet-host" style={{ minBlockSize: height }}/>{offline && <Offline/>}</div>;
}
