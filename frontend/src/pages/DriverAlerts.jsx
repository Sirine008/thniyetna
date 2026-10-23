import React, { useEffect, useState } from 'react';
import BottomNav from '../components/BottomNav';
import { api } from '../lib/api';
import { hazardLabel } from '../lib/constants';

function alertTitle(item) {
  if (item.topic === 'driver.reroute.alert') return 'Nouvel itinéraire recommandé';
  if (item.topic === 'driver.route.warning') return item.payload?.title || 'Danger sur l’itinéraire — aucune alternative sûre';
  return 'Information réseau';
}

export default function DriverAlerts() {
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => { api.alerts().then(setAlerts).catch(err => setError(err.message)); }, []);
  return <div className="mobile-app"><header className="topbar"><div><span className="eyebrow">SRTB · Bizerte</span><h2>Centre d’alertes</h2></div></header>{error && <div className="form-error">{error}</div>}<div className="alert-list">{alerts.map(item => <div className="alert-card" key={item.id}><div className="alert-symbol">!</div><div><b>{alertTitle(item)}</b>{item.payload?.superseded && <small className="alert-superseded">{item.payload.superseded_note || 'Remplacée'}</small>}{item.payload?.confirmations > 1 && <small className="alert-superseded">Confirmée {item.payload.confirmations}× · dernière vérification {new Date(item.payload.last_confirmed_at).toLocaleTimeString('fr-TN', { hour: '2-digit', minute: '2-digit' })}</small>}<p>{item.payload?.reason || 'Mise à jour du réseau routier.'}</p>{item.topic === 'driver.route.warning' && item.payload?.hazards?.length > 0 && <ul className="alert-hazards">{item.payload.hazards.map((h, i) => <li key={i}>{hazardLabel(h.type)} · risque {Math.round(h.risk * 100)}% · à {Math.round(h.distance_m)} m du trajet</li>)}</ul>}<span>{new Date(item.created_at).toLocaleTimeString('fr-TN', { hour: '2-digit', minute: '2-digit' })}</span></div></div>)}{!alerts.length && !error && <div className="empty">Aucune alerte.</div>}</div><BottomNav kind="driver"/></div>;
}
