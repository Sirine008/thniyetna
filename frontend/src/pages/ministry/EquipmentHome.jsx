import React from 'react';
import { Link } from 'react-router-dom';
import { dateTime, pct } from '../../lib/format';
import { defectTitle, reportCategoryLabel } from '../../lib/labels';
import { maintenanceQueue } from '../../lib/segments';
import { Card, DemoBadge, EmptyState, KpiTile, PriorityBadge, ReportStateBadge, SkeletonRows } from '../../ui';
import { riskCell } from './Priorities';

const link = (vue, extra = {}) => `/ministry/equipment?${new URLSearchParams({ vue, ...extra })}`;
const OPEN = c => !['resolved', 'rejected'].includes(c.status);
const latest = (rows, field, n = 5) => [...rows].sort((a, b) => String(b[field]).localeCompare(String(a[field]))).slice(0, n);

/** Short list with a link to the full list. */
function ShortList({ title, to, toLabel, items, render, empty }) {
  return <Card title={title} actions={<Link to={to} className="t-sm">{toLabel}</Link>} bodyClass={null}>
    {items.length ? <ul className="short-list">{items.map(render)}</ul> : <EmptyState title={empty}/>}
  </Card>;
}

export default function EquipmentHome({ w }) {
  const d = w.dashboard;
  const reports = latest(w.complaints.filter(OPEN), 'created_at');
  const detections = latest(w.events.filter(e => !e.validated), 'timestamp');
  const priorities = maintenanceQueue(w.segments).filter(s => ['P1', 'P2'].includes(s.maintenance_priority)).slice(0, 5);
  if (!w.loaded && w.loading) return <SkeletonRows rows={4} cols={4}/>;
  return <>
    <section aria-label="Compteurs" className="grid-kpi">
      <KpiTile label="Signalements ouverts" value={d.open_complaints} to={link('signalements', { statut: 'a-traiter' })}/>
      <KpiTile label="Détections à valider" value={d.unvalidated_events} to={link('detections')}/>
      <KpiTile label="Détections des dernières 24 h" value={d.events_24h} to={link('detections', { etat: 'toutes', periode: '24h' })}/>
      <KpiTile label="Inspections en cours" value={d.active_inspections} to={link('inspections', { etat: 'active' })}/>
    </section>
    <div className="grid-2">
      <ShortList title="Derniers signalements à traiter" to={link('signalements', { statut: 'a-traiter' })} toLabel="Tous les signalements à traiter" items={reports} empty="Aucun signalement à traiter."
        render={c => <li key={c.id}><Link to={link('signalements', { statut: 'a-traiter', signalement: c.id })} className="short-link">
          <span className="short-main"><span className="cell-title clamp-2">{c.description}</span><span className="cell-sub">{reportCategoryLabel(c.category)} · {dateTime(c.created_at)}</span>{c.demo && <DemoBadge/>}</span>
          <ReportStateBadge status={c.status}/></Link></li>}/>
      <ShortList title="Dernières détections à valider" to={link('detections')} toLabel="Toutes les détections à valider" items={detections} empty="Aucune détection à valider."
        render={e => <li key={e.id}><Link to={link('detections', { detection: e.id })} className="short-link">
          <span className="short-main"><span className="cell-title">{defectTitle(e.defect_type)}</span><span className="cell-sub">Confiance {pct(e.confidence)} · {dateTime(e.timestamp)}</span>{e.demo && <DemoBadge/>}</span>
          <span className="t-sm">Valider</span></Link></li>}/>
    </div>
    <ShortList title="Segments prioritaires (P1 et P2)" to={link('priorites')} toLabel="Toutes les priorités d’entretien" items={priorities} empty="Aucun segment en priorité P1 ou P2."
      render={s => <li key={s.segment_code}><Link to={link('priorites', { segment: s.segment_code })} className="short-link">
        <span className="short-main"><span className="cell-title">{s.name || 'Segment sans nom'}</span><span className="cell-sub t-mono">{s.segment_code}</span></span>
        <span className="row"><PriorityBadge priority={s.maintenance_priority}/>{riskCell(s)}</span></Link></li>}/>
  </>;
}
