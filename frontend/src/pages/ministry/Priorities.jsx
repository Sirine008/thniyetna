import React, { useMemo } from 'react';
import { FileText } from 'lucide-react';
import { SegmentMap } from '../../components/LeafletMap';
import { plural, score } from '../../lib/format';
import { PRIORITIES, conditionLabel, priorityLabel, roadClassLabel } from '../../lib/labels';
import { mainFactor, priorityRank, riskLevel } from '../../lib/risk';
import { centile, exposureFallback, maintenanceQueue, modelLine, watchOnly } from '../../lib/segments';
import { Button, Card, DataTable, EmptyState, Field, PriorityBadge, RiskBadge, SkeletonRows, Toolbar } from '../../ui';
import { matches, useUrlFilter } from './filters';

export const riskCell = s => <span className="row" style={{ gap: 6 }}><RiskBadge level={riskLevel(s)}/><span className="t-num t-sm">{score(s.risk_score)}</span></span>;
export const segmentCell = s => <><span className="cell-title">{s.name || 'Segment sans nom'}</span><span className="cell-sub t-mono">{s.segment_code}</span></>;

export default function Priorities({ w, onSheet }) {
  const [priority, setPriority] = useUrlFilter('priorite', 'toutes');
  const [klass, setKlass] = useUrlFilter('classe', 'toutes');
  const [query, setQuery] = useUrlFilter('q', '');
  const [selected, setSelected] = useUrlFilter('segment', '');
  const queue = maintenanceQueue(w.segments);
  const exposure = exposureFallback(w.segments);
  const watchCount = w.segments.filter(watchOnly).length;
  const classes = [...new Set(queue.map(s => s.road_class).filter(Boolean))].sort((a, b) => roadClassLabel(a).localeCompare(roadClassLabel(b), 'fr'));
  const rows = useMemo(() => queue.filter(s => (priority === 'toutes' || s.maintenance_priority === priority) && (klass === 'toutes' || s.road_class === klass)
    && matches(query, s.name, s.segment_code)), [w.segments, priority, klass, query]); // eslint-disable-line react-hooks/exhaustive-deps
  const sheetButton = s => <Button size="sm" icon={FileText} onClick={e => { e.stopPropagation(); onSheet(s); }} aria-label={`Fiche d’intervention : ${s.name || s.segment_code}`}>Fiche d’intervention</Button>;

  const columns = [
    { key: 'priority', label: 'Priorité', render: s => <PriorityBadge priority={s.maintenance_priority}/>, sort: s => priorityRank(s.maintenance_priority), width: 150 },
    { key: 'segment', label: 'Segment', render: segmentCell, sort: s => s.name || s.segment_code },
    { key: 'road_class', label: 'Classe', render: s => roadClassLabel(s.road_class), sort: s => roadClassLabel(s.road_class) },
    { key: 'condition', label: 'État prédit', render: s => conditionLabel(s.predicted_condition), sort: s => conditionLabel(s.predicted_condition) },
    { key: 'risk', label: 'Risque M2', render: riskCell, sort: s => Number(s.risk_score || 0) },
    { key: 'factor', label: 'Facteur principal', render: s => <span className="t-sm">{mainFactor(s)}</span>, sort: false },
    { key: 'actions', label: '', sort: false, render: s => <div className="cell-actions">{sheetButton(s)}</div> },
  ];
  const exposureColumns = [
    { key: 'segment', label: 'Segment', render: segmentCell, sort: s => s.name || s.segment_code },
    { key: 'road_class', label: 'Classe', render: s => roadClassLabel(s.road_class) },
    { key: 'risk', label: 'Risque M2', render: riskCell, sort: s => Number(s.risk_score || 0) },
    { key: 'centile', label: 'Exposition', render: s => centile(s.exposure_percentile), sort: s => Number(s.exposure_percentile) },
    { key: 'priority', label: 'Priorité', render: s => (s.maintenance_priority ? priorityLabel(s.maintenance_priority) : '—'), sort: s => priorityRank(s.maintenance_priority) },
    { key: 'actions', label: '', sort: false, render: s => <div className="cell-actions">{sheetButton(s)}</div> },
  ];
  const onMap = rows.length ? rows : exposure;
  return <>
    <p className="t-muted">{plural(queue.length, 'segment à traiter', 'segments à traiter')}{watchCount ? ` · ${plural(watchCount, 'segment en surveillance', 'segments en surveillance')} (P3 sans défaut observé, non listés)` : ''} · {modelLine(w.model)}</p>
    <SegmentMap segments={onMap} selectedCode={selected} onSelect={s => setSelected(s.segment_code)} label="Carte des segments à entretenir" height={340}/>
    <Card bodyClass={null}>
        <Toolbar count={w.loaded ? plural(rows.length, 'résultat') : 'Chargement…'}>
          <Field label="Rechercher" className="field-grow"><input className="input" type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Nom ou code du segment"/></Field>
          <Field label="Priorité"><select className="select" value={priority} onChange={e => setPriority(e.target.value)}><option value="toutes">P1 à P3</option>{PRIORITIES.slice(0, 3).map(p => <option key={p} value={p}>{priorityLabel(p)}</option>)}</select></Field>
          <Field label="Classe"><select className="select" value={klass} onChange={e => setKlass(e.target.value)}><option value="toutes">Toutes</option>{classes.map(c => <option key={c} value={c}>{roadClassLabel(c)}</option>)}</select></Field>
        </Toolbar>
        {!w.loaded && w.loading ? <SkeletonRows rows={6} cols={5}/>
          : <DataTable caption="Segments à entretenir" rowKey={s => s.segment_code} rows={rows} columns={columns} pageSize={15}
            onRowClick={s => setSelected(s.segment_code)} selectedKey={selected} rowLabel={s => `Afficher sur la carte : ${s.name || s.segment_code}`}
            empty={<EmptyState title={queue.length ? 'Aucun segment ne correspond aux filtres.' : 'Aucun segment à traiter.'}>{queue.length ? null : 'Les priorités apparaissent après un passage du worker M2 (jobs.score).'}</EmptyState>}/>}
    </Card>
    {exposure.length > 0 && <Card title="À surveiller : exposition relative (top 5 %)" actions={<span className="t-sm t-muted">Risque absolu faible partout ; classement par exposition dans le gouvernorat</span>} bodyClass={null}>
      <DataTable caption="Segments les plus exposés" rowKey={s => s.segment_code} rows={exposure} columns={exposureColumns} pageSize={10} initialSort={{ key: 'centile', dir: 'desc' }}
        onRowClick={s => setSelected(s.segment_code)} selectedKey={selected}/>
    </Card>}
  </>;
}
