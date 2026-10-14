import React, { useEffect, useState } from 'react';
import BottomNav from '../components/BottomNav';
import { api } from '../lib/api';

export default function DriverAlerts() {
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => { api.alerts().then(setAlerts).catch(err => setError(err.message)); }, []);
  return <div className="mobile-app"><header className="topbar"><div><span className="eyebrow">SRTB · Bizerte</span><h2>Centre d’alertes</h2></div></header>{error && <div className="form-error">{error}</div>}<div className="alert-list">{alerts.map(item => <div className="alert-card" key={item.id}><div className="alert-symbol">!</div><div><b>{item.topic === 'driver.reroute.alert' ? 'Nouvel itinéraire recommandé' : 'Information réseau'}</b><p>{item.payload?.reason || 'Mise à jour du réseau routier.'}</p><span>{new Date(item.created_at).toLocaleTimeString('fr-TN', { hour: '2-digit', minute: '2-digit' })}</span></div></div>)}{!alerts.length && !error && <div className="empty">Aucune alerte.</div>}</div><BottomNav kind="driver"/></div>;
}
