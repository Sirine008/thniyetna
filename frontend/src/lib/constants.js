import { DEFECTS, defectLabel } from './labels.js';

export const BIZERTE = [37.2746, 9.8739];
// Rows created by scripts/seed_demo.py carry `demo: true` (API); always shown with this label.
export const DEMO_LABEL = 'DÉMO — données fictives';
export const demoBadge = item => item?.demo ? `<span class="badge badge-demo">${DEMO_LABEL}</span><br/>` : '';
export const EMPTY_MAP = { events: [], complaints: [], segments: [], routes: [] };
// M1 / citizen hazard types in French (driver alerts, citizen route card): labels.js is the single source
export const HAZARD_LABELS = DEFECTS;
export const hazardLabel = type => (type ? defectLabel(type) : 'danger');
