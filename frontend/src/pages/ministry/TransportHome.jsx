import React from 'react';
import { Link } from 'react-router-dom';
import { TriangleAlert } from 'lucide-react';
import { date, dateTime, pct } from '../../lib/format';
import { riskLevel } from '../../lib/risk';
import { dayForecasts, exposureTop, nextForecastDay, riskySegments } from '../../lib/segments';
import { Badge, Card, EmptyState, KpiTile, RiskBadge, SkeletonRows } from '../../ui';

const link = (vue, extra = {}) => `/ministry/transport?${new URLSearchParams({ vue, ...extra })}`;

export default function TransportHome({ w }) {
  const d = w.dashboard;
  if (!w.loaded && w.loading) return <SkeletonRows rows={4} cols={4}/>;
  const day = nextForecastDay(w.forecasts);
  const alerts = dayForecasts(w.forecasts).filter(f => f.alert);
  const risky = riskySegments(w.segments);
  const watched = (risky.length ? risky : exposureTop(w.segments)).slice(0, 5);
  const latest = [...w.assignments].sort((a, b) => String(b.valid_from).localeCompare(String(a.valid_from))).slice(0, 5);
  return <>
    <section aria-label="Compteurs" className="grid-kpi">
      <KpiTile label="Lignes actives" value={d.active_routes} to={link('lignes')}/>
      <KpiTile label="Bus actifs" value={d.active_buses} to={link('lignes')}/>
      <KpiTile label="Affectations actives" value={d.assignments} to={link('affectations')}/>
      <KpiTile label="Scores de risque élevé ou critique (24 h)" value={d.high_risk_updates} to={link('reseau')}/>
    </section>
    <div className="grid-2">
      <Card title={day ? `Gouvernorats en alerte le ${date(day)}` : 'Gouvernorats en alerte'} actions={<Link to={link('reseau')} className="t-sm">Prévision complète</Link>} bodyClass={null}>
        {alerts.length ? <ul className="short-list">{alerts.slice(0, 6).map(f => <li key={f.gov_code}><div className="short-link">
          <span className="short-main"><span className="cell-title">{f.governorate || f.gov_code}</span><span className="cell-sub">Probabilité d’accident {pct(f.p_accident)}</span></span>
          <Badge tone="red" icon={TriangleAlert}>Alerte</Badge></div></li>)}</ul>
          : <EmptyState title={w.forecasts.length ? 'Aucun gouvernorat en alerte.' : 'Aucune prévision disponible.'}/>}
      </Card>
      <Card title={risky.length ? 'Segments à risque' : 'Segments les plus exposés'} actions={<Link to={link('reseau')} className="t-sm">Réseau à risque</Link>} bodyClass={null}>
        {watched.length ? <ul className="short-list">{watched.map(s => <li key={s.segment_code}><Link to={link('reseau', { segment: s.segment_code })} className="short-link">
          <span className="short-main"><span className="cell-title">{s.name || 'Segment sans nom'}</span><span className="cell-sub t-mono">{s.segment_code}</span></span>
          <RiskBadge level={riskLevel(s)}/></Link></li>)}</ul> : <EmptyState title="Aucun segment sous surveillance."/>}
      </Card>
    </div>
    <Card title="Dernières affectations" actions={<Link to={link('affectations')} className="t-sm">Toutes les affectations</Link>} bodyClass={null}>
      {latest.length ? <ul className="short-list">{latest.map(a => <li key={a.assignment_id}><div className="short-link">
        <span className="short-main"><span className="cell-title">{a.route_name}</span><span className="cell-sub">{a.vehicle_code} · {a.driver_username || 'sans conducteur'}</span></span>
        <span className="t-sm t-muted t-num">{dateTime(a.valid_from)}</span></div></li>)}</ul> : <EmptyState title="Aucune affectation active."/>}
    </Card>
  </>;
}
