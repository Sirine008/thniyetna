// One French label for every technical value shown in the UI. Pure module: runs under `node --test`.
// Unknown values fall back to a readable form of the raw value (never hidden).
const readable = value => (value == null || value === '' ? '—' : String(value).replaceAll('_', ' '));
const lookup = table => value => table[value] ?? readable(value);

// M1 defect classes (RDD2022) and other point hazards
export const DEFECTS = {
  alligator_crack: 'faïençage', pothole: 'nid-de-poule', longitudinal_crack: 'fissure longitudinale',
  transverse_crack: 'fissure transversale', citizen_report: 'signalement citoyen', hazard: 'danger',
};
export const defectLabel = lookup(DEFECTS);
export const defectTitle = value => { const s = defectLabel(value); return s.charAt(0).toUpperCase() + s.slice(1); };

// Citizen reports (complaints.status). Supervisors and citizens read the same states.
export const REPORT_STATES = {
  open: 'Nouveau', under_review: 'En analyse', validated: 'Validé', planned: 'Intervention planifiée',
  resolved: 'Résolu', rejected: 'Rejeté',
};
export const reportStateLabel = lookup(REPORT_STATES);
// Order of the workflow (rejected is a terminal branch, not a step)
export const REPORT_FLOW = ['open', 'under_review', 'validated', 'planned', 'resolved'];
// States a supervisor can set (same list as before the redesign; "open" is the initial state only)
export const REPORT_TARGET_STATES = ['under_review', 'validated', 'planned', 'resolved', 'rejected'];
export const REPORT_CATEGORIES = { road_damage: 'Dégradation de la chaussée', flooding: 'Inondation', obstacle: 'Obstacle' };
export const reportCategoryLabel = lookup(REPORT_CATEGORIES);

// M1 road events
export const EVENT_STATES = { observed: 'À valider', validated: 'Validée', closed: 'Clôturée' };
export const eventStateLabel = lookup(EVENT_STATES);
export const SOURCES = { citizen: 'Signalement citoyen (photo)', inspection_vehicle: 'Véhicule d’inspection' };
export const sourceLabel = lookup(SOURCES);
export const INSPECTION_STATES = { active: 'En cours', completed: 'Terminée' };
export const inspectionStateLabel = lookup(INSPECTION_STATES);

// Notifications (notification_outbox.topic)
export const ALERT_TOPICS = {
  'driver.reroute.alert': 'Nouvel itinéraire recommandé',
  'driver.route.warning': 'Danger sur l’itinéraire — aucune alternative sûre',
  'route.assignment': 'Nouvelle affectation de ligne',
  'route.updated': 'Ligne mise à jour',
  'complaint.created': 'Nouveau signalement citoyen',
  'complaint.status': 'Statut de signalement modifié',
  'road.event.created': 'Nouvelle détection routière',
  'road.event.validated': 'Détection validée',
  'risk.batch_updated': 'Scores de risque M2 mis à jour',
  'risk.updated': 'Score de risque mis à jour',
  'staff.account.created': 'Compte créé',
  'perception.job.queued': 'Analyse d’image en attente',
  'perception.job.completed': 'Analyse d’image terminée',
  'perception.job.failed': 'Analyse d’image en échec',
  'vehicle.position': 'Position du véhicule',
};
export const alertTopicLabel = lookup(ALERT_TOPICS);

// Accounts
export const ROLES = {
  citizen: 'Citoyen', bus_driver: 'Conducteur de bus', inspection_vehicle: 'Véhicule d’inspection',
  equipment_supervisor: 'Superviseur Équipement', transport_supervisor: 'Superviseur Transport',
};
export const roleLabel = lookup(ROLES);
export const MINISTRIES = { equipment: 'Ministère de l’Équipement', transport: 'Ministère du Transport' };
export const VEHICLE_TYPES = { bus: 'Bus', inspection: 'Véhicule d’inspection' };
export const vehicleTypeLabel = lookup(VEHICLE_TYPES);

// M2 RiskScore 1.1.0
export const RISK_LEVELS = ['low', 'medium', 'high', 'critical'];
export const RISK_LABELS = { low: 'Faible', medium: 'Moyen', high: 'Élevé', critical: 'Critique' };
export const riskLabel = lookup(RISK_LABELS);
export const PRIORITIES = ['P1', 'P2', 'P3', 'P4'];
export const PRIORITY_LABELS = { P1: 'P1 · Urgent', P2: 'P2 · Prioritaire', P3: 'P3 · Planifier', P4: 'P4 · Surveiller' };
export const priorityLabel = lookup(PRIORITY_LABELS);
export const CONDITIONS = {
  no_observed_defect: 'Aucun défaut observé', good: 'Bon', fair: 'Moyen', poor: 'Dégradé', critical: 'Critique',
};
export const conditionLabel = lookup(CONDITIONS);
// M2 road classes (model features) and the OSM highway tags stored on road_segments.road_class
export const ROAD_CLASSES = {
  motorway: 'Autoroute', national: 'Route nationale', regional: 'Route régionale', local: 'Route locale', urban: 'Voie urbaine',
  trunk: 'Voie express', primary: 'Route principale', secondary: 'Route secondaire', tertiary: 'Route tertiaire',
  unclassified: 'Route non classée', residential: 'Voie résidentielle',
  motorway_link: 'Bretelle d’autoroute', trunk_link: 'Bretelle de voie express', primary_link: 'Bretelle (route principale)',
  secondary_link: 'Bretelle (route secondaire)', tertiary_link: 'Bretelle (route tertiaire)',
};
export const roadClassLabel = value => (value ? ROAD_CLASSES[value] ?? readable(value) : '—');

/** M2 factor (top_factors item) as a readable phrase: "Route nationale — augmente le risque". */
export function factorName(factor) {
  const name = factor?.feature || '';
  const window = name.match(/_(\d+)$/)?.[1];
  if (name === 'm1:road_condition') return `État de la chaussée observé (M1${factor?.value != null ? ` · ${factor.value} défaut(s)` : ''})`;
  if (name.startsWith('segment:road_class=')) return roadClassLabel(name.split('=')[1]);
  const base = name.replace(/^gov:/, '');
  if (base.startsWith('hist_acc_sum')) return `Accidents dans le gouvernorat (${window} derniers jours)`;
  if (base.startsWith('nat_acc_sum')) return `Accidents en Tunisie (${window} derniers jours)`;
  if (base.startsWith('road_density')) return 'Densité du réseau routier';
  if (/rain|precip/.test(base)) return `Pluie${window ? ` (${window} derniers jours)` : ''}`;
  if (/ramadan|holiday|eid|dow|month|weekend/.test(base)) return 'Calendrier (jour, mois, fêtes)';
  return readable(base);
}
export const factorEffect = factor => (Number(factor?.contribution) > 0 ? 'augmente le risque' : Number(factor?.contribution) < 0 ? 'diminue le risque' : 'sans effet');
export const factorPhrase = factor => `${factorName(factor)} — ${factorEffect(factor)}`;

// Known API error messages (English in the backend) shown in French; anything else is shown as received.
const API_ERRORS = [
  [/^Invalid username or password$/i, 'Identifiant ou mot de passe incorrect.'],
  [/^Username already exists$/i, 'Cet identifiant est déjà utilisé.'],
  [/^Insufficient role$/i, 'Votre compte n’a pas accès à cette action.'],
  [/^(Not authenticated|Could not validate credentials)$/i, 'Session expirée : reconnectez-vous.'],
  [/^Failed to fetch$|NetworkError|Load failed/i, 'Serveur injoignable. Vérifiez la connexion et réessayez.'],
  [/^Request failed \((\d+)\)$/, (m, code) => `La requête a échoué (erreur ${code}).`],
];
export function apiErrorMessage(message) {
  const text = String(message || '').trim();
  for (const [pattern, fr] of API_ERRORS) {
    const m = text.match(pattern);
    if (m) return typeof fr === 'function' ? fr(...m) : fr;
  }
  return text || 'Une erreur est survenue.';
}
