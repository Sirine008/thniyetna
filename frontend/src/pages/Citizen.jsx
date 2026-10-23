import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import BottomNav from '../components/BottomNav';
import LivePill from '../components/LivePill';
import MapCanvas from '../components/MapCanvas';
import PlaceSearch, { placeDetail } from '../components/PlaceSearch';
import { api, openRealtime } from '../lib/api';
import { BIZERTE, EMPTY_MAP } from '../lib/constants';
import { routeState } from '../lib/routeState';

const QUICK = [
  ['Menzel Jemil', 37.2366, 9.9140],
  ['Centre-ville de Bizerte', 37.2746, 9.8739],
  ['Corniche de Bizerte', 37.2905, 9.8795],
];
const DEFAULT_START = { pos: BIZERTE, label: 'Centre de Bizerte', mode: 'default' };
const OUT_OF_ZONE = 'Destination hors de la zone couverte (gouvernorat de Bizerte)';

// "Près de Rue Avicenne (Rue · 100 m)" from GET /routing/places/nearest
const nearLabel = place => place ? `Près de ${place.name}` : 'Point choisi sur la carte';
const nearDetail = place => place ? [place.category, place.locality, place.distance_m != null && `à ${place.distance_m} m`].filter(Boolean).join(' · ') : 'Aucun lieu nommé à proximité';

export default function Citizen() {
  const [data, setData] = useState(EMPTY_MAP);
  const [live, setLive] = useState('reconnecting');
  const [start, setStart] = useState(DEFAULT_START);
  const [query, setQuery] = useState('');
  const [dest, setDest] = useState(null);   // {pos, label, detail, covered, focus}
  const [pickStart, setPickStart] = useState(false);
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [locating, setLocating] = useState(false);
  const [routeError, setRouteError] = useState('');
  const [notice, setNotice] = useState('');
  const lookup = useRef(0);

  const refresh = async () => {
    try { setData(await api.map()); }
    catch (error) { setNotice(`Carte indisponible : ${error.message}`); }
  };

  useEffect(() => {
    refresh();
    return openRealtime((topic) => {
      if (topic === 'complaint.created' || topic === 'road.event.created' || topic === 'road.event.validated') refresh();
    }, setLive);
  }, []);

  const resetPlan = () => { setPlan(null); setRouteError(''); };

  const choose = place => {
    lookup.current++;
    setQuery(place.label);
    setDest({ pos: [place.lat, place.lon], label: place.label, detail: place.detail, covered: true, focus: true });
    resetPlan();
  };

  const useMyPosition = () => {
    if (!navigator.geolocation) { setNotice('Géolocalisation indisponible sur cet appareil'); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      p => { setStart({ pos: [p.coords.latitude, p.coords.longitude], label: 'Ma position', mode: 'gps' }); setLocating(false); resetPlan(); },
      () => { setNotice('Position indisponible — départ : centre de Bizerte'); setLocating(false); },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  // A map click sets the destination (or the start after "Choisir sur la carte"), then names the nearest place.
  const onMapClick = async pos => {
    const id = ++lookup.current;
    const forStart = pickStart;
    setPickStart(false);
    resetPlan();
    if (forStart) setStart({ pos, label: 'Point choisi sur la carte', mode: 'map' });
    else { setDest({ pos, label: 'Point choisi sur la carte', detail: 'Recherche du lieu le plus proche…', covered: null }); setQuery(''); }
    try {
      const { place, covered, message } = await api.nearestPlace(pos[0], pos[1]);
      if (id !== lookup.current) return;
      if (forStart) setStart(s => ({ ...s, label: covered === false ? 'Hors zone couverte' : nearLabel(place) }));
      else {
        setDest({ pos, label: nearLabel(place), detail: covered === false ? message : nearDetail(place), covered });
        setQuery(nearLabel(place));
      }
    } catch {
      if (id === lookup.current && !forStart) setDest(d => d && { ...d, detail: 'Point sur la carte' });
    }
  };

  const clearDestination = () => { lookup.current++; setDest(null); resetPlan(); };

  const analyze = async () => {
    if (!dest || loading) return;
    setLoading(true);
    setRouteError('');
    try {
      setPlan(await api.planRoute({
        vehicle_id: 'citizen',
        current_lat: start.pos[0], current_lon: start.pos[1],
        destination_lat: dest.pos[0], destination_lon: dest.pos[1],
        alternatives: 3,
      }));
    } catch (error) {
      // 422: point outside the OSRM coverage / not routable, the API already gives the French message
      setRouteError(error.status === 422 ? error.message : `Analyse impossible : ${error.message}`);
      setPlan(null);
    } finally { setLoading(false); }
  };

  const normal = plan?.fastest_polyline || [];
  const safe = plan?.reroute_needed ? plan.polyline : [];
  const state = plan ? routeState(plan) : null;
  const outOfZone = dest?.covered === false;

  return <div className={`citizen-nav${pickStart ? ' picking' : ''}`}>
    <MapCanvas data={data} userPosition={start.pos} destination={dest?.pos} selectedRoute={normal} alternative={safe} dangerRoute={state?.kind === 'warning'}
      focus={dest?.focus ? dest.pos : undefined} onMapClick={onMapClick}
      startLabel={`Départ · ${start.label}`} destinationLabel={dest ? `Destination · ${dest.label}` : 'Destination'} className="citizen-nav-map"/>
    <div className="citizen-nav-top">
      <div className="nav-brand"><b>THNIYETNA</b><LivePill status={live}/></div>
      <div className="trip-box">
        <div className="trip-row-start">
          <span className="start-dot"/>
          <div><small>Départ</small><b title={start.label}>{start.label}</b></div>
          <button type="button" className={start.mode === 'gps' ? 'on' : ''} onClick={useMyPosition} disabled={locating} aria-label="Partir de ma position">⌖ <span>{locating ? '…' : 'Ma position'}</span></button>
          <button type="button" className={pickStart ? 'on' : ''} onClick={() => setPickStart(v => !v)} aria-pressed={pickStart} aria-label="Choisir le départ sur la carte">◎ <span>Carte</span></button>
        </div>
        <div className="trip-row-dest">
          <span className="dest-dot"/>
          <div><small>Destination</small><PlaceSearch value={query} onValueChange={setQuery} onChoose={r => choose({ label: r.name, lat: r.lat, lon: r.lon, detail: placeDetail(r) })} onClear={clearDestination}/></div>
        </div>
      </div>
      {pickStart && <div className="pick-hint">Touchez la carte pour choisir le point de départ <button type="button" onClick={() => setPickStart(false)}>Annuler</button></div>}
    </div>
    {notice && <div className="realtime-toast" onClick={() => setNotice('')}><i/> {notice}</div>}
    {!dest && <div className="nav-welcome"><span>Carte des incidents · Bizerte</span><h1>Voyagez avec une route vérifiée.</h1><p>Recherchez un lieu, une rue ou un établissement, ou touchez la carte pour choisir votre destination. THNIYETNA compare le trajet rapide aux alternatives OSRM et tient compte des événements routiers enregistrés.</p><div className="quick-destinations">{QUICK.map((q, i) => <button key={i} onClick={() => choose({ label: q[0], lat: q[1], lon: q[2], detail: 'Raccourci' })}>{q[0]}</button>)}</div></div>}
    {dest && !plan && <div className="citizen-route-sheet pre-analysis"><div className="sheet-handle"/><div className="route-summary"><div><small>Destination sélectionnée</small><b>{dest.label}</b>{dest.detail && <em className="dest-detail">{dest.detail}</em>}</div>{!outOfZone && <span className="gps-ready">{start.mode === 'gps' ? 'GPS prêt' : 'Départ prêt'}</span>}</div>
      {outOfZone || routeError
        ? <div className="route-alert route-error" role="alert"><span>!</span><div><b>{outOfZone ? OUT_OF_ZONE : routeError}</b><small>Choisissez un point dans le gouvernorat de Bizerte.</small></div></div>
        : <p className="analysis-copy">Départ : {start.label}. L’analyse utilise les incidents réellement enregistrés dans la plateforme.</p>}
      <button className="analyze-route-btn" onClick={analyze} disabled={loading || outOfZone}>{loading ? <>Analyse du trajet…</> : <>Analyser le trajet <span>→</span></>}</button></div>}
    {plan && state && <div className={`citizen-route-sheet route-state-${state.kind}`}><div className="sheet-handle"/>
      <div className="route-summary"><div><small>{start.mode === 'gps' ? 'GPS' : 'Départ'} → destination</small><b>{dest.label}</b></div><strong>{Math.round((plan.duration_s || 0) / 60)} <small>min</small></strong></div>
      {state.kind === 'reroute' && <div className="route-alert"><span>!</span><div><b>Trajet initial impacté</b><small>Risque {Math.round((plan.fastest_risk || 0) * 100)} % · {plan.hazards_on_initial ? `${plan.hazards_on_initial} danger(s)` : 'segments à risque élevé (M2)'}</small></div></div>}
      <div className={`route-verdict ${state.tone}`} role={state.kind === 'safe' ? undefined : 'alert'}><span>{state.kind === 'safe' ? '✓' : state.kind === 'reroute' ? '↪' : '!'}</span><div><b>{state.title}</b><small>{state.detail}</small></div></div>
      {(state.hazards.length > 0 || state.note) && <div className={`route-hazards ${state.tone}`}>{state.hazards.length > 0 && <><small>{state.hazardsTitle}</small><ul>{state.hazards.map((h, i) => <li key={i}>{h}</li>)}</ul></>}{state.note && <p>{state.note}</p>}</div>}
      {state.kind === 'reroute' && <div className="route-legend"><i className="red"/> Trajet initial <i className="green"/> Alternative OSRM</div>}
      {state.kind === 'warning' && <div className="route-legend"><i className="red"/> Seul trajet disponible · roulez prudemment</div>}
      <button className="secondary-route-btn" onClick={analyze}>Recalculer</button></div>}
    <Link className="floating-report" to="/citizen/report">＋ <span>Signaler</span></Link>
    <BottomNav kind="citizen"/>
  </div>;
}
