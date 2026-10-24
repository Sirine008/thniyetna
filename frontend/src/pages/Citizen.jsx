import React, { useEffect, useRef, useState } from 'react';
import BottomNav from '../components/BottomNav';
import LivePill from '../components/LivePill';
import MapCanvas from '../components/MapCanvas';
import PlaceSearch, { placeDetail } from '../components/PlaceSearch';
import { api, openRealtime } from '../lib/api';
import { BIZERTE, EMPTY_MAP } from '../lib/constants';
import { routeState } from '../lib/routeState';
import { clickTarget, readTripQuery, swapTrip, tripError, tripQuery } from '../lib/trip';

// shortcuts: they fill « Arrivée »
const QUICK = [
  ['Menzel Jemil', 37.2366, 9.9140],
  ['Centre-ville de Bizerte', 37.2746, 9.8739],
  ['Corniche de Bizerte', 37.2905, 9.8795],
];
// first suggestions of « Départ »; the Bizerte centre is a shortcut, no longer an implicit start
const START_OPTIONS = [
  { key: 'gps', name: 'Ma position', category: 'Géolocalisation de l’appareil', category_key: 'gps' },
  { key: 'centre', name: 'Centre de Bizerte', category: 'Raccourci', category_key: 'shortcut', lat: BIZERTE[0], lon: BIZERTE[1] },
];
const FIELDS = { from: 'Départ', to: 'Arrivée' };
const AUTO_CHECK_MS = 300;

// "Près de Rue Avicenne" / "Rue · La Medina · à 100 m" from GET /routing/places/nearest
const nearLabel = place => place ? `Près de ${place.name}` : 'Point choisi sur la carte';
const nearDetail = place => place ? [place.category, place.locality, place.distance_m != null && `à ${place.distance_m} m`].filter(Boolean).join(' · ') : 'Aucun lieu nommé à proximité';
const posKey = p => p ? `${p.pos[0].toFixed(6)},${p.pos[1].toFixed(6)}` : '';
// route fitted between the fields (over the map on desktop, above it on mobile) and the result card
const routePadding = () => (window.matchMedia?.('(max-width:650px)').matches
  ? { paddingTopLeft: [30, 40], paddingBottomRight: [30, 260] }
  : { paddingTopLeft: [40, 200], paddingBottomRight: [40, 400] });

export default function Citizen() {
  const [data, setData] = useState(EMPTY_MAP);
  const [live, setLive] = useState('reconnecting');
  const [points, setPoints] = useState({ from: null, to: null }); // {pos, label, detail, covered}
  const [text, setText] = useState({ from: '', to: '' });
  const [active, setActive] = useState(null);                     // field focused last, filled by a map click
  const [focus, setFocus] = useState(null);
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [locating, setLocating] = useState(false);
  const [routeError, setRouteError] = useState('');
  const [notice, setNotice] = useState('');
  const lookups = useRef({ from: 0, to: 0 });
  const analysis = useRef(0);
  const { from, to } = points;

  const refresh = async () => {
    try { setData(await api.map()); }
    catch (error) { setNotice(`Carte indisponible : ${error.message}`); }
  };

  const resetPlan = () => { analysis.current++; setPlan(null); setRouteError(''); setLoading(false); };

  const setPoint = (field, point, fieldText = point?.label ?? '') => {
    lookups.current[field]++;
    setPoints(p => ({ ...p, [field]: point }));
    setText(t => ({ ...t, [field]: fieldText }));
    resetPlan();
  };

  // A point without a place name (map click, drag, GPS, shared URL): name it after the nearest indexed place
  // and learn whether it is inside the covered zone.
  const resolve = async (field, pos, label) => {
    setPoint(field, { pos, label: label || 'Point choisi sur la carte', detail: 'Recherche du lieu le plus proche…', covered: null });
    const id = lookups.current[field];
    try {
      const { place, covered, message } = await api.nearestPlace(pos[0], pos[1]);
      if (id !== lookups.current[field]) return;
      const name = label || nearLabel(place);
      setPoints(p => ({ ...p, [field]: { pos, label: name, detail: covered === false ? message : nearDetail(place), covered } }));
      setText(t => ({ ...t, [field]: name }));
    } catch {
      if (id === lookups.current[field]) setPoints(p => ({ ...p, [field]: p[field] && { ...p[field], detail: 'Point sur la carte' } }));
    }
  };

  useEffect(() => {
    refresh();
    const shared = readTripQuery(window.location.search); // ?from=lat,lon&to=lat,lon
    if (shared.from) resolve('from', shared.from);
    if (shared.to) resolve('to', shared.to);
    if (shared.from || shared.to) setFocus(shared.to || shared.from);
    return openRealtime((topic) => {
      if (topic === 'complaint.created' || topic === 'road.event.created' || topic === 'road.event.validated') refresh();
    }, setLive);
  }, []);

  // shareable URL, without adding a history entry per change
  useEffect(() => {
    const query = tripQuery(window.location.search, from, to);
    if (query !== window.location.search) window.history.replaceState(window.history.state, '', `${window.location.pathname}${query}`);
  }, [posKey(from), posKey(to)]);

  const useMyPosition = () => {
    if (!navigator.geolocation) { setNotice('Géolocalisation indisponible sur cet appareil'); return; }
    setLocating(true);
    setText(t => ({ ...t, from: 'Ma position…' }));
    navigator.geolocation.getCurrentPosition(
      p => { setLocating(false); const pos = [p.coords.latitude, p.coords.longitude]; resolve('from', pos, 'Ma position'); setFocus(pos); },
      () => { setLocating(false); setText(t => ({ ...t, from: '' })); setNotice('Position indisponible : choisissez le départ dans la liste ou sur la carte'); },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  const choose = (field, option) => {
    setActive(null);
    if (option.key === 'gps') { useMyPosition(); return; }
    const pos = [option.lat, option.lon];
    setPoint(field, { pos, label: option.name, detail: option.key ? option.category : placeDetail(option), covered: true });
    setFocus(pos);
  };

  const onMapClick = pos => {
    const field = clickTarget(active, from, to);
    setActive(null);
    resolve(field, pos);
  };

  const onMarkerDrag = (which, pos) => resolve(which === 'start' ? 'from' : 'to', pos);

  const swap = () => {
    const s = swapTrip({ from, to, text });
    lookups.current.from++; lookups.current.to++;
    setPoints({ from: s.from, to: s.to });
    setText(s.text);
    setActive(a => (a === 'from' ? 'to' : a === 'to' ? 'from' : a));
    resetPlan();
    // a name lookup still running belonged to the other field: run it again
    if (s.from?.covered === null) resolve('from', s.from.pos);
    if (s.to?.covered === null) resolve('to', s.to.pos);
  };

  const error = tripError(from, to);
  const ready = Boolean(from && to && !error);

  const analyze = async () => {
    if (!from || !to || tripError(from, to)) return;
    const id = ++analysis.current;
    setLoading(true);
    setRouteError('');
    try {
      const result = await api.planRoute({
        vehicle_id: 'citizen',
        current_lat: from.pos[0], current_lon: from.pos[1],
        destination_lat: to.pos[0], destination_lon: to.pos[1],
        alternatives: 3,
      });
      if (id === analysis.current) setPlan(result);
    } catch (err) {
      // 422: point outside the OSRM coverage / not routable, the API already gives the French message
      if (id === analysis.current) { setRouteError(err.status === 422 ? err.message : `Analyse impossible : ${err.message}`); setPlan(null); }
    } finally { if (id === analysis.current) setLoading(false); }
  };

  // automatic check as soon as both points are set and valid (the button re-runs it)
  useEffect(() => {
    if (!ready) return undefined;
    const t = setTimeout(analyze, AUTO_CHECK_MS);
    return () => clearTimeout(t);
  }, [posKey(from), posKey(to), ready]);

  const normal = plan?.fastest_polyline || [];
  const safe = plan?.reroute_needed ? plan.polyline : [];
  const state = plan ? routeState(plan) : null;
  const problem = error || routeError;
  const field = (name, extra = {}) => <PlaceSearch label={FIELDS[name]} badge={name === 'from' ? 'A' : 'B'} value={text[name]}
    onValueChange={v => setText(t => ({ ...t, [name]: v }))} onChoose={o => choose(name, o)} onFocus={() => setActive(name)}
    onClear={() => { setPoint(name, null); setActive(name); }} active={active === name} {...extra}/>;

  return <div className={`citizen-nav${active ? ' picking' : ''}`}>
    <MapCanvas data={data} userPosition={from?.pos} destination={to?.pos} selectedRoute={normal} alternative={safe} dangerRoute={state?.kind === 'warning'}
      focus={plan ? undefined : focus} onMapClick={onMapClick} onMarkerDrag={onMarkerDrag} centerOnStart={false} fitPadding={routePadding()}
      startIcon="A" destinationIcon="B" startLabel={from ? `Départ · ${from.label}` : 'Départ'} destinationLabel={to ? `Arrivée · ${to.label}` : 'Arrivée'}
      className="citizen-nav-map"/>
    <div className="citizen-nav-top">
      <div className="nav-brand"><b>THNIYETNA</b><LivePill status={live}/></div>
      <div className="trip-box">
        {field('from', { leading: START_OPTIONS, placeholder: locating ? 'Localisation…' : 'Lieu, « Ma position » ou la carte' })}
        <button type="button" className="swap-btn" onClick={swap} disabled={!from && !to} aria-label="Inverser départ et arrivée" title="Inverser départ et arrivée">⇅</button>
        {field('to', { placeholder: 'Où allez-vous ?' })}
      </div>
      {active && <div className="pick-hint" role="status">Touchez la carte pour choisir : {FIELDS[active]} <button type="button" onClick={() => setActive(null)}>Annuler</button></div>}
    </div>
    {notice && <div className="realtime-toast" onClick={() => setNotice('')}><i/> {notice}</div>}
    {!to && <div className="nav-welcome"><span>Carte des incidents · Bizerte</span><h1>Voyagez avec une route vérifiée.</h1><p>Choisissez un départ et une arrivée : recherchez un lieu, utilisez « Ma position » ou touchez la carte (les repères A et B se déplacent). THNIYETNA compare le trajet rapide aux alternatives OSRM et tient compte des événements routiers enregistrés.</p><div className="quick-destinations" aria-label="Raccourcis d’arrivée">{QUICK.map((q, i) => <button key={i} onClick={() => choose('to', { name: q[0], lat: q[1], lon: q[2], key: 'quick', category: 'Raccourci' })}>{q[0]}</button>)}</div></div>}
    {to && !plan && <div className="citizen-route-sheet pre-analysis"><div className="sheet-handle"/>
      <div className="trip-summary">
        <div><i className="badge-a">A</i><span><b>{from ? from.label : 'Départ à choisir'}</b>{from?.detail && <em>{from.detail}</em>}</span></div>
        <div><i className="badge-b">B</i><span><b>{to.label}</b>{to.detail && <em>{to.detail}</em>}</span></div>
      </div>
      {problem
        ? <div className="route-alert route-error" role="alert"><span>!</span><div><b>{problem}</b><small>{error && error.startsWith('Le départ') ? 'Choisissez deux points différents.' : 'Choisissez un point dans le gouvernorat de Bizerte.'}</small></div></div>
        : <p className="analysis-copy">{from ? (loading ? 'Analyse du trajet en cours…' : 'L’analyse utilise les incidents réellement enregistrés dans la plateforme.') : 'Indiquez le départ : tapez un lieu, choisissez « Ma position » ou touchez la carte.'}</p>}
      <button className="analyze-route-btn" onClick={analyze} disabled={loading || !ready}>{loading ? <>Analyse du trajet…</> : <>Vérifier le trajet <span>→</span></>}</button></div>}
    {plan && state && <div className={`citizen-route-sheet route-state-${state.kind}`}><div className="sheet-handle"/>
      <div className="route-summary"><div><small>{from.label} → arrivée</small><b>{to.label}</b></div><strong>{Math.round((plan.duration_s || 0) / 60)} <small>min</small></strong></div>
      {state.kind === 'reroute' && <div className="route-alert"><span>!</span><div><b>Trajet initial impacté</b><small>Risque {Math.round((plan.fastest_risk || 0) * 100)} % · {plan.hazards_on_initial ? `${plan.hazards_on_initial} danger(s)` : 'segments à risque élevé (M2)'}</small></div></div>}
      <div className={`route-verdict ${state.tone}`} role={state.kind === 'safe' ? undefined : 'alert'}><span>{state.kind === 'safe' ? '✓' : state.kind === 'reroute' ? '↪' : '!'}</span><div><b>{state.title}</b><small>{state.detail}</small></div></div>
      {(state.hazards.length > 0 || state.note) && <div className={`route-hazards ${state.tone}`}>{state.hazards.length > 0 && <><small>{state.hazardsTitle}</small><ul>{state.hazards.map((h, i) => <li key={i}>{h}</li>)}</ul></>}{state.note && <p>{state.note}</p>}</div>}
      {state.kind === 'reroute' && <div className="route-legend"><i className="red"/> Trajet initial <i className="green"/> Alternative OSRM</div>}
      {state.kind === 'warning' && <div className="route-legend"><i className="red"/> Seul trajet disponible · roulez prudemment</div>}
      <button className="secondary-route-btn" onClick={analyze}>Recalculer</button></div>}
    {/* « Signaler » is in the bottom nav (the floating button covered the welcome / route cards) */}
    <BottomNav kind="citizen"/>
  </div>;
}
