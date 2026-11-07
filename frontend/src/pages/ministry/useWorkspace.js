import { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import { apiErrorMessage } from '../../lib/labels';

// Data and actions of a ministry workspace. Same requests as before the redesign: one Promise.all on load and
// after every action (no per-screen refetch), same payloads. Screens only read `w` and call its actions.
export const STAFF_ROLES = { equipment: ['inspection_vehicle', 'equipment_supervisor'], transport: ['bus_driver', 'transport_supervisor'] };
export const SUPERVISOR_ROLES = ['transport_supervisor', 'equipment_supervisor'];
// Username of the signed-in account (JWT `sub`); display only, never trusted by the API.
export const sessionUsername = session => {
  try { return JSON.parse(atob(session.access_token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).sub || ''; }
  catch { return ''; }
};

export function useWorkspace(ministry) {
  const isEquipment = ministry === 'equipment';
  const [dashboard, setDashboard] = useState({});
  const [complaints, setComplaints] = useState([]);
  const [events, setEvents] = useState([]);
  const [inspections, setInspections] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [segments, setSegments] = useState([]);
  const [forecasts, setForecasts] = useState([]);
  const [model, setModel] = useState(null);
  const [staff, setStaff] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function load() {
    setLoading(true); setError('');
    try {
      if (isEquipment) {
        const [summary, reports, detections, sessions, map, modelInfo, staffRows] = await Promise.all([api.equipmentDashboard(), api.complaints(), api.roadEvents(), api.inspections(), api.map(), api.riskModel().catch(() => null), api.staffList()]);
        setDashboard(summary); setComplaints(reports); setEvents(detections); setInspections(sessions); setSegments(map.segments || []); setModel(modelInfo); setStaff(staffRows);
      } else {
        const [summary, routeRows, vehicleRows, assignmentRows, map, govRows, modelInfo, staffRows] = await Promise.all([api.transportDashboard(), api.officialRoutes(), api.vehicles(), api.assignments(), api.map(), api.governorateForecasts().catch(() => []), api.riskModel().catch(() => null), api.staffList()]);
        setDashboard(summary); setRoutes(routeRows); setVehicles(vehicleRows); setAssignments(assignmentRows); setSegments(map.segments || []); setForecasts(govRows); setModel(modelInfo); setStaff(staffRows);
      }
      setLoaded(true);
    } catch (err) { setError(apiErrorMessage(err.message || 'Impossible de charger les données.')); }
    finally { setLoading(false); }
  }

  useEffect(() => { void load(); }, [ministry]); // eslint-disable-line react-hooks/exhaustive-deps

  // Runs an action, then reloads the workspace (as before). Returns true on success.
  async function run(key, action, success) {
    setSaving(key); setError(''); setNotice('');
    try { await action(); setNotice(typeof success === 'function' ? success() : success); await load(); return true; }
    catch (err) { setError(apiErrorMessage(err.message)); return false; }
    finally { setSaving(''); }
  }

  const actions = {
    updateComplaint: (complaint, draft) => run(complaint.id, () => api.updateComplaint(complaint.id, draft), 'Statut enregistré.'),
    validateEvent: eventId => run(eventId, () => api.validateEvent(eventId), 'Détection validée.'),
    assignBus: body => run('assignment', () => api.assignRoute(body), 'Affectation enregistrée.'),
    createVehicle: body => run('vehicle', () => api.createVehicle(body), 'Véhicule enregistré.'),
    // Line = OSRM polyline between two points, then saved as an official route (same two calls as before)
    createRoute: draft => run('route', async () => {
      const route = await api.planRoute({
        vehicle_id: 'transport-planning',
        current_lat: Number(draft.start_lat), current_lon: Number(draft.start_lon),
        destination_lat: Number(draft.end_lat), destination_lon: Number(draft.end_lon), alternatives: 0,
      });
      await api.createOfficialRoute({ route_code: draft.route_code, name: draft.name, owner_org: 'SRTB', active: true, coordinates: route.polyline });
    }, 'Ligne créée à partir du graphe OSRM.'),
    createStaff: draft => { let created; return run('staff', async () => { created = await api.createStaff(draft); }, () => `Compte ${created.username} créé.`); },
    toggleStaffActive: account => run(account.username, () => api.setStaffActive(account.username, !account.active), `Compte ${account.username} ${account.active ? 'désactivé' : 'réactivé'}.`),
    // No reload after a password reset (as before)
    async resetStaffPassword(account, password) {
      if (password.length < 8) { setError('Le mot de passe doit contenir au moins 8 caractères.'); return false; }
      setSaving(account.username); setError(''); setNotice('');
      try { await api.resetStaffPassword(account.username, password); setNotice(`Mot de passe de ${account.username} réinitialisé.`); return true; }
      catch (err) { setError(apiErrorMessage(err.message)); return false; }
      finally { setSaving(''); }
    },
  };

  return { ministry, isEquipment, dashboard, complaints, events, inspections, routes, vehicles, assignments, segments, forecasts, model, staff,
    loaded, loading, saving, error, notice, setError, setNotice, reload: load, ...actions };
}
