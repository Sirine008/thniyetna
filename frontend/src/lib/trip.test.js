// npm test (node --test): click-assignment rule, swap, validation and shareable URL of the trip fields.
import test from 'node:test';
import assert from 'node:assert/strict';
import { clickTarget, swapTrip, tripError, tripQuery, readTripQuery, parseLatLon, distanceM,
  OUT_OF_ZONE_START, OUT_OF_ZONE_DESTINATION, SAME_POINTS } from './trip.js';

const A = { pos: [37.2746, 9.8739], label: 'Bizerte', covered: true };
const B = { pos: [37.1537, 9.7856], label: 'Menzel Bourguiba', covered: true };

test('map click fills the active field, whatever is already filled', () => {
  assert.equal(clickTarget('from', null, null), 'from');
  assert.equal(clickTarget('from', A, B), 'from');
  assert.equal(clickTarget('to', null, null), 'to');
  assert.equal(clickTarget('to', A, B), 'to');
});

test('map click with no active field: Départ if empty, otherwise Arrivée', () => {
  assert.equal(clickTarget(null, null, null), 'from');
  assert.equal(clickTarget(null, null, B), 'from');
  assert.equal(clickTarget(null, A, null), 'to');
  assert.equal(clickTarget(null, A, B), 'to');      // both set: replaces the arrival
  assert.equal(clickTarget(undefined, A, null), 'to');
});

test('swap exchanges the points and the field texts', () => {
  const s = swapTrip({ from: A, to: B, text: { from: 'Bizerte', to: 'Menzel' } });
  assert.equal(s.from, B);
  assert.equal(s.to, A);
  assert.deepEqual(s.text, { from: 'Menzel', to: 'Bizerte' });
  assert.deepEqual(swapTrip(swapTrip({ from: A, to: B, text: { from: 'x', to: 'y' } })), { from: A, to: B, text: { from: 'x', to: 'y' } });
  const half = swapTrip({ from: A, to: null });
  assert.equal(half.from, null);
  assert.equal(half.to, A);
});

test('validation: out of zone (start first), identical points under 50 m', () => {
  assert.equal(tripError(A, B), null);
  assert.equal(tripError({ ...A, covered: false }, B), OUT_OF_ZONE_START);
  assert.equal(tripError(A, { ...B, covered: false }), OUT_OF_ZONE_DESTINATION);
  assert.equal(tripError(A, { ...A }), SAME_POINTS);
  assert.equal(tripError(A, { pos: [37.2749, 9.8739] }), SAME_POINTS);          // ~33 m
  assert.equal(tripError(A, { pos: [37.2752, 9.8739] }), null);                 // ~67 m
  assert.equal(SAME_POINTS, 'Le départ et l’arrivée sont identiques');
  assert.equal(tripError(A, null), null);
  assert.ok(Math.abs(distanceM(A.pos, B.pos) - 15552) < 5);  // straight line Bizerte - Menzel Bourguiba
});

test('shareable URL round trip', () => {
  const q = tripQuery('', A, B);
  assert.equal(q, '?from=37.274600,9.873900&to=37.153700,9.785600');
  assert.deepEqual(readTripQuery(q), { from: A.pos, to: B.pos });
  assert.equal(tripQuery('?from=1,2&to=3,4', null, null), '');
  assert.equal(tripQuery('?x=1', null, B), '?x=1&to=37.153700,9.785600');
  assert.deepEqual(readTripQuery('?from=abc&to=91,9'), { from: null, to: null });
  assert.deepEqual(parseLatLon(' 37.27 , 9.87 '), [37.27, 9.87]);
});
