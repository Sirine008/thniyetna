import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import { clearSession, getSession } from '../lib/auth';
import { CONDITION_LABELS, PRIORITY_LABELS, RISK_LABELS, levelRank, mainFactor, percent, priorityRank, riskLevel, roadClassLabel } from '../lib/risk';
import './supervisor.css';

const complaintStatuses = [
  ['under_review', 'En analyse'], ['validated', 'Validé'], ['planned', 'Intervention planifiée'],
  ['resolved', 'Résolu'], ['rejected', 'Rejeté'],
];
const statusLabels = { open: 'Nouveau', under_review: 'En analyse', validated: 'Validé', planned: 'Planifié', resolved: 'Résolu', rejected: 'Rejeté', active: 'En cours', completed: 'Terminé' };
const dateLabel = value => value ? new Date(value).toLocaleString('fr-TN', { dateStyle: 'medium', timeStyle: 'short' }) : '—';
// Rank of risk_score within the governorate (M2 exposure_percentile): a ranking aid, not a probability.
const EXPOSURE_TOP = 0.05;
const centile = value => value == null ? '—' : `${Math.round(Number(value) * 100)}e centile`;
const STAFF_ROLE_LABELS = { bus_driver: 'Conducteur de bus', transport_supervisor: 'Superviseur transport', inspection_vehicle: 'Véhicule d’inspection', equipment_supervisor: 'Superviseur équipement' };
// Same permission map as backend/auth/router.py (the API enforces it; this only shapes the form).
const STAFF_ROLES = { equipment: ['inspection_vehicle', 'equipment_supervisor'], transport: ['bus_driver', 'transport_supervisor'] };
const SUPERVISOR_ROLES = ['transport_supervisor', 'equipment_supervisor'];
const emptyStaffDraft = role => ({ username: '', display_name: '', role, password: '' });
// Username of the signed-in account (JWT `sub`); display only, never trusted by the API.
const sessionUsername = session => {
  try { return JSON.parse(atob(session.access_token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).sub || ''; }
  catch { return ''; }
};

export default function Ministry({ ministry }) {
  const isEquipment = ministry === 'equipment';
  const title = isEquipment ? 'Ministère de l’Équipement' : 'Ministère du Transport';
  const session = getSession();
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
  const [section, setSection] = useState(isEquipment ? 'reports' : 'network');
  const [drafts, setDrafts] = useState({});
  const [routeCode, setRouteCode] = useState('');
  const [vehicleCode, setVehicleCode] = useState('');
  const [driverUsername, setDriverUsername] = useState('');
  const [staff, setStaff] = useState([]);
  const [staffDraft, setStaffDraft] = useState(emptyStaffDraft(STAFF_ROLES[ministry][0]));
  const me = sessionUsername(session);
  const [vehicleDraft, setVehicleDraft] = useState({ vehicle_code: '', vehicle_type: 'bus', owner_org: 'SRTB', label: '' });
  const [routeDraft, setRouteDraft] = useState({ route_code: '', name: '', start_lat: '', start_lon: '', end_lat: '', end_lon: '' });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function loadWorkspace() {
    setLoading(true); setError('');
    try {
      if (isEquipment) {
        const [summary, reports, detections, sessions, map, modelInfo, staffRows] = await Promise.all([api.equipmentDashboard(), api.complaints(), api.roadEvents(), api.inspections(), api.map(), api.riskModel().catch(() => null), api.staffList()]);
        setDashboard(summary); setComplaints(reports); setEvents(detections); setInspections(sessions); setSegments(map.segments || []); setModel(modelInfo); setStaff(staffRows);
      } else {
        const [summary, routeRows, vehicleRows, assignmentRows, map, govRows, modelInfo, staffRows] = await Promise.all([api.transportDashboard(), api.officialRoutes(), api.vehicles(), api.assignments(), api.map(), api.governorateForecasts().catch(() => []), api.riskModel().catch(() => null), api.staffList()]);
        setDashboard(summary); setRoutes(routeRows); setVehicles(vehicleRows); setAssignments(assignmentRows); setSegments(map.segments || []); setForecasts(govRows); setModel(modelInfo); setStaff(staffRows);
        setRouteCode(current => current || routeRows.find(row => row.active)?.route_code || '');
        setVehicleCode(current => current || vehicleRows.find(row => row.vehicle_type === 'bus' && row.active)?.vehicle_code || '');
        setDriverUsername(current => current || staffRows.find(row => row.role === 'bus_driver' && row.active)?.username || '');
      }
    } catch (err) { setError(err.message || 'Impossible de charger les données.'); }
    finally { setLoading(false); }
  }

  useEffect(() => { void loadWorkspace(); }, [ministry]);

  async function updateComplaint(complaint) {
    const draft = drafts[complaint.id] || { status: 'under_review', note: '' };
    setSaving(complaint.id); setError(''); setNotice('');
    try { await api.updateComplaint(complaint.id, draft); setNotice('Statut enregistré.'); await loadWorkspace(); }
    catch (err) { setError(err.message); } finally { setSaving(''); }
  }

  async function validateEvent(eventId) {
    setSaving(eventId); setError(''); setNotice('');
    try { await api.validateEvent(eventId); setNotice('Détection validée.'); await loadWorkspace(); }
    catch (err) { setError(err.message); } finally { setSaving(''); }
  }

  async function assignBus(event) {
    event.preventDefault(); setSaving('assignment'); setError(''); setNotice('');
    try { await api.assignRoute({ route_code: routeCode, vehicle_code: vehicleCode, driver_username: driverUsername }); setNotice('Affectation enregistrée.'); await loadWorkspace(); }
    catch (err) { setError(err.message); } finally { setSaving(''); }
  }

  async function createVehicle(event) {
    event.preventDefault(); setSaving('vehicle'); setError(''); setNotice('');
    try { await api.createVehicle(vehicleDraft); setVehicleDraft({ vehicle_code: '', vehicle_type: 'bus', owner_org: 'SRTB', label: '' }); setNotice('Véhicule enregistré.'); await loadWorkspace(); }
    catch (err) { setError(err.message); } finally { setSaving(''); }
  }

  async function createRoute(event) {
    event.preventDefault(); setSaving('route'); setError(''); setNotice('');
    try {
      const route = await api.planRoute({
        vehicle_id: 'transport-planning',
        current_lat: Number(routeDraft.start_lat), current_lon: Number(routeDraft.start_lon),
        destination_lat: Number(routeDraft.end_lat), destination_lon: Number(routeDraft.end_lon), alternatives: 0,
      });
      await api.createOfficialRoute({ route_code: routeDraft.route_code, name: routeDraft.name, owner_org: 'SRTB', active: true, coordinates: route.polyline });
      setRouteDraft({ route_code: '', name: '', start_lat: '', start_lon: '', end_lat: '', end_lon: '' });
      setNotice('Ligne créée à partir du graphe OSRM.'); await loadWorkspace();
    } catch (err) { setError(err.message); } finally { setSaving(''); }
  }

  async function createStaff(event) {
    event.preventDefault(); setSaving('staff'); setError(''); setNotice('');
    try {
      const created = await api.createStaff(staffDraft);
      setStaffDraft(emptyStaffDraft(staffDraft.role));
      setNotice(`Compte ${created.username} créé.`); await loadWorkspace();
    } catch (err) { setError(err.message); } finally { setSaving(''); }
  }

  async function toggleStaffActive(account) {
    setSaving(account.username); setError(''); setNotice('');
    try { await api.setStaffActive(account.username, !account.active); setNotice(`Compte ${account.username} ${account.active ? 'désactivé' : 'réactivé'}.`); await loadWorkspace(); }
    catch (err) { setError(err.message); } finally { setSaving(''); }
  }

  async function resetStaffPassword(account) {
    const password = window.prompt(`Nouveau mot de passe pour ${account.username} (8 caractères minimum)`);
    if (password === null) return;
    if (password.length < 8) { setError('Le mot de passe doit contenir au moins 8 caractères.'); return; }
    setSaving(account.username); setError(''); setNotice('');
    try { await api.resetStaffPassword(account.username, password); setNotice(`Mot de passe de ${account.username} réinitialisé.`); }
    catch (err) { setError(err.message); } finally { setSaving(''); }
  }

  function signOut() { clearSession(); window.location.assign('/'); }

  const pendingEvents = events.filter(item => !item.validated);
  const activeBuses = vehicles.filter(vehicle => vehicle.vehicle_type === 'bus' && vehicle.active);
  const activeDrivers = staff.filter(account => account.role === 'bus_driver' && account.active);
  // M2 contract: 4 risk levels (critical included); legacy 3-level rows still display.
  const riskySegments = segments.filter(segment => levelRank(riskLevel(segment)) >= 1).sort((a, b) => Number(b.risk_score || 0) - Number(a.risk_score || 0));
  // All absolute risks low: show the most exposed segments of their governorate instead (relative ranking).
  const exposureTop = riskySegments.length ? [] : segments.filter(segment => segment.exposure_percentile != null && Number(segment.exposure_percentile) >= 1 - EXPOSURE_TOP)
    .sort((a, b) => Number(b.exposure_percentile) - Number(a.exposure_percentile) || Number(b.risk_score || 0) - Number(a.risk_score || 0));
  // Maintenance worklist: M2 priority first (P1 → P4), then risk score.
  // P3 driven only by accident exposure (no observed defect) is a watch item, not a work order.
  const watchOnly = segment => priorityRank(segment.maintenance_priority) === 3 && segment.predicted_condition === 'no_observed_defect';
  const watchCount = segments.filter(watchOnly).length;
  const maintenanceQueue = segments.filter(segment => priorityRank(segment.maintenance_priority) <= 3 && !watchOnly(segment))
    .sort((a, b) => priorityRank(a.maintenance_priority) - priorityRank(b.maintenance_priority) || Number(b.risk_score || 0) - Number(a.risk_score || 0));
  // Next forecast day per governorate, alerts first.
  const nextDay = forecasts.reduce((min, f) => (!min || f.forecast_date < min ? f.forecast_date : min), null);
  const dayForecasts = forecasts.filter(f => f.forecast_date === nextDay).sort((a, b) => Number(b.alert) - Number(a.alert) || b.p_accident - a.p_accident);
  const modelLine = model?.status === 'ok' ? `Modèle M2 ${model.version} · ${model.classifier}` : 'Modèle M2 non chargé · scores contextuels';
  const levelBadge = segment => { const level = riskLevel(segment); return level ? <span className={`status-label risk-${level}`}>{RISK_LABELS[level] || level}</span> : '—'; };

  return <main className="ministry-workspace">
    <header className="ministry-topbar"><Link to="/" className="ministry-brand"><span>ط</span><b>THNIYETNA</b></Link><div className="ministry-account"><span>{session?.display_name || session?.role}</span><button onClick={signOut}>Déconnexion</button></div></header>
    <div className="ministry-content">
      <div className="ministry-heading"><div><span className="ministry-kicker">BIZERTE · SUPERVISION OPÉRATIONNELLE</span><h1>{title}</h1><p>{isEquipment ? 'Traitement des signalements et contrôle des inspections routières.' : 'Gestion des lignes, du risque routier, de la flotte et des affectations.'}</p></div><button className="ministry-secondary" onClick={loadWorkspace} disabled={loading}>{loading ? 'Actualisation…' : '↻ Actualiser'}</button></div>
      {error && <p className="ministry-message is-error">{error}</p>}{notice && <p className="ministry-message is-success">{notice}</p>}
      <section className="ministry-metrics">{(isEquipment ? [['Signalements ouverts', dashboard.open_complaints], ['Détections à valider', dashboard.unvalidated_events], ['Événements · 24 h', dashboard.events_24h], ['Inspections actives', dashboard.active_inspections]] : [['Lignes actives', dashboard.active_routes], ['Bus actifs', dashboard.active_buses], ['Affectations', dashboard.assignments], ['Risque élevé · 24 h', dashboard.high_risk_updates]]).map(([label, value]) => <div className="ministry-metric" key={label}><span>{label}</span><strong>{value ?? '—'}</strong></div>)}</section>
      <nav className="ministry-tabs">{(isEquipment ? [['reports', 'Signalements'], ['events', 'Détections'], ['priorities', 'Priorités d’entretien'], ['inspections', 'Inspections'], ['accounts', 'Comptes']] : [['network', 'Réseau à risque'], ['assignments', 'Affectations'], ['fleet', 'Lignes & flotte'], ['accounts', 'Comptes']]).map(([key, label]) => <button key={key} className={section === key ? 'is-active' : ''} onClick={() => setSection(key)}>{label}</button>)}</nav>

      {isEquipment && section === 'reports' && <section className="ministry-panel"><div className="ministry-panel-heading"><div><span className="ministry-kicker">À TRAITER</span><h2>Signalements citoyens</h2></div><span>{complaints.length} dossiers</span></div>{complaints.length ? <div className="ministry-list">{complaints.map(complaint => { const draft = drafts[complaint.id] || { status: complaint.status === 'open' ? 'under_review' : complaint.status, note: '' }; return <article className="ministry-record" key={complaint.id}><div className="record-main"><span className={`status-dot status-${complaint.status}`}/><div><h3>{complaint.description}</h3><p>{complaint.category || 'Route'} · {dateLabel(complaint.created_at)} · {Number(complaint.latitude).toFixed(4)}, {Number(complaint.longitude).toFixed(4)}</p></div></div><span className={`status-label status-${complaint.status}`}>{statusLabels[complaint.status] || complaint.status}</span><div className="record-actions"><select value={draft.status} onChange={e => setDrafts(current => ({ ...current, [complaint.id]: { ...draft, status: e.target.value } }))}>{complaintStatuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><input placeholder="Note de traitement" value={draft.note} onChange={e => setDrafts(current => ({ ...current, [complaint.id]: { ...draft, note: e.target.value } }))}/><button className="ministry-primary" disabled={saving === complaint.id} onClick={() => updateComplaint(complaint)}>Enregistrer</button></div></article>; })}</div> : <p className="ministry-empty">Aucun signalement.</p>}</section>}

      {isEquipment && section === 'events' && <section className="ministry-panel"><div className="ministry-panel-heading"><div><span className="ministry-kicker">PERCEPTION M1</span><h2>Détections routières</h2></div><span>{pendingEvents.length} à valider</span></div>{pendingEvents.length ? <div className="ministry-list">{pendingEvents.map(item => <article className="ministry-record" key={item.id}><div className="record-main"><span className="event-symbol">!</span><div><h3>{item.defect_type.replaceAll('_', ' ')}</h3><p>Sévérité {Math.round(Number(item.severity || 0) * 100)}% · confiance {Math.round(Number(item.confidence || 0) * 100)}% · {item.source}</p><p>{dateLabel(item.timestamp)}</p></div></div>{item.media_uri && <a className="record-link" href={item.media_uri} target="_blank" rel="noreferrer">Voir média ↗</a>}<button className="ministry-primary" disabled={saving === item.id} onClick={() => validateEvent(item.id)}>Valider</button></article>)}</div> : <p className="ministry-empty">Aucune détection à valider.</p>}</section>}

      {isEquipment && section === 'priorities' && <section className="ministry-panel"><div className="ministry-panel-heading"><div><span className="ministry-kicker">PRÉDICTION M2</span><h2>Segments à entretenir</h2></div><span>{maintenanceQueue.length} à traiter{watchCount ? ` · ${watchCount} en surveillance (P3 sans défaut observé)` : ''} · {modelLine}</span></div>{maintenanceQueue.length ? <div className="ministry-table-wrap"><table><thead><tr><th>Priorité</th><th>Segment</th><th>Classe</th><th>État prédit</th><th>Risque</th><th>Facteur principal</th></tr></thead><tbody>{maintenanceQueue.map(segment => <tr key={segment.segment_code}><td><span className={`status-label priority-${segment.maintenance_priority}`}>{PRIORITY_LABELS[segment.maintenance_priority] || segment.maintenance_priority}</span></td><td>{segment.name || segment.segment_code}</td><td>{roadClassLabel(segment.road_class)}</td><td>{CONDITION_LABELS[segment.predicted_condition] || segment.predicted_condition || '—'}</td><td>{levelBadge(segment)} {percent(segment.risk_score)}</td><td>{mainFactor(segment)}</td></tr>)}</tbody></table></div> : <p className="ministry-empty">Aucun segment à traiter. Les priorités apparaissent après un passage du worker M2 (jobs.score).</p>}{exposureTop.length > 0 && <><div className="ministry-panel-heading assignments-heading"><div><span className="ministry-kicker">EXPOSITION RELATIVE (TOP 5 %) — RISQUE ABSOLU FAIBLE</span><h2>À surveiller (exposition)</h2></div><span>{exposureTop.length} segments</span></div><div className="ministry-table-wrap"><table><thead><tr><th>Segment</th><th>Classe</th><th>Risque</th><th>Centile</th><th>Priorité</th></tr></thead><tbody>{exposureTop.map(segment => <tr key={segment.segment_code}><td>{segment.name || segment.segment_code}</td><td>{roadClassLabel(segment.road_class)}</td><td>{levelBadge(segment)} {percent(segment.risk_score)}</td><td>{centile(segment.exposure_percentile)}</td><td>{PRIORITY_LABELS[segment.maintenance_priority] || segment.maintenance_priority || '—'}</td></tr>)}</tbody></table></div></>}</section>}

      {isEquipment && section === 'inspections' && <section className="ministry-panel"><div className="ministry-panel-heading"><div><span className="ministry-kicker">VÉHICULES D’INSPECTION</span><h2>Sessions récentes</h2></div><span>{inspections.length} sessions</span></div>{inspections.length ? <div className="ministry-table-wrap"><table><thead><tr><th>Véhicule</th><th>Début</th><th>État</th><th>Dernière position</th><th>Vidéo</th></tr></thead><tbody>{inspections.map(row => <tr key={row.id}><td>{row.vehicle_label || row.vehicle_code || '—'}</td><td>{dateLabel(row.started_at)}</td><td>{statusLabels[row.status] || row.status}</td><td>{row.latitude == null ? '—' : `${Number(row.latitude).toFixed(4)}, ${Number(row.longitude).toFixed(4)}`}</td><td>{row.video_uri ? <a className="record-link" href={row.video_uri} target="_blank" rel="noreferrer">Ouvrir ↗</a> : '—'}</td></tr>)}</tbody></table></div> : <p className="ministry-empty">Aucune inspection.</p>}</section>}

      {!isEquipment && section === 'network' && <>
        <section className="ministry-panel forecast-panel"><div className="ministry-panel-heading"><div><span className="ministry-kicker">PRÉVISION M2 · {nextDay ? new Date(`${nextDay}T00:00:00`).toLocaleDateString('fr-TN', { dateStyle: 'medium' }).toUpperCase() : 'AUCUNE'}</span><h2>Risque d’accident par gouvernorat</h2></div><span>{modelLine}</span></div>{dayForecasts.length ? <div className="ministry-table-wrap"><table><thead><tr><th>Gouvernorat</th><th>P(accident)</th><th>Accidents attendus</th><th>P(accident mortel)</th><th>Alerte</th><th>Fraîcheur des données</th></tr></thead><tbody>{dayForecasts.map(f => <tr key={f.gov_code}><td>{f.governorate || f.gov_code}</td><td>{percent(f.p_accident)}</td><td>{Number(f.expected_accidents).toFixed(2)}</td><td>{percent(f.p_fatal_accident)}</td><td>{f.alert ? <span className="status-label risk-high">Alerte</span> : '—'}</td><td>{f.history_staleness_days ? `historique en retard de ${f.history_staleness_days} j` : 'à jour'}</td></tr>)}</tbody></table></div> : <p className="ministry-empty">Aucune prévision. Lancez le worker M2 (jobs.score) pour remplir governorate_risk_forecasts.</p>}</section>
        <section className="ministry-panel"><div className="ministry-panel-heading"><div><span className="ministry-kicker">SÉCURITÉ DES ITINÉRAIRES</span><h2>Segments sous surveillance</h2></div><span>{riskySegments.length} segments</span></div>{riskySegments.length ? <div className="ministry-table-wrap"><table><thead><tr><th>Segment</th><th>Nom</th><th>Niveau</th><th>Score</th><th>Entretien</th><th>Facteur principal</th></tr></thead><tbody>{riskySegments.map(segment => <tr key={segment.segment_code}><td>{segment.segment_code}</td><td>{segment.name || '—'}</td><td>{levelBadge(segment)}</td><td>{percent(segment.risk_score)}</td><td>{segment.maintenance_priority || '—'}</td><td>{mainFactor(segment)}</td></tr>)}</tbody></table></div> : exposureTop.length ? <><p className="ministry-empty">Aucun segment à risque moyen, élevé ou critique. Exposition relative (top 5 %) — risque absolu faible :</p><div className="ministry-table-wrap"><table><thead><tr><th>Segment</th><th>Nom</th><th>Niveau</th><th>Score</th><th>Centile</th><th>Entretien</th><th>Facteur principal</th></tr></thead><tbody>{exposureTop.map(segment => <tr key={segment.segment_code}><td>{segment.segment_code}</td><td>{segment.name || '—'}</td><td>{levelBadge(segment)}</td><td>{percent(segment.risk_score)}</td><td>{centile(segment.exposure_percentile)}</td><td>{segment.maintenance_priority || '—'}</td><td>{mainFactor(segment)}</td></tr>)}</tbody></table></div></> : <p className="ministry-empty">Aucun segment à risque moyen, élevé ou critique.</p>}</section>
      </>}

      {!isEquipment && section === 'assignments' && <section className="ministry-panel"><div className="ministry-panel-heading"><div><span className="ministry-kicker">PLANIFICATION DE FLOTTE</span><h2>Affecter un bus à une ligne</h2></div></div><form className="assignment-form" onSubmit={assignBus}><label>Ligne<select required value={routeCode} onChange={e => setRouteCode(e.target.value)}><option value="">Choisir</option>{routes.filter(r => r.active).map(r => <option key={r.route_code} value={r.route_code}>{r.route_code} · {r.name}</option>)}</select></label><label>Bus<select required value={vehicleCode} onChange={e => setVehicleCode(e.target.value)}><option value="">Choisir</option>{activeBuses.map(v => <option key={v.vehicle_code} value={v.vehicle_code}>{v.vehicle_code} · {v.label}</option>)}</select></label><label>Conducteur<select required value={driverUsername} onChange={e => setDriverUsername(e.target.value)}><option value="">Choisir</option>{activeDrivers.map(d => <option key={d.username} value={d.username}>{d.username} · {d.display_name}</option>)}</select></label><button className="ministry-primary" disabled={saving === 'assignment'}>Confirmer l’affectation</button></form><div className="ministry-panel-heading assignments-heading"><div><span className="ministry-kicker">EN SERVICE</span><h2>Affectations actives</h2></div><span>{assignments.length}</span></div>{assignments.length ? <div className="ministry-table-wrap"><table><thead><tr><th>Ligne</th><th>Véhicule</th><th>Conducteur</th><th>Depuis</th></tr></thead><tbody>{assignments.map(a => <tr key={a.assignment_id}><td>{a.route_code} · {a.route_name}</td><td>{a.vehicle_code} · {a.vehicle_label}</td><td>{a.driver_username || '—'}</td><td>{dateLabel(a.valid_from)}</td></tr>)}</tbody></table></div> : <p className="ministry-empty">Aucune affectation active.</p>}</section>}

      {!isEquipment && section === 'fleet' && <section className="ministry-panel"><div className="ministry-panel-heading"><div><span className="ministry-kicker">CONFIGURATION OPÉRATIONNELLE</span><h2>Lignes et flotte</h2></div><span>{routes.length} lignes · {vehicles.length} véhicules</span></div><div className="setup-grid"><form className="assignment-form" onSubmit={createVehicle}><h3>Ajouter un véhicule</h3><label>Code<input required value={vehicleDraft.vehicle_code} onChange={e => setVehicleDraft({ ...vehicleDraft, vehicle_code: e.target.value })}/></label><label>Libellé<input value={vehicleDraft.label} onChange={e => setVehicleDraft({ ...vehicleDraft, label: e.target.value })}/></label><label>Type<select value={vehicleDraft.vehicle_type} onChange={e => setVehicleDraft({ ...vehicleDraft, vehicle_type: e.target.value })}><option value="bus">Bus</option><option value="inspection">Inspection</option></select></label><button className="ministry-primary" disabled={saving === 'vehicle'}>Enregistrer</button></form><form className="assignment-form" onSubmit={createRoute}><h3>Créer une ligne avec OSRM</h3><label>Code<input required value={routeDraft.route_code} onChange={e => setRouteDraft({ ...routeDraft, route_code: e.target.value })}/></label><label>Nom<input required value={routeDraft.name} onChange={e => setRouteDraft({ ...routeDraft, name: e.target.value })}/></label><label>Départ lat<input type="number" step="any" required value={routeDraft.start_lat} onChange={e => setRouteDraft({ ...routeDraft, start_lat: e.target.value })}/></label><label>Départ lon<input type="number" step="any" required value={routeDraft.start_lon} onChange={e => setRouteDraft({ ...routeDraft, start_lon: e.target.value })}/></label><label>Arrivée lat<input type="number" step="any" required value={routeDraft.end_lat} onChange={e => setRouteDraft({ ...routeDraft, end_lat: e.target.value })}/></label><label>Arrivée lon<input type="number" step="any" required value={routeDraft.end_lon} onChange={e => setRouteDraft({ ...routeDraft, end_lon: e.target.value })}/></label><button className="ministry-primary" disabled={saving === 'route'}>Calculer et enregistrer</button></form></div><div className="ministry-table-wrap"><table><thead><tr><th>Code</th><th>Nom</th><th>Type</th><th>Organisation</th><th>État</th></tr></thead><tbody>{routes.map(r => <tr key={r.route_code}><td>{r.route_code}</td><td>{r.name}</td><td>Ligne</td><td>{r.owner_org}</td><td>{r.active ? 'Active' : 'Inactive'}</td></tr>)}{vehicles.map(v => <tr key={v.vehicle_code}><td>{v.vehicle_code}</td><td>{v.label || '—'}</td><td>{v.vehicle_type}</td><td>{v.owner_org}</td><td>{v.active ? 'Actif' : 'Inactif'}</td></tr>)}</tbody></table></div></section>}

      {section === 'accounts' && <section className="ministry-panel"><div className="ministry-panel-heading"><div><span className="ministry-kicker">GESTION DES ACCÈS</span><h2>Comptes du ministère</h2></div><span>{staff.length} comptes · {staff.filter(a => a.active).length} actifs</span></div><form className="assignment-form" onSubmit={createStaff}><label>Identifiant<input required minLength={3} maxLength={80} pattern={'[A-Za-z0-9._\\-]+'} title="Lettres, chiffres, . _ -" value={staffDraft.username} onChange={e => setStaffDraft({ ...staffDraft, username: e.target.value })}/></label><label>Nom affiché<input required minLength={2} maxLength={120} value={staffDraft.display_name} onChange={e => setStaffDraft({ ...staffDraft, display_name: e.target.value })}/></label><label>Rôle<select value={staffDraft.role} onChange={e => setStaffDraft({ ...staffDraft, role: e.target.value })}>{STAFF_ROLES[ministry].map(role => <option key={role} value={role}>{STAFF_ROLE_LABELS[role]}</option>)}</select></label><label>Mot de passe<input type="password" required minLength={8} maxLength={128} autoComplete="new-password" value={staffDraft.password} onChange={e => setStaffDraft({ ...staffDraft, password: e.target.value })}/></label><button className="ministry-primary" disabled={saving === 'staff'}>Créer le compte</button></form>{staff.length ? <div className="ministry-table-wrap"><table><thead><tr><th>Identifiant</th><th>Nom</th><th>Rôle</th><th>Actif</th><th>Créé le</th><th>Actions</th></tr></thead><tbody>{staff.map(account => { const own = account.username === me; return <tr key={account.username}><td>{account.username}{own ? ' (vous)' : ''}</td><td>{account.display_name}</td><td>{STAFF_ROLE_LABELS[account.role] || account.role}</td><td>{account.active ? 'Actif' : 'Inactif'}</td><td>{dateLabel(account.created_at)}</td><td>{own ? '—' : <div className="record-actions"><button className="ministry-secondary" disabled={saving === account.username} onClick={() => toggleStaffActive(account)}>{account.active ? 'Désactiver' : 'Réactiver'}</button>{!SUPERVISOR_ROLES.includes(account.role) && <button className="ministry-secondary" disabled={saving === account.username} onClick={() => resetStaffPassword(account)}>Réinitialiser le mot de passe</button>}</div>}</td></tr>; })}</tbody></table></div> : <p className="ministry-empty">Aucun compte.</p>}</section>}
    </div>
  </main>;
}
