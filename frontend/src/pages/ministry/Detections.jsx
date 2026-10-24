import React, { useEffect, useMemo, useState } from 'react';
import { Check, ExternalLink } from 'lucide-react';
import { PointMap } from '../../components/LeafletMap';
import { api } from '../../lib/api';
import { coords, dateTime, pct, plural } from '../../lib/format';
import { defectTitle, sourceLabel } from '../../lib/labels';
import { Button, Card, DataTable, DefinitionList, DemoBadge, DemoBanner, EmptyState, EventStateBadge, Field, SidePanel, SkeletonRows, Toolbar } from '../../ui';
import { ImageBoxes } from '../../ui/ImageBoxes';
import { useUrlFilter } from './filters';

const DAY_MS = 24 * 3600 * 1000;
const STATES = [['a-valider', 'À valider', e => !e.validated], ['validees', 'Validées', e => e.validated], ['toutes', 'Toutes', () => true]];

function DetectionPanel({ event, boxes, w, onClose }) {
  return <SidePanel title={defectTitle(event.defect_type)} subtitle={`Observée le ${dateTime(event.timestamp)}`} onClose={onClose}
    footer={!event.validated ? <Button variant="primary" icon={Check} loading={w.saving === event.id} onClick={() => w.validateEvent(event.id)}>Valider la détection</Button>
      : <span className="t-sm t-muted">Détection validée : elle est prise en compte par la prédiction M2.</span>}>
    {event.demo && <DemoBanner/>}
    <div className="panel-section"><h3>Image analysée</h3>
      <ImageBoxes src={event.media_uri} alt={`Image de la détection : ${defectTitle(event.defect_type)}`} boxes={boxes}/>
      {event.media_uri && <a className="t-sm row" style={{ gap: 4 }} href={event.media_uri} target="_blank" rel="noreferrer">Ouvrir le média<ExternalLink size={14} aria-hidden="true"/></a>}
    </div>
    <div className="panel-section"><h3>Détection</h3>
      <DefinitionList items={[['Classe', defectTitle(event.defect_type)], ['Confiance du modèle', pct(event.confidence)], ['Sévérité estimée', pct(event.severity)],
        ['Source', sourceLabel(event.source)], ['État', <EventStateBadge validated={event.validated}/>], ['Coordonnées', <span className="t-num">{coords(event.latitude, event.longitude)}</span>]]}/>
    </div>
    <div className="panel-section"><h3>Position</h3><PointMap lat={Number(event.latitude)} lon={Number(event.longitude)} kind="event" label={`Position de la détection : ${coords(event.latitude, event.longitude)}`}/></div>
  </SidePanel>;
}

export default function Detections({ w }) {
  const [state, setState] = useUrlFilter('etat', 'a-valider'); // same default as before: detections to validate
  const [period, setPeriod] = useUrlFilter('periode', 'toutes');
  const [klass, setKlass] = useUrlFilter('classe', 'toutes');
  const [openId, setOpenId] = useUrlFilter('detection', '');
  const [observations, setObservations] = useState([]);
  useEffect(() => { api.observations(500).then(setObservations).catch(() => setObservations([])); }, [w.events.length]);

  const boxesFor = event => observations.filter(o => o.event_id === event.id && Array.isArray(o.bbox_xyxy) && o.bbox_xyxy.length === 4)
    .map(o => ({ bbox: o.bbox_xyxy, label: `${defectTitle(o.defect_type)} ${pct(o.confidence)}` }));
  const classes = [...new Set(w.events.map(e => e.defect_type))].sort();
  const stateFilter = (STATES.find(s => s[0] === state) || STATES[0])[2];
  const rows = useMemo(() => w.events.filter(e => stateFilter(e) && (klass === 'toutes' || e.defect_type === klass)
    && (period !== '24h' || Date.now() - new Date(e.timestamp).getTime() <= DAY_MS)), [w.events, state, klass, period]); // eslint-disable-line react-hooks/exhaustive-deps
  const pending = w.events.filter(e => !e.validated).length;
  const open = w.events.find(e => e.id === openId);

  const columns = [
    { key: 'timestamp', label: 'Observée le', render: e => <span className="t-num">{dateTime(e.timestamp)}</span>, sort: e => e.timestamp, width: 170 },
    { key: 'defect_type', label: 'Classe', render: e => <><span className="cell-title">{defectTitle(e.defect_type)}</span><span className="cell-sub">{sourceLabel(e.source)}</span>{e.demo && <DemoBadge/>}</>, sort: e => defectTitle(e.defect_type) },
    { key: 'confidence', label: 'Confiance', num: true, render: e => pct(e.confidence), sort: e => Number(e.confidence) },
    { key: 'severity', label: 'Sévérité', num: true, render: e => pct(e.severity), sort: e => Number(e.severity) },
    { key: 'state', label: 'État', render: e => <EventStateBadge validated={e.validated}/>, sort: e => (e.validated ? 1 : 0) },
    { key: 'actions', label: '', sort: false, render: e => <div className="cell-actions">
      <Button size="sm" onClick={ev => { ev.stopPropagation(); setOpenId(e.id); }}>Voir</Button>
      {!e.validated && <Button size="sm" variant="primary" icon={Check} loading={w.saving === e.id} onClick={ev => { ev.stopPropagation(); w.validateEvent(e.id); }} aria-label={`Valider la détection ${defectTitle(e.defect_type)} du ${dateTime(e.timestamp)}`}>Valider</Button>}
    </div>, width: 190 },
  ];
  return <>
    <p className="t-muted">{plural(pending, 'détection à valider', 'détections à valider')} · détections du modèle M1 sur les photos citoyennes et les inspections.</p>
    <Card bodyClass={null}>
      <Toolbar count={w.loaded ? plural(rows.length, 'résultat') : 'Chargement…'}>
        <Field label="État"><select className="select" value={state} onChange={e => setState(e.target.value)}>{STATES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
        <Field label="Classe"><select className="select" value={klass} onChange={e => setKlass(e.target.value)}><option value="toutes">Toutes</option>{classes.map(c => <option key={c} value={c}>{defectTitle(c)}</option>)}</select></Field>
        <Field label="Période"><select className="select" value={period} onChange={e => setPeriod(e.target.value)}><option value="toutes">Toutes</option><option value="24h">Dernières 24 h</option></select></Field>
      </Toolbar>
      {!w.loaded && w.loading ? <SkeletonRows rows={5} cols={5}/>
        : <DataTable caption="Détections routières" rowKey={e => e.id} rows={rows} columns={columns} initialSort={{ key: 'timestamp', dir: 'desc' }}
          onRowClick={e => setOpenId(e.id)} selectedKey={openId} rowLabel={e => `Ouvrir la détection ${defectTitle(e.defect_type)}`}
          empty={<EmptyState title={state === 'a-valider' && period === 'toutes' && klass === 'toutes' ? 'Aucune détection à valider.' : 'Aucune détection ne correspond aux filtres.'}
            action={state !== 'toutes' || period !== 'toutes' || klass !== 'toutes' ? <Button onClick={() => { setState('toutes'); setPeriod('toutes'); setKlass('toutes'); }}>Afficher toutes les détections</Button> : null}/>}/>}
    </Card>
    {open && <DetectionPanel event={open} boxes={boxesFor(open)} w={w} onClose={() => setOpenId('')}/>}
  </>;
}
