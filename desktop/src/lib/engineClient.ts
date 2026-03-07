/**
 * 核心引擎通信客户端（桌面应用版）
 *
 * 与 Python FastAPI 后端通过 HTTP + WebSocket 通信。
 * 通过 Vite proxy 转发，前端直接用相对路径。
 */

/** 引擎健康检查响应 */
export interface HealthResponse {
  status: string;
  version: string;
  sandbox_count: number;
  browser_ready: boolean;
}

/** 测试报告响应 */
export interface TestReportResponse {
  test_name: string;
  url: string;
  total_steps: number;
  passed_steps: number;
  failed_steps: number;
  bug_count: number;
  pass_rate: number;
  duration_seconds: number;
  report_markdown: string;
  repair_summary: string | null;
  fixed_bug_count: number | null;
  credits_used: number | null;
  estimated_cost: number | null;
}

/** WebSocket 消息 */
export interface WsMessage {
  type: 'step_start' | 'step_done' | 'bug_found' | 'repair_start' | 'repair_done' | 'test_done' | 'error' | 'log' | 'screenshot' | 'state_change' | 'terminal_log';
  data: Record<string, unknown>;
}

/** 测试状态（v2.0） */
export interface TestStatus {
  state: 'idle' | 'running' | 'paused' | 'stopped';
  current_step: number;
  total_steps: number;
  description: string;
  step_mode: boolean;
  step_delay: number;
  cancelled: boolean;
}

/** 控制命令响应（v2.0） */
export interface ControlResponse {
  action: string;
  success: boolean;
  state: string;
}

/** 测试启动参数 */
export interface StartTestParams {
  url: string;
  description?: string;
  focus?: string;
  reasoning_effort?: string;
  auto_repair?: boolean;
  project_path?: string;
}

/** 设置项 */
export interface AppSettings {
  engineUrl: string;
  wsUrl: string;
  autoRepair: boolean;
  reasoningEffort: string;
}

const DEFAULT_SETTINGS: AppSettings = {
  engineUrl: 'http://127.0.0.1:8900',
  wsUrl: 'ws://127.0.0.1:8900/ws',
  autoRepair: false,
  reasoningEffort: 'medium',
};

/** 从 localStorage 读取设置 */
export function loadSettings(): AppSettings {
  try {
    const raw = localStorage.getItem('testpilot-settings');
    if (raw) { return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) }; }
  } catch { /* 忽略 */ }
  return { ...DEFAULT_SETTINGS };
}

/** 保存设置到 localStorage */
export function saveSettings(settings: AppSettings): void {
  localStorage.setItem('testpilot-settings', JSON.stringify(settings));
}

/** 获取基础 URL（优先用 proxy 相对路径，否则用设置中的地址） */
function getBaseUrl(): string {
  const settings = loadSettings();
  // 开发模式下 Vite proxy 会转发 /api，直接用相对路径
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return '';
  }
  return settings.engineUrl;
}

function getWsUrl(): string {
  const settings = loadSettings();
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return `ws://${window.location.host}/ws`;
  }
  return settings.wsUrl;
}

// ── HTTP API ──────────────────────────────────────

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const base = getBaseUrl();
  const resp = await fetch(`${base}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${text}`);
  }
  return resp.json() as Promise<T>;
}

export async function checkHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('GET', '/api/v1/health');
}

export async function startTest(params: StartTestParams): Promise<TestReportResponse> {
  return request<TestReportResponse>('POST', '/api/v1/test/run', params);
}

export async function getHistory(url?: string, limit?: number): Promise<unknown[]> {
  const query = new URLSearchParams();
  if (url) { query.set('url', url); }
  if (limit) { query.set('limit', String(limit)); }
  const qs = query.toString();
  return request<unknown[]>('GET', `/api/v1/memory/history${qs ? '?' + qs : ''}`);
}

export async function getStats(): Promise<Record<string, number>> {
  return request<Record<string, number>>('GET', '/api/v1/memory/stats');
}

// ── 测试控制 v2.0 ────────────────────────────────

export async function getTestStatus(): Promise<TestStatus> {
  return request<TestStatus>('GET', '/api/v1/test/status');
}

export async function controlTest(action: string, stepDelay?: number): Promise<ControlResponse> {
  const params = new URLSearchParams({ action });
  if (stepDelay !== undefined) { params.set('step_delay', String(stepDelay)); }
  return request<ControlResponse>('POST', `/api/v1/test/control?${params}`);
}

/** 通过WebSocket发送控制命令（低延迟） */
export function sendWsControl(action: string, data?: Record<string, unknown>): void {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'control', action, data: data || {} }));
  }
}

// ── WebSocket ─────────────────────────────────────

export type ProgressCallback = (msg: WsMessage) => void;

let ws: WebSocket | null = null;
let callbacks: ProgressCallback[] = [];
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

export function connectWs(): void {
  if (ws && ws.readyState === WebSocket.OPEN) { return; }
  try {
    ws = new WebSocket(getWsUrl());
    ws.onopen = () => console.log('[TestPilot AI] WebSocket 已连接');
    ws.onmessage = (e) => {
      try {
        const msg: WsMessage = JSON.parse(e.data);
        callbacks.forEach((cb) => cb(msg));
      } catch { /* 忽略非JSON */ }
    };
    ws.onclose = () => {
      console.log('[TestPilot AI] WebSocket 断开，5秒后重连');
      scheduleReconnect();
    };
    ws.onerror = () => { /* onclose 会处理 */ };
  } catch {
    scheduleReconnect();
  }
}

export function disconnectWs(): void {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  if (ws) { ws.close(); ws = null; }
}

export function onProgress(cb: ProgressCallback): () => void {
  callbacks.push(cb);
  return () => { callbacks = callbacks.filter((c) => c !== cb); };
}

function scheduleReconnect(): void {
  if (reconnectTimer) { return; }
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWs();
  }, 5000);
}

// ── 手机测试 v5.0 ─────────────────────────────────

/** 手机设备信息 */
export interface MobileDevice {
  serial: string;
  status: string;
  model?: string;
  device?: string;
  transport_id?: string;
}

/** 手机会话信息 */
export interface MobileSession {
  session_id: string;
  device: Record<string, unknown>;
  message: string;
}

/** 手机会话创建参数 */
export interface CreateSessionParams {
  device_name?: string;
  app_package?: string;
  app_activity?: string;
  app_path?: string;
}

/** 手机截图响应 */
export interface MobileScreenshotResponse {
  image_base64: string;
  path: string;
}

/** 手机AI分析响应 */
export interface MobileAnalyzeResponse {
  analysis: string;
  screenshot_base64: string;
}

/** 列出已连接的手机设备 */
export async function getMobileDevices(): Promise<{ devices: MobileDevice[]; count: number; error?: string }> {
  return request('GET', '/api/v1/mobile/devices');
}

/** 检查Appium Server状态 */
export async function getAppiumStatus(): Promise<{ running: boolean; message: string }> {
  return request('GET', '/api/v1/mobile/appium/status');
}

/** 创建手机测试会话 */
export async function createMobileSession(params: CreateSessionParams): Promise<MobileSession> {
  return request('POST', '/api/v1/mobile/session/create', params);
}

/** 关闭手机测试会话 */
export async function closeMobileSession(sessionId: string): Promise<{ message: string }> {
  return request('DELETE', `/api/v1/mobile/session/${sessionId}`);
}

/** 手机点击 */
export async function mobileTap(sessionId: string, selector: string): Promise<{ ok: boolean }> {
  return request('POST', `/api/v1/mobile/session/${sessionId}/tap`, { selector });
}

/** 手机输入 */
export async function mobileInput(sessionId: string, selector: string, text: string): Promise<{ ok: boolean }> {
  return request('POST', `/api/v1/mobile/session/${sessionId}/input`, { selector, text });
}

/** 手机滑动 */
export async function mobileSwipe(
  sessionId: string, startX: number, startY: number, endX: number, endY: number,
): Promise<{ ok: boolean }> {
  return request('POST', `/api/v1/mobile/session/${sessionId}/swipe`, {
    start_x: startX, start_y: startY, end_x: endX, end_y: endY,
  });
}

/** 手机截图 */
export async function mobileScreenshot(sessionId: string, name?: string): Promise<MobileScreenshotResponse> {
  const qs = name ? `?name=${encodeURIComponent(name)}` : '';
  return request('GET', `/api/v1/mobile/session/${sessionId}/screenshot${qs}`);
}

/** 获取手机UI层级XML */
export async function mobilePageSource(sessionId: string): Promise<{ source: string }> {
  return request('GET', `/api/v1/mobile/session/${sessionId}/source`);
}

/** 手机导航（打开URL或Activity） */
export async function mobileNavigate(sessionId: string, url: string): Promise<{ ok: boolean }> {
  return request('POST', `/api/v1/mobile/session/${sessionId}/navigate`, { url });
}

/** 手机返回键 */
export async function mobileBack(sessionId: string): Promise<{ ok: boolean }> {
  return request('POST', `/api/v1/mobile/session/${sessionId}/back`);
}

/** 手机截图+AI分析 */
export async function mobileAnalyze(
  sessionId: string, context?: string, expected?: string,
): Promise<MobileAnalyzeResponse> {
  return request('POST', `/api/v1/mobile/session/${sessionId}/analyze`, { context, expected });
}

// ── 报告分析 v5.2 ─────────────────────────────────

/** 通过率趋势数据 */
export interface TrendData {
  labels: string[];
  pass_rates: number[];
  total_steps: number[];
  bug_counts: number[];
  durations: number[];
  test_names: string[];
  count: number;
}

/** Bug热力图数据 */
export interface HeatmapData {
  by_page: { url: string; count: number }[];
  by_category: { category: string; count: number }[];
  by_severity: Record<string, number>;
  by_location: { location: string; count: number }[];
  total_bugs: number;
}

/** 截图时间线数据 */
export interface TimelineData {
  test_name: string;
  url: string;
  pass_rate: number;
  created_at: string;
  steps: { step: number; action: string; status: string; description: string; error: string | null }[];
  error?: string;
}

/** 报告对比数据 */
export interface CompareData {
  summary: Record<string, unknown>;
  new_bugs: Record<string, unknown>[];
  fixed_bugs: Record<string, unknown>[];
  persistent_bugs: Record<string, unknown>[];
  improved: boolean;
  error?: string;
}

/** 获取通过率趋势 */
export async function getPassRateTrend(url?: string, limit?: number): Promise<TrendData> {
  const query = new URLSearchParams();
  if (url) { query.set('url', url); }
  if (limit) { query.set('limit', String(limit)); }
  const qs = query.toString();
  return request<TrendData>('GET', `/api/v1/analytics/trend${qs ? '?' + qs : ''}`);
}

/** 获取截图时间线 */
export async function getScreenshotTimeline(testId: number): Promise<TimelineData> {
  return request<TimelineData>('GET', `/api/v1/analytics/timeline/${testId}`);
}

/** 获取Bug热力图 */
export async function getBugHeatmap(url?: string, limit?: number): Promise<HeatmapData> {
  const query = new URLSearchParams();
  if (url) { query.set('url', url); }
  if (limit) { query.set('limit', String(limit)); }
  const qs = query.toString();
  return request<HeatmapData>('GET', `/api/v1/analytics/heatmap${qs ? '?' + qs : ''}`);
}

/** 对比两次报告 */
export async function compareReports(idA: number, idB: number): Promise<CompareData> {
  return request<CompareData>('GET', `/api/v1/analytics/compare?id_a=${idA}&id_b=${idB}`);
}

/** 获取HTML报告导出URL */
export function getExportHtmlUrl(testId: number): string {
  const base = getBaseUrl();
  return `${base}/api/v1/analytics/export/${testId}`;
}

// ── 用户系统 v6.0 ─────────────────────────────────

export interface UserInfo {
  id: number; email: string; username: string; role: string;
  is_active: boolean; max_tests_per_day: number; max_projects: number;
  max_ai_calls_per_day: number; storage_limit_mb: number; created_at: string;
}

export interface AuthResponse { access_token: string; token_type: string; user: UserInfo; }

export interface ProjectInfo {
  id: number; name: string; description: string; base_url: string;
  owner_id: number; test_count: number; last_pass_rate: number;
  total_bugs_found: number; created_at: string; updated_at: string;
}

export interface UsageSummary {
  period_days: number; total_tests: number; total_ai_calls: number; total_screenshots: number;
  daily_records: { date: string; tests: number; ai_calls: number; screenshots: number }[];
  quotas: Record<string, number>;
}

const TOKEN_KEY = 'testpilot-token';
export function getToken(): string | null { return localStorage.getItem(TOKEN_KEY); }
export function setToken(token: string): void { localStorage.setItem(TOKEN_KEY, token); }
export function clearToken(): void { localStorage.removeItem(TOKEN_KEY); }

async function authRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  const base = getBaseUrl();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) { headers['Authorization'] = `Bearer ${token}`; }
  const resp = await fetch(`${base}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (!resp.ok) { throw new Error(`HTTP ${resp.status}: ${await resp.text()}`); }
  return resp.json() as Promise<T>;
}

export async function authRegister(email: string, username: string, password: string): Promise<AuthResponse> {
  const res = await request<AuthResponse>('POST', '/api/v1/auth/register', { email, username, password });
  setToken(res.access_token); return res;
}

export async function authLogin(email: string, password: string): Promise<AuthResponse> {
  const res = await request<AuthResponse>('POST', '/api/v1/auth/login', { email, password });
  setToken(res.access_token); return res;
}

export function authLogout(): void { clearToken(); }

export async function getMe(): Promise<UserInfo> { return authRequest<UserInfo>('GET', '/api/v1/auth/me'); }

export async function createProject(name: string, description?: string, baseUrl?: string): Promise<ProjectInfo> {
  return authRequest<ProjectInfo>('POST', '/api/v1/projects', { name, description: description || '', base_url: baseUrl || '' });
}

export async function listProjects(): Promise<ProjectInfo[]> { return authRequest<ProjectInfo[]>('GET', '/api/v1/projects'); }

export async function getProject(id: number): Promise<ProjectInfo> { return authRequest<ProjectInfo>('GET', `/api/v1/projects/${id}`); }

export async function updateProject(id: number, data: { name?: string; description?: string; base_url?: string }): Promise<ProjectInfo> {
  return authRequest<ProjectInfo>('PUT', `/api/v1/projects/${id}`, data);
}

export async function deleteProject(id: number): Promise<{ message: string }> {
  return authRequest<{ message: string }>('DELETE', `/api/v1/projects/${id}`);
}

export async function getUsage(days?: number): Promise<UsageSummary> {
  const qs = days ? `?days=${days}` : '';
  return authRequest<UsageSummary>('GET', `/api/v1/usage${qs}`);
}

export async function checkQuota(action?: string): Promise<{ allowed: boolean; used: number; limit: number; remaining: number }> {
  const qs = action ? `?action=${action}` : '';
  return authRequest<{ allowed: boolean; used: number; limit: number; remaining: number }>('GET', `/api/v1/usage/check${qs}`);
}
