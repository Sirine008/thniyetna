import React, { useState } from 'react';
import { Bus, Plus, Route } from 'lucide-react';
import { plural } from '../../lib/format';
import { vehicleTypeLabel } from '../../lib/labels';
import { Badge, Button, Card, DataTable, EmptyState, Field, Modal, SkeletonRows } from '../../ui';

const EMPTY_VEHICLE = { vehicle_code: '', vehicle_type: 'bus', owner_org: 'SRTB', label: '' };
const EMPTY_ROUTE = { route_code: '', name: '', start_lat: '', start_lon: '', end_lat: '', end_lon: '' };
const activeBadge = (active, feminine) => (active ? <Badge tone="green">{feminine ? 'Active' : 'Actif'}</Badge> : <Badge>{feminine ? 'Inactive' : 'Inactif'}</Badge>);

/** Same two forms as before (POST /platform/vehicles; POST /routing/route then POST /routing/official-routes), in modals. */
function VehicleForm({ w, onDone }) {
  const [draft, setDraft] = useState(EMPTY_VEHICLE);
  const submit = async event => { event.preventDefault(); if (await w.createVehicle(draft)) { setDraft(EMPTY_VEHICLE); onDone(); } };
  return <Modal title="Ajouter un véhicule" onClose={onDone} footer={<><Button onClick={onDone}>Annuler</Button><Button type="submit" form="vehicle-form" variant="primary" loading={w.saving === 'vehicle'}>Enregistrer le véhicule</Button></>}>
    <form id="vehicle-form" className="stack" onSubmit={submit}>
      <Field label="Code" help="Ex. : SRTB-BUS-12. Un code existant met à jour le véhicule."><input className="input" required value={draft.vehicle_code} onChange={e => setDraft({ ...draft, vehicle_code: e.target.value })} data-autofocus/></Field>
      <Field label="Libellé"><input className="input" value={draft.label} onChange={e => setDraft({ ...draft, label: e.target.value })}/></Field>
      <Field label="Type"><select className="select" value={draft.vehicle_type} onChange={e => setDraft({ ...draft, vehicle_type: e.target.value })}><option value="bus">Bus</option><option value="inspection">Véhicule d’inspection</option></select></Field>
    </form>
  </Modal>;
}

function RouteForm({ w, onDone }) {
  const [draft, setDraft] = useState(EMPTY_ROUTE);
  const submit = async event => { event.preventDefault(); if (await w.createRoute(draft)) { setDraft(EMPTY_ROUTE); onDone(); } };
  const coord = (key, label) => <Field label={label}><input className="input" type="number" step="any" required inputMode="decimal" value={draft[key]} onChange={e => setDraft({ ...draft, [key]: e.target.value })}/></Field>;
  return <Modal wide title="Créer une ligne" onClose={onDone} footer={<><Button onClick={onDone}>Annuler</Button><Button type="submit" form="route-form" variant="primary" loading={w.saving === 'route'}>Calculer et enregistrer la ligne</Button></>}>
    <form id="route-form" className="stack" onSubmit={submit}>
      <p className="t-sm t-muted">Le tracé est calculé par OSRM entre le départ et l’arrivée, puis enregistré comme ligne officielle active (SRTB).</p>
      <div className="grid-2"><Field label="Code de la ligne"><input className="input" required value={draft.route_code} onChange={e => setDraft({ ...draft, route_code: e.target.value })} data-autofocus/></Field>
        <Field label="Nom"><input className="input" required value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })}/></Field></div>
      <fieldset className="fieldset"><legend>Départ (coordonnées décimales)</legend><div className="grid-2">{coord('start_lat', 'Latitude')}{coord('start_lon', 'Longitude')}</div></fieldset>
      <fieldset className="fieldset"><legend>Arrivée (coordonnées décimales)</legend><div className="grid-2">{coord('end_lat', 'Latitude')}{coord('end_lon', 'Longitude')}</div></fieldset>
    </form>
  </Modal>;
}

export default function Fleet({ w }) {
  const [form, setForm] = useState('');
  const routeColumns = [
    { key: 'route_code', label: 'Code', render: r => <span className="t-mono">{r.route_code}</span> },
    { key: 'name', label: 'Nom' },
    { key: 'owner_org', label: 'Organisation' },
    { key: 'active', label: 'État', render: r => activeBadge(r.active, true), sort: r => Number(r.active) },
  ];
  const vehicleColumns = [
    { key: 'vehicle_code', label: 'Code', render: v => <span className="t-mono">{v.vehicle_code}</span> },
    { key: 'label', label: 'Libellé', render: v => v.label || '—' },
    { key: 'vehicle_type', label: 'Type', render: v => vehicleTypeLabel(v.vehicle_type), sort: v => vehicleTypeLabel(v.vehicle_type) },
    { key: 'owner_org', label: 'Organisation' },
    { key: 'active', label: 'État', render: v => activeBadge(v.active), sort: v => Number(v.active) },
  ];
  if (!w.loaded && w.loading) return <SkeletonRows rows={6} cols={4}/>;
  return <>
    <p className="t-muted">{plural(w.routes.length, 'ligne')} · {plural(w.vehicles.length, 'véhicule')}.</p>
    <Card title="Lignes" actions={<Button variant="primary" icon={Route} onClick={() => setForm('route')}>Créer une ligne</Button>} bodyClass={null}>
      <DataTable caption="Lignes officielles" rowKey={r => r.route_code} rows={w.routes} columns={routeColumns} initialSort={{ key: 'route_code', dir: 'asc' }}
        empty={<EmptyState title="Aucune ligne." action={<Button icon={Plus} onClick={() => setForm('route')}>Créer une ligne</Button>}/>}/>
    </Card>
    <Card title="Véhicules" actions={<Button icon={Bus} onClick={() => setForm('vehicle')}>Ajouter un véhicule</Button>} bodyClass={null}>
      <DataTable caption="Véhicules" rowKey={v => v.vehicle_code} rows={w.vehicles} columns={vehicleColumns} initialSort={{ key: 'vehicle_code', dir: 'asc' }}
        empty={<EmptyState title="Aucun véhicule." action={<Button icon={Plus} onClick={() => setForm('vehicle')}>Ajouter un véhicule</Button>}/>}/>
    </Card>
    {form === 'vehicle' && <VehicleForm w={w} onDone={() => setForm('')}/>}
    {form === 'route' && <RouteForm w={w} onDone={() => setForm('')}/>}
  </>;
}
