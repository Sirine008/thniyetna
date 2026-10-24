import React, { useEffect, useRef, useState } from 'react';
import { CircleCheck, RefreshCw, Route, TriangleAlert } from 'lucide-react';
import BottomNav from '../components/BottomNav';
import LivePill from '../components/LivePill';
import MapCanvas from '../components/MapCanvas';
import { api, openRealtime } from '../lib/api';
import { BIZERTE, EMPTY_MAP } from '../lib/constants';
import { distance, duration, plural } from '../lib/format';
import { apiErrorMessage } from '../lib/labels';
import { routeState } from '../lib/routeState';
import { Button, MapLegend, Notice } from '../ui';

function routeDestination(assignment) {
  const coordinates = assignment?.geometry?.coordinates;
  if (!coordinates?.length) return null;
  const line = Array.isArray(coordinates[0]?.[0]) ? coordinates[coordinates.length - 1] : coordinates;
  const last = line?.[line.length - 1];
  return last ? [last[1], last[0]] : null;
}

const BANNER_ICON = { safe: CircleCheck, reroute: Route, warning: TriangleAlert };

/** Large state banner: reroute (orange), warning (red), verified (green); same wording as the citizen card. */
function RouteBanner({ plan }) {
  const state = routeState(plan);
  const Icon = BANNER_ICON[state.kind];
  return <section className={`drive-banner is-${state.kind}`} role={state.kind === 'safe' ? 'status' : 'alert'} aria-label="État de l’itinéraire">
    <Icon aria-hidden="true"/>
    <div className="drive-banner-body">
      <h2>{state.kind === 'safe' ? 'Itinéraire affecté vérifié' : state.title}</h2>
      <p>{state.kind === 'safe' ? 'Aucun détour plus sûr nécessaire.' : state.detail}</p>
      {state.kind === 'reroute' && <p className="t-sm">Rouge : trajet initial · vert : itinéraire de remplacement calculé par OSRM.</p>}
    </div>
    {(state.hazards.length > 0 || state.note) && <div className="drive-hazards">
      {state.hazards.length > 0 && <><h3>{state.hazardsTitle} ({state.hazards.length})</h3><ul>{state.hazards.map((h, i) => <li key={i}>{h}</li>)}</ul></>}
      {state.note && <p>{state.note}</p>}
    </div>}
  </section>;
}

export default function Driver() {
  const [data, setData] = useState(EMPTY_MAP);
  const [assignment, setAssignment] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [plan, setPlan] = useState(null);
  const [live, setLive] = useState('reconnecting');
  const [rerouting, setRerouting] = useState(false);
  const [pos, setPos] = useState(BIZERTE);
  const [notice, setNotice] = useState('');
  const busy = useRef(false);
  const mounted = useRef(true);

  const refresh = async () => {
    try { setData(await api.map()); }
    catch (error) { setNotice(`Carte indisponible : ${apiErrorMessage(error.message)}`); }
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
      if (mounted.current) setNotice(`Recalcul impossible : ${apiErrorMessage(error.message)}`);
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
      setLoaded(true);
      if (!active) { setNotice('Aucune ligne active ne vous est affectée.'); return; }
      navigator.geolocation?.getCurrentPosition(
        p => { const current = [p.coords.latitude, p.coords.longitude]; setPos(current); calculate(active, current); },
        () => calculate(active, BIZERTE),
      );
    }).catch(error => { setLoaded(true); setNotice(apiErrorMessage(error.message)); });
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
  const state = plan ? routeState(plan) : null;
  const legend = ['hazards', ...(state && state.kind !== 'safe' ? ['route'] : [])];

  return <div className="m-shell drive">
    <a className="skip-link" href="#contenu">Aller au contenu</a>
    <header className="m-header">
      <span className="wordmark">THNIYETNA</span>
      <div className="drive-bus"><b className="t-mono">{assignment?.vehicle_code || 'Aucun bus'}</b><span className="t-xs t-muted">SRTB · {assignment ? 'en service' : 'en attente d’affectation'}</span></div>
      <LivePill status={live}/>
    </header>
    <main id="contenu" className="m-content drive-content">
      <section className="drive-line" aria-label="Ligne affectée">
        <p className="t-xs t-muted">Ligne affectée</p>
        <h1>{assignment?.name || (loaded ? 'Aucune ligne affectée' : 'Chargement de la ligne…')}</h1>
        {!assignment && loaded && <p className="t-sm t-muted">Le Ministère du Transport doit vous affecter une ligne.</p>}
        {plan && <p className="drive-trip t-num">{duration(plan.duration_s)} · {distance(plan.distance_m)}</p>}
      </section>
      <div className="drive-map">
        <MapCanvas data={data} userPosition={pos} destination={destination} selectedRoute={normal} alternative={safe} dangerRoute={state?.kind === 'warning'}
          startLabel="Position du bus" destinationLabel="Terminus de la ligne" className="drive-map-canvas"/>
        <MapLegend show={legend} floating/>
      </div>
      {notice && <Notice tone={assignment ? 'error' : 'info'} title={notice}/>}
      {rerouting && !plan && <div className="loading-line" role="status"><span className="spinner" aria-hidden="true"/>Analyse de l’itinéraire…</div>}
      {plan && <RouteBanner plan={plan}/>}
      <Button variant="primary" size="lg" block icon={RefreshCw} loading={rerouting} disabled={!assignment} onClick={() => calculate()}>{rerouting ? 'Analyse en cours…' : 'Vérifier et recalculer'}</Button>
      <p className="t-xs t-muted">Carte : {plural(data.events.length, 'détection')} · {plural(data.complaints.length, 'signalement')}. Les nouveaux événements sont reçus automatiquement.</p>
    </main>
    <BottomNav kind="driver"/>
  </div>;
}
