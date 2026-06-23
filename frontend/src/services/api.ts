import axios from 'axios';

const API_BASE = '/api';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

// Attach token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Redirect to login on 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// ── Auth ───────────────────────────────────────────────────────────
export const authApi = {
  login: (username: string, password: string) =>
    api.post('/auth/login', new URLSearchParams({ username, password }), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),
  register: (data: { username: string; email: string; password: string }) =>
    api.post('/auth/register', data),
  me: () => api.get('/auth/me'),
};

// ── Devices ────────────────────────────────────────────────────────
export const deviceApi = {
  list: (params?: { device_type?: string; status?: string; is_active?: boolean }) =>
    api.get('/devices', { params }),
  get: (id: number) => api.get(`/devices/${id}`),
  create: (data: Record<string, unknown>) => api.post('/devices', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/devices/${id}`, data),
  delete: (id: number) => api.delete(`/devices/${id}`),
};

// ── Metrics ────────────────────────────────────────────────────────
export const metricApi = {
  get: (deviceId: number, params?: { metric_name?: string; hours?: number }) =>
    api.get(`/metrics/${deviceId}`, { params }),
  getInterfaces: (deviceId: number, params?: { ifname?: string; hours?: number }) =>
    api.get(`/metrics/${deviceId}/interfaces`, { params }),
};

// ── Alerts ─────────────────────────────────────────────────────────
export const alertApi = {
  list: (params?: { state?: string; severity?: string; device_id?: number; limit?: number }) =>
    api.get('/alerts', { params }),
  acknowledge: (id: number, acknowledged_by: string) =>
    api.post(`/alerts/${id}/acknowledge`, { acknowledged_by }),
  resolve: (id: number) => api.post(`/alerts/${id}/resolve`),
};

// ── Alert Rules ────────────────────────────────────────────────────
export const alertRuleApi = {
  list: () => api.get('/alert-rules'),
  create: (data: Record<string, unknown>) => api.post('/alert-rules', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/alert-rules/${id}`, data),
  delete: (id: number) => api.delete(`/alert-rules/${id}`),
};

// ── Dashboard ──────────────────────────────────────────────────────
export const dashboardApi = {
  overview: () => api.get('/dashboard/overview'),
};

// ── Agent ──────────────────────────────────────────────────────────
export const agentApi = {
  register: (data: { name: string; location?: string; description?: string }) =>
    api.post('/agent/register', data),
};

export default api;
