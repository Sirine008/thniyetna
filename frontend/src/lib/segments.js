// Segment lists of the supervisor screens (M2 RiskScore). Same rules as before the redesign, moved out of the
// page so they are shared by the tables and the maps, and tested. Pure module: runs under `node --test`.
import { levelRank, priorityRank, riskLevel } from './risk.js';

// Rank of risk_score within the governorate (M2 exposure_percentile): a ranking aid, not a probability.
export const EXPOSURE_TOP = 0.05;

// M2 contract: 4 risk levels (critical included); legacy 3-level rows still display.
export const riskySegments = segments => segments.filter(s => levelRank(riskLevel(s)) >= 1)
  .sort((a, b) => Number(b.risk_score || 0) - Number(a.risk_score || 0));

// All absolute risks low: the most exposed segments of their governorate instead (relative ranking).
export const exposureTop = segments => segments
  .filter(s => s.exposure_percentile != null && Number(s.exposure_percentile) >= 1 - EXPOSURE_TOP)
  .sort((a, b) => Number(b.exposure_percentile) - Number(a.exposure_percentile) || Number(b.risk_score || 0) - Number(a.risk_score || 0));
export const exposureFallback = segments => (riskySegments(segments).length ? [] : exposureTop(segments));

// P3 driven only by accident exposure (no observed defect) is a watch item, not a work order.
export const watchOnly = s => priorityRank(s.maintenance_priority) === 3 && s.predicted_condition === 'no_observed_defect';
// Maintenance worklist: M2 priority first (P1 → P4), then risk score.
export const maintenanceQueue = segments => segments.filter(s => priorityRank(s.maintenance_priority) <= 3 && !watchOnly(s))
  .sort((a, b) => priorityRank(a.maintenance_priority) - priorityRank(b.maintenance_priority) || Number(b.risk_score || 0) - Number(a.risk_score || 0));

// Next forecast day per governorate, alerts first.
export const nextForecastDay = forecasts => forecasts.reduce((min, f) => (!min || f.forecast_date < min ? f.forecast_date : min), null);
export const dayForecasts = forecasts => {
  const day = nextForecastDay(forecasts);
  return forecasts.filter(f => f.forecast_date === day).sort((a, b) => Number(b.alert) - Number(a.alert) || b.p_accident - a.p_accident);
};

export const modelLine = model => (model?.status === 'ok' ? `Modèle M2 ${model.version} · ${model.classifier}` : 'Modèle M2 non chargé · scores contextuels');
export const centile = value => (value == null ? '—' : `${Math.round(Number(value) * 100)}e centile`);

/** GeoJSON LineString / MultiLineString → Leaflet [[lat, lon], ...] lines. */
export function geoLines(geometry) {
  if (!geometry?.coordinates) return [];
  const flip = line => line.map(([lon, lat]) => [lat, lon]);
  if (geometry.type === 'LineString') return [flip(geometry.coordinates)];
  if (geometry.type === 'MultiLineString') return geometry.coordinates.map(flip);
  return [];
}
