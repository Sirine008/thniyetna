import React from 'react';
import { RISK_LABELS } from '../lib/labels';

// One legend vocabulary for every map. Line styles differ per level (not only the colour).
export const RISK_STYLE = {
  low: { color: 'var(--c-green-solid)', hex: '#2e8540', weight: 3, dash: null },
  medium: { color: 'var(--c-yellow-solid)', hex: '#d8a800', weight: 4, dash: '8 6' },
  high: { color: 'var(--c-orange-solid)', hex: '#dd6b10', weight: 5, dash: null },
  critical: { color: 'var(--c-red-solid)', hex: '#c62828', weight: 6, dash: null },
};
export const UNSCORED_STYLE = { hex: '#8d99a6', weight: 2, dash: '2 6' };

const ITEMS = {
  risk: ['low', 'medium', 'high', 'critical'].map(level => ({
    key: level, node: <span className="legend-line" style={{ color: RISK_STYLE[level].color, borderBlockStartWidth: RISK_STYLE[level].weight - 1, borderBlockStartStyle: RISK_STYLE[level].dash ? 'dashed' : 'solid' }}/>, label: `Risque ${RISK_LABELS[level].toLowerCase()}`,
  })),
  hazards: [
    { key: 'event', node: <span className="legend-marker" style={{ background: 'var(--c-red-solid)' }}/>, label: 'Détection (M1)' },
    { key: 'claim', node: <span className="legend-marker" style={{ background: 'var(--c-orange-solid)', borderRadius: '50%' }}/>, label: 'Signalement citoyen' },
  ],
  route: [
    { key: 'route', node: <span className="legend-line" style={{ color: 'var(--c-primary)' }}/>, label: 'Itinéraire' },
    { key: 'initial', node: <span className="legend-line dashed" style={{ color: 'var(--c-red-solid)' }}/>, label: 'Trajet initial (à risque)' },
    { key: 'safe', node: <span className="legend-line" style={{ color: 'var(--c-green-solid)' }}/>, label: 'Alternative plus sûre' },
  ],
  line: [{ key: 'line', node: <span className="legend-line" style={{ color: 'var(--c-primary)' }}/>, label: 'Ligne affectée' }],
};

/** show: list of groups among risk | hazards | route | line. */
export function MapLegend({ show = ['hazards'], floating = false, label = 'Légende de la carte' }) {
  return <ul className={`legend${floating ? ' is-floating' : ''}`} aria-label={label} style={{ listStyle: 'none', margin: floating ? undefined : 0, padding: floating ? undefined : 0 }}>
    {show.flatMap(group => ITEMS[group] || []).map(item => <li className="legend-item" key={item.key}>{item.node}<span>{item.label}</span></li>)}
  </ul>;
}
