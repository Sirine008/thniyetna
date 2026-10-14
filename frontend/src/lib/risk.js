// Display helpers for M2 RiskScore 1.1.0 (data/schemas/risk_score.schema.json).

export const RISK_LEVELS = ['low', 'medium', 'high', 'critical'];
export const RISK_LABELS = { low: 'Faible', medium: 'Moyen', high: 'Élevé', critical: 'Critique' };
export const CONDITION_LABELS = {
  no_observed_defect: 'Aucun défaut observé', good: 'Bon', fair: 'Moyen', poor: 'Dégradé', critical: 'Critique',
};
export const PRIORITY_LABELS = { P1: 'P1 · Urgent', P2: 'P2 · Prioritaire', P3: 'P3 · Planifier', P4: 'P4 · Surveiller' };
export const ROAD_CLASSES = { motorway: 'autoroute', national: 'nationale', regional: 'régionale', local: 'locale', urban: 'urbaine' };

// 4-level contract value; falls back to the legacy 3-level category for contextual-v1 rows.
export const riskLevel = segment => segment?.risk_level || segment?.risk_category || null;
export const levelRank = level => RISK_LEVELS.indexOf(level);
export const priorityRank = p => (p && /^P\d$/.test(p) ? Number(p.slice(1)) : 9);
export const percent = value => (value == null ? '—' : `${Math.round(Number(value) * 100)}%`);

const parseFactors = raw => {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  try { return JSON.parse(raw); } catch { return []; }
};

export const roadClassLabel = c => (c ? ROAD_CLASSES[c] || c : '—');

export function factorLabel(factor) {
  const name = factor?.feature || '';
  const window = name.match(/_(\d+)$/)?.[1];
  if (name === 'm1:road_condition') return `État de la chaussée (${factor.value ?? '?'} défaut(s) M1)`;
  if (name.startsWith('segment:road_class=')) return `Route ${ROAD_CLASSES[name.split('=')[1]] || name.split('=')[1]}`;
  const base = name.replace(/^gov:/, '');
  if (base.startsWith('hist_acc_sum')) return `Accidents du gouvernorat · ${window} j`;
  if (base.startsWith('nat_acc_sum')) return `Accidents nationaux · ${window} j`;
  if (base.startsWith('road_density')) return 'Densité du réseau routier';
  if (/rain|precip/.test(base)) return `Pluie${window ? ` · ${window} j` : ''}`;
  if (/ramadan|holiday|eid|dow|month|weekend/.test(base)) return 'Calendrier';
  return base.replaceAll('_', ' ');
}

// Strongest factor that pushes the risk UP (positive log-odds contribution).
export function mainFactor(segment) {
  const factors = parseFactors(segment?.top_factors).filter(f => Number(f.contribution) > 0);
  if (!factors.length) return '—';
  const top = factors.sort((a, b) => Number(b.contribution) - Number(a.contribution))[0];
  return factorLabel(top);
}
