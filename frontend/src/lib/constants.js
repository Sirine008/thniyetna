export const BIZERTE = [37.2746, 9.8739];
// Rows created by scripts/seed_demo.py carry `demo: true` (API); always shown with this label.
export const DEMO_LABEL = 'DÉMO — données fictives';
export const demoBadge = item => item?.demo ? `<span class="demo-badge">${DEMO_LABEL}</span><br/>` : '';
export const EMPTY_MAP = { events: [], complaints: [], segments: [], routes: [] };
