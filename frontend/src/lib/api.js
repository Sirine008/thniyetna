import { clearSession, getToken, setSession } from './auth';

const API = import.meta.env.VITE_API_BASE || '/api';

async function parseError(response) {
  try {
    const payload = await response.json();
    return payload.detail || `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

export async function request(path, { method = 'GET', body, headers = {}, auth = false, token } = {}) {
  const requestHeaders = { ...headers };
  if (body && !(body instanceof FormData)) requestHeaders['Content-Type'] = 'application/json';

  const authToken = token || (auth ? getToken() : null);
  if (authToken) requestHeaders.Authorization = `Bearer ${authToken}`;

  const response = await fetch(`${API}${path}`, {
    method,
    headers: requestHeaders,
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  });

  if (response.status === 401 && auth) clearSession();
  if (!response.ok) throw new Error(await parseError(response));
  if (response.status === 204) return null;
  return response.json();
}

export async function loginWithCredentials(username, password) {
  const session = await request('/auth/login', { method: 'POST', body: { username, password } });
  setSession(session);
  return session;
}

export async function registerCitizen({ username, password, display_name }) {
  const session = await request('/auth/register', {
    method: 'POST',
    body: { username, password, display_name },
  });
  setSession(session);
  return session;
}

export const api = {
  me: () => request('/auth/me', { auth: true }),
  map: () => request('/platform/map'),
  myClaims: () => request('/platform/complaints/mine', { auth: true }),
  submitClaim: body => request('/platform/complaints', { auth: true, method: 'POST', body }),
  uploadImage: file => {
    const form = new FormData();
    form.append('file', file);
    return request('/media/image', { auth: true, method: 'POST', body: form });
  },
  driver: () => request('/routing/driver/me', { auth: true }),
  alerts: () => request('/platform/alerts', { auth: true }),
  nextBest: body => request('/routing/driver/next-best', { auth: true, method: 'POST', body }),
  planRoute: body => request('/routing/route', { method: 'POST', body }),
  geocode: q => request(`/routing/geocode?q=${encodeURIComponent(q)}`),
  equipmentDashboard: () => request('/platform/dashboard/equipment', { auth: true }),
  complaints: () => request('/platform/complaints', { auth: true }),
  updateComplaint: (id, body) => request(`/platform/complaints/${id}/status`, { auth: true, method: 'PATCH', body }),
  roadEvents: () => request('/perception/events?limit=100', { auth: true }),
  validateEvent: id => request(`/perception/events/${id}/validate`, { auth: true, method: 'PATCH' }),
  inspections: () => request('/perception/inspections?limit=100', { auth: true }),
  transportDashboard: () => request('/platform/dashboard/transport', { auth: true }),
  officialRoutes: () => request('/routing/official-routes'),
  createOfficialRoute: body => request('/routing/official-routes', { auth: true, method: 'POST', body }),
  vehicles: () => request('/platform/vehicles', { auth: true }),
  createVehicle: body => request('/platform/vehicles', { auth: true, method: 'POST', body }),
  assignments: () => request('/routing/assignments', { auth: true }),
  assignRoute: body => request('/routing/assignments', { auth: true, method: 'POST', body }),
  // M2 risk prediction
  governorateForecasts: () => request('/prediction/governorates'),
  riskModel: () => request('/prediction/model'),
};

export function openRealtime(onEvent, onStatus) {
  const es = new EventSource(`${API}/realtime/stream`);
  es.onopen = () => onStatus?.('live');
  es.onerror = () => onStatus?.('reconnecting');
  [
    'road.event.created',
    'road.event.validated',
    'complaint.created',
    'risk.updated',
    'vehicle.position',
    'complaint.status',
    'route.updated',
    'route.assignment',
    'driver.reroute.alert',
  ].forEach(topic => es.addEventListener(topic, event => {
    try {
      onEvent(topic, JSON.parse(event.data));
    } catch {
      onEvent(topic, event.data);
    }
  }));
  return () => es.close();
}
