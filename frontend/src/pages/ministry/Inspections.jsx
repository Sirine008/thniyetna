import React from 'react';
import { ExternalLink } from 'lucide-react';
import { coords, dateTime, plural } from '../../lib/format';
import { INSPECTION_STATES, inspectionStateLabel } from '../../lib/labels';
import { Badge, Card, DataTable, EmptyState, Field, SkeletonRows, Toolbar } from '../../ui';
import { useUrlFilter } from './filters';

const stateBadge = status => (status === 'active' ? <Badge tone="primary">{inspectionStateLabel(status)}</Badge> : <Badge>{inspectionStateLabel(status)}</Badge>);

export default function Inspections({ w }) {
  const [state, setState] = useUrlFilter('etat', 'toutes');
  const rows = w.inspections.filter(r => state === 'toutes' || r.status === state);
  const columns = [
    { key: 'vehicle', label: 'Véhicule', render: r => <><span className="cell-title">{r.vehicle_label || r.vehicle_code || '—'}</span>{r.vehicle_label && <span className="cell-sub t-mono">{r.vehicle_code}</span>}</>, sort: r => r.vehicle_label || r.vehicle_code },
    { key: 'started_at', label: 'Début', render: r => <span className="t-num">{dateTime(r.started_at)}</span>, sort: r => r.started_at },
    { key: 'ended_at', label: 'Fin', render: r => <span className="t-num">{dateTime(r.ended_at)}</span>, sort: r => r.ended_at },
    { key: 'status', label: 'État', render: r => stateBadge(r.status), sort: r => r.status },
    { key: 'position', label: 'Dernière position', render: r => <span className="t-num">{r.latitude == null ? '—' : coords(r.latitude, r.longitude)}</span>, sort: false },
    { key: 'video', label: 'Vidéo', sort: false, render: r => (r.video_uri ? <a className="row" style={{ gap: 4 }} href={r.video_uri} target="_blank" rel="noreferrer">Ouvrir<ExternalLink size={14} aria-hidden="true"/></a> : '—') },
  ];
  return <>
    <p className="t-muted">{plural(w.inspections.length, 'session', 'sessions')} d’inspection enregistrées · les véhicules envoient leurs sessions via l’API.</p>
    <Card bodyClass={null}>
      <Toolbar count={w.loaded ? plural(rows.length, 'résultat') : 'Chargement…'}>
        <Field label="État"><select className="select" value={state} onChange={e => setState(e.target.value)}><option value="toutes">Toutes</option>{Object.keys(INSPECTION_STATES).map(s => <option key={s} value={s}>{inspectionStateLabel(s)}</option>)}</select></Field>
      </Toolbar>
      {!w.loaded && w.loading ? <SkeletonRows rows={4} cols={5}/>
        : <DataTable caption="Sessions d’inspection" rowKey={r => r.id} rows={rows} columns={columns} initialSort={{ key: 'started_at', dir: 'desc' }}
          empty={<EmptyState title={w.inspections.length ? 'Aucune session ne correspond au filtre.' : 'Aucune session d’inspection.'}>{w.inspections.length ? null : 'Les sessions démarrées par un véhicule d’inspection apparaissent ici.'}</EmptyState>}/>}
    </Card>
  </>;
}
