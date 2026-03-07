/**
 * 侧边栏 Webview Provider
 *
 * 提供 TestPilot AI 的侧边栏面板，显示：
 * - 引擎连接状态
 * - 测试配置表单（URL、描述、重点、自动修复开关）
 * - 实时测试进度日志
 * - 测试结果概览
 * - Bug 列表与修复状态
 */

import * as vscode from "vscode";
import { EngineClient, WsMessage, TestReportResponse, StepDetail, BugDetail } from "./engineClient";

export class SidebarProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "testpilot-ai.panel";

  private _view?: vscode.WebviewView;
  private _client: EngineClient;

  constructor(
    private readonly _extensionUri: vscode.Uri,
    client: EngineClient,
  ) {
    this._client = client;
  }

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken,
  ): void {
    this._view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this._extensionUri],
    };

    webviewView.webview.html = this._getHtml(webviewView.webview);

    // 处理前端发来的消息
    webviewView.webview.onDidReceiveMessage(async (msg) => {
      switch (msg.command) {
        case "checkEngine":
          await this._handleCheckEngine();
          break;
        case "startTest":
          await this._handleStartTest(msg);
          break;
        case "blueprintTest":
          await this._handleBlueprintTest(msg);
          break;
        case "blueprintBatchTest":
          await this._handleBlueprintBatchTest(msg);
          break;
        case "controlTest":
          await this._handleControlTest(msg.action);
          break;
        case "getHistory":
          await this._handleGetHistory();
          break;
        case "copyBugs":
          await this._handleCopyBugs(msg.report);
          break;
        case "launchEngine":
          vscode.commands.executeCommand("testpilot-ai.launchEngine");
          break;
        case "stopEngine":
          vscode.commands.executeCommand("testpilot-ai.stopEngine");
          break;
        case "scanBlueprints":
          await this._handleScanBlueprints();
          break;
        case "browseBlueprint":
          await this._handleBrowseBlueprint();
          break;
        case "copyBlueprintPrompt":
          await this._handleCopyBlueprintPrompt();
          break;
      }
    });

    // 监听 WebSocket 进度，转发给 Webview
    this._client.onProgress((wsMsg: WsMessage) => {
      this._postMessage({ command: "progress", data: wsMsg });
    });
  }

  /** 向 Webview 发送消息 */
  public postMessage(msg: unknown): void {
    this._postMessage(msg);
  }

  private _postMessage(msg: unknown): void {
    if (this._view) {
      this._view.webview.postMessage(msg);
    }
  }

  private async _handleCheckEngine(): Promise<void> {
    try {
      const health = await this._client.checkHealth();
      this._postMessage({
        command: "engineStatus",
        data: { connected: true, ...health },
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      this._postMessage({
        command: "engineStatus",
        data: { connected: false, error: message },
      });
    }
  }

  private async _handleStartTest(msg: {
    url: string;
    description: string;
    focus: string;
    autoRepair: boolean;
    projectPath: string;
  }): Promise<void> {
    try {
      this._postMessage({ command: "testStarted" });

      const config = vscode.workspace.getConfiguration("testpilotAI");
      const reasoningEffort = config.get<string>("reasoningEffort", "medium");

      const report: TestReportResponse = await this._client.startTest({
        url: msg.url,
        description: msg.description || "",
        focus: msg.focus || "核心功能",
        reasoning_effort: reasoningEffort,
        auto_repair: msg.autoRepair,
        project_path: msg.projectPath || "",
      });

      this._postMessage({ command: "testResult", data: report });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      this._postMessage({ command: "testError", data: { error: message } });
    }
  }

  private async _handleBlueprintTest(msg: {
    blueprint_path: string;
    base_url?: string;
  }): Promise<void> {
    try {
      this._postMessage({ command: "testStarted" });

      const report: TestReportResponse = await this._client.startBlueprintTest({
        blueprint_path: msg.blueprint_path,
        base_url: msg.base_url || undefined,
      });

      this._postMessage({ command: "testResult", data: report });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      this._postMessage({ command: "testError", data: { error: message } });
    }
  }

  private async _handleBlueprintBatchTest(msg: {
    blueprint_paths: string[];
    base_url?: string;
  }): Promise<void> {
    try {
      this._postMessage({ command: "testStarted" });

      // 依次执行每个蓝本，汇总结果
      const results: TestReportResponse[] = [];
      for (const bp of msg.blueprint_paths) {
        try {
          const report = await this._client.startBlueprintTest({
            blueprint_path: bp,
            base_url: msg.base_url || undefined,
          });
          results.push(report);
        } catch (err: unknown) {
          const errMsg = err instanceof Error ? err.message : String(err);
          results.push({
            test_name: bp.split(/[/\\]/).pop() || bp,
            url: "",
            total_steps: 0,
            passed_steps: 0,
            failed_steps: 0,
            bug_count: 0,
            pass_rate: 0,
            duration_seconds: 0,
            report_markdown: `❌ 执行失败: ${errMsg}`,
          } as TestReportResponse);
        }
      }

      // 汇总报告
      const totalSteps = results.reduce((n, r) => n + (r.total_steps || 0), 0);
      const passedSteps = results.reduce((n, r) => n + (r.passed_steps || 0), 0);
      const failedSteps = results.reduce((n, r) => n + (r.failed_steps || 0), 0);
      const totalBugs = results.reduce((n, r) => n + (r.bug_count || 0), 0);
      const totalDuration = results.reduce((n, r) => n + (r.duration_seconds || 0), 0);
      const passRate = totalSteps > 0 ? (passedSteps / totalSteps * 100) : 0;

      let md = `# 批量蓝本测试汇总\n\n`;
      md += `- 蓝本数: ${results.length}\n`;
      md += `- 总步骤: ${totalSteps}（通过 ${passedSteps} / 失败 ${failedSteps}）\n`;
      md += `- 总Bug数: ${totalBugs}\n`;
      md += `- 总通过率: ${passRate.toFixed(0)}%\n`;
      md += `- 总耗时: ${totalDuration.toFixed(1)}秒\n\n`;
      results.forEach((r, i) => {
        const icon = (r.bug_count || 0) === 0 && (r.total_steps || 0) > 0 ? "✅" : "❌";
        md += `## ${i + 1}. ${icon} ${r.test_name}\n`;
        md += `通过率: ${(r.pass_rate || 0).toFixed(0)}% | Bug: ${r.bug_count || 0}\n\n`;
      });

      // 用最后一个报告的格式返回汇总
      const summary: TestReportResponse = {
        test_name: `批量测试（${results.length}个蓝本）`,
        url: "",
        total_steps: totalSteps,
        passed_steps: passedSteps,
        failed_steps: failedSteps,
        bug_count: totalBugs,
        pass_rate: passRate,
        duration_seconds: totalDuration,
        report_markdown: md,
      } as TestReportResponse;

      this._postMessage({ command: "testResult", data: summary });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      this._postMessage({ command: "testError", data: { error: message } });
    }
  }

  private async _handleControlTest(action: string): Promise<void> {
    try {
      const result = await this._client.controlTest(action);
      this._postMessage({ command: "controlResult", data: result });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      this._postMessage({ command: "controlError", data: { error: message } });
    }
  }

  private async _handleGetHistory(): Promise<void> {
    try {
      const history = await this._client.getHistory(undefined, 10);
      this._postMessage({ command: "history", data: history });
    } catch {
      this._postMessage({ command: "history", data: [] });
    }
  }

  private _formatBugText(report: Record<string, unknown>): string {
    const bugCount = report.bug_count as number || 0;
    const lines: string[] = [
      `TestPilot AI 发现 ${bugCount} 个Bug，请修复：`,
      `测试: ${report.test_name} | URL: ${report.url} | 通过率: ${(report.pass_rate as number || 0).toFixed(0)}%`,
      "",
    ];
    const bugs = (report.bugs as Array<Record<string, unknown>>) || [];
    if (bugs.length > 0) {
      bugs.forEach((bug, i) => {
        const step = bug.step_number ? ` (步骤#${bug.step_number})` : "";
        lines.push(`${i + 1}. [${(bug.severity as string || "medium").toUpperCase()}] ${bug.title}${step}`);
        if (bug.description) {
          lines.push(`   ${(bug.description as string).split("\n")[0].substring(0, 150)}`);
        }
      });
    } else {
      lines.push((report.report_markdown as string || "").substring(0, 1000));
    }
    lines.push("", "请根据以上Bug修复代码，修复后调用 run_blueprint_test 重新测试验证。");
    return lines.join("\n");
  }

  private async _handleCopyBugs(report: Record<string, unknown>): Promise<void> {
    const bugText = this._formatBugText(report);

    // 尝试直接发送到 Cascade/Copilot 聊天
    try {
      // Windsurf Cascade
      await vscode.commands.executeCommand("windsurf.newCascade", bugText);
      vscode.window.showInformationMessage("Bug报告已发送给AI，等待修复");
      return;
    } catch {
      // 不是 Windsurf，尝试其他方式
    }

    try {
      // GitHub Copilot Chat
      await vscode.commands.executeCommand("workbench.action.chat.open", { query: bugText });
      vscode.window.showInformationMessage("Bug报告已发送到聊天面板");
      return;
    } catch {
      // 没有 Copilot Chat
    }

    // 兜底：复制到剪贴板
    await vscode.env.clipboard.writeText(bugText);
    vscode.window.showInformationMessage("Bug摘要已复制到剪贴板，粘贴到聊天窗口让AI修复");
  }

  private async _handleScanBlueprints(): Promise<void> {
    const entries: { path: string; mtime: number; appName: string; description: string; platform: string; scenarioCount: number; stepCount: number }[] = [];
    const folders = vscode.workspace.workspaceFolders;
    if (folders) {
      for (const folder of folders) {
        // 扫描 testpilot.json 和 *.testpilot.json
        const patterns = [
          new vscode.RelativePattern(folder, "**/testpilot.json"),
          new vscode.RelativePattern(folder, "**/*.testpilot.json"),
        ];
        const seen = new Set<string>();
        for (const pattern of patterns) {
          const files = await vscode.workspace.findFiles(pattern, "**/node_modules/**", 50);
          for (const f of files) {
            if (seen.has(f.fsPath)) { continue; }
            seen.add(f.fsPath);
            let mtime = 0;
            let appName = "";
            let description = "";
            let platform = "web";
            let scenarioCount = 0;
            let stepCount = 0;
            try {
              const stat = await vscode.workspace.fs.stat(f);
              mtime = stat.mtime;
              const raw = await vscode.workspace.fs.readFile(f);
              const json = JSON.parse(Buffer.from(raw).toString("utf-8"));
              appName = json.app_name || "";
              description = json.description || "";
              platform = json.platform || "web";
              scenarioCount = (json.pages || []).reduce((n: number, p: any) => n + (p.scenarios || []).length, 0);
              stepCount = (json.pages || []).reduce((n: number, p: any) => n + (p.scenarios || []).reduce((m: number, s: any) => m + (s.steps || []).length, 0), 0);
            } catch { /* ignore parse errors */ }
            entries.push({ path: f.fsPath, mtime, appName, description, platform, scenarioCount, stepCount });
          }
        }
      }
    }
    entries.sort((a, b) => b.mtime - a.mtime);
    this._postMessage({ command: "blueprintList", data: entries });
  }

  private async _handleBrowseBlueprint(): Promise<void> {
    const result = await vscode.window.showOpenDialog({
      canSelectFiles: true,
      canSelectFolders: false,
      canSelectMany: false,
      filters: { "TestPilot 蓝本": ["json"] },
      title: "选择蓝本文件 (testpilot.json)",
    });
    if (result && result.length > 0) {
      this._postMessage({ command: "blueprintSelected", data: result[0].fsPath });
    }
  }

  private async _handleCopyBlueprintPrompt(): Promise<void> {
    const prompt = `请帮我为当前项目生成测试蓝本文件，放在项目的 testpilot/ 文件夹下。

重要：按功能模块拆分成多个蓝本文件，不要创建单一的 testpilot.json！

例如电商项目应拆分为：
- testpilot/auth.testpilot.json（登录/注册/权限）
- testpilot/product.testpilot.json（商品管理CRUD）
- testpilot/order.testpilot.json（订单管理）
- testpilot/cart.testpilot.json（购物车）

要求：
1. 分析源代码中所有可操作 UI 元素（按钮/表单/导航/弹窗）
2. 选择器使用代码中的真实 id（如 #login-btn）或稳定 class，禁止用 div:nth-child(3) 这类脆弱选择器
3. 每个功能页面对应一个场景，覆盖正常流程和异常场景（空表单提交、错误输入）
4. 每个 fill 操作后必须有 assert_text 或 screenshot 验证
5. 每次 navigate 必须有断言验证页面已正确加载
6. 如果应用需要命令行启动（如 npm start、python app.py），必须填写 start_command 字段；纯HTML静态应用留空

每个蓝本文件格式：
{
  "app_name": "模块名称（如：用户认证模块）",
  "description": "蓝本功能说明（50-200字，描述本蓝本覆盖哪些功能和测试范围）",
  "base_url": "http://localhost:端口",
  "version": "1.0",
  "platform": "web",
  "start_command": "npm start 或 python app.py（纯HTML留空）",
  "start_cwd": "./（启动命令的工作目录，默认项目根目录）",
  "pages": [
    {
      "url": "/",
      "title": "页面标题",
      "elements": { "元素描述": "#实际CSS选择器" },
      "scenarios": [
        {
          "name": "功能场景名",
          "steps": [
            {"action": "navigate", "value": "http://localhost:端口"},
            {"action": "fill", "target": "#input-id", "value": "测试值"},
            {"action": "click", "target": "#submit-btn"},
            {"action": "assert_text", "target": "#result", "expected": "预期文本"}
          ]
        }
      ]
    }
  ]
}

支持的 action：navigate / click / fill / select / wait / screenshot / assert_text / assert_visible / hover / scroll

重要提醒：以后修改代码时，主动审视并更新对应模块的蓝本，无需用户提醒！`;
    await vscode.env.clipboard.writeText(prompt);
    vscode.window.showInformationMessage("✅ 提示词已复制！请粘贴到 Cursor / Windsurf，让编程AI读取源码生成蓝本。");
  }

  private _getHtml(webview: vscode.Webview): string {
    const nonce = getNonce();

    return /*html*/ `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy"
    content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}'; img-src data:;">
  <title>TestPilot AI</title>
  <style>
    :root {
      --bg: var(--vscode-sideBar-background);
      --fg: var(--vscode-sideBar-foreground);
      --input-bg: var(--vscode-input-background);
      --input-border: var(--vscode-input-border);
      --input-fg: var(--vscode-input-foreground);
      --btn-bg: var(--vscode-button-background);
      --btn-fg: var(--vscode-button-foreground);
      --btn-hover: var(--vscode-button-hoverBackground);
      --success: #4ec9b0;
      --error: #f44747;
      --warn: #cca700;
      --info: var(--vscode-descriptionForeground);
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: var(--vscode-font-family); font-size: 13px; color: var(--fg); padding: 12px; }
    h2 { font-size: 14px; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
    .section { margin-bottom: 16px; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
    .status-dot.connected { background: var(--success); }
    .status-dot.disconnected { background: var(--error); }

    label { display: block; font-size: 11px; color: var(--info); margin: 6px 0 2px; }
    input, select {
      width: 100%; padding: 5px 8px; font-size: 13px;
      background: var(--input-bg); color: var(--input-fg);
      border: 1px solid var(--input-border); border-radius: 3px;
    }
    .input-row { display: flex; gap: 4px; align-items: center; }
    .input-row select { flex: 1; }
    .input-row button { width: auto; min-width: 32px; margin-top: 0; font-size: 14px; }
    .checkbox-row { display: flex; align-items: center; gap: 6px; margin: 6px 0; }
    .checkbox-row input[type="checkbox"] { width: auto; }

    button {
      width: 100%; padding: 7px; margin-top: 8px; font-size: 13px; font-weight: 600;
      background: var(--btn-bg); color: var(--btn-fg);
      border: none; border-radius: 3px; cursor: pointer;
    }
    button:hover { background: var(--btn-hover); }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-secondary { background: transparent; border: 1px solid var(--input-border); color: var(--fg); }
    .btn-row { display: flex; gap: 6px; margin-top: 8px; }
    .btn-row button { flex: 1; margin-top: 0; }
    .btn-danger { background: var(--error); }

    /* 模式Tab */
    .tab-bar { display: flex; border-bottom: 1px solid var(--input-border); margin-bottom: 10px; }
    .tab-bar button { flex: 1; padding: 6px; font-size: 12px; font-weight: 600; background: none; border: none; border-bottom: 2px solid transparent; color: var(--info); cursor: pointer; margin: 0; }
    .tab-bar button.active { color: var(--btn-bg); border-bottom-color: var(--btn-bg); }
    .tab-content { display: none; }
    .tab-content.active { display: block; }

    .log-area {
      background: var(--vscode-editor-background);
      border: 1px solid var(--input-border);
      border-radius: 3px;
      padding: 8px;
      max-height: 200px;
      overflow-y: auto;
      font-family: var(--vscode-editor-font-family);
      font-size: 12px;
      line-height: 1.5;
    }
    .log-entry { margin-bottom: 2px; }
    .log-entry.info { color: var(--info); }
    .log-entry.success { color: var(--success); }
    .log-entry.error { color: var(--error); }
    .log-entry.warn { color: var(--warn); }

    .result-card {
      background: var(--vscode-editor-background);
      border: 1px solid var(--input-border);
      border-radius: 3px;
      padding: 10px;
    }
    .result-row { display: flex; justify-content: space-between; margin: 3px 0; }
    .result-label { color: var(--info); }
    .result-value { font-weight: 600; }
    .result-value.pass { color: var(--success); }
    .result-value.fail { color: var(--error); }

    .screenshot-area { text-align: center; margin: 8px 0; }
    .screenshot-area img { max-width: 100%; border: 1px solid var(--input-border); border-radius: 3px; }

    .hidden { display: none; }

    /* Bug列表样式 */
    .bug-item {
      background: var(--vscode-editor-background);
      border: 1px solid var(--input-border);
      border-radius: 3px;
      padding: 8px;
      margin-bottom: 6px;
      border-left: 3px solid var(--warn);
    }
    .bug-item.high { border-left-color: var(--error); }
    .bug-item.medium { border-left-color: var(--warn); }
    .bug-item.low { border-left-color: var(--info); }
    .bug-title { font-weight: 600; font-size: 12px; margin-bottom: 4px; }
    .bug-meta { font-size: 11px; color: var(--info); }
    .bug-desc { font-size: 11px; margin-top: 4px; color: var(--fg); opacity: 0.85; max-height: 60px; overflow: hidden; }
    .severity-badge {
      display: inline-block; font-size: 10px; padding: 1px 5px;
      border-radius: 2px; font-weight: 600; margin-right: 4px;
    }
    .severity-badge.high { background: var(--error); color: #fff; }
    .severity-badge.medium { background: var(--warn); color: #000; }
    .severity-badge.low { background: var(--info); color: #fff; }

    /* 步骤列表样式 */
    .step-item {
      display: flex; align-items: center; gap: 6px;
      font-size: 11px; padding: 3px 0;
      border-bottom: 1px solid var(--input-border);
    }
    .step-icon { width: 16px; text-align: center; }
    .step-num { color: var(--info); min-width: 20px; }
    .step-desc { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .step-time { color: var(--info); font-size: 10px; min-width: 36px; text-align: right; }
  </style>
</head>
<body>
  <!-- 引擎状态 -->
  <div class="section">
    <h2>
      <span class="status-dot disconnected" id="statusDot"></span>
      引擎: <span id="engineStatus">未连接</span>
    </h2>
    <button class="btn-secondary" id="btnCheckEngine">检查连接</button>
    <button id="btnLaunchEngine" class="hidden" style="background:#22c55e;margin-top:6px">🚀 一键启动引擎</button>
    <button id="btnStopEngine" class="hidden" style="background:#ef4444;margin-top:6px">⏹ 断开引擎</button>
  </div>

  <!-- 模式切换Tab -->
  <div class="section">
    <div class="tab-bar">
      <button class="active" id="tabBlueprint">蓝本模式</button>
      <button id="tabExplore">探索模式</button>
    </div>

    <!-- 蓝本模式 -->
    <div class="tab-content active" id="panelBlueprint">
      <label>蓝本列表
        <span style="font-size:11px;color:var(--muted);margin-left:4px">（勾选要测试的蓝本）</span>
      </label>
      <div id="blueprintList" style="max-height:150px;overflow-y:auto;border:1px solid var(--border);border-radius:3px;padding:4px;font-size:11px;margin-bottom:4px"></div>
      <input type="text" id="inputBlueprintPath" placeholder="或手动输入路径..." style="font-size:11px;margin-top:4px" />

      <label>覆盖 base_url（可选）</label>
      <input type="text" id="inputBpBaseUrl" placeholder="http://localhost:3000" />

      <button id="btnBlueprintTest">▶ 运行选中蓝本</button>
      <hr style="border:0;border-top:1px solid var(--border);margin:10px 0" />
      <button id="btnCopyBlueprintPrompt" class="btn-secondary" style="background:#8b5cf6">📋 复制蓝本生成提示词</button>
    </div>

    <!-- 探索模式 -->
    <div class="tab-content" id="panelExplore">
      <label>被测应用 URL *</label>
      <input type="text" id="inputUrl" placeholder="http://localhost:3000" />

      <label>应用描述</label>
      <input type="text" id="inputDesc" placeholder="电商网站、管理后台..." />

      <label>测试重点</label>
      <select id="selectFocus">
        <option value="核心功能">核心功能</option>
        <option value="用户注册登录">用户注册登录</option>
        <option value="表单验证">表单验证</option>
        <option value="页面导航">页面导航</option>
        <option value="数据展示">数据展示</option>
      </select>

      <div class="checkbox-row">
        <input type="checkbox" id="cbAutoRepair" />
        <label for="cbAutoRepair" style="margin:0">发现Bug后自动修复</label>
      </div>

      <label id="lblProjectPath" class="hidden">项目根目录（自动修复需要）</label>
      <input type="text" id="inputProjectPath" class="hidden" placeholder="D:\\projects\\my-app" />

      <button id="btnStartTest">▶ 开始测试</button>
    </div>
  </div>

  <!-- 测试控制 -->
  <div class="section hidden" id="controlSection">
    <div class="btn-row">
      <button class="btn-secondary" id="btnPause">⏸ 暂停</button>
      <button class="btn-secondary" id="btnResume">▶ 继续</button>
      <button class="btn-danger" id="btnStop">⏹ 停止</button>
    </div>
  </div>

  <!-- 截图预览 -->
  <div class="section hidden" id="screenshotSection">
    <h2>📸 实时画面</h2>
    <div class="screenshot-area">
      <img id="screenshotImg" src="" alt="截图" />
    </div>
  </div>

  <!-- 实时日志 -->
  <div class="section">
    <h2>📋 测试日志</h2>
    <div class="log-area" id="logArea">
      <div class="log-entry info">等待测试开始...</div>
    </div>
  </div>

  <!-- 测试结果 -->
  <div class="section hidden" id="resultSection">
    <h2>📊 测试结果</h2>
    <div class="result-card">
      <div class="result-row">
        <span class="result-label">测试名称</span>
        <span class="result-value" id="resName">-</span>
      </div>
      <div class="result-row">
        <span class="result-label">通过率</span>
        <span class="result-value" id="resPassRate">-</span>
      </div>
      <div class="result-row">
        <span class="result-label">步骤</span>
        <span class="result-value" id="resSteps">-</span>
      </div>
      <div class="result-row">
        <span class="result-label">Bug 数</span>
        <span class="result-value" id="resBugs">-</span>
      </div>
      <div class="result-row">
        <span class="result-label">耗时</span>
        <span class="result-value" id="resDuration">-</span>
      </div>
      <div class="result-row hidden" id="repairRow">
        <span class="result-label">自动修复</span>
        <span class="result-value" id="resRepair">-</span>
      </div>
    </div>
    <div class="btn-row" style="margin-top:8px">
      <button class="btn-secondary" id="btnRetest">🔄 重测</button>
      <button id="btnCopyBugs">🤖 发送给AI修复</button>
    </div>
  </div>

  <!-- Bug列表 -->
  <div class="section hidden" id="bugSection">
    <h2>🐛 Bug 列表 (<span id="bugTotal">0</span>)</h2>
    <div id="bugList"></div>
  </div>

  <!-- 步骤详情 -->
  <div class="section hidden" id="stepSection">
    <h2 style="cursor:pointer" id="stepToggle">📝 步骤详情 ▸</h2>
    <div id="stepList" class="hidden"></div>
  </div>

  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();

    // Tab切换
    const tabBlueprint = document.getElementById("tabBlueprint");
    const tabExplore = document.getElementById("tabExplore");
    const panelBlueprint = document.getElementById("panelBlueprint");
    const panelExplore = document.getElementById("panelExplore");

    tabBlueprint.addEventListener("click", () => {
      tabBlueprint.classList.add("active"); tabExplore.classList.remove("active");
      panelBlueprint.classList.add("active"); panelExplore.classList.remove("active");
    });
    tabExplore.addEventListener("click", () => {
      tabExplore.classList.add("active"); tabBlueprint.classList.remove("active");
      panelExplore.classList.add("active"); panelBlueprint.classList.remove("active");
    });

    // 蓝本多选列表
    const blueprintListEl = document.getElementById("blueprintList");
    const inputBlueprintPath = document.getElementById("inputBlueprintPath");
    let blueprintEntries = []; // 存储蓝本元数据

    // 获取所有选中的蓝本路径
    function getSelectedBlueprints() {
      const globalCb = document.getElementById("cbGlobalBlueprint");
      if (globalCb && globalCb.checked) {
        // 全局蓝本：返回所有蓝本路径
        return blueprintEntries.map(e => typeof e === "string" ? e : e.path);
      }
      // 局部蓝本：返回勾选的
      const cbs = blueprintListEl.querySelectorAll('.local-blueprint-cb:checked');
      return Array.from(cbs).map(cb => cb.value);
    }

    // 扫描按钮
    document.getElementById("btnScanBp").addEventListener("click", () => {
      vscode.postMessage({ command: "scanBlueprints" });
    });

    // 浏览按钮
    document.getElementById("btnBrowseBp").addEventListener("click", () => {
      vscode.postMessage({ command: "browseBlueprint" });
    });

    // 页面加载时自动扫描
    vscode.postMessage({ command: "scanBlueprints" });

    // 元素引用
    const statusDot = document.getElementById("statusDot");
    const engineStatus = document.getElementById("engineStatus");
    const logArea = document.getElementById("logArea");
    const resultSection = document.getElementById("resultSection");
    const controlSection = document.getElementById("controlSection");
    const screenshotSection = document.getElementById("screenshotSection");
    const screenshotImg = document.getElementById("screenshotImg");
    const cbAutoRepair = document.getElementById("cbAutoRepair");
    const lblProjectPath = document.getElementById("lblProjectPath");
    const inputProjectPath = document.getElementById("inputProjectPath");
    const bugSection = document.getElementById("bugSection");
    const bugList = document.getElementById("bugList");
    const bugTotal = document.getElementById("bugTotal");
    const stepSection = document.getElementById("stepSection");
    const stepList = document.getElementById("stepList");
    const stepToggle = document.getElementById("stepToggle");

    // 步骤详情折叠
    let stepExpanded = false;
    stepToggle.addEventListener("click", () => {
      stepExpanded = !stepExpanded;
      stepList.classList.toggle("hidden", !stepExpanded);
      stepToggle.textContent = stepExpanded ? "📝 步骤详情 ▾" : "📝 步骤详情 ▸";
    });

    // 存储最后一次报告数据
    let lastReport = null;

    // 复制Bug给AI
    document.getElementById("btnCopyBugs").addEventListener("click", () => {
      if (!lastReport) { addLog("暂无测试报告", "error"); return; }
      vscode.postMessage({ command: "copyBugs", report: lastReport });
    });

    // 重测按钮
    document.getElementById("btnRetest").addEventListener("click", () => {
      const bp = document.getElementById("inputBlueprintPath").value.trim();
      if (bp) {
        vscode.postMessage({
          command: "blueprintTest",
          blueprint_path: bp,
          base_url: document.getElementById("inputBpBaseUrl").value.trim() || undefined,
        });
      } else {
        const url = document.getElementById("inputUrl").value.trim();
        if (url) {
          vscode.postMessage({
            command: "startTest",
            url: url,
            description: document.getElementById("inputDesc").value.trim(),
            focus: document.getElementById("selectFocus").value,
            autoRepair: cbAutoRepair.checked,
            projectPath: inputProjectPath.value.trim(),
          });
        } else {
          addLog("请先填写蓝本路径或测试URL", "error");
        }
      }
    });

    // 自动修复联动
    cbAutoRepair.addEventListener("change", () => {
      const show = cbAutoRepair.checked;
      lblProjectPath.classList.toggle("hidden", !show);
      inputProjectPath.classList.toggle("hidden", !show);
    });

    // 检查引擎
    const btnLaunchEngine = document.getElementById("btnLaunchEngine");
    const btnStopEngine = document.getElementById("btnStopEngine");
    let isStarting = false;  // 是否处于「正在启动中」状态
    document.getElementById("btnCheckEngine").addEventListener("click", () => {
      vscode.postMessage({ command: "checkEngine" });
    });

    // 一键启动引擎
    btnLaunchEngine.addEventListener("click", () => {
      isStarting = true;
      vscode.postMessage({ command: "launchEngine" });
      btnLaunchEngine.classList.add("hidden");
      btnStopEngine.classList.remove("hidden");
      btnStopEngine.textContent = "⏹ 断开引擎";
      btnStopEngine.disabled = false;
      addLog("正在启动引擎，请稍候（最长约25秒）...", "info");

      // 分别在 8s / 16s / 25s 重试检查连接，哪次成功就停止
      let checked = 0;
      const delays = [8000, 16000, 25000];
      function scheduleCheck(idx) {
        if (idx >= delays.length) { return; }
        setTimeout(() => {
          checked++;
          vscode.postMessage({ command: "checkEngine" });
          if (checked < delays.length) { scheduleCheck(idx + 1); }
        }, delays[idx] - (idx > 0 ? delays[idx - 1] : 0));
      }
      scheduleCheck(0);
    });

    // 一键断开引擎
    btnStopEngine.addEventListener("click", () => {
      isStarting = false;
      vscode.postMessage({ command: "stopEngine" });
      btnStopEngine.textContent = "⏳ 断开中...";
      btnStopEngine.disabled = true;
      addLog("正在断开引擎...", "info");
    });

    // 蓝本测试（支持多选批量）
    document.getElementById("btnBlueprintTest").addEventListener("click", () => {
      const selected = getSelectedBlueprints();
      const manualPath = document.getElementById("inputBlueprintPath").value.trim();
      const baseUrl = document.getElementById("inputBpBaseUrl").value.trim() || undefined;

      if (selected.length > 1) {
        // 多选：批量执行
        vscode.postMessage({
          command: "blueprintBatchTest",
          blueprint_paths: selected,
          base_url: baseUrl,
        });
      } else if (selected.length === 1) {
        // 单选：单个执行
        vscode.postMessage({
          command: "blueprintTest",
          blueprint_path: selected[0],
          base_url: baseUrl,
        });
      } else if (manualPath) {
        // 无勾选但有手动输入
        vscode.postMessage({
          command: "blueprintTest",
          blueprint_path: manualPath,
          base_url: baseUrl,
        });
      } else {
        addLog("请勾选蓝本或输入蓝本路径", "error");
      }
    });

    // 复制蓝本生成提示词
    document.getElementById("btnCopyBlueprintPrompt").addEventListener("click", () => {
      vscode.postMessage({ command: "copyBlueprintPrompt" });
    });

    // 探索测试
    document.getElementById("btnStartTest").addEventListener("click", () => {
      const url = document.getElementById("inputUrl").value.trim();
      if (!url) { addLog("请输入被测应用 URL", "error"); return; }
      vscode.postMessage({
        command: "startTest",
        url: url,
        description: document.getElementById("inputDesc").value.trim(),
        focus: document.getElementById("selectFocus").value,
        autoRepair: cbAutoRepair.checked,
        projectPath: inputProjectPath.value.trim(),
      });
    });

    // 测试控制
    document.getElementById("btnPause").addEventListener("click", () => {
      vscode.postMessage({ command: "controlTest", action: "pause" });
    });
    document.getElementById("btnResume").addEventListener("click", () => {
      vscode.postMessage({ command: "controlTest", action: "resume" });
    });
    document.getElementById("btnStop").addEventListener("click", () => {
      vscode.postMessage({ command: "controlTest", action: "stop" });
    });

    // 接收后端消息
    window.addEventListener("message", (event) => {
      const msg = event.data;
      switch (msg.command) {
        case "engineStatus": updateEngineStatus(msg.data); break;
        case "testStarted": onTestStarted(); break;
        case "testResult": onTestResult(msg.data); break;
        case "testError": onTestError(msg.data); break;
        case "progress": onProgress(msg.data); break;
        case "controlResult": addLog("控制: " + msg.data.action + " → " + msg.data.state, "info"); break;
        case "controlError": addLog("控制失败: " + msg.data.error, "error"); break;
        case "blueprintList": onBlueprintList(msg.data); break;
        case "blueprintSelected": onBlueprintSelected(msg.data); break;
      }
    });

    function onBlueprintList(entries) {
      blueprintListEl.innerHTML = "";
      blueprintEntries = entries;
      if (!entries || entries.length === 0) {
        blueprintListEl.innerHTML = '<div style="color:var(--muted);padding:8px;text-align:center;font-size:12px">未找到蓝本文件</div>';
        return;
      }

      // 全局蓝本选项（固定在顶部）
      const globalItem = document.createElement("label");
      globalItem.style.cssText = "display:flex;align-items:center;gap:4px;padding:4px 4px;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600;background:var(--bg-secondary,#1e1e1e);border:1px solid var(--border);margin-bottom:4px";
      globalItem.title = "勾选后将测试所有蓝本";
      
      const globalCb = document.createElement("input");
      globalCb.type = "checkbox";
      globalCb.id = "cbGlobalBlueprint";
      globalCb.checked = true; // 默认勾选全局
      globalCb.style.cssText = "flex-shrink:0;width:14px;height:14px";
      
      const globalLabel = document.createElement("span");
      globalLabel.textContent = "🌍 全局蓝本（测试所有）";
      globalLabel.style.cssText = "flex:1;color:var(--fg)";
      
      globalItem.appendChild(globalCb);
      globalItem.appendChild(globalLabel);
      blueprintListEl.appendChild(globalItem);

      // 分割线
      const divider = document.createElement("div");
      divider.style.cssText = "height:1px;background:var(--border);margin:4px 0";
      blueprintListEl.appendChild(divider);

      // 局部蓝本列表
      entries.forEach((entry, i) => {
        const path = typeof entry === "string" ? entry : entry.path;
        const appName = entry.appName || "";
        const desc = entry.description || "";
        const platform = entry.platform || "web";
        const scenarios = entry.scenarioCount || 0;
        const steps = entry.stepCount || 0;

        const parts = path.replace(/\\\\/g, "/").split("/");
        const shortPath = parts.slice(-3).join("/");
        const displayName = appName || shortPath;

        const platformBadge = {web:"🌐",android:"📱",ios:"📱",miniprogram:"💬",desktop:"🖥️"}[platform] || "📄";
        const tooltipText = desc ? (desc + "\\n场景:" + scenarios + " 步骤:" + steps + "\\n" + path) : ("场景:" + scenarios + " 步骤:" + steps + "\\n" + path);

        const item = document.createElement("label");
        item.className = "local-blueprint-item";
        item.style.cssText = "display:flex;align-items:flex-start;gap:4px;padding:3px 4px;border-radius:4px;cursor:pointer;font-size:12px;line-height:1.4;overflow:hidden;width:100%;box-sizing:border-box";
        item.title = tooltipText;
        item.addEventListener("mouseenter", () => { item.style.background = "var(--hover-bg,#2a2d2e)"; });
        item.addEventListener("mouseleave", () => { item.style.background = "transparent"; });

        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.className = "local-blueprint-cb";
        cb.value = path;
        cb.checked = false; // 默认不选（因为全局已选）
        cb.disabled = true; // 默认禁用（因为全局已选）
        cb.style.cssText = "margin-top:2px;flex-shrink:0;width:14px;height:14px";

        const fileName = path.replace(/\\\\/g, "/").split("/").pop() || path;

        const info = document.createElement("div");
        info.style.cssText = "flex:1;min-width:0;overflow:hidden";
        info.innerHTML = '<div style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + platformBadge + ' ' + displayName + '</div>'
          + (desc ? '<div style="color:var(--muted);font-size:11px;margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + desc + '</div>' : '')
          + '<div style="color:var(--muted);font-size:10px;margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + scenarios + '场景 ' + steps + '步骤 · ' + fileName + '</div>';

        item.appendChild(cb);
        item.appendChild(info);
        blueprintListEl.appendChild(item);
      });

      // 全局蓝本checkbox交互逻辑
      globalCb.addEventListener("change", () => {
        const localItems = blueprintListEl.querySelectorAll(".local-blueprint-item");
        const localCbs = blueprintListEl.querySelectorAll(".local-blueprint-cb");
        if (globalCb.checked) {
          // 勾选全局 → 局部全部禁用+灰化
          localCbs.forEach(cb => { cb.disabled = true; cb.checked = false; });
          localItems.forEach(item => { 
            item.style.opacity = "0.5"; 
            item.title = "已勾选全局蓝本，无需勾选局部。如需局部测试，请取消全局勾选。";
          });
        } else {
          // 取消全局 → 局部恢复可选
          localCbs.forEach(cb => { cb.disabled = false; });
          localItems.forEach((item, i) => { 
            item.style.opacity = "1";
            const entry = entries[i];
            const desc = entry.description || "";
            const scenarios = entry.scenarioCount || 0;
            const steps = entry.stepCount || 0;
            const path = entry.path;
            item.title = desc ? (desc + "\\n场景:" + scenarios + " 步骤:" + steps + "\\n" + path) : ("场景:" + scenarios + " 步骤:" + steps + "\\n" + path);
          });
        }
      });

      // 填入第一个路径到手动输入框
      const firstPath = typeof entries[0] === "string" ? entries[0] : entries[0].path;
      inputBlueprintPath.value = firstPath;
      addLog("找到 " + entries.length + " 个蓝本文件", "info");
    }

    function onBlueprintSelected(path) {
      inputBlueprintPath.value = path;
      // 确保在列表中勾选
      const cbs = blueprintListEl.querySelectorAll('input[type="checkbox"]');
      let found = false;
      cbs.forEach(cb => {
        if (cb.value === path) { cb.checked = true; found = true; }
      });
      if (!found) {
        // 手动添加一个条目
        const item = document.createElement("label");
        item.style.cssText = "display:flex;align-items:flex-start;gap:6px;padding:4px 6px;border-radius:4px;cursor:pointer;font-size:12px;line-height:1.4";
        const parts = path.replace(/\\\\/g, "/").split("/");
        item.title = path;
        const cb = document.createElement("input");
        cb.type = "checkbox"; cb.value = path; cb.checked = true; cb.style.cssText = "margin-top:2px;flex-shrink:0";
        const info = document.createElement("div");
        info.innerHTML = '<div style="font-weight:600">📄 ' + parts.slice(-3).join("/") + '</div>';
        item.appendChild(cb); item.appendChild(info);
        blueprintListEl.appendChild(item);
      }
    }

    function updateEngineStatus(data) {
      if (data.connected) {
        isStarting = false;
        statusDot.className = "status-dot connected";
        engineStatus.textContent = "v" + (data.version || "?");
        btnLaunchEngine.classList.add("hidden");
        btnStopEngine.classList.remove("hidden");
        btnStopEngine.textContent = "⏹ 断开引擎";
        btnStopEngine.disabled = false;
        addLog("引擎连接成功 | v" + data.version, "success");
      } else {
        statusDot.className = "status-dot disconnected";
        engineStatus.textContent = isStarting ? "启动中..." : "未连接";
        if (!isStarting) {
          // 只有不在启动中时才恢复启动按钮，避免闪烁
          btnLaunchEngine.classList.remove("hidden");
          btnStopEngine.classList.add("hidden");
        }
        addLog(isStarting ? "引擎尚未就绪，继续等待..." : "引擎未连接，点击「一键启动引擎」按钮启动", isStarting ? "warn" : "error");
      }
    }

    function onTestStarted() {
      controlSection.classList.remove("hidden");
      resultSection.classList.add("hidden");
      // 立即清空上一轮的Bug列表和步骤详情
      bugList.innerHTML = "";
      bugTotal.textContent = "0";
      bugSection.classList.add("hidden");
      stepList.innerHTML = "";
      stepSection.classList.add("hidden");
      logArea.innerHTML = "";
      addLog("测试任务已启动...", "info");
    }

    function onTestResult(report) {
      lastReport = report;
      controlSection.classList.add("hidden");
      screenshotSection.classList.add("hidden");
      addLog("测试完成!", "success");

      // pass_rate from API is already percentage (e.g. 83), not decimal
      const passRateNum = report.pass_rate;
      const passRate = passRateNum.toFixed(0) + "%";

      document.getElementById("resName").textContent = report.test_name;
      const resPassRate = document.getElementById("resPassRate");
      resPassRate.textContent = passRate;
      resPassRate.className = "result-value " + (passRateNum >= 80 ? "pass" : "fail");
      document.getElementById("resSteps").textContent = report.passed_steps + "/" + report.total_steps + " 通过";
      const resBugs = document.getElementById("resBugs");
      resBugs.textContent = report.bug_count;
      resBugs.className = "result-value " + (report.bug_count === 0 ? "pass" : "fail");
      document.getElementById("resDuration").textContent = report.duration_seconds.toFixed(1) + "秒";

      const repairRow = document.getElementById("repairRow");
      if (report.fixed_bug_count !== null && report.fixed_bug_count !== undefined) {
        repairRow.classList.remove("hidden");
        document.getElementById("resRepair").textContent = "修复 " + report.fixed_bug_count + " 个";
      }
      resultSection.classList.remove("hidden");

      // 渲染Bug列表
      renderBugs(report.bugs || []);

      // 渲染步骤详情
      renderSteps(report.steps || []);

      // MCP闭环提示
      if (report.bug_count > 0) {
        addLog("💡 在Cascade聊天窗口说「帮我修复这些Bug」可自动闭环修复", "info");
      }
    }

    function renderBugs(bugs) {
      bugList.innerHTML = "";
      bugTotal.textContent = bugs.length;
      if (bugs.length === 0) {
        bugSection.classList.add("hidden");
        return;
      }
      bugSection.classList.remove("hidden");
      bugs.forEach((bug, i) => {
        const sev = bug.severity || "medium";
        const div = document.createElement("div");
        div.className = "bug-item " + sev;
        div.innerHTML =
          '<div class="bug-title">' +
            '<span class="severity-badge ' + sev + '">' + sev.toUpperCase() + '</span>' +
            escapeHtml(bug.title || "Bug #" + (i+1)) +
          '</div>' +
          (bug.step_number ? '<div class="bug-meta">步骤 #' + bug.step_number + (bug.category ? ' · ' + escapeHtml(bug.category) : '') + '</div>' : '') +
          '<div class="bug-desc">' + escapeHtml((bug.description || "").substring(0, 200)) + '</div>';
        bugList.appendChild(div);
      });
    }

    function renderSteps(steps) {
      stepList.innerHTML = "";
      if (steps.length === 0) {
        stepSection.classList.add("hidden");
        return;
      }
      stepSection.classList.remove("hidden");
      steps.forEach((s) => {
        const icon = s.status === "passed" ? "✅" : s.status === "failed" ? "❌" : "⚠️";
        const div = document.createElement("div");
        div.className = "step-item";
        div.innerHTML =
          '<span class="step-icon">' + icon + '</span>' +
          '<span class="step-num">#' + s.step + '</span>' +
          '<span class="step-desc" title="' + escapeHtml(s.description || s.action) + '">' + escapeHtml(s.description || s.action) + '</span>' +
          '<span class="step-time">' + s.duration_seconds.toFixed(1) + 's</span>';
        stepList.appendChild(div);
      });
    }

    function escapeHtml(text) {
      const d = document.createElement("div");
      d.textContent = text;
      return d.innerHTML;
    }

    function onTestError(data) {
      controlSection.classList.add("hidden");
      addLog("测试失败: " + data.error, "error");
    }

    function onProgress(wsMsg) {
      const typeMap = {
        step_start: "info", step_done: "success", bug_found: "warn",
        repair_start: "info", repair_done: "success", test_done: "success",
        error: "error", log: "info", state_change: "info", terminal_log: "info",
      };
      // 截图推送
      if (wsMsg.type === "screenshot" && wsMsg.data?.image) {
        screenshotSection.classList.remove("hidden");
        screenshotImg.src = "data:image/png;base64," + wsMsg.data.image;
        return;
      }
      const level = typeMap[wsMsg.type] || "info";
      const text = wsMsg.data?.message || wsMsg.type;
      addLog(text, level);
    }

    function addLog(text, level) {
      const entry = document.createElement("div");
      entry.className = "log-entry " + (level || "info");
      const now = new Date().toLocaleTimeString("zh-CN", { hour12: false });
      entry.textContent = "[" + now + "] " + text;
      logArea.appendChild(entry);
      logArea.scrollTop = logArea.scrollHeight;
    }

    // 初始检查
    vscode.postMessage({ command: "checkEngine" });
  </script>
</body>
</html>`;
  }
}

function getNonce(): string {
  let text = "";
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) {
    text += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return text;
}
