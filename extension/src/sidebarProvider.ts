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
import * as path from "path";
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
          await this._handleCopyBlueprintPrompt(msg.platform || "web");
          break;
        case "platformPrecheck":
          await this._handlePlatformPrecheck(msg);
          break;
        case "checkDeviceStatus":
          await this._handleCheckDeviceStatus(msg);
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
    platform?: string;
    mobile_session_id?: string;
  }): Promise<void> {
    try {
      this._postMessage({ command: "testStarted" });

      const platform = (msg.platform || "web").toLowerCase();
      let report: TestReportResponse;

      if (platform === "miniprogram") {
        report = await this._client.startMiniprogramBlueprintTest({
          blueprint_path: msg.blueprint_path,
          base_url: msg.base_url || undefined,
          project_path: this._guessProjectPathFromBlueprint(msg.blueprint_path),
        });
      } else if (platform === "desktop") {
        report = await this._client.startDesktopBlueprintTest({
          blueprint_path: msg.blueprint_path,
          base_url: msg.base_url || undefined,
        });
      } else if (platform === "android" || platform === "ios") {
        report = await this._client.startMobileBlueprintTest({
          blueprint_path: msg.blueprint_path,
          base_url: msg.base_url || undefined,
          mobile_session_id: msg.mobile_session_id || "",
        });
      } else {
        report = await this._client.startBlueprintTest({
          blueprint_path: msg.blueprint_path,
          base_url: msg.base_url || undefined,
        });
      }

      this._postMessage({ command: "testResult", data: report });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      this._postMessage({ command: "testError", data: { error: message } });
    }
  }

  private async _handleBlueprintBatchTest(msg: {
    blueprint_paths: string[];
    base_url?: string;
    platform?: string;
    mobile_session_id?: string;
  }): Promise<void> {
    try {
      this._postMessage({ command: "testStarted" });

      // 依次执行每个蓝本，汇总结果
      const results: TestReportResponse[] = [];
      for (const bp of msg.blueprint_paths) {
        try {
          const platform = (msg.platform || "web").toLowerCase();
          let report: TestReportResponse;

          if (platform === "miniprogram") {
            report = await this._client.startMiniprogramBlueprintTest({
              blueprint_path: bp,
              base_url: msg.base_url || undefined,
              project_path: this._guessProjectPathFromBlueprint(bp),
            });
          } else if (platform === "desktop") {
            report = await this._client.startDesktopBlueprintTest({
              blueprint_path: bp,
              base_url: msg.base_url || undefined,
            });
          } else if (platform === "android" || platform === "ios") {
            report = await this._client.startMobileBlueprintTest({
              blueprint_path: bp,
              base_url: msg.base_url || undefined,
              mobile_session_id: msg.mobile_session_id || "",
            });
          } else {
            report = await this._client.startBlueprintTest({
              blueprint_path: bp,
              base_url: msg.base_url || undefined,
            });
          }

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
    type BpEntry = { path: string; mtime: number; appName: string; description: string; platform: string; scenarioCount: number; stepCount: number };
    type ProjectGroup = { projectDir: string; projectName: string; platform: string; blueprints: BpEntry[] };
    const projectMap = new Map<string, ProjectGroup>();
    const folders = vscode.workspace.workspaceFolders;
    if (folders) {
      for (const folder of folders) {
        const patterns = [
          new vscode.RelativePattern(folder, "**/testpilot.json"),
          new vscode.RelativePattern(folder, "**/*.testpilot.json"),
        ];
        const seen = new Set<string>();
        for (const pattern of patterns) {
          const files = await vscode.workspace.findFiles(pattern, "{**/node_modules/**,**/test_fixtures/**,**/.venv/**}", 50);
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
            // 确定项目目录（testpilot/子目录取上一级）
            const fPath = f.fsPath.replace(/\\/g, "/");
            const parts = fPath.split("/");
            parts.pop(); // 移除文件名
            if (parts.length > 0 && parts[parts.length - 1] === "testpilot") { parts.pop(); }
            const dir = parts.join("/");
            const entry: BpEntry = { path: f.fsPath, mtime, appName, description, platform, scenarioCount, stepCount };
            if (projectMap.has(dir)) {
              projectMap.get(dir)!.blueprints.push(entry);
            } else {
              const dirName = dir.split("/").pop() || dir;
              projectMap.set(dir, { projectDir: dir, projectName: appName || dirName, platform, blueprints: [entry] });
            }
          }
        }
      }
    }
    const projects = Array.from(projectMap.values());
    projects.sort((a, b) => b.blueprints.length - a.blueprints.length);
    projects.forEach(p => p.blueprints.sort((a, b) => b.mtime - a.mtime));
    this._postMessage({ command: "blueprintList", data: projects });
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

  private async _handleCopyBlueprintPrompt(platform: string): Promise<void> {
    const commonRules = `══════ 测试设计黄金规则（必须严格遵守） ══════

【规则1：功能全覆盖】
- 先通读全部源代码，列出所有功能点（每个按钮、每个表单、每个Tab、每个弹窗、每个下拉框）
- 每个功能点必须至少有一个测试场景，不能遗漏任何可操作的UI元素
- 自检清单：数一数代码里有多少个按钮/表单/页面，蓝本里是否每个都覆盖到了

【规则2：操作→断言配对（最核心）】
- 每一个操作（click/fill/select）后面必须跟一个断言（assert_text/assert_visible/screenshot）验证结果
- 错误示范：click登录按钮 → 结束（没验证是否登录成功）
- 正确示范：click登录按钮 → assert_text验证"欢迎回来"或验证用户名显示正确
- 原则：没有断言的操作等于没测

【规则3：业务流程端到端串联】
- 除了单点功能测试，必须有完整业务流程场景：
  例：注册→登录→浏览商品→加入购物车→填写地址→提交订单→查看订单详情
- 每个流程场景至少串联3个以上页面/功能

【规则4：状态变化验证】
- 操作前先读取当前状态值，操作后再读取，对比变化是否符合预期
- 例：加入购物车前读购物车数量=0，加入后断言数量=1
- 例：删除商品前列表有3条，删除后断言列表有2条

【规则5：异常和边界测试】
- 每个表单必须测试：空提交、超长输入、特殊字符、格式错误
- 每个需要权限的操作必须测试：未登录访问、无权限操作
- 验证错误提示消息是否正确显示

【规则6：弹窗和提示验证】
- 操作后出现的成功提示、错误提示、确认弹窗，必须用断言验证内容
- 例：提交订单后验证"下单成功"提示
- 例：删除操作后验证确认弹窗文字

【规则7：选择器规范】
- 使用代码中的真实 id（如 #login-btn）或稳定 class
- 禁止用 div:nth-child(3) 这类脆弱选择器
- 必须先阅读源代码确认选择器存在

【规则8：启动命令】
- 如果应用需要命令行启动（npm start、python app.py），必须填写 start_command 字段
- 纯HTML静态应用留空

【规则9：深度Bug挖掘（安全审计视角）】
- 请以资深QA架构师+安全审计师的双重视角审视代码，主动挖掘以下隐蔽Bug：
  * 认证绕过：密码是否真正校验？是否存在硬编码密码/万能密码？未登录能否直接访问受保护页面？
  * 数值精度：价格/金额计算是否用浮点加法（0.1+0.2≠0.3）？是否做了toFixed/Math.round处理？
  * 库存/数量边界：加购是否校验库存上限？数量能否改为负数/0/超大数？
  * 优惠/折扣逻辑：优惠金额是否真正从总价中扣除？满减条件是否正确判断？
  * 配送/运费逻辑：不同配送方式的运费计算是否正确？免费配送条件是否生效？
  * 状态一致性：前端显示的文字（如"免费"）与实际计算值是否一致？
  * 并发/重复提交：按钮是否有防重复点击？表单能否重复提交？
- 对于每个可疑逻辑，设计专门的验证场景：先构造触发条件，再用assert_text断言实际计算结果

【规则10：参考功能文档】
- 如果项目目录下存在 README.md、需求文档、功能说明、CHANGELOG 等文件，必须先阅读
- 根据文档中描述的功能清单逐一核对：文档说有的功能，蓝本必须覆盖
- 根据文档中的业务规则设计断言（如"满100免运费"→ 构造99元和100元两个场景分别验证）
- 如果没有文档，则从代码注释、变量命名、函数名中推断业务意图，对比实际行为是否一致

【规则11：截图策略（省钱省时）】
- 截图用于发现视觉Bug（布局溢出、元素遮挡、样式错乱、响应式崩坏），断言无法检测这类问题
- 规则：每个蓝本模块的第1个场景末尾加1张 screenshot，其余场景不加
  * 例：auth.testpilot.json 的第1个场景末尾 → screenshot（覆盖登录页视觉）
  * 例：cart.testpilot.json 的第1个场景末尾 → screenshot（覆盖购物车视觉）
  * 同模块的第2、3、4…个场景 → 不加 screenshot
- 断言失败时引擎会自动截图留证，蓝本不用额外写
- ❌ 禁止每个场景末尾都加 screenshot（浪费视觉大模型费用和时间）

【规则12：蓝本按功能模块拆分】
- 按业务功能模块拆分蓝本，不要把所有场景塞进一个文件
- 拆分原则：一个功能模块 = 一个蓝本文件，改了哪个功能就只跑哪个蓝本
  * 例：auth（登录注册）、cart（购物车）、checkout（结算支付）、profile（个人中心）
  * 跨页面的端到端流程归属到终点功能模块（如"加购→结算→下单"归入 checkout）
- 命名规范：testpilot/<模块名>.testpilot.json
- 每个蓝本独立可运行，场景开头都要从 navigate 开始
- 全量测试时通过 run_blueprint_batch 批量运行所有蓝本

【规则13：蓝本增量修改（省Token）】
- 已有蓝本时，只修改/新增变更涉及的场景，不要重写整个文件
- 新增功能 → 新增场景追加到对应模块蓝本
- 修改功能 → 更新对应场景的步骤和断言
- 删除功能 → 删除对应场景
- 禁止每次都从零生成全新蓝本覆盖旧文件

重要提醒：以后修改代码时，主动审视并更新对应模块的蓝本，无需用户提醒！`;

    let prompt = "";
    if (platform === "miniprogram") {
      prompt = `请帮我为当前【微信小程序】项目生成测试蓝本文件 testpilot/testpilot.json。

⚠️ 小程序蓝本与Web蓝本完全不同！必须严格遵守以下铁律：

【铁律1】evaluate 的 value 必须是可被 new Function(code) 包裹的纯JS代码字符串
  ✅ "value": "(() => { const app = getApp(); return app.globalData.cart.length; })()"
  ❌ "value": "() => getApp().globalData.cart.length"（箭头函数不能被new Function直接执行）

【铁律2】小程序没有 document 对象！evaluate 里只能用：
  ✅ getApp() / getCurrentPages() / wx.xxx / Page方法
  ❌ document.querySelector / window.location（这些在小程序里不存在）

【铁律3】每个场景的第一步必须是 reset_state（清空购物车等全局状态+reLaunch回首页）
  {"action": "reset_state", "description": "重置状态回首页"}

【铁律4】跨页面导航必须用 navigate_to，不能用 navigate
  {"action": "navigate_to", "value": "/pages/cart/cart", "description": "跳转到购物车页"}

【铁律5】call_method 的参数必须用 JSON 格式
  {"action": "call_method", "target": "onCategoryTap", "value": "{\\"detail\\": {\\"dataset\\": {\\"cat\\": \\"水果\\"}}}"}

【铁律6】assert_compare 的 value 格式为 "操作符 期望值"
  {"action": "assert_compare", "target": "#cartCount", "value": "> 0"}
  {"action": "assert_compare", "target": "#total", "value": "== 100"}

【铁律7】page_query 读取DOM文本/数量时用 value 指定返回类型
  {"action": "page_query", "target": ".product", "value": "count"}  → 返回元素数量
  {"action": "page_query", "target": "#price", "value": "text"}    → 返回文本内容

支持的 action（15种）：
reset_state / navigate_to / click / fill / call_method / evaluate / read_text / assert_text / assert_compare / page_query / tap_multiple / screenshot / wait / select / scroll

蓝本格式：
{
  "app_name": "小程序名称",
  "description": "功能说明",
  "base_url": "miniprogram://项目绝对路径",
  "version": "1.0",
  "platform": "miniprogram",
  "pages": [
    {
      "url": "/pages/index/index",
      "title": "首页",
      "elements": { "元素描述": "CSS选择器（来自wxml）" },
      "scenarios": [
        {
          "name": "场景名",
          "steps": [
            {"action": "reset_state", "description": "重置状态回首页"},
            {"action": "read_text", "target": "#price", "description": "读取价格"},
            {"action": "evaluate", "value": "(() => { return getApp().globalData.isVip; })()", "expected": "true", "description": "验证会员状态"}
          ]
        }
      ]
    }
  ]
}

请先阅读项目中所有 .wxml 和 .js 文件，提取选择器和业务逻辑，再生成蓝本。

${commonRules}`;
    } else if (platform === "android") {
      prompt = `请帮我为当前【Android】项目生成测试蓝本文件 testpilot/testpilot.json。

蓝本格式：
{
  "app_name": "应用名称",
  "description": "功能说明",
  "base_url": "http://被测网页URL（手机浏览器测试）",
  "version": "1.0",
  "platform": "android",
  "pages": [
    {
      "url": "/",
      "title": "页面标题",
      "elements": { "元素描述": "#CSS选择器" },
      "scenarios": [
        {
          "name": "场景名",
          "steps": [
            {"action": "navigate", "value": "http://被测URL"},
            {"action": "click", "target": "#btn"},
            {"action": "assert_text", "target": "#result", "expected": "预期文本"}
          ]
        }
      ]
    }
  ]
}

注意：Android测试通过手机浏览器执行，选择器与Web相同（CSS选择器）。
如果是原生App测试，target改用 resource-id 格式（如 com.app:id/btnLogin）。

支持的 action：navigate / click / fill / select / wait / screenshot / assert_text / assert_visible / hover / scroll

${commonRules}`;
    } else if (platform === "desktop") {
      prompt = `请帮我为当前【Windows桌面应用】项目生成测试蓝本文件 testpilot/testpilot.json。

蓝本格式：
{
  "app_name": "桌面应用名称",
  "description": "功能说明",
  "base_url": "desktop://应用名称",
  "version": "1.0",
  "platform": "desktop",
  "pages": [
    {
      "url": "/",
      "title": "主窗口",
      "elements": { "元素描述": "选择器" },
      "scenarios": [
        {
          "name": "场景名",
          "steps": [
            {"action": "click", "target": "name:按钮名称"},
            {"action": "fill", "target": "automationid:inputField", "value": "测试值"},
            {"action": "assert_text", "target": "name:结果标签", "expected": "预期文本"}
          ]
        }
      ]
    }
  ]
}

桌面选择器格式（4种）：
- name:XXX — 按UI元素Name属性查找
- automationid:XXX — 按AutomationId查找（最稳定）
- class:XXX — 按ClassName查找
- point:X,Y — 按屏幕坐标点击（兜底方案）

支持的 action：click / fill / assert_text / screenshot / wait

${commonRules}`;
    } else {
      // Web（默认）
      prompt = `请帮我为当前【Web】项目生成测试蓝本文件，放在项目的 testpilot/ 文件夹下。

重要：按功能模块拆分成多个蓝本文件，不要创建单一的 testpilot.json！

例如电商项目应拆分为：
- testpilot/auth.testpilot.json（登录/注册/权限）
- testpilot/product.testpilot.json（商品管理CRUD）
- testpilot/order.testpilot.json（订单管理）
- testpilot/cart.testpilot.json（购物车）

蓝本文件格式：
{
  "app_name": "模块名称",
  "description": "蓝本功能说明（50-200字）",
  "base_url": "http://localhost:端口",
  "version": "1.0",
  "platform": "web",
  "start_command": "npm start 或 python app.py（纯HTML留空）",
  "start_cwd": "./",
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

${commonRules}`;
    }

    await vscode.env.clipboard.writeText(prompt);
    const platformNames: Record<string, string> = { web: "Web", miniprogram: "微信小程序", android: "Android", desktop: "Windows桌面", ios: "iOS" };
    const pName = platformNames[platform] || "Web";
    vscode.window.showInformationMessage(`✅ ${pName}蓝本提示词已复制！请粘贴到 Cursor / Windsurf，让编程AI读取源码生成蓝本。`);
  }

  private _guessProjectPathFromBlueprint(blueprintPath: string): string {
    const normalized = blueprintPath.replace(/\\/g, "/");
    const parts = normalized.split("/");
    if (parts.length <= 1) {
      return "";
    }
    parts.pop(); // file
    if (parts.length > 0 && parts[parts.length - 1] === "testpilot") {
      parts.pop();
    }
    return parts.join("/");
  }

  private async _handlePlatformPrecheck(msg: { platform?: string; blueprint_path?: string }): Promise<void> {
    const platform = (msg.platform || "web").toLowerCase();
    try {
      if (platform === "android" || platform === "ios") {
        const devices = await this._client.listMobileDevices();
        if ((devices.count || 0) === 0) {
          this._postMessage({
            command: "platformPrecheckResult",
            data: {
              ok: false,
              platform,
              message: "未检测到手机设备，请先连接手机并开启USB调试。",
            },
          });
          return;
        }

        const sessions = await this._client.listMobileSessions();
        if ((sessions.count || 0) === 0) {
          const first = devices.devices?.[0] || {};
          const deviceName = String((first as Record<string, unknown>).model || (first as Record<string, unknown>).serial || "");
          const created = await this._client.createMobileSession({ device_name: deviceName });
          this._postMessage({
            command: "platformPrecheckResult",
            data: {
              ok: true,
              platform,
              message: `设备已连接，已创建会话 ${created.session_id}，可以开始测试。`,
              mobile_session_id: created.session_id,
            },
          });
          return;
        }

        const sid = String((sessions.sessions?.[0] as Record<string, unknown>)?.session_id || "");
        this._postMessage({
          command: "platformPrecheckResult",
          data: {
            ok: true,
            platform,
            message: `检测到已连接设备和活跃会话 ${sid}，可以开始测试。`,
            mobile_session_id: sid,
          },
        });
        return;
      }

      if (platform === "miniprogram") {
        const status = await this._client.getMiniprogramDevtoolsStatus();
        if (!status.found) {
          this._postMessage({
            command: "platformPrecheckResult",
            data: {
              ok: false,
              platform,
              message: status.message || "未检测到微信开发者工具，请先安装并开启服务端口。",
            },
          });
          return;
        }

        this._postMessage({
          command: "platformPrecheckResult",
          data: {
            ok: true,
            platform,
            message: "微信开发者工具可用。请确保已使用固定端口（建议9420）启动自动化。",
          },
        });
        return;
      }

      this._postMessage({
        command: "platformPrecheckResult",
        data: {
          ok: true,
          platform,
          message: "平台检查通过，可以开始测试。",
        },
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      this._postMessage({
        command: "platformPrecheckResult",
        data: {
          ok: false,
          platform,
          message: `平台检查失败: ${message}`,
        },
      });
    }
  }

  private async _handleCheckDeviceStatus(msg: { platform?: string }): Promise<void> {
    const platform = (msg.platform || "web").toLowerCase();
    try {
      if (platform === "android" || platform === "ios") {
        const devices = await this._client.listMobileDevices();
        if ((devices.count || 0) === 0) {
          this._postMessage({
            command: "deviceStatusResult",
            data: {
              connected: false,
              message: "未检测到设备，请连接手机并开启USB调试",
              deviceName: "",
            },
          });
          return;
        }
        const first = devices.devices?.[0] || {};
        const deviceName = String((first as Record<string, unknown>).model || (first as Record<string, unknown>).serial || "未知设备");
        this._postMessage({
          command: "deviceStatusResult",
          data: {
            connected: true,
            message: `设备已连接：${deviceName}`,
            deviceName,
          },
        });
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      this._postMessage({
        command: "deviceStatusResult",
        data: {
          connected: false,
          message: `检测失败: ${message}`,
          deviceName: "",
        },
      });
    }
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
    <!-- 项目选择器 -->
    <div style="display:flex;gap:4px;align-items:center;margin:6px 0">
      <select id="projectSelect" style="flex:1;font-size:12px;padding:4px 6px" disabled>
        <option value="">暂无测试项目</option>
      </select>
      <button id="btnRefreshProjects" class="btn-secondary" style="width:28px;min-width:28px;margin:0;padding:3px;font-size:13px" title="刷新项目列表">🔄</button>
    </div>
    <button class="btn-secondary hidden" id="btnCheckEngine">检查连接</button>
    <!-- 设备状态提示（仅Android/iOS项目显示） -->
    <div id="deviceStatusRow" class="hidden" style="background:var(--bg-secondary,#1e1e1e);border:1px solid var(--border);border-radius:3px;padding:6px 8px;margin:6px 0;font-size:11px">
      <div style="display:flex;align-items:flex-start;gap:4px;margin-bottom:4px">
        <span id="deviceStatusIcon" style="flex-shrink:0;line-height:1.4">📱</span>
        <span id="deviceStatusText" style="color:var(--muted);word-break:break-word;line-height:1.4">检测中...</span>
      </div>
      <button id="btnDetectDevice" class="btn-secondary" style="font-size:10px;padding:3px 6px;width:100%">检测设备</button>
    </div>
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
      <div id="blueprintList" style="max-height:280px;overflow-y:auto;border:1px solid var(--border);border-radius:3px;padding:4px;font-size:11px;margin-bottom:4px"></div>
      <div class="btn-row" style="margin-top:4px">
        <button class="btn-secondary" id="btnScanBp" style="flex:1;font-size:11px;padding:4px">🔍 扫描蓝本</button>
        <button class="btn-secondary" id="btnBrowseBp" style="flex:1;font-size:11px;padding:4px">📂 浏览文件</button>
      </div>
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
    const projectSelect = document.getElementById("projectSelect");
    let allProjects = [];
    let currentProjectIdx = 0;
    let blueprintEntries = []; // 当前项目的蓝本列表

    // 获取当前项目平台
    function getCurrentPlatform() {
      if (allProjects.length === 0) { return "web"; }
      return allProjects[currentProjectIdx] ? allProjects[currentProjectIdx].platform : "web";
    }

    // 获取所有选中的蓝本路径
    function getSelectedBlueprints() {
      const globalCb = document.getElementById("cbGlobalBlueprint");
      if (globalCb && globalCb.checked) {
        return blueprintEntries.map(e => typeof e === "string" ? e : e.path);
      }
      const cbs = blueprintListEl.querySelectorAll('.local-blueprint-cb:checked');
      return Array.from(cbs).map(cb => cb.value);
    }

    // 项目切换（记住上次选中的项目）
    projectSelect.addEventListener("change", () => {
      currentProjectIdx = parseInt(projectSelect.value);
      if (allProjects.length > 0 && allProjects[currentProjectIdx]) {
        blueprintEntries = allProjects[currentProjectIdx].blueprints || [];
        // 记住选中的项目（按项目名+平台唯一标识）
        var proj = allProjects[currentProjectIdx];
        localStorage.setItem("testpilot_lastProject", (proj.projectName || "") + "|" + (proj.platform || ""));
      } else {
        blueprintEntries = [];
      }
      renderBlueprintList(blueprintEntries);
      updateDeviceStatusVisibility();
    });

    // 根据当前项目平台更新设备状态行可见性
    function updateDeviceStatusVisibility() {
      const platform = getCurrentPlatform();
      const deviceRow = document.getElementById("deviceStatusRow");
      const isWin = navigator.userAgent.indexOf("Windows") !== -1 || navigator.platform.indexOf("Win") !== -1;
      if (platform === "ios" && isWin) {
        // iOS在Windows下：显示提示但不检测设备
        deviceRow.classList.remove("hidden");
        document.getElementById("deviceStatusIcon").textContent = "🍎";
        document.getElementById("deviceStatusText").textContent = "iOS项目需要macOS环境才能运行测试";
        document.getElementById("deviceStatusText").style.color = "var(--warning,#f59e0b)";
        document.getElementById("btnDetectDevice").style.display = "none";
      } else if (platform === "android") {
        deviceRow.classList.remove("hidden");
        document.getElementById("btnDetectDevice").style.display = "";
        checkDeviceStatus();
      } else {
        deviceRow.classList.add("hidden");
      }
    }

    // 检测设备连接状态
    function checkDeviceStatus() {
      const statusText = document.getElementById("deviceStatusText");
      const statusIcon = document.getElementById("deviceStatusIcon");
      statusText.textContent = "检测中...";
      statusText.style.color = "var(--muted)";
      statusIcon.textContent = "📱";
      vscode.postMessage({ command: "checkDeviceStatus", platform: getCurrentPlatform() });
    }

    // 检测设备按钮
    document.getElementById("btnDetectDevice").addEventListener("click", () => {
      checkDeviceStatus();
    });

    // 刷新项目按钮
    document.getElementById("btnRefreshProjects").addEventListener("click", () => {
      vscode.postMessage({ command: "scanBlueprints" });
    });

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
    let engineFound = false;   // 引擎是否已连接成功（防止重复检查）
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

      // 分别在 8s / 16s / 25s 重试检查连接，连接成功后停止后续检查
      engineFound = false;
      const delays = [8000, 16000, 25000];
      function scheduleCheck(idx) {
        if (idx >= delays.length || engineFound) { return; }
        setTimeout(() => {
          if (engineFound) { return; }
          vscode.postMessage({ command: "checkEngine" });
          scheduleCheck(idx + 1);
        }, delays[idx] - (idx > 0 ? delays[idx - 1] : 0));
      }
      scheduleCheck(0);
    });

    // 一键断开引擎
    btnStopEngine.addEventListener("click", () => {
      isStarting = false;
      wasConnected = false;
      engineFound = false;
      vscode.postMessage({ command: "stopEngine" });
      btnStopEngine.textContent = "⏳ 断开中...";
      btnStopEngine.disabled = true;
      addLog("正在断开引擎...", "info");
    });

    let currentMobileSessionId = "";
    let pendingBlueprintRun = null;

    // 蓝本测试（支持多选批量 + 平台路由 + 前置检查）
    document.getElementById("btnBlueprintTest").addEventListener("click", () => {
      const selected = getSelectedBlueprints();
      const manualPath = document.getElementById("inputBlueprintPath").value.trim();
      const baseUrl = document.getElementById("inputBpBaseUrl").value.trim() || undefined;
      const platform = getCurrentPlatform();

      if (selected.length === 0 && !manualPath) {
        addLog("请勾选蓝本或输入蓝本路径", "error");
        return;
      }

      const paths = selected.length > 0 ? selected : [manualPath];
      pendingBlueprintRun = { paths, baseUrl, platform };
      const firstPath = paths[0] || "";
      vscode.postMessage({ command: "platformPrecheck", platform: platform, blueprint_path: firstPath });
    });

    // 复制蓝本生成提示词（根据当前选中项目的平台生成不同提示词）
    document.getElementById("btnCopyBlueprintPrompt").addEventListener("click", () => {
      const sel = document.getElementById("projectSelect");
      const platform = sel && sel.selectedOptions[0] ? (sel.selectedOptions[0].dataset.platform || "web") : "web";
      vscode.postMessage({ command: "copyBlueprintPrompt", platform: platform });
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
        case "platformPrecheckResult": onPlatformPrecheckResult(msg.data); break;
        case "deviceStatusResult": onDeviceStatusResult(msg.data); break;
      }
    });

    function onDeviceStatusResult(data) {
      const statusText = document.getElementById("deviceStatusText");
      const statusIcon = document.getElementById("deviceStatusIcon");
      if (!data) return;
      
      if (data.connected) {
        statusText.textContent = data.message || "设备已连接";
        statusText.style.color = "var(--success,#22c55e)";
        statusIcon.textContent = "✅";
      } else {
        statusText.textContent = data.message || "未检测到设备";
        statusText.style.color = "var(--error,#ef4444)";
        statusIcon.textContent = "❌";
      }
    }

    function onPlatformPrecheckResult(data) {
      if (!data || !pendingBlueprintRun) {
        return;
      }
      if (!data.ok) {
        addLog(data.message || "平台检查未通过", "error");
        pendingBlueprintRun = null;
        return;
      }

      if (data.mobile_session_id) {
        currentMobileSessionId = data.mobile_session_id;
      }

      addLog(data.message || "平台检查通过", "success");

      const run = pendingBlueprintRun;
      pendingBlueprintRun = null;
      const platformNames = {web:"Web",miniprogram:"微信小程序",android:"Android",ios:"iOS",desktop:"Windows桌面"};
      addLog("平台: " + (platformNames[run.platform] || run.platform) + " | 蓝本: " + run.paths.length + "个", "info");

      if (run.paths.length > 1) {
        vscode.postMessage({
          command: "blueprintBatchTest",
          blueprint_paths: run.paths,
          base_url: run.baseUrl,
          platform: run.platform,
          mobile_session_id: currentMobileSessionId || undefined,
        });
      } else {
        vscode.postMessage({
          command: "blueprintTest",
          blueprint_path: run.paths[0],
          base_url: run.baseUrl,
          platform: run.platform,
          mobile_session_id: currentMobileSessionId || undefined,
        });
      }
    }

    function onBlueprintList(projects) {
      allProjects = projects || [];
      // 更新项目下拉框
      projectSelect.innerHTML = "";
      if (allProjects.length === 0) {
        projectSelect.innerHTML = '<option value="">暂无测试项目</option>';
        projectSelect.disabled = true;
        blueprintEntries = [];
        blueprintListEl.innerHTML = '<div style="color:var(--muted);padding:12px;text-align:center;font-size:12px;line-height:1.6">暂无测试项目<br><br>请在项目中创建蓝本文件，<br>或点击下方「📋 复制蓝本生成提示词」<br>让编程AI自动生成。</div>';
        return;
      }

      var platformNames = {
        web: "Web",
        android: "Android",
        ios: "iOS",
        miniprogram: "微信小程序",
        desktop: "Windows桌面"
      };

      // 检测当前操作系统
      var isWindows = navigator.userAgent.indexOf("Windows") !== -1 || navigator.platform.indexOf("Win") !== -1;

      // 各项目选项（无“全部项目”）
      var firstSelectableIdx = -1;
      allProjects.forEach(function(proj, i) {
        var opt = document.createElement("option");
        opt.value = String(i);
        opt.dataset.platform = proj.platform || "web";
        var pName = platformNames[proj.platform] || proj.platform || "Web";
        // iOS项目在Windows下灰色不可选
        if (proj.platform === "ios" && isWindows) {
          opt.textContent = proj.projectName + "（" + pName + "）— 需macOS环境";
          opt.disabled = true;
          opt.style.color = "#666";
        } else {
          opt.textContent = proj.projectName + "（" + pName + "）";
          if (firstSelectableIdx === -1) { firstSelectableIdx = i; }
        }
        projectSelect.appendChild(opt);
      });

      // 尝试恢复上次选中的项目（按项目名+平台匹配）
      if (firstSelectableIdx === -1) { firstSelectableIdx = 0; }
      var lastProjectKey = localStorage.getItem("testpilot_lastProject") || "";
      var restoredIdx = -1;
      if (lastProjectKey) {
        allProjects.forEach(function(proj, i) {
          var key = (proj.projectName || "") + "|" + (proj.platform || "");
          if (key === lastProjectKey && !(proj.platform === "ios" && isWindows)) {
            restoredIdx = i;
          }
        });
      }
      var selectedIdx = restoredIdx >= 0 ? restoredIdx : firstSelectableIdx;
      projectSelect.disabled = allProjects.length <= 1;
      currentProjectIdx = selectedIdx;
      projectSelect.value = String(selectedIdx);
      blueprintEntries = allProjects[selectedIdx] ? (allProjects[selectedIdx].blueprints || []) : [];
      renderBlueprintList(blueprintEntries);
      updateDeviceStatusVisibility();

      var totalBp = allProjects.reduce(function(n, p) { return n + (p.blueprints ? p.blueprints.length : 0); }, 0);
      addLog("找到 " + allProjects.length + " 个项目，共 " + totalBp + " 个蓝本", "info");
    }

    function renderBlueprintList(entries) {
      blueprintListEl.innerHTML = "";
      if (!entries || entries.length === 0) {
        blueprintListEl.innerHTML = '<div style="color:var(--muted);padding:8px;text-align:center;font-size:12px">该项目暂无蓝本文件</div>';
        return;
      }

      // 全局蓝本选项（固定在顶部）
      var globalItem = document.createElement("label");
      globalItem.style.cssText = "display:flex;align-items:center;gap:4px;padding:4px 4px;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600;background:var(--bg-secondary,#1e1e1e);border:1px solid var(--border);margin-bottom:4px";
      globalItem.title = "勾选后将测试当前项目所有蓝本";
      
      var globalCb = document.createElement("input");
      globalCb.type = "checkbox";
      globalCb.id = "cbGlobalBlueprint";
      globalCb.checked = true;
      globalCb.style.cssText = "flex-shrink:0;width:14px;height:14px";
      
      var globalLabel = document.createElement("span");
      globalLabel.textContent = "🌍 全局蓝本（测试所有）";
      globalLabel.style.cssText = "flex:1;color:var(--fg)";
      
      globalItem.appendChild(globalCb);
      globalItem.appendChild(globalLabel);
      blueprintListEl.appendChild(globalItem);

      var divider = document.createElement("div");
      divider.style.cssText = "height:1px;background:var(--border);margin:4px 0";
      blueprintListEl.appendChild(divider);

      var platformBadges = {web:"🌐",android:"📱",ios:"📱",miniprogram:"💬",desktop:"🖥️"};

      entries.forEach(function(entry, i) {
        var path = typeof entry === "string" ? entry : entry.path;
        var appName = entry.appName || "";
        var desc = entry.description || "";
        var platform = entry.platform || "web";
        var scenarios = entry.scenarioCount || 0;
        var steps = entry.stepCount || 0;

        var parts = path.replace(/\\\\/g, "/").split("/");
        var shortPath = parts.slice(-3).join("/");
        var displayName = appName || shortPath;

        var platformBadge = platformBadges[platform] || "📄";
        var tooltipText = desc ? (desc + "\\n场景:" + scenarios + " 步骤:" + steps + "\\n" + path) : ("场景:" + scenarios + " 步骤:" + steps + "\\n" + path);

        var item = document.createElement("label");
        item.className = "local-blueprint-item";
        item.style.cssText = "display:flex;align-items:flex-start;gap:4px;padding:3px 4px;border-radius:4px;cursor:pointer;font-size:12px;line-height:1.4;overflow:hidden;width:100%;box-sizing:border-box";
        item.addEventListener("mouseenter", function() { item.style.background = "var(--hover-bg,#2a2d2e)"; });
        item.addEventListener("mouseleave", function() { item.style.background = "transparent"; });

        // 复选框区域（独立tooltip：操作提示）
        var cbWrap = document.createElement("span");
        cbWrap.className = "local-blueprint-cbwrap";
        cbWrap.style.cssText = "flex-shrink:0;display:inline-flex;align-items:center;padding:2px";
        cbWrap.title = "已启用全局蓝本，如需局部选择请先取消全局蓝本";
        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.className = "local-blueprint-cb";
        cb.value = path;
        cb.checked = false;
        cb.disabled = true;
        cb.style.cssText = "width:14px;height:14px;cursor:pointer";
        cbWrap.appendChild(cb);

        var fileName = path.replace(/\\\\/g, "/").split("/").pop() || path;

        // 内容区域（独立tooltip：蓝本详情）
        var info = document.createElement("div");
        info.className = "local-blueprint-info";
        info.style.cssText = "flex:1;min-width:0;overflow:hidden";
        info.title = tooltipText;
        info.innerHTML = '<div style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + platformBadge + ' ' + displayName + '</div>'
          + (desc ? '<div style="color:var(--muted);font-size:11px;margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + desc + '</div>' : '')
          + '<div style="color:var(--muted);font-size:10px;margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + scenarios + '场景 ' + steps + '步骤 · ' + fileName + '</div>';

        item.appendChild(cbWrap);
        item.appendChild(info);
        blueprintListEl.appendChild(item);
      });

      // 全局蓝本checkbox交互逻辑（Tooltip分区：复选框区=操作提示，内容区=蓝本详情）
      globalCb.addEventListener("change", function() {
        var localItems = blueprintListEl.querySelectorAll(".local-blueprint-item");
        var localCbs = blueprintListEl.querySelectorAll(".local-blueprint-cb");
        var cbWraps = blueprintListEl.querySelectorAll(".local-blueprint-cbwrap");
        if (globalCb.checked) {
          localCbs.forEach(function(cb) { cb.disabled = true; cb.checked = false; });
          localItems.forEach(function(item) { item.style.opacity = "0.5"; });
          // 复选框区：显示操作提示
          cbWraps.forEach(function(w) { w.title = "已启用全局蓝本，如需局部选择请先取消全局蓝本"; });
          // 内容区：保持蓝本详情不变（不覆盖）
        } else {
          localCbs.forEach(function(cb) { cb.disabled = false; });
          localItems.forEach(function(item) { item.style.opacity = "1"; });
          // 恢复复选框区提示
          cbWraps.forEach(function(w) { w.title = "勾选以加入局部测试"; });
        }
      });

      // 填入第一个路径到手动输入框
      var firstPath = typeof entries[0] === "string" ? entries[0] : entries[0].path;
      inputBlueprintPath.value = firstPath;
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

    var wasConnected = false;  // 防止重复触发连接成功日志和扫描
    function updateEngineStatus(data) {
      if (data.connected) {
        isStarting = false;
        engineFound = true;
        statusDot.className = "status-dot connected";
        engineStatus.textContent = "v" + (data.version || "?");
        btnLaunchEngine.classList.add("hidden");
        btnStopEngine.classList.remove("hidden");
        btnStopEngine.textContent = "⏹ 断开引擎";
        btnStopEngine.disabled = false;
        if (!wasConnected) {
          wasConnected = true;
          addLog("引擎连接成功 | v" + data.version, "success");
          // 引擎连接成功时自动重新扫描项目（仅首次）
          vscode.postMessage({ command: "scanBlueprints" });
        }
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

    let testingTimer = null;
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
      // 持续跳动提示，让用户知道系统在运行
      let dots = 0;
      const phases = ["正在连接模拟器...", "正在执行测试步骤...", "仍在测试中，请耐心等待..."];
      let phase = 0;
      if (testingTimer) clearInterval(testingTimer);
      testingTimer = setInterval(() => {
        dots = (dots + 1) % 4;
        const dotStr = ".".repeat(dots + 1);
        addLog("⏳ " + phases[phase] + dotStr, "info");
        if (dots === 3) phase = Math.min(phase + 1, phases.length - 1);
      }, 5000);
    }

    function onTestResult(report) {
      if (testingTimer) { clearInterval(testingTimer); testingTimer = null; }
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

      // 渲染步骤详情（自动展开）
      renderSteps(report.steps || []);
      if ((report.steps || []).length > 0) {
        stepExpanded = true;
        stepList.classList.remove("hidden");
        stepToggle.textContent = "📝 步骤详情 ▾";
      }

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
      if (testingTimer) { clearInterval(testingTimer); testingTimer = null; }
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
