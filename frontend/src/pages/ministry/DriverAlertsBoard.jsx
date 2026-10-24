import React, { useEffect, useMemo, useState } from 'react';
import { Check } from 'lucide-react';
import LivePill from '../../components/LivePill';
import { api, openRealtime } from '../../lib/api';
import { dateTime, pct, plural, time } from '../../lib/format';
import { apiErrorMessage } from '../../lib/labels';
import { AlertBadge, Badge, Card, ConfirmedBadge, DataTable, DefinitionList, DemoBadge, DemoBanner, EmptyState, Field, Notice, SidePanel, SkeletonRows, Toolbar } from '../../ui';
import { useUrlFilter } from './filters';

// Transport supervisor: the drivers' M3 alerts (GET /platform/driver-alerts, read-only), refreshed live when a
// driver alert is published on the realtime stream.
const LIVE_TOPICS = ['driver.reroute.alert', 'driver.route.warning'];
const STATES = [['actives', 'Actives', a => a.active], ['prises', 'Prises en compte', a => a.acknowledged], ['remplacees', 'Remplacées', a => a.superseded], ['toutes', 'Toutes', () => true]];
const stateBadge = a => (a.superseded ? null : a.acknowledged ? <Badge tone="neutral" icon={Check}>Prise en compte{a.delivered_at ? ` à ${time(a.delivered_at)}` : ''}</Badge> : <Badge tone="primary">Active</Badge>);

export default function DriverAlertsBoard() {
  const [alerts, setAlerts] = useState(null);
  const [error, setError] = useState('');
  const [live, setLive] = useState('reconnecting');
  const [kind, setKind] = useUrlFilter('type', 'tous');
  const [state, setState] = useUrlFilter('etat', 'toutes');
  const [line, setLine] = useUrlFilter('ligne', 'toutes');
  const [driver, setDriver] = useUrlFilter('conducteur', 'tous');
  const [openId, setOpenId] = useUrlFilter('alerte', '');

  const load = () => api.driverAlerts().then(rows => { setAlerts(rows); setError(''); }).catch(err => { setAlerts(a => a || []); setError(apiErrorMessage(err.message)); });
  useEffect(() => {
    load();
    return openRealtime(topic => { if (LIVE_TOPICS.includes(topic)) load(); }, setLive);
  }, []);

  const all = alerts || [];
  const lines = [...new Map(all.filter(a => a.route_code).map(a => [a.route_code, a.route_name])).entries()].sort();
  const drivers = [...new Set(all.map(a => a.driver).filter(Boolean))].sort();
  const stateFilter = (STATES.find(s => s[0] === state) || STATES[3])[2];
  const rows = useMemo(() => all.filter(a => stateFilter(a) && (kind === 'tous' || a.kind === kind)
    && (line === 'toutes' || a.route_code === line) && (driver === 'tous' || a.driver === driver)), [alerts, kind, state, line, driver]); // eslint-disable-line react-hooks/exhaustive-deps
  const active = all.filter(a => a.active).length;
  const open = all.find(a => a.id === openId);

  const columns = [
    { key: 'created_at', label: 'Reçue le', render: a => <span className="t-num">{dateTime(a.created_at)}</span>, sort: a => a.created_at, width: 160 },
    { key: 'kind', label: 'Type', render: a => <div className="row"><AlertBadge topic={a.topic} superseded={a.superseded}/>{a.demo && <DemoBadge/>}</div>, sort: a => `${a.superseded}${a.kind}` },
    { key: 'line', label: 'Ligne', render: a => (a.route_code ? <><span className="cell-title">{a.route_name}</span><span className="cell-sub t-mono">{a.route_code}</span></> : <span className="t-subtle">—</span>), sort: a => a.route_code || '' },
    { key: 'driver', label: 'Conducteur', render: a => <><span className="t-mono">{a.driver}</span><span className="cell-sub t-mono">{a.vehicle_code}</span></>, sort: a => a.driver },
    { key: 'risk', label: 'Risque', render: a => (a.kind === 'reroute' ? `${pct(a.risk)} → ${pct(a.alternative_risk)}` : pct(a.risk)), sort: a => Number(a.risk || 0) },
    { key: 'state', label: 'État', render: a => <div className="row">{stateBadge(a)}<ConfirmedBadge count={a.confirmations}/></div>, sort: a => (a.active ? 0 : a.acknowledged ? 1 : 2) },
  ];
  return <>
    <div className="row-between"><p className="t-muted">{alerts ? `${plural(active, 'alerte active', 'alertes actives')} sur ${plural(all.length, 'alerte')} · une seule alerte active par conducteur et par ligne.` : 'Chargement…'}</p><LivePill status={live}/></div>
    {error && <Notice tone="error" title="Alertes indisponibles">{error}</Notice>}
    <Card bodyClass={null}>
      <Toolbar count={alerts ? plural(rows.length, 'résultat') : 'Chargement…'}>
        <Field label="Type"><select className="select" value={kind} onChange={e => setKind(e.target.value)}><option value="tous">Tous</option><option value="reroute">Déviation</option><option value="warning">Danger sans alternative</option></select></Field>
        <Field label="État"><select className="select" value={state} onChange={e => setState(e.target.value)}>{STATES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
        <Field label="Ligne"><select className="select" value={line} onChange={e => setLine(e.target.value)}><option value="toutes">Toutes</option>{lines.map(([code, name]) => <option key={code} value={code}>{code} · {name}</option>)}</select></Field>
        <Field label="Conducteur"><select className="select" value={driver} onChange={e => setDriver(e.target.value)}><option value="tous">Tous</option>{drivers.map(d => <option key={d} value={d}>{d}</option>)}</select></Field>
      </Toolbar>
      {!alerts ? <SkeletonRows rows={5} cols={5}/>
        : <DataTable caption="Alertes des conducteurs" rowKey={a => a.id} rows={rows} columns={columns} initialSort={{ key: 'created_at', dir: 'desc' }}
          onRowClick={a => setOpenId(a.id)} selectedKey={openId} rowLabel={a => `Ouvrir l’alerte de ${a.driver}`}
          empty={<EmptyState title={all.length ? 'Aucune alerte ne correspond aux filtres.' : 'Aucune alerte conducteur.'}>{all.length ? null : 'Les alertes de déviation et de danger calculées pour les conducteurs apparaissent ici en direct.'}</EmptyState>}/>}
    </Card>
    {open && <SidePanel title={open.kind === 'reroute' ? 'Nouvel itinéraire recommandé' : 'Danger sur l’itinéraire — aucune alternative sûre'} subtitle={`Reçue le ${dateTime(open.created_at)}`} onClose={() => setOpenId('')}>
      {open.demo && <DemoBanner/>}
      <div className="row"><AlertBadge topic={open.topic} superseded={open.superseded}/>{stateBadge(open)}<ConfirmedBadge count={open.confirmations}/></div>
      <DefinitionList items={[['Ligne', open.route_code ? `${open.route_code} · ${open.route_name}` : '—'], ['Conducteur', open.driver], ['Véhicule', open.vehicle_code],
        ['Risque du trajet initial', pct(open.risk)], open.kind === 'reroute' && ['Risque de l’alternative', pct(open.alternative_risk)], ['Dangers sur le trajet initial', open.hazards_on_initial],
        open.confirmations > 1 && ['Dernière vérification', dateTime(open.last_confirmed_at)], open.acknowledged && ['Prise en compte', dateTime(open.delivered_at)],
        open.superseded && ['Remplacée', open.superseded_note || 'Oui']]}/>
      <div className="panel-section"><h3>Motif (calcul M3)</h3><p>{open.reason}</p></div>
    </SidePanel>}
  </>;
}
