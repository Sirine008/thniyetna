// Display helpers for M2 RiskScore 1.1.0 (data/schemas/risk_score.schema.json). Labels live in labels.js.
import { CONDITIONS, PRIORITY_LABELS, RISK_LABELS, RISK_LEVELS, ROAD_CLASSES, factorName, factorPhrase, roadClassLabel } from './labels.js';
import { pct } from './format.js';

export { RISK_LEVELS, RISK_LABELS, PRIORITY_LABELS, ROAD_CLASSES, roadClassLabel };
export const CONDITION_LABELS = CONDITIONS;

// 4-level contract value; falls back to the legacy 3-level category for contextual-v1 rows.
export const riskLevel = segment => segment?.risk_level || segment?.risk_category || null;
export const levelRank = level => RISK_LEVELS.indexOf(level);
export const priorityRank = p => (p && /^P\d$/.test(p) ? Number(p.slice(1)) : 9);
export const percent = pct;

export const parseFactors = raw => {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  try { return JSON.parse(raw); } catch { return []; }
};
export const factorLabel = factorName;

// Strongest factor that pushes the risk UP (positive log-odds contribution), as a phrase.
export function mainFactor(segment) {
  const factors = parseFactors(segment?.top_factors).filter(f => Number(f.contribution) > 0);
  if (!factors.length) return '—';
  return factorPhrase(factors.sort((a, b) => Number(b.contribution) - Number(a.contribution))[0]);
}
// Every factor, strongest effect first (both directions)
export const factorList = segment => parseFactors(segment?.top_factors)
  .slice().sort((a, b) => Math.abs(Number(b.contribution)) - Math.abs(Number(a.contribution)));
