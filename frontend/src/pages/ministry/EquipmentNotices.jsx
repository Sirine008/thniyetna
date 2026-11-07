import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import { dateTime } from '../../lib/format';
import { apiErrorMessage } from '../../lib/labels';
import { Card, DemoBadge, EmptyState, Notice } from '../../ui';

// « Alertes de l'Équipement » (Transport home): messages sent by the equipment supervisor through the agent
// (notify_transport, confirmed by a human) = GET /platform/alerts, topic equipment.segment.notice. Read-only.
export const NOTICE_TOPIC = 'equipment.segment.notice';
export const equipmentNotices = alerts => (alerts || []).filter(a => a.topic === NOTICE_TOPIC);

export default function EquipmentNotices({ limit = 8 }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    api.alerts().then(all => setRows(equipmentNotices(all))).catch(err => { setRows([]); setError(apiErrorMessage(err.message)); });
  }, []);
  return <Card title="Alertes de l’Équipement" actions={<span className="t-sm t-muted">Messages du superviseur Équipement</span>} bodyClass={null}>
    {error && <div className="card-body"><Notice tone="error" title="Alertes indisponibles.">{error}</Notice></div>}
    {rows === null ? <p className="card-body t-sm t-muted">Chargement…</p>
      : rows.length ? <ul className="short-list">{rows.slice(0, limit).map(a => <li key={a.id}><div className="short-link">
        <span className="short-main">
          <span className="cell-title">{a.payload?.message}</span>
          <span className="cell-sub">{a.payload?.segment_name || 'Segment sans nom'} · <span className="t-mono">{a.payload?.segment_code}</span> · par {a.payload?.sent_by || '—'}</span>
        </span>
        <span className="row" style={{ gap: 6 }}>{a.payload?.demo && <DemoBadge/>}<span className="t-sm t-muted t-num">{dateTime(a.created_at)}</span></span>
      </div></li>)}</ul>
      : <EmptyState title="Aucun message de l’Équipement."/>}
  </Card>;
}
