// Citizen trip fields « Départ » (from) / « Arrivée » (to): pure rules, run under `node --test`.
export const OUT_OF_ZONE_START = 'Point de départ hors de la zone couverte (gouvernorat de Bizerte)';
export const OUT_OF_ZONE_DESTINATION = 'Destination hors de la zone couverte (gouvernorat de Bizerte)';
export const SAME_POINTS = 'Le départ et l’arrivée sont identiques';
export const SAME_POINTS_M = 50;

/** Field a map click fills: the active (focused) one; else « Départ » if empty, otherwise « Arrivée ». */
export function clickTarget(active, from, to) {
  if (active === 'from' || active === 'to') return active;
  return from ? 'to' : 'from';
}

/** ⇅: the two points and their field texts change places. */
export function swapTrip({ from, to, text = { from: '', to: '' } }) {
  return { from: to, to: from, text: { from: text.to, to: text.from } };
}

export function distanceM(a, b) {
  const r = 6371008.8, rad = Math.PI / 180;
  const dp = (b[0] - a[0]) * rad, dl = (b[1] - a[1]) * rad;
  const h = Math.sin(dp / 2) ** 2 + Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(h));
}

/** First blocking problem of the trip (French message), or null. `covered` comes from /routing/places/nearest. */
export function tripError(from, to) {
  if (from?.covered === false) return OUT_OF_ZONE_START;
  if (to?.covered === false) return OUT_OF_ZONE_DESTINATION;
  if (from && to && distanceM(from.pos, to.pos) < SAME_POINTS_M) return SAME_POINTS;
  return null;
}

// Shareable URL: ?from=lat,lon&to=lat,lon (6 decimals ≈ 0.1 m)
const fmt = p => `${p[0].toFixed(6)},${p[1].toFixed(6)}`;
export function parseLatLon(value) {
  const m = /^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/.exec(value || '');
  if (!m) return null;
  const lat = Number(m[1]), lon = Number(m[2]);
  return Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? [lat, lon] : null;
}
export function readTripQuery(search) {
  const q = new URLSearchParams(search);
  return { from: parseLatLon(q.get('from')), to: parseLatLon(q.get('to')) };
}
/** The query string for the current points, keeping any other parameter of `search`. */
export function tripQuery(search, from, to) {
  const q = new URLSearchParams(search);
  for (const [key, point] of [['from', from], ['to', to]]) {
    if (point) q.set(key, fmt(point.pos)); else q.delete(key);
  }
  const s = q.toString().replaceAll('%2C', ',');
  return s ? `?${s}` : '';
}
