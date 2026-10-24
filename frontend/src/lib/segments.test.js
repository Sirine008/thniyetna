// npm test: segment lists, same rules as the pre-redesign Ministry.jsx.
import test from 'node:test';
import assert from 'node:assert/strict';
import { dayForecasts, exposureFallback, geoLines, maintenanceQueue, riskySegments, watchOnly, centile, modelLine } from './segments.js';

const seg = (code, p, score, extra = {}) => ({ segment_code: code, maintenance_priority: p, risk_score: score, risk_level: 'low', ...extra });

test('maintenance queue: P1 → P3 by priority then score, P3 watch-only excluded, P4 excluded', () => {
  const rows = [seg('a', 'P3', 0.5, { predicted_condition: 'poor' }), seg('b', 'P2', 0.2), seg('c', 'P2', 0.4), seg('d', 'P4', 0.9),
    seg('e', 'P3', 0.9, { predicted_condition: 'no_observed_defect' }), seg('f', 'P1', 0.1)];
  assert.deepEqual(maintenanceQueue(rows).map(s => s.segment_code), ['f', 'c', 'b', 'a']);
  assert.equal(rows.filter(watchOnly).length, 1);
});
test('risky segments (medium and above) and the exposure fallback when none', () => {
  const rows = [seg('a', 'P4', 0.1, { exposure_percentile: 0.99 }), seg('b', 'P4', 0.2, { exposure_percentile: 0.96 }), seg('c', 'P4', 0.3, { exposure_percentile: 0.5 })];
  assert.equal(riskySegments(rows).length, 0);
  assert.deepEqual(exposureFallback(rows).map(s => s.segment_code), ['a', 'b']);
  rows.push(seg('d', 'P2', 0.4, { risk_level: 'medium' }), seg('e', 'P1', 0.6, { risk_category: 'high', risk_level: null }));
  assert.deepEqual(riskySegments(rows).map(s => s.segment_code), ['e', 'd']);
  assert.deepEqual(exposureFallback(rows), []);
});
test('next forecast day, alerts first then probability', () => {
  const f = [{ gov_code: 'A', forecast_date: '2026-10-25', alert: true, p_accident: 0.9 }, { gov_code: 'B', forecast_date: '2026-10-24', alert: false, p_accident: 0.8 },
    { gov_code: 'C', forecast_date: '2026-10-24', alert: true, p_accident: 0.3 }, { gov_code: 'D', forecast_date: '2026-10-24', alert: true, p_accident: 0.6 }];
  assert.deepEqual(dayForecasts(f).map(x => x.gov_code), ['D', 'C', 'B']);
});
test('helpers', () => {
  assert.deepEqual(geoLines({ type: 'LineString', coordinates: [[9.8, 37.2], [9.9, 37.3]] }), [[[37.2, 9.8], [37.3, 9.9]]]);
  assert.equal(geoLines({ type: 'MultiLineString', coordinates: [[[1, 2]], [[3, 4]]] }).length, 2);
  assert.equal(centile(0.973), '97e centile');
  assert.equal(modelLine({ status: 'ok', version: '2026.10.11-2054', classifier: 'logreg' }), 'Modèle M2 2026.10.11-2054 · logreg');
  assert.equal(modelLine(null), 'Modèle M2 non chargé · scores contextuels');
});
