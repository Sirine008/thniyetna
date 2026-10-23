// npm test (node --test): the citizen route card never says "vérifié" on a risky route.
import test from 'node:test';
import assert from 'node:assert/strict';
import { routeState, hazardLine, fromStart, WARNING_TITLE } from './routeState.js';

const ALLIGATOR = { type: 'alligator_crack', latitude: 37.27, longitude: 9.865, risk: 0.9, distance_m: 0, distance_from_start_m: 2340 };

test('risky route without a safe alternative: red warning listing each hazard', () => {
  const s = routeState({ status: 'warning', warning: true, reroute_needed: false, fastest_risk: 0.65, risk: 0.65,
    distance_m: 3000, duration_s: 300, hazards: [ALLIGATOR, { type: 'citizen_report', risk: 0.72, distance_from_start_m: 450 }] });
  assert.equal(s.kind, 'warning');
  assert.equal(s.tone, 'red');
  assert.equal(s.title, WARNING_TITLE);
  assert.deepEqual(s.hazards, ['signalement citoyen · à 450 m du départ · risque 72 %',  // trip order
    'faïençage · à 2,3 km du départ · risque 90 %']);
  assert.match(s.detail, /^Risque 65 %/);
});

test('M2-only warning has no point hazard but still explains the danger', () => {
  const s = routeState({ warning: true, fastest_risk: 0.5, hazards: [] });
  assert.equal(s.kind, 'warning');
  assert.equal(s.note, 'Segments à risque élevé (prédiction M2)');
});

test('never "Trajet vérifié" when the fastest route is >= 0.42, even without the warning flag', () => {
  for (const risk of [0.42, 0.5, 1]) {
    const s = routeState({ warning: false, reroute_needed: false, fastest_risk: risk, risk, hazards: [] });
    assert.equal(s.kind, 'warning');
    assert.doesNotMatch(s.title, /vérifié/);
  }
});

test('reroute: risk A % -> B % and the hazards avoided', () => {
  const s = routeState({ reroute_needed: true, fastest_risk: 0.9, risk: 0.05, distance_m: 4200, duration_s: 420, hazards: [ALLIGATOR] });
  assert.equal(s.kind, 'reroute');
  assert.equal(s.title, 'Alternative plus sûre recommandée');
  assert.equal(s.detail, 'Risque 90 % → 5 % · 4,2 km · 7 min');
  assert.deepEqual(s.hazards, [hazardLine(ALLIGATOR)]);
});

test('safe route', () => {
  const s = routeState({ reroute_needed: false, warning: false, fastest_risk: 0.1, risk: 0.1, distance_m: 2500, duration_s: 240, hazards: [] });
  assert.equal(s.kind, 'safe');
  assert.equal(s.tone, 'green');
  assert.equal(s.title, 'Trajet vérifié · aucun danger significatif');
});

test('distance formatting', () => {
  assert.equal(fromStart(0), '0 m');
  assert.equal(fromStart(987), '990 m');
  assert.equal(fromStart(12345), '12,3 km');
});
