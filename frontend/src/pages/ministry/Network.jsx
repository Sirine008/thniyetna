import React from 'react';
import { TriangleAlert } from 'lucide-react';
import { SegmentMap } from '../../components/LeafletMap';
import { date, number, pct, plural } from '../../lib/format';
import { mainFactor, priorityRank, riskLevel, levelRank } from '../../lib/risk';
import { centile, dayForecasts, exposureTop, modelLine, nextForecastDay, riskySegments } from '../../lib/segments';
import { Badge, Card, DataTable, EmptyState, Notice, PriorityBadge, RiskBadge, SkeletonRows } from '../../ui';
import { useUrlFilter } from './filters';
import { segmentCell } from './Priorities';

export default function Network({ w }) {
  const [selected, setSelected] = useUrlFilter('segment', '');
  const day = nextForecastDay(w.forecasts);
  const forecasts = dayForecasts(w.forecasts);
  const risky = riskySegments(w.segments);
  const fallback = risky.length ? [] : exposureTop(w.segments);
  const shown = risky.length ? risky : fallback;
  if (!w.loaded && w.loading) return <SkeletonRows rows={6} cols={5}/>;

  const forecastColumns = [
    { key: 'governorate', label: 'Gouvernorat', render: f => f.governorate || f.gov_code, sort: f => f.governorate || f.gov_code },
    { key: 'p_accident', label: 'Probabilité d’accident', num: true, render: f => pct(f.p_accident), sort: f => Number(f.p_accident) },
    { key: 'expected', label: 'Accidents attendus', num: true, render: f => number(f.expected_accidents, 2), sort: f => Number(f.expected_accidents) },
    { key: 'p_fatal', label: 'Probabilité d’accident mortel', num: true, render: f => pct(f.p_fatal_accident), sort: f => Number(f.p_fatal_accident) },
    { key: 'alert', label: 'Alerte', render: f => (f.alert ? <Badge tone="red" icon={TriangleAlert}>Alerte</Badge> : <span className="t-subtle">—</span>), sort: f => Number(f.alert) },
    { key: 'staleness', label: 'Fraîcheur des données', render: f => (f.history_staleness_days ? `Historique en retard de ${plural(f.history_staleness_days, 'jour')}` : 'À jour'), sort: f => Number(f.history_staleness_days || 0) },
  ];
  const segmentColumns = [
    { key: 'segment', label: 'Segment', render: segmentCell, sort: s => s.name || s.segment_code },
    { key: 'level', label: 'Niveau', render: s => <RiskBadge level={riskLevel(s)}/>, sort: s => levelRank(riskLevel(s)) },
    { key: 'score', label: 'Score', num: true, render: s => number(s.risk_score, 2), sort: s => Number(s.risk_score || 0) },
    ...(risky.length ? [] : [{ key: 'centile', label: 'Exposition', render: s => centile(s.exposure_percentile), sort: s => Number(s.exposure_percentile) }]),
    { key: 'priority', label: 'Entretien', render: s => <PriorityBadge priority={s.maintenance_priority}/>, sort: s => priorityRank(s.maintenance_priority) },
    { key: 'factor', label: 'Facteur principal', render: s => <span className="t-sm">{mainFactor(s)}</span>, sort: false },
  ];
  const alerts = forecasts.filter(f => f.alert).length;
  return <>
    <Card title={day ? `Prévision M2 du ${date(day)} : risque d’accident par gouvernorat` : 'Prévision M2 par gouvernorat'} actions={<span className="t-sm t-muted">{modelLine(w.model)}</span>} bodyClass={null}>
      {forecasts.length > 0 && <div className="card-body t-muted" style={{ paddingBlockEnd: 0 }}>{plural(alerts, 'gouvernorat en alerte', 'gouvernorats en alerte')} sur {forecasts.length}.</div>}
      <DataTable caption="Prévision par gouvernorat" rowKey={f => f.gov_code} rows={forecasts} columns={forecastColumns} pageSize={30}
        empty={<EmptyState title="Aucune prévision.">Lancez le worker M2 (jobs.score) pour remplir les prévisions par gouvernorat.</EmptyState>}/>
    </Card>
    <Card title="Segments sous surveillance" actions={<span className="t-sm t-muted">{plural(shown.length, 'segment')}</span>} bodyClass={null}>
      {!risky.length && fallback.length > 0 && <div className="card-body"><Notice tone="info" title="Aucun segment à risque moyen, élevé ou critique.">Les segments ci-dessous sont les plus exposés de leur gouvernorat (top 5 %, risque absolu faible) : un classement relatif, pas une probabilité.</Notice></div>}
      {shown.length > 0 && <div className="card-body" style={{ paddingBlockEnd: 0 }}><SegmentMap segments={shown} selectedCode={selected} onSelect={s => setSelected(s.segment_code)} label="Carte des segments sous surveillance" height={320}/></div>}
      <DataTable caption="Segments sous surveillance" rowKey={s => s.segment_code} rows={shown} columns={segmentColumns} pageSize={15}
        onRowClick={s => setSelected(s.segment_code)} selectedKey={selected} rowLabel={s => `Afficher sur la carte : ${s.name || s.segment_code}`}
        empty={<EmptyState title="Aucun segment à risque moyen, élevé ou critique."/>}/>
    </Card>
  </>;
}
