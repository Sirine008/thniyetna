import React, { useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import { dateTime, plural } from '../../lib/format';
import { Button, Card, DataTable, EmptyState, Field, SkeletonRows } from '../../ui';

/** Assign a bus and a driver to a line (same POST /routing/assignments), then the active assignments. */
export default function Assignments({ w }) {
  const { routes, vehicles, staff, assignments } = w;
  const activeRoutes = routes.filter(r => r.active);
  const activeBuses = vehicles.filter(v => v.vehicle_type === 'bus' && v.active);
  const activeDrivers = staff.filter(a => a.role === 'bus_driver' && a.active);
  const [routeCode, setRouteCode] = useState('');
  const [vehicleCode, setVehicleCode] = useState('');
  const [driverUsername, setDriverUsername] = useState('');
  // Same pre-selection as before: first active line, bus and driver
  useEffect(() => {
    setRouteCode(current => current || routes.find(r => r.active)?.route_code || '');
    setVehicleCode(current => current || vehicles.find(v => v.vehicle_type === 'bus' && v.active)?.vehicle_code || '');
    setDriverUsername(current => current || staff.find(a => a.role === 'bus_driver' && a.active)?.username || '');
  }, [routes, vehicles, staff]);
  const submit = event => { event.preventDefault(); w.assignBus({ route_code: routeCode, vehicle_code: vehicleCode, driver_username: driverUsername }); };

  const columns = [
    { key: 'route', label: 'Ligne', render: a => <><span className="cell-title">{a.route_name}</span><span className="cell-sub t-mono">{a.route_code}</span></>, sort: a => a.route_code },
    { key: 'vehicle', label: 'Véhicule', render: a => <><span>{a.vehicle_label || a.vehicle_code}</span><span className="cell-sub t-mono">{a.vehicle_code}</span></>, sort: a => a.vehicle_code },
    { key: 'driver_username', label: 'Conducteur', render: a => a.driver_username || '—' },
    { key: 'valid_from', label: 'Depuis', render: a => <span className="t-num">{dateTime(a.valid_from)}</span>, sort: a => a.valid_from },
  ];
  if (!w.loaded && w.loading) return <SkeletonRows rows={5} cols={4}/>;
  return <>
    <Card title="Affecter un bus à une ligne">
      <form className="form-grid" onSubmit={submit}>
        <Field label="Ligne"><select className="select" required value={routeCode} onChange={e => setRouteCode(e.target.value)}><option value="">Choisir une ligne</option>{activeRoutes.map(r => <option key={r.route_code} value={r.route_code}>{r.route_code} · {r.name}</option>)}</select></Field>
        <Field label="Bus"><select className="select" required value={vehicleCode} onChange={e => setVehicleCode(e.target.value)}><option value="">Choisir un bus</option>{activeBuses.map(v => <option key={v.vehicle_code} value={v.vehicle_code}>{v.vehicle_code} · {v.label}</option>)}</select></Field>
        <Field label="Conducteur"><select className="select" required value={driverUsername} onChange={e => setDriverUsername(e.target.value)}><option value="">Choisir un conducteur</option>{activeDrivers.map(d => <option key={d.username} value={d.username}>{d.username} · {d.display_name}</option>)}</select></Field>
        <div><Button type="submit" variant="primary" icon={Check} loading={w.saving === 'assignment'}>Confirmer l’affectation</Button></div>
      </form>
    </Card>
    <Card title="Affectations actives" actions={<span className="t-sm t-muted">{plural(assignments.length, 'affectation')}</span>} bodyClass={null}>
      <DataTable caption="Affectations actives" rowKey={a => a.assignment_id} rows={assignments} columns={columns} initialSort={{ key: 'valid_from', dir: 'desc' }}
        empty={<EmptyState title="Aucune affectation active.">Affectez un bus et un conducteur à une ligne avec le formulaire ci-dessus.</EmptyState>}/>
    </Card>
  </>;
}
