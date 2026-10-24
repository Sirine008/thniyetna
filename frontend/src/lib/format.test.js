// npm test: French formatters, Tunisian time.
import test from 'node:test';
import assert from 'node:assert/strict';
import { score, pct, distance, duration, dateTime, date, time, coords, plural, number, videoTime } from './format.js';

const S = ' ';
test('scores keep 2 decimals with a French comma', () => {
  assert.equal(score(0.39404), '0,39');
  assert.equal(score(1), '1,00');
  assert.equal(score(null), '—');
});
test('percentages for risk and confidence', () => {
  assert.equal(pct(0.354), `35${S}%`);
  assert.equal(pct(0.8), `80${S}%`);
  assert.equal(pct(0.0123, 1), `1,2${S}%`);
  assert.equal(pct(undefined), '—');
});
test('distances in m then km, durations in min', () => {
  assert.equal(distance(450.4), `450${S}m`);
  assert.equal(distance(2340), `2,3${S}km`);
  assert.equal(distance(28200), `28,2${S}km`);
  assert.equal(duration(2280), `38${S}min`);
  assert.equal(duration(3900), `1${S}h${S}05`);
});
test('dates in Africa/Tunis time, whatever the input zone', () => {
  // 17:44 UTC = 18:44 in Tunis (UTC+1, no DST)
  assert.equal(dateTime('2026-10-23T17:44:00Z'), '23 oct. 2026, 18:44');
  assert.equal(dateTime('2026-10-23T23:30:00Z'), '24 oct. 2026, 00:30');
  assert.equal(time('2026-10-23T17:44:00+00:00'), '18:44');
  assert.equal(date('2026-10-23T23:30:00Z'), '24 oct. 2026');
  assert.equal(date('2026-10-23'), '23 oct. 2026'); // calendar day, not shifted
  assert.equal(dateTime(null), '—');
  assert.equal(dateTime('not a date'), '—');
});
test('position in a video', () => {
  assert.equal(videoTime(4.25), '00:04,3');
  assert.equal(videoTime(67.4), '01:07,4');
  assert.equal(videoTime(null), '—');
});
test('coordinates and counts', () => {
  assert.equal(coords(37.2746, 9.8739), '37.27460, 9.87390');
  assert.equal(plural(0, 'signalement'), '0 signalement');
  assert.equal(plural(1, 'signalement'), '1 signalement');
  assert.equal(plural(3, 'signalement'), '3 signalements');
  assert.equal(plural(2, 'détection à valider', 'détections à valider'), '2 détections à valider');
  assert.equal(number(1234), `1${S}234`);
});
