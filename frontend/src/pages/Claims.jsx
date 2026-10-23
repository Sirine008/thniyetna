import React, { useEffect, useState } from 'react';
import BottomNav from '../components/BottomNav';
import { DEMO_LABEL } from '../lib/constants';
import { api } from '../lib/api';

export default function Claims() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => { api.myClaims().then(setItems).catch(err => setError(err.message)); }, []);
  return <div className="mobile-app"><header className="topbar"><div><span className="eyebrow">Mes contributions</span><h2>Suivi des signalements</h2></div></header>{error && <div className="form-error">{error}</div>}<div className="timeline-list">{items.map(item => <div className="claim-card" key={item.id}><div className="claim-status">{item.status === 'resolved' ? '✓' : '◉'}</div><div>{item.demo && <span className="demo-badge">{DEMO_LABEL}</span>}<strong>{item.description}</strong><span>{new Date(item.created_at).toLocaleString('fr-TN')}</span><em>{({ open: 'Reçu', under_review: 'En cours d’analyse', validated: 'Validé', planned: 'Intervention planifiée', resolved: 'Résolu', rejected: 'Rejeté' }[item.status] || item.status)}</em></div></div>)}{!items.length && !error && <div className="empty">Aucun signalement pour le moment.</div>}</div><BottomNav kind="citizen"/></div>;
}
