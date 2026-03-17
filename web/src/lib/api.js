const BASE = '/api/v1';

function getHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  const token = localStorage.getItem('token');
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

async function request(method, path, body) {
  const opts = { method, headers: getHeaders() };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE}${path}`, opts);
  if (res.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login';
    return null;
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '请求失败');
  return data;
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body),
  put: (path, body) => request('PUT', path, body),
  del: (path) => request('DELETE', path),
};

export const auth = {
  login: (emailOrUsername, password) => api.post('/auth/login', { email_or_username: emailOrUsername, password }),
  register: (email, username, password) => api.post('/auth/register', { email, username, password }),
};

export const community = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return api.get(`/community/experiences${qs ? '?' + qs : ''}`);
  },
  get: (id) => api.get(`/community/experiences/${id}`),
  create: (data) => api.post('/community/experiences', data),
  update: (id, data) => api.put(`/community/experiences/${id}`, data),
  del: (id) => api.del(`/community/experiences/${id}`),
  trending: (limit = 10) => api.get(`/community/experiences/trending?limit=${limit}`),
  suggest: (platform, errorType) => api.get(`/community/experiences/suggest?platform=${platform}&error_type=${errorType}`),
  vote: (id, voteType) => api.post(`/community/experiences/${id}/vote`, { vote_type: voteType }),
  stats: () => api.get('/community/stats'),
  leaderboard: (limit = 20) => api.get(`/community/leaderboard?limit=${limit}`),
};

export const profile = {
  get: (userId) => api.get(`/community/profile/${userId}`),
  update: (data) => api.put('/community/profile', data),
  contributions: (userId) => api.get(`/community/profile/${userId}/contributions`),
  stats: (userId) => api.get(`/community/profile/${userId}/stats`),
};

export const credits = {
  balance: () => api.get('/community/credits'),
  transactions: (page = 1) => api.get(`/community/credits/transactions?page=${page}`),
};

export const billing = {
  plans: () => api.get('/billing/plans'),
  myPlan: () => api.get('/billing/my-plan'),
};
