import React, { useEffect, useRef, useState } from 'react';
import BottomNav from '../components/BottomNav';
import LivePill from '../components/LivePill';
import MapCanvas from '../components/MapCanvas';
import { api, openRealtime } from '../lib/api';
import { BIZERTE, EMPTY_MAP } from '../lib/constants';

function routeDestination(assignment) {
  const coordinates = assignment?.geometry?.coordinates;
  if (!coordinates?.length) return null;
  const line = Array.isArray(coordinates[0]?.[0]) ? coordinates[coordinates.length - 1] : coordinates;
  const last = line?.[line.length - 1];
  return last ? [last[1], last[0]] : null;
}

export default function Driver() {
  const [data, setData] = useState(EMPTY_MAP);
  const [assignment, setAssignment] = useState(null);
  const [plan, setPlan] = useState(null);
  const [live, setLive] = useState('reconnecting');
  const [rerouting, setRerouting] = useState(false);
  const [pos, setPos] = useState(BIZERTE);
  const [notice, setNotice] = useState('');
  const busy = useRef(false);
  const mounted = useRef(true);

  const refresh = async () => {
    try { setData(await api.map()); }
    catch (error) { setNotice(`Carte indisponible : ${error.message}`); }
  };

  const calculate = async (activeAssignment = assignment, currentPosition = pos) => {
    const destination = routeDestination(activeAssignment);
    if (!destination) { setNotice('Aucune ligne active n’est affectée à ce conducteur.'); return; }
    if (busy.current) return;
    busy.current = true;
    setRerouting(true);
    setNotice('');
    try {
      const response = await api.nextBest({
        vehicle_id: activeAssignment.vehicle_code,
        current_lat: currentPosition[0], current_lon: currentPosition[1],
        destination_lat: destination[0], destination_lon: destination[1],
        alternatives: 3,
      });
      if (mounted.current) setPlan(response);
    } catch (error) {
      if (mounted.current) setNotice(`Recalcul impossible : ${error.message}`);
    } finally {
      busy.current = false;
      if (mounted.current) setRerouting(false);
    }
  };

  useEffect(() => {
    mounted.current = true;
    refresh();
    api.driver().then(rows => {
      const active = rows[0] || null;
      setAssignment(active);
      if (!active) { setNotice('Aucune ligne active ne vous est affectée.'); return; }
      navigator.geolocation?.getCurrentPosition(
        p => { const current = [p.coords.latitude, p.coords.longitude]; setPos(current); calculate(active, current); },
        () => calculate(active, BIZERTE),
      );
    }).catch(error => setNotice(error.message));
    const close = openRealtime(topic => {
      if (['complaint.created', 'road.event.created', 'road.event.validated', 'route.assignment'].includes(topic)) {
        refresh();
      }
    }, setLive);
    return () => { mounted.current = false; close?.(); };
  }, []);

  const destination = routeDestination(assignment);
  const normal = plan?.fastest_polyline || [];
  const safe = plan?.reroute_needed ? plan.polyline : [];

  return <div className="driver-app">
    <div className="driver-map-wrap">
      <MapCanvas data={data} userPosition={pos} destination={destination} selectedRoute={normal} alternative={safe} className="driver-map"/>
      <div className="driver-top"><div className="bus-chip"><span>BUS</span><div><b>{assignment?.vehicle_code || 'Non affecté'}</b><small>SRTB · {assignment ? 'En service' : 'En attente'}</small></div></div><LivePill status={live}/></div>
      <div className="nav-instruction"><div className="turn-arrow">↗</div><div><small>Navigation routière</small><strong>{!assignment ? 'Aucune ligne affectée' : plan?.reroute_needed ? 'Alternative de sécurité recommandée' : plan?.warning ? 'Danger sur l’itinéraire' : 'Itinéraire affecté vérifié'}</strong><span>{assignment?.name || 'Le Ministère du Transport doit affecter une ligne.'}</span></div></div>
      {notice && <div className="driver-live-toast"><i/> {notice}</div>}
    </div>
    <section className="driver-sheet"><div className="sheet-handle"/><div className="trip-row"><div><span>Ligne affectée</span><b>{assignment?.name || 'Aucune'}</b></div><div className="eta"><strong>{plan ? Math.round(plan.duration_s / 60) : '—'}</strong><span>min</span></div></div>
      {plan?.reroute_needed ? <><div className="hazard-banner"><div>!</div><span><b>{plan.hazards_on_initial ? 'Dangers détectés sur le trajet initial' : 'Trajet initial sur des segments à risque élevé'}</b><small>{plan.hazards_on_initial ? `${plan.hazards_on_initial} point(s)` : 'prédiction M2'} · risque {Math.round((plan.fastest_risk || 0) * 100)}%</small></span></div><div className="route-choice safe"><span className="shield">✓</span><div><b>Alternative plus sûre calculée</b><small>{(plan.distance_m / 1000).toFixed(1)} km · {Math.round(plan.duration_s / 60)} min · risque {Math.round((plan.risk || 0) * 100)}%</small><p>Rouge = trajet initial · Vert = prochain meilleur itinéraire calculé par OSRM.</p></div></div></> : plan?.warning ? <div className="hazard-banner"><div>!</div><span><b>Danger sur l’itinéraire — aucune alternative sûre</b><small>{plan.hazards_on_initial ? `${plan.hazards_on_initial} danger(s) sur le trajet` : 'segments à risque M2'} · risque {Math.round((plan.fastest_risk || 0) * 100)}% · prudence</small></span></div> : plan && <div className="route-choice safe"><span className="shield">✓</span><div><b>Itinéraire affecté vérifié</b><small>Aucun détour plus sûr nécessaire</small></div></div>}
      <button className="next-route-btn" disabled={rerouting || !assignment} onClick={() => calculate()}>{rerouting ? 'Analyse en cours…' : '↻ Vérifier et recalculer'}</button>
      <div className="trip-stats"><div><b>{data.events.length}</b><span>détections</span></div><div><b>{data.complaints.length}</b><span>signalements</span></div><div><b>{live === 'live' ? 'SSE' : '...'}</b><span>flux événements</span></div></div>
    </section>
    <BottomNav kind="driver"/>
  </div>;
}
