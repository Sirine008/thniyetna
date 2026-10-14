import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import BottomNav from '../components/BottomNav';
import LivePill from '../components/LivePill';
import MapCanvas from '../components/MapCanvas';
import { api, openRealtime } from '../lib/api';
import { BIZERTE, EMPTY_MAP } from '../lib/constants';

const QUICK = [
  ['Menzel Jemil', 37.2366, 9.9140],
  ['Centre-ville de Bizerte', 37.2746, 9.8739],
  ['Corniche de Bizerte', 37.2905, 9.8795],
];

export default function Citizen() {
  const [data, setData] = useState(EMPTY_MAP);
  const [live, setLive] = useState('reconnecting');
  const [pos, setPos] = useState(BIZERTE);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [dest, setDest] = useState(null);
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState('');
  const timer = useRef();

  const refresh = async () => {
    try { setData(await api.map()); }
    catch (error) { setNotice(`Carte indisponible : ${error.message}`); }
  };

  useEffect(() => {
    refresh();
    navigator.geolocation?.getCurrentPosition(p => setPos([p.coords.latitude, p.coords.longitude]));
    return openRealtime((topic) => {
      if (topic === 'complaint.created' || topic === 'road.event.created' || topic === 'road.event.validated') refresh();
    }, setLive);
  }, []);

  const search = value => {
    setQuery(value);
    setPlan(null);
    clearTimeout(timer.current);
    if (value.trim().length < 2) { setResults([]); return; }
    timer.current = setTimeout(async () => {
      try {
        const rows = await api.geocode(value);
        setResults(rows.length ? rows : QUICK.filter(x => x[0].toLowerCase().includes(value.toLowerCase())).map(x => ({ label: x[0], lat: x[1], lon: x[2] })));
      } catch {
        setResults(QUICK.filter(x => x[0].toLowerCase().includes(value.toLowerCase())).map(x => ({ label: x[0], lat: x[1], lon: x[2] })));
      }
    }, 280);
  };

  const choose = place => {
    setQuery(place.label.split(',')[0]);
    setResults([]);
    setDest([place.lat, place.lon]);
    setPlan(null);
  };

  const analyze = async () => {
    if (!dest || loading) return;
    setLoading(true);
    setNotice('');
    try {
      setPlan(await api.planRoute({
        vehicle_id: 'citizen',
        current_lat: pos[0], current_lon: pos[1],
        destination_lat: dest[0], destination_lon: dest[1],
        alternatives: 3,
      }));
    } catch (error) {
      setNotice(`Analyse impossible : ${error.message}`);
    } finally { setLoading(false); }
  };

  const normal = plan?.fastest_polyline || [];
  const safe = plan?.reroute_needed ? plan.polyline : [];

  return <div className="citizen-nav">
    <MapCanvas data={data} userPosition={pos} destination={dest} selectedRoute={normal} alternative={safe} className="citizen-nav-map"/>
    <div className="citizen-nav-top">
      <div className="nav-brand"><b>THNIYETNA</b><LivePill status={live}/></div>
      <div className="destination-box"><span className="start-dot"/><div><small>Départ · GPS actuel</small><input value={query} onChange={e => search(e.target.value)} placeholder="Où allez-vous ?" autoComplete="off"/></div><button onClick={() => navigator.geolocation?.getCurrentPosition(p => setPos([p.coords.latitude, p.coords.longitude]))}>⌖</button></div>
      {results.length > 0 && <div className="search-results">{results.map((r, i) => <button key={i} onClick={() => choose(r)}><span>⌖</span><div><b>{r.label.split(',')[0]}</b><small>{r.label}</small></div></button>)}</div>}
    </div>
    {notice && <div className="realtime-toast"><i/> {notice}</div>}
    {!dest && <div className="nav-welcome"><span>Carte des incidents · Bizerte</span><h1>Voyagez avec une route vérifiée.</h1><p>Choisissez une destination. THNIYETNA compare le trajet rapide aux alternatives OSRM et tient compte des événements routiers enregistrés.</p><div className="quick-destinations">{QUICK.map((q, i) => <button key={i} onClick={() => choose({ label: q[0], lat: q[1], lon: q[2] })}>{q[0]}</button>)}</div></div>}
    {dest && !plan && <div className="citizen-route-sheet pre-analysis"><div className="sheet-handle"/><div className="route-summary"><div><small>Destination sélectionnée</small><b>{query}</b></div><span className="gps-ready">GPS prêt</span></div><p className="analysis-copy">L’analyse utilise les incidents réellement enregistrés dans la plateforme.</p><button className="analyze-route-btn" onClick={analyze} disabled={loading}>{loading ? <>Analyse du trajet…</> : <>Analyser le trajet <span>→</span></>}</button></div>}
    {plan && <div className="citizen-route-sheet"><div className="sheet-handle"/><div className="route-summary"><div><small>GPS → destination</small><b>{query}</b></div><strong>{Math.round((plan.duration_s || 0) / 60)} <small>min</small></strong></div>{plan.reroute_needed ? <><div className="route-alert"><span>!</span><div><b>Trajet initial impacté</b><small>Risque {Math.round((plan.fastest_risk || 0) * 100)}% · {plan.hazards_on_initial ? `${plan.hazards_on_initial} danger(s)` : 'segments à risque élevé (M2)'}</small></div></div><div className="route-recommend"><span>✓</span><div><b>Alternative plus sûre calculée</b><small>{(plan.distance_m / 1000).toFixed(1)} km · {Math.round(plan.duration_s / 60)} min · risque {Math.round((plan.risk || 0) * 100)}%</small></div></div><div className="route-legend"><i className="red"/> Trajet initial <i className="green"/> Alternative OSRM</div></> : <div className="route-recommend"><span>✓</span><div><b>Trajet vérifié</b><small>{(plan.distance_m / 1000).toFixed(1)} km · aucun détour plus sûr nécessaire</small></div></div>}<button className="secondary-route-btn" onClick={analyze}>Recalculer</button></div>}
    <Link className="floating-report" to="/citizen/report">＋ <span>Signaler</span></Link>
    <BottomNav kind="citizen"/>
  </div>;
}
