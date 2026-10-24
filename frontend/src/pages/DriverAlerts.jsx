import React, { useEffect, useState } from 'react';
import BottomNav from '../components/BottomNav';
import { api } from '../lib/api';
import { hazardLabel } from '../lib/constants';
import { dateTime, distance, pct, plural, time } from '../lib/format';
import { alertTopicLabel, apiErrorMessage } from '../lib/labels';
import { AlertBadge, ConfirmedBadge, EmptyState, Loading, Notice } from '../ui';

function alertTitle(item) {
  if (item.topic === 'driver.reroute.alert') return 'Nouvel itinéraire recommandé';
  if (item.topic === 'driver.route.warning') return item.payload?.title || 'Danger sur l’itinéraire — aucune alternative sûre';
  return alertTopicLabel(item.topic);
}

export default function DriverAlerts() {
  const [alerts, setAlerts] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { api.alerts().then(setAlerts).catch(err => { setAlerts([]); setError(apiErrorMessage(err.message)); }); }, []);
  return <div className="m-shell">
    <a className="skip-link" href="#contenu">Aller au contenu</a>
    <header className="m-header"><span className="wordmark">THNIYETNA</span><span className="t-sm t-muted">Conducteur SRTB</span></header>
    <main id="contenu" className="m-content">
      <div><h1>Alertes</h1>{alerts && <p className="t-muted">{plural(alerts.length, 'notification')}</p>}</div>
      {error && <Notice tone="error" title="Alertes indisponibles">{error}</Notice>}
      {!alerts && <Loading label="Chargement des alertes…"/>}
      {alerts && !alerts.length && !error && <EmptyState title="Aucune alerte.">Les alertes de déviation et de danger sur votre ligne apparaissent ici.</EmptyState>}
      {alerts && alerts.length > 0 && <ol className="alert-feed">{alerts.map(item => {
        const p = item.payload || {};
        return <li key={item.id} className={`alert-entry${p.superseded ? ' is-superseded' : ''}`}>
          <div className="row-between"><div className="row"><AlertBadge topic={item.topic} superseded={p.superseded}/><ConfirmedBadge count={p.confirmations}/></div>
            <time className="t-sm t-muted t-num" dateTime={item.created_at} title={dateTime(item.created_at)}>{time(item.created_at)}</time></div>
          <h2>{alertTitle(item)}</h2>
          {p.superseded && <p className="t-sm t-muted">{p.superseded_note || 'Remplacée'}</p>}
          {p.confirmations > 1 && p.last_confirmed_at && <p className="t-sm t-muted">Dernière vérification à {time(p.last_confirmed_at)}</p>}
          <p>{p.reason || 'Mise à jour du réseau routier.'}</p>
          {item.topic === 'driver.route.warning' && p.hazards?.length > 0 && <ul className="alert-hazards-list">{p.hazards.map((h, i) =>
            <li key={i}>{hazardLabel(h.type)} · risque {pct(h.risk)} · à {distance(h.distance_m)} du trajet</li>)}</ul>}
          <p className="t-xs t-muted">{dateTime(item.created_at)}</p>
        </li>;
      })}</ol>}
    </main>
    <BottomNav kind="driver"/>
  </div>;
}
