// Citizen route card: the three outcomes of POST /routing/route, worded like the driver alerts.
// Pure module (no React / browser API) so it runs under `node --test`.
import { hazardLabel } from './constants.js';

export const REROUTE_MIN_RISK = 0.42; // backend/routing/router.py: above it the fastest route is never "vérifié"
export const WARNING_TITLE = 'Danger sur l’itinéraire — aucune alternative sûre';

const pct = risk => `${Math.round((risk || 0) * 100)} %`;
const km = m => `${((m || 0) / 1000).toFixed(1).replace('.', ',')} km`;
const minutes = s => `${Math.round((s || 0) / 60)} min`;
export const fromStart = m => (m < 1000 ? `${Math.round(m / 10) * 10} m` : km(m));

/** "faïençage · à 2,3 km du départ · risque 90 %" */
export const hazardLine = h => `${hazardLabel(h.type)} · à ${fromStart(h.distance_from_start_m ?? 0)} du départ · risque ${pct(h.risk)}`;

/** {kind: 'safe' | 'reroute' | 'warning', tone, title, detail, hazards[] (lines), note} */
export function routeState(plan) {
  // in trip order (the API lists them by exposure)
  const hazards = [...(plan.hazards || [])].sort((a, b) => (a.distance_from_start_m ?? 0) - (b.distance_from_start_m ?? 0)).map(hazardLine);
  const m2 = 'Segments à risque élevé (prédiction M2)';
  if (plan.reroute_needed) {
    return {
      kind: 'reroute', tone: 'orange', title: 'Alternative plus sûre recommandée',
      detail: `Risque ${pct(plan.fastest_risk)} → ${pct(plan.risk)} · ${km(plan.distance_m)} · ${minutes(plan.duration_s)}`,
      hazardsTitle: 'Dangers évités', hazards, note: hazards.length ? null : `Évite : ${m2.toLowerCase()}`,
    };
  }
  // warning flag from the API, or (defensively) any fastest route at or above the reroute threshold
  if (plan.warning || (plan.fastest_risk || 0) >= REROUTE_MIN_RISK) {
    return {
      kind: 'warning', tone: 'red', title: WARNING_TITLE,
      detail: `Risque ${pct(plan.fastest_risk)} · ${km(plan.fastest_distance_m || plan.distance_m)} · prudence`,
      hazardsTitle: 'Dangers sur le trajet', hazards, note: hazards.length ? null : m2,
    };
  }
  return {
    kind: 'safe', tone: 'green', title: 'Trajet vérifié · aucun danger significatif',
    detail: `${km(plan.distance_m)} · ${minutes(plan.duration_s)} · risque ${pct(plan.risk)}`, hazards: [], note: null,
  };
}
