// Display formatters (French). Pure module: runs under `node --test`.
// Dates are always shown in Tunisian time (Africa/Tunis), whatever the device time zone.
export const TIME_ZONE = 'Africa/Tunis';
const NBSP = ' '; // narrow no-break space, French typography before % and units

const num = (value, digits) => new Intl.NumberFormat('fr-FR', { minimumFractionDigits: digits, maximumFractionDigits: digits })
  .format(value).replace(/ /g, NBSP);
const isBlank = value => value == null || value === '' || Number.isNaN(Number(value));

/** Model scores (0..1): 2 decimals, "0,39". */
export const score = value => (isBlank(value) ? '—' : num(Number(value), 2));
/** Probabilities / risks / confidences (0..1) as a percentage: "39 %"; `digits` decimals. */
export const pct = (value, digits = 0) => (isBlank(value) ? '—' : `${num(Number(value) * 100, digits)}${NBSP}%`);
/** Plain number with French separators. */
export const number = (value, digits = 0) => (isBlank(value) ? '—' : num(Number(value), digits));
/** Distances: "450 m" under 1 km, then "2,3 km". */
export function distance(metres) {
  if (isBlank(metres)) return '—';
  const m = Number(metres);
  return m < 1000 ? `${Math.round(m)}${NBSP}m` : `${num(m / 1000, 1)}${NBSP}km`;
}
/** Durations given in seconds: "38 min", "1 h 05". */
export function duration(seconds) {
  if (isBlank(seconds)) return '—';
  const minutes = Math.round(Number(seconds) / 60);
  if (minutes < 60) return `${minutes}${NBSP}min`;
  return `${Math.floor(minutes / 60)}${NBSP}h${NBSP}${String(minutes % 60).padStart(2, '0')}`;
}
/** Coordinates as stored (decimal point, 5 decimals): "37.27460, 9.87390". */
export const coords = (lat, lon) => (isBlank(lat) || isBlank(lon) ? '—' : `${Number(lat).toFixed(5)}, ${Number(lon).toFixed(5)}`);

const partsOf = (value, options) => {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return Object.fromEntries(new Intl.DateTimeFormat('fr-FR', { timeZone: TIME_ZONE, ...options })
    .formatToParts(date).map(p => [p.type, p.value]));
};
/** "23 oct. 2026, 18:44" (Tunisian time). */
export function dateTime(value) {
  if (!value) return '—';
  const p = partsOf(value, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  return p ? `${p.day} ${p.month} ${p.year}, ${p.hour}:${p.minute}` : '—';
}
/** "23 oct. 2026" (Tunisian time). Date-only strings ("2026-10-23") are calendar days, not shifted. */
export function date(value) {
  if (!value) return '—';
  const p = /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? partsOf(new Date(`${value}T12:00:00Z`), { day: 'numeric', month: 'short', year: 'numeric' })
    : partsOf(value, { day: 'numeric', month: 'short', year: 'numeric' });
  return p ? `${p.day} ${p.month} ${p.year}` : '—';
}
/** "18:44" (Tunisian time). */
export function time(value) {
  if (!value) return '—';
  const p = partsOf(value, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  return p ? `${p.hour}:${p.minute}` : '—';
}
/** Position in a video: "01:07,4" (minutes:seconds, one decimal). */
export function videoTime(seconds) {
  if (isBlank(seconds)) return '—';
  const s = Math.max(0, Number(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${num(s % 60, 1).padStart(4, '0')}`;
}
/** "3 signalements", "1 signalement", "0 signalement" (French: 0 and 1 are singular). */
export const plural = (n, one, many = `${one}s`) => `${number(n)} ${Math.abs(Number(n)) >= 2 ? many : one}`;
