/**
 * 核心引擎通信客户端
 *
 * 负责与 Python FastAPI 后端通过 HTTP + WebSocket 通信：
 * - HTTP: 调用 REST API（健康检查、启动测试、查看报告等）
 * - WebSocket: 接收实时测试进度推送
 */

import * as vscode from "vscode";
import WebSocket from "ws";

/** 引擎健康检查响应 */
export interface HealthResponse {
  status: string;
  version: string;
  sandbox_count: number;
  browser_ready: boolean;
}

/** 单步执行详情 */
export interface StepDetail {
  step: number;
  action: string;
  description: string;
  status: string;
  duration_seconds: number;
  error_message: string;
  screenshot_path: string | null;
}

/** Bug 详情（含日志切片） */
export interface BugDetail {
  severity: string;
  title: string;
  description: string;
  category: string;
  location: string;
  step_number: number | null;
  screenshot_path: string | null;
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
  steps: StepDetail[];
  bugs: BugDetail[];
  repair_summary: string | null;
  fixed_bug_count: number | null;
  stopped?: boolean;
}

/** WebSocket 消息类型 */
export interface WsMessage {
  type: "step_start" | "step_done" | "bug_found" | "repair_start" | "repair_done" | "test_done" | "error" | "log" | "screenshot" | "state_change" | "terminal_log";
  data: Record<string, unknown>;
}

/** 测试状态（v2.0） */
export interface TestStatus {
  state: "idle" | "running" | "paused" | "stopped";
  current_step: number;
  total_steps: number;
  description: string;
  step_mode: boolean;
  step_delay: number;
  cancelled: boolean;
}

/** 测试进度回调 */
export type ProgressCallback = (msg: WsMessage) => void;

export class EngineClient {
  private _ws: WebSocket | null = null;
  private _progressCallbacks: ProgressCallback[] = [];
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  /** 获取配置的引擎 HTTP 地址 */
  private get httpUrl(): string {
    return vscode.workspace
      .getConfiguration("testpilotAI")
      .get<string>("engineUrl", "http://127.0.0.1:8900");
  }

  /** 获取配置的 WebSocket 地址 */
  private get wsUrl(): string {
    return vscode.workspace
      .getConfiguration("testpilotAI")
      .get<string>("wsUrl", "ws://127.0.0.1:8900/ws");
  }

  // ── HTTP API ─────────────────────────────────────

  /** 健康检查 */
  async checkHealth(): Promise<HealthResponse> {
    return this._get<HealthResponse>("/api/v1/health");
  }

  /** 启动测试 */
  async startTest(params: {
    url: string;
    description?: string;
    focus?: string;
    reasoning_effort?: string;
    auto_repair?: boolean;
    project_path?: string;
  }): Promise<TestReportResponse> {
    return this._post<TestReportResponse>("/api/v1/test/run", params);
  }

  /** 查询测试历史 */
  async getHistory(url?: string, limit?: number): Promise<unknown[]> {
    const query = new URLSearchParams();
    if (url) { query.set("url", url); }
    if (limit) { query.set("limit", String(limit)); }
    const qs = query.toString();
    return this._get<unknown[]>(`/api/v1/memory/history${qs ? "?" + qs : ""}`);
  }

  /** Web 蓝本模式测试 */
  async startBlueprintTest(params: {
    blueprint_path: string;
    base_url?: string;
    cloud_token?: string;
  }): Promise<TestReportResponse> {
    return this._post<TestReportResponse>("/api/v1/test/blueprint", params);
  }

  /** 手机蓝本测试（Android/iOS） */
  async startMobileBlueprintTest(params: {
    blueprint_path: string;
    base_url?: string;
    mobile_session_id: string;
  }): Promise<TestReportResponse> {
    return this._post<TestReportResponse>("/api/v1/test/mobile-blueprint", params);
  }

  /** 小程序蓝本测试 */
  async startMiniprogramBlueprintTest(params: {
    blueprint_path: string;
    base_url?: string;
    project_path?: string;
  }): Promise<TestReportResponse> {
    return this._post<TestReportResponse>("/api/v1/test/miniprogram-blueprint", params);
  }

  /** 桌面蓝本测试 */
  async startDesktopBlueprintTest(params: {
    blueprint_path: string;
    base_url?: string;
    window_title?: string;
  }): Promise<TestReportResponse> {
    return this._post<TestReportResponse>("/api/v1/test/desktop-blueprint", params);
  }

  /** 蓝本自动生成（v10.1） */
  async generateBlueprint(params: {
    url: string;
    app_name?: string;
    description?: string;
    output_path?: string;
  }): Promise<{
    success: boolean;
    app_name: string;
    base_url: string;
    total_scenarios: number;
    total_steps: number;
    blueprint_json: Record<string, unknown>;
    saved_path: string;
  }> {
    return this._post("/api/v1/blueprint/generate", params);
  }

  /** 获取预览应用列表 */
  async getPreviewApps(): Promise<Array<{ name: string; preview_url: string }>> {
    return this._get<Array<{ name: string; preview_url: string }>>("/api/v1/preview/apps");
  }

  /** 查询测试状态（v2.0） */
  async getTestStatus(): Promise<TestStatus> {
    return this._get<TestStatus>("/api/v1/test/status");
  }

  /** 列出已连接移动设备 */
  async listMobileDevices(): Promise<{ devices: Array<Record<string, unknown>>; count: number; error?: string }> {
    return this._get<{ devices: Array<Record<string, unknown>>; count: number; error?: string }>("/api/v1/mobile/devices");
  }

  /** 列出活动移动会话 */
  async listMobileSessions(): Promise<{ sessions: Array<Record<string, unknown>>; count: number }> {
    return this._get<{ sessions: Array<Record<string, unknown>>; count: number }>("/api/v1/mobile/sessions");
  }

  /** 创建移动会话 */
  async createMobileSession(params: {
    device_name?: string;
    app_package?: string;
    app_activity?: string;
    app_path?: string;
    permissions?: string[];
  } = {}): Promise<{ session_id: string; message: string; device?: Record<string, unknown> }> {
    return this._post<{ session_id: string; message: string; device?: Record<string, unknown> }>("/api/v1/mobile/session/create", params);
  }

  /** 手机测试环境一键检测（设备+Appium） */
  async mobilePrecheck(): Promise<{
    ok: boolean;
    device_ok: boolean;
    appium_ok: boolean;
    message: string;
    device_message: string;
    appium_message: string;
  }> {
    return this._get("/api/v1/mobile/precheck");
  }

  /** 检查小程序开发者工具状态 */
  async getMiniprogramDevtoolsStatus(): Promise<{ found: boolean; path?: string; message?: string }> {
    return this._get<{ found: boolean; path?: string; message?: string }>("/api/v1/miniprogram/devtools/status");
  }

  /** 测试控制：暂停/继续/停止（v2.0） */
  async controlTest(action: string): Promise<{ action: string; success: boolean; state: string }> {
    return this._post<{ action: string; success: boolean; state: string }>(
      `/api/v1/test/control?action=${action}`, {}
    );
  }

  /** 记忆系统统计 */
  async getStats(): Promise<Record<string, number>> {
    return this._get<Record<string, number>>("/api/v1/memory/stats");
  }

  // ── WebSocket ────────────────────────────────────

  /** 连接 WebSocket，接收实时进度 */
  connectWs(): void {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      return;
    }
    // 清理残留连接
    if (this._ws) {
      try { this._ws.close(); } catch { /* ignore */ }
      this._ws = null;
    }

    try {
      this._ws = new WebSocket(this.wsUrl);

      this._ws.on("open", () => {
        console.log("[TestPilot AI] WebSocket 已连接");
      });

      this._ws.on("message", (raw: WebSocket.Data) => {
        try {
          const msg: WsMessage = JSON.parse(raw.toString());
          for (const cb of this._progressCallbacks) {
            cb(msg);
          }
        } catch {
          // 忽略非 JSON 消息
        }
      });

      this._ws.on("close", () => {
        console.log("[TestPilot AI] WebSocket 断开，5秒后重连");
        this._ws = null;
        this._scheduleReconnect();
      });

      this._ws.on("error", (err) => {
        console.error("[TestPilot AI] WebSocket 错误:", err.message);
        // error后通常会触发close，但保险起见也清理
      });
    } catch {
      this._ws = null;
      this._scheduleReconnect();
    }
  }

  /** 确保 WebSocket 已连接（测试开始前调用） */
  ensureWsConnected(): void {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      return;
    }
    // 取消定时重连，立即重连
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    this.connectWs();
  }

  /** 断开 WebSocket */
  disconnectWs(): void {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
  }

  /** 注册进度回调 */
  onProgress(cb: ProgressCallback): vscode.Disposable {
    this._progressCallbacks.push(cb);
    return new vscode.Disposable(() => {
      this._progressCallbacks = this._progressCallbacks.filter((c) => c !== cb);
    });
  }

  // ── 内部方法 ─────────────────────────────────────

  private _scheduleReconnect(): void {
    if (this._reconnectTimer) { return; }
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      this.connectWs();
    }, 5000);
  }

  private async _get<T>(path: string): Promise<T> {
    const url = `${this.httpUrl}${path}`;
    const resp = await fetch(url, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`HTTP ${resp.status}: ${text}`);
    }
    return resp.json() as Promise<T>;
  }

  private async _post<T>(path: string, body: unknown): Promise<T> {
    const url = `${this.httpUrl}${path}`;
    const payload = JSON.stringify(body);

    // 使用 Node.js http 模块替代 fetch，避免 undici 的 bodyTimeout (300s)
    // 导致长时间测试（6分钟+）中途 "fetch failed"
    return new Promise<T>((resolve, reject) => {
      const parsed = new URL(url);
      const http = require("http");
      const req = http.request(
        {
          hostname: parsed.hostname,
          port: parsed.port,
          path: parsed.pathname + parsed.search,
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(payload),
          },
          timeout: 900_000, // 15分钟连接超时
        },
        (res: any) => {
          const chunks: Buffer[] = [];
          res.on("data", (chunk: Buffer) => chunks.push(chunk));
          res.on("end", () => {
            const text = Buffer.concat(chunks).toString("utf-8");
            if (res.statusCode && res.statusCode >= 400) {
              reject(new Error(`HTTP ${res.statusCode}: ${text}`));
            } else {
              try {
                resolve(JSON.parse(text) as T);
              } catch {
                reject(new Error(`JSON解析失败: ${text.substring(0, 200)}`));
              }
            }
          });
        },
      );
      req.on("timeout", () => {
        req.destroy();
        reject(new Error("请求超时（15分钟）"));
      });
      req.on("error", (err: Error) => reject(err));
      // 禁用 socket 空闲超时，防止长测试期间连接被断开
      req.on("socket", (socket: any) => {
        socket.setTimeout(0);
        socket.setKeepAlive(true, 30_000);
      });
      req.write(payload);
      req.end();
    });
  }

  // ── 云端认证 API ─────────────────────────────────

  /** 云端 API 基础地址 */
  private get cloudUrl(): string {
    return vscode.workspace
      .getConfiguration("testpilotAI")
      .get<string>("cloudApiUrl", "https://testpilot.xinzaoai.com");
  }

  /** 云端 POST（走 HTTPS，短超时） */
  private async _cloudPost<T>(path: string, body: unknown, token?: string): Promise<T> {
    const url = `${this.cloudUrl}${path}`;
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const resp = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const text = await resp.text();
      let msg = `HTTP ${resp.status}`;
      try { msg = JSON.parse(text).detail || msg; } catch { /* ignore */ }
      throw new Error(msg);
    }
    return resp.json() as Promise<T>;
  }

  /** 云端 GET */
  private async _cloudGet<T>(path: string, token: string): Promise<T> {
    const url = `${this.cloudUrl}${path}`;
    const resp = await fetch(url, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
      },
    });
    if (!resp.ok) {
      const text = await resp.text();
      let msg = `HTTP ${resp.status}`;
      try { msg = JSON.parse(text).detail || msg; } catch { /* ignore */ }
      throw new Error(msg);
    }
    return resp.json() as Promise<T>;
  }

  /** 云端登录 */
  async cloudLogin(emailOrUsername: string, password: string): Promise<{
    access_token: string;
    token_type: string;
    user: { id: number; email: string; username: string; role: string };
  }> {
    return this._cloudPost("/auth/login", {
      email_or_username: emailOrUsername,
      password,
    });
  }

  /** 云端注册 */
  async cloudRegister(email: string, username: string, password: string): Promise<{
    access_token: string;
    token_type: string;
    user: { id: number; email: string; username: string; role: string };
  }> {
    return this._cloudPost("/auth/register", { email, username, password });
  }

  /** 获取当前用户信息 */
  async cloudGetMe(token: string): Promise<{
    id: number; email: string; username: string; role: string;
    credits: number; plan: string;
  }> {
    return this._cloudGet("/auth/me", token);
  }

  /** 用 Refresh Token 换取新的 Access Token + 新 Refresh Token */
  async cloudRefreshToken(refreshToken: string): Promise<{
    access_token: string;
    refresh_token: string;
    token_type: string;
    user: { id: number; email: string; username: string; role: string };
  }> {
    return this._cloudPost("/auth/refresh", { refresh_token: refreshToken });
  }

  /** 发送邮箱注册验证码 */
  async cloudSendEmailCode(email: string): Promise<{ ok: boolean; message: string; dev_code?: string }> {
    return this._cloudPost("/auth/send-code", { email });
  }

  // ── 云端经验库 API ───────────────────────────────

  /** 直接分享经验到社区（Bug 自动上传） */
  async cloudShareDirect(token: string, data: {
    title: string;
    platform: string;
    framework: string;
    error_type: string;
    problem_desc: string;
    solution_desc: string;
    root_cause?: string;
    code_snippet?: string;
    tags?: string[];
    difficulty?: string;
    fix_pattern?: string;
  }): Promise<{
    ok: boolean;
    experience: Record<string, unknown>;
    score_breakdown: Record<string, unknown>;
  }> {
    return this._cloudPost("/api/v1/community/share/direct", data, token);
  }

  /** 根据错误类型获取经验建议 */
  async cloudGetSuggestions(token: string, platform: string, errorType: string): Promise<{
    items: Array<{ id: number; title: string; solution_desc: string; upvote_count: number }>;
  }> {
    const params = new URLSearchParams({ platform, error_type: errorType, limit: "5" });
    return this._cloudGet(`/api/v1/community/experiences/suggest?${params}`, token);
  }

  /** 查询当前用户积分余额 */
  async cloudGetCreditsBalance(token: string): Promise<{
    balance: number; credits_used: number; plan: string;
  }> {
    return this._cloudGet("/api/v1/credits/balance", token);
  }

  /** 查询积分变动历史 */
  async cloudGetCreditsHistory(token: string, limit = 20): Promise<{
    history: Array<{ id: number; amount: number; reason: string; detail: string; balance_after: number; created_at: string }>;
    total: number;
  }> {
    return this._cloudGet(`/api/v1/credits/history?limit=${limit}`, token);
  }
}
