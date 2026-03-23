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
          await this._handleCopyBugs(msg.report, msg.blueprintPath || "", msg.retryInfo || {});
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
          await this._handleCopyBlueprintPrompt(msg.platform || "web", msg.projectDir || "");
          break;
        case "platformPrecheck":
          await this._handlePlatformPrecheck(msg);
          break;
        case "checkDeviceStatus":
          await this._handleCheckDeviceStatus(msg);
          break;
        case "connectDevice":
          await this._handleConnectDevice(msg);
          break;
        case "openBlueprintFile":
          if (msg.filePath) {
            const fileUri = vscode.Uri.file(msg.filePath);
            vscode.workspace.openTextDocument(fileUri).then((doc) => {
              vscode.window.showTextDocument(doc, { preview: false });
            });
          }
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
      this._client.ensureWsConnected();
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
      // 测试前确保 WebSocket 已连接，保证步骤进度能实时推送到 WebView
      this._client.ensureWsConnected();
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
      const raw = err instanceof Error ? err.message : String(err);
      // 解析引擎返回的 JSON 错误详情（如 HTTP 400: {"detail":"Appium未就绪: ..."} ）
      let message = raw;
      try {
        const jsonMatch = raw.match(/\{[\s\S]*"detail"\s*:\s*"([^"]+)"/);
        if (jsonMatch) { message = jsonMatch[1]; }
      } catch { /* 解析失败用原始信息 */ }
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
      this._client.ensureWsConnected();
      this._postMessage({ command: "testStarted" });
      this._postMessage({ command: "batchTestStarted", count: msg.blueprint_paths.length });

      // 依次执行每个蓝本，汇总结果（用户停止时中断后续蓝本）
      const results: TestReportResponse[] = [];
      let userStopped = false;
      for (const bp of msg.blueprint_paths) {
        if (userStopped) { break; }
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

          // 检查是否被用户停止，停止则中断后续蓝本
          if (report.stopped) {
            userStopped = true;
          }
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
      if (userStopped) {
        md += `> ⚠️ 用户手动停止，已执行 ${results.length}/${msg.blueprint_paths.length} 个蓝本\n\n`;
      }
      md += `- 蓝本数: ${results.length}${userStopped ? `/${msg.blueprint_paths.length}` : ""}\n`;
      md += `- 总步骤: ${totalSteps}（通过 ${passedSteps} / 失败 ${failedSteps}）\n`;
      md += `- 总Bug数: ${totalBugs}\n`;
      md += `- 总通过率: ${passRate.toFixed(0)}%\n`;
      md += `- 总耗时: ${totalDuration.toFixed(1)}秒\n\n`;
      results.forEach((r, i) => {
        const icon = (r.bug_count || 0) === 0 && (r.total_steps || 0) > 0 ? "✅" : "❌";
        md += `## ${i + 1}. ${icon} ${r.test_name}\n`;
        md += `通过率: ${(r.pass_rate || 0).toFixed(0)}% | Bug: ${r.bug_count || 0}\n\n`;
      });

      // 合并所有蓝本的 bugs 和 steps（重新编号步骤，为bug打来源蓝本标签）
      let stepOffset = 0;
      const allSteps = results.flatMap((r, ri) => {
        const bpName = (r.test_name || `蓝本${ri + 1}`).replace(/\.testpilot\.json$/i, "");
        const steps = ((r as unknown as Record<string, unknown>).steps as unknown[] || []) as Record<string, unknown>[];
        const renumbered = steps.map((s, si) => ({
          ...s,
          step: stepOffset + si + 1,
          blueprint_label: bpName,
        }));
        stepOffset += steps.length;
        return renumbered;
      });
      const allBugs = results.flatMap((r, ri) => {
        const bpName = (r.test_name || `蓝本${ri + 1}`).replace(/\.testpilot\.json$/i, "");
        return ((r as unknown as Record<string, unknown>).bugs as unknown[] || []).map((b) => ({
          ...(b as Record<string, unknown>),
          category: `[${bpName}] ${(b as Record<string, unknown>).category || ""}`.trim(),
        }));
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
        bugs: allBugs as unknown as BugDetail[],
        steps: allSteps as unknown as StepDetail[],
        repair_summary: null,
        fixed_bug_count: null,
      };

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

  private _formatBugText(report: Record<string, unknown>, blueprintPath: string = "", retryInfo: Record<string, number> = {}): string {
    const bugCount = report.bug_count as number || 0;
    const lines: string[] = [
      `TestPilot AI 发现 ${bugCount} 个Bug，请修复：`,
      `测试: ${report.test_name} | URL: ${report.url} | 通过率: ${(report.pass_rate as number || 0).toFixed(0)}%`,
      "",
    ];
    const bugs = (report.bugs as Array<Record<string, unknown>>) || [];
    if (bugs.length > 0) {
      bugs.forEach((bug, i) => {
        const cat = (bug.category as string) || "";
        const bugDesc = (bug.description as string) || "";
        const bugTitle = (bug.title as string) || "";
        const bugSig = `${bug.step_number || "0"}|${bugTitle.substring(0, 40)}`;
        const retryCount = retryInfo[bugSig] || 0;  // ≥2 = 已失败3次（初次+2次重试）
        const step = bug.step_number ? ` (步骤#${bug.step_number})` : "";
        lines.push(`${i + 1}. [${(bug.severity as string || "medium").toUpperCase()}] ${cat ? cat + " " : ""}${bugTitle}${step}`);
        if (bugDesc) {
          const firstLine = bugDesc.split("\n")[0].substring(0, 200);
          lines.push(`   ${firstLine}`);
          // 显示根因分析（关键！编程AI需要看到Playwright的真正报错原因）
          if (bugDesc.includes("🔍 根因分析")) {
            const rootCause = bugDesc.split("🔍 根因分析: ")[1];
            if (rootCause) {
              lines.push(`   🔍 根因分析: ${rootCause.split("\n")[0].substring(0, 200)}`);
            }
          }
          // 显示修复建议
          if (bugDesc.includes("💡 修复建议")) {
            const suggestion = bugDesc.split("💡 修复建议")[1];
            if (suggestion) {
              lines.push(`   💡 修复建议${suggestion.split("\n")[0].substring(0, 200)}`);
            }
          }
        }
        // ── 智能归因提示（帮助AI判断是蓝本问题还是APP问题）──
        // 1. SnackBar/Toast 误判：断言失败但预期文本是瞬态消息关键词
        const snackbarKeywords = ["成功", "已添加", "已删除", "已保存", "已更新", "已提交", "完成"];
        const isAssertFail = bugDesc.includes("未找到预期文本") || bugTitle.includes("文本断言失败");
        const looksLikeSnackbar = snackbarKeywords.some(k => bugDesc.includes(`'${k}`) || bugDesc.includes(`"${k}`));
        if (isAssertFail && looksLikeSnackbar && !cat.includes("[蓝本问题]")) {
          lines.push(`   ⚠️ 归因提示：预期文本可能是 SnackBar/Toast 瞬态消息（2-3秒后消失），Appium检查时已消失。若APP确实显示了该提示，则这是【蓝本问题】，应将 assert_text 改为 screenshot。`);
        }
        // 2. accessibility_id 使用英文缩写而非实际 Semantics label
        const isElementNotFound = bugDesc.includes("元素找不到") || bugDesc.includes("no such element");
        const usesEnglishId = /accessibility_id:[a-z_]{3,}/.test(bugDesc) || /accessibility_id:[a-z_]{3,}/.test(bugTitle);
        if (isElementNotFound && usesEnglishId && !cat.includes("[蓝本问题]")) {
          lines.push(`   ⚠️ 归因提示：accessibility_id 使用了英文缩写（如 btn_login），但 Flutter/Android Semantics 通常映射为中文 label。请查看源码 Semantics(label:'xxx') 的实际值，更新蓝本选择器。大概率是【蓝本问题】。`);
        }
        // 3. XPath[@hint='xxx'] 在 Flutter 中不稳定
        if (isElementNotFound && bugDesc.includes("@hint=") && !cat.includes("[蓝本问题]")) {
          lines.push(`   ⚠️ 归因提示：XPath[@hint='xxx'] 在 Flutter 中不稳定（UiAutomator2 有时无法读取 EditText hint）。建议改用 Semantics label 的 accessibility_id 定位。大概率是【蓝本问题】。`);
        }
        // ── 顽固Bug多级递进分析 ──
        if (retryCount === 1) {
          lines.push(`   ⚠️ [第2次出现] 此Bug上次已出现过，修复后依然发生。请优先检查：蓝本断言是否本身有误？选择器是否精确对应源码？`);
        }
        if (retryCount >= 2) {
          lines.push(`   🚨 [顽固Bug × ${retryCount + 1}次] 此Bug已连续 ${retryCount + 1} 次出现，前几次修复均无效。请强制换思路深度分析：`);
          lines.push(`      ① expected 文本/元素在APP当前状态下真的可见/存在吗？（不要假设）`);
          lines.push(`      ② 你上几次的修复方向是否相同？如果是，本次必须换一个完全不同的角度`);
          lines.push(`      ③ 这究竟是APP逻辑Bug，还是蓝本断言本身不合理？`);
          lines.push(`      ④ 如果APP没有后端/数据库，操作后不会有文字反馈，断言应改为验证UI状态变化`);
          lines.push(`      ⑤ 禁止重复使用上一次失败的同一修复方案`);
        }
        if (retryCount >= 3) {
          lines.push(`   🚨🚨 [第${retryCount + 1}次·请人工介入] AI已无法独立解决此Bug，建议暂停AI自动修复，手动打开蓝本文件检查断言逻辑，并直接运行APP验证该操作的真实反馈，再决定修复方向。`);
        }
      });
    } else {
      lines.push((report.report_markdown as string || "").substring(0, 1000));
    }
    lines.push(
      "",
      "⚠️ 重要：每个Bug的category标签说明了错误归因：",
      "- [应用Bug]：被测应用代码有问题，请修复应用代码",
      "- [蓝本问题]：testpilot.json蓝本写错了（选择器错、动作类型错等），请修正蓝本文件",
      "- 无标签：需要你自行判断是应用问题还是蓝本问题",
      "- ⚠️ 归因提示：TestPilot AI基于规则的自动推断，供参考，请结合实际源码判断",
      "",
      "🔍 修复前请先自行判断每个Bug的真实来源，常见蓝本问题误报为[应用Bug]的情况：",
      "1. assert_text 断言了 SnackBar/Toast 等瞬态提示（2-3秒消失，Appium来不及检查）→ 改为 screenshot",
      "2. accessibility_id 使用了英文缩写（如 btn_login），而非源码 Semantics(label:'xxx') 的实际中文值 → 查源码更新选择器",
      "3. XPath[@hint='xxx'] 在 Flutter EditText 中不稳定 → 改用 Semantics label 的 accessibility_id",
      "4. 被测APP没有后端/数据库，操作后无持久化反馈 → 断言改为验证UI状态变化（如表单清空、余额数字变化），而非文字提示",
      "如果以上任何一条符合，请直接修改蓝本，不要改APP代码。",
      "",
    );
    // 闭环指令：包含蓝本路径，让编程AI能直接调用MCP工具重测
    if (blueprintPath) {
      lines.push(
        `请逐个修复以上Bug（蓝本错改蓝本，应用错改应用），修复后调用 run_blueprint_test 重新测试：`,
        `  blueprint_path: "${blueprintPath}"`,
        `重复修复+测试，直到全部通过为止。`,
      );
    } else {
      lines.push(
        "请逐个修复以上Bug（蓝本错改蓝本，应用错改应用），修复后调用 run_blueprint_test 重新测试，直到全部通过为止。",
      );
    }
    return lines.join("\n");
  }

  private async _handleCopyBugs(report: Record<string, unknown>, blueprintPath: string = "", retryInfo: Record<string, number> = {}): Promise<void> {
    const bugText = this._formatBugText(report, blueprintPath, retryInfo);

    // 按IDE类型依次尝试发送到聊天面板
    // 各IDE的 appHost / 扩展 ID 用于检测当前运行环境
    const chatCommands: Array<{ name: string; fn: () => Promise<void> }> = [
      {
        // Windsurf — Cascade 新建对话
        name: "Windsurf",
        fn: async () => { await vscode.commands.executeCommand("windsurf.newCascade", bugText); },
      },
      {
        // Trae（字节跳动）— 发送到 AI 对话
        name: "Trae",
        fn: async () => { await vscode.commands.executeCommand("trae.action.newChat", bugText); },
      },
      {
        // Cursor — 打开 Composer/Chat 并填入内容
        name: "Cursor",
        fn: async () => { await vscode.commands.executeCommand("aichat.newchataction", bugText); },
      },
      {
        // GitHub Copilot Chat（VS Code 原生）
        name: "Copilot",
        fn: async () => {
          await vscode.commands.executeCommand("workbench.action.chat.open", { query: bugText });
        },
      },
      {
        // Copilot Chat 旧版命令（VS Code < 1.90）
        name: "Copilot(legacy)",
        fn: async () => {
          await vscode.commands.executeCommand("github.copilot.chat", bugText);
        },
      },
    ];

    for (const { name, fn } of chatCommands) {
      try {
        await fn();
        vscode.window.showInformationMessage(`Bug报告已发送到 ${name} AI，等待修复`);
        return;
      } catch {
        // 当前IDE不支持此命令，继续尝试下一个
      }
    }

    // 所有IDE命令均不可用，兜底复制到剪贴板
    await vscode.env.clipboard.writeText(bugText);
    vscode.window.showInformationMessage("Bug摘要已复制到剪贴板，请粘贴到AI聊天窗口让AI修复");
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

  private async _handleCopyBlueprintPrompt(platform: string, projectDir: string = ""): Promise<void> {
    const platformNames: Record<string, string> = {
      web: "Web",
      miniprogram: "微信小程序",
      android: "Android/Flutter",
      desktop: "Windows桌面",
      ios: "iOS/SwiftUI",
    };
    const pName = platformNames[platform] || "Web";

    const lines: string[] = [];
    if (projectDir) {
      lines.push(`当前项目路径：${projectDir.replace(/\\/g, "/")}`);
      lines.push(`请直接读取该目录下的源代码生成蓝本，无需再次询问项目路径。`);
      lines.push(``);
    }
    lines.push(`请为当前【${pName}】项目生成或更新测试蓝本。`);
    lines.push(``);
    lines.push(`⚠️ 生成前请先按顺序完成以下步骤（缺一不可）：`);
    lines.push(`1. 阅读 AGENTS.md（蓝本通用规则）`);
    lines.push(`2. 阅读 .testpilot/platforms/${platform}.md（${pName}平台专属规则、选择器规范和完整模板）`);
    lines.push(`3. 通读项目源代码，确认已实现的功能列表`);
    lines.push(`4. 检查 testpilot/ 目录是否已有蓝本文件：`);
    lines.push(`   - 若【没有蓝本】：按规则从零生成完整蓝本，保存到 testpilot/ 目录`);
    lines.push(`   - 若【已有蓝本】：必须按以下步骤做增量更新（禁止跳过任意一步）：`);
    lines.push(`     a. 读取现有蓝本，列出其中所有 target 选择器`);
    lines.push(`     b. 对每个 target，在项目源码中搜索该选择器（用 id、class、placeholder、type 等真实属性）`);
    lines.push(`        - 搜到：保留`);
    lines.push(`        - 搜不到或已失效：更正为源码中实际存在的选择器`);
    lines.push(`     c. 检查源码中是否有新增功能未被现有蓝本覆盖，若有则补充对应场景`);
    lines.push(`     d. 检查已删除的功能，删除对应场景`);
    lines.push(`     e. 将更新后的完整蓝本覆盖写回原文件（禁止新建额外文件）`);
    lines.push(`     ⚠️ 禁止仅凭印象或整体扫描就宣布"无需更新"——必须逐个搜索验证每个 target`);

    const prompt = lines.join("\n");
    await vscode.env.clipboard.writeText(prompt);
    vscode.window.showInformationMessage(`✅ ${pName}蓝本提示词已复制！请粘贴给编程AI，它会先读规则文件再生成蓝本。`);
  }

  // ── 以下为旧版长提示词备份（已废弃，改用短口令模式） ──
  private async _handleCopyBlueprintPrompt_LEGACY(platform: string, projectDir: string = ""): Promise<void> {
    const commonRules = `══════ 测试设计黄金规则（必须严格遵守） ══════

【铁律0：每个项目必须有独立蓝本】
- 蓝本文件必须放在当前项目根目录下，不同项目绝对不能共用蓝本
- 不同平台（Web/小程序/Android/桌面）必须各自独立蓝本，platform字段不同
- <select>下拉框必须用 select 动作，不能用 fill（否则引擎报错"Element is not an input"）

【铁律00：场景自包含原则（极其重要）】
- 每个 scenario 必须能独立运行，不依赖前一个场景的状态
- 每个场景的第一步必须是 navigate 到起始页面
- 引擎会在每个场景开始前自动清除 cookie/storage，确保干净状态
- 禁止场景间传递状态（如场景1登录后场景2直接操作已登录页面）
- 正确：场景2需要登录态？那场景2自己从navigate→登录→操作，不要依赖场景1的登录

【核心哲学：绝对正向验证（最最重要！这是蓝本的灵魂）】
- 蓝本 = 假设一切功能完全正确的测试路线图
- 你不知道哪里有Bug，你认为所有功能都是对的，写出"正确时应该是什么样"的断言
- 当测试引擎跑蓝本发现"实际≠预期"时，那就是Bug——由引擎自动发现，不是你预知的
- ❌ 绝对禁止：看到代码有Bug就针对性写用例确认（这是作弊，不是测试）
- ✅ 正确做法：按功能正常逻辑写断言，Bug自然会暴露出来

【核心哲学：穷举每条路径（蓝本的完整性）】
- 信息来源分三层，但代码是唯一真相：
  1. 用户描述 → 帮你理解项目方向和整体意图（但用户可能描述的是愿景，很多功能还没实现）
  2. 你的理解 → 结合用户描述形成对功能的整体认知（但不要凭空假设功能存在）
  3. 代码穷举 → 这是唯一依据！代码里实现了什么就测什么，没实现的不测
- 流程：先听用户描述理解方向 → 再通读代码确认哪些功能已实现 → 对已实现的功能穷举测试路径
- 穷举 = 每条路径的每种合理输入变体都要试：
  搜索 → 精确匹配、部分匹配、大写、小写、混合大小写、空搜索（共6次）
  登录 → 正确账号、错误密码、空账号、空密码（共4次）
  数值输入 → 正常值、边界值、零、负数
  列表操作 → 添加、删除、编辑、排序（代码有的都试）
- 对每个功能，主动思考："这个功能有哪些合理的输入变体？" 然后每种都写测试
- 原则：宁可多测不可漏测，每个场景都以assert结尾

【规则1：功能全覆盖】
- 先通读全部源代码，列出所有功能点（每个按钮、每个表单、每个Tab、每个弹窗、每个下拉框）
- 每个功能点必须至少有一个测试场景，不能遗漏任何可操作的UI元素
- 自检清单：数一数代码里有多少个按钮/表单/页面，蓝本里是否每个都覆盖到了

【规则2：操作→断言配对（最核心）】
- 每一个操作（click/fill/select）后面必须跟一个断言（assert_text/assert_visible/screenshot）验证结果
- 错误示范：click登录按钮 → 结束（没验证是否登录成功）
- 正确示范：click登录按钮 → assert_text验证"欢迎回来"或验证用户名显示正确
- 原则：没有断言的操作等于没测
- 断言的expected必须写"正确时应该显示什么"，不要写"错误时会显示什么"

【规则3：业务流程端到端串联】
- 除了单点功能测试，必须有完整业务流程场景：
  例：注册→登录→浏览商品→加入购物车→填写地址→提交订单→查看订单详情
- 每个流程场景至少串联3个以上页面/功能

【规则4：断言必须严格基于代码逻辑（极其重要！禁止凭常识猜测）】
- 每个assert_text的expected值必须能在代码中找到出处（哪个变量、哪行代码会输出这个文本）
- 禁止凭"常识"或"应该这样"写断言。例：
  * 代码只验证非空就跳转 → 蓝本不能写"错误密码→登录失败"（代码根本不验证密码！）
  * 代码catch里写'登录失败' → 要看什么条件触发catch，不是所有错误都走这条路
- 必须追踪完整调用链：按钮点击→调用哪个函数→函数做了什么判断→跳转去哪→路由是否注册
  * 例：登录→pushReplacementNamed('/dashboard') → 检查main.dart是否注册了/dashboard路由
  * 路由未注册=应用Bug，蓝本正向写"记账台"断言，引擎会自动发现这个Bug
- 必须检查输入框是否有默认值（如TextEditingController(text:'admin')、value属性、defaultValue）
  * 有默认值时：蓝本的fill值会追加到默认值后面，而非替换！
  * 如果默认值已满足测试需求，可以跳过fill步骤直接点击提交

【规则5：状态变化验证】
- 操作前先读取当前状态值，操作后再读取，对比变化是否符合预期
- 例：加入购物车前读购物车数量=0，加入后断言数量=1
- 例：删除商品前列表有3条，删除后断言列表有2条

【规则6：异常和边界测试】
- 每个表单必须测试：空提交、超长输入、特殊字符、格式错误
- 每个需要权限的操作必须测试：未登录访问、无权限操作
- 验证错误提示消息是否正确显示

【规则7：弹窗和提示验证】
- 操作后出现的成功提示、错误提示、确认弹窗，必须用断言验证内容
- 例：提交订单后验证"下单成功"提示
- 例：删除操作后验证确认弹窗文字

【规则8：选择器规范】
- 使用代码中的真实 id（如 #login-btn）或稳定 class
- 禁止用 div:nth-child(3) 这类脆弱选择器
- 必须先阅读源代码确认选择器存在

【规则9：启动命令】
- 如果应用需要命令行启动（npm start、python app.py），必须填写 start_command 字段
- 纯HTML静态应用留空

【规则10：深度Bug挖掘（安全审计视角）】
- 请以资深QA架构师+安全审计师的双重视角审视代码，主动挖掘以下隐蔽Bug：
  * 认证绕过：密码是否真正校验？是否存在硬编码密码/万能密码？未登录能否直接访问受保护页面？
  * 数值精度：价格/金额计算是否用浮点加法（0.1+0.2≠0.3）？是否做了toFixed/Math.round处理？
  * 库存/数量边界：加购是否校验库存上限？数量能否改为负数/0/超大数？
  * 优惠/折扣逻辑：优惠金额是否真正从总价中扣除？满减条件是否正确判断？
  * 配送/运费逻辑：不同配送方式的运费计算是否正确？免费配送条件是否生效？
  * 状态一致性：前端显示的文字（如"免费"）与实际计算值是否一致？
  * 并发/重复提交：按钮是否有防重复点击？表单能否重复提交？
- 对于每个可疑逻辑，设计专门的验证场景：先构造触发条件，再用assert_text断言实际计算结果

【规则11：参考功能文档】
- 如果项目目录下存在 README.md、需求文档、功能说明、CHANGELOG 等文件，必须先阅读
- 根据文档中描述的功能清单逐一核对：文档说有的功能，蓝本必须覆盖
- 根据文档中的业务规则设计断言（如"满100免运费"→ 构造99元和100元两个场景分别验证）
- 如果没有文档，则从代码注释、变量命名、函数名中推断业务意图，对比实际行为是否一致

【规则12：截图策略（省钱省时）】
- 截图用于发现视觉Bug（布局溢出、元素遮挡、样式错乱、响应式崩坏），断言无法检测这类问题
- 规则：每个蓝本模块的第1个场景末尾加1张 screenshot，其余场景不加
  * 例：auth.testpilot.json 的第1个场景末尾 → screenshot（覆盖登录页视觉）
  * 例：cart.testpilot.json 的第1个场景末尾 → screenshot（覆盖购物车视觉）
  * 同模块的第2、3、4…个场景 → 不加 screenshot
- 断言失败时引擎会自动截图留证，蓝本不用额外写
- ❌ 禁止每个场景末尾都加 screenshot（浪费视觉大模型费用和时间）

【规则13：蓝本文件命名与拆分】
- 命名规范：
  * 主蓝本（小项目/全量测试）：testpilot/testpilot.json
  * 分模块蓝本（大项目按功能拆分）：testpilot/<模块名>.testpilot.json
- 拆分判断：页面≤3个用一个 testpilot.json；页面>3个按功能模块拆分
  * 例：auth.testpilot.json、cart.testpilot.json、checkout.testpilot.json
  * 跨页面的端到端流程归属到终点功能模块（如"加购→结算→下单"归入 checkout）
- 每个蓝本独立可运行，非首页场景开头要从 navigate 开始
- 全量测试时通过 run_blueprint_batch 批量运行所有蓝本

【规则14：蓝本管理（必须遵守！）】
- 每个被测应用目录下只允许一个 testpilot.json（或 testpilot/ 目录下按模块拆分）
- 若已存在 testpilot.json，直接覆盖更新，禁止创建 _v2/_new/_backup 等变体
- 功能较多时（页面>3个），按功能模块拆分到 testpilot/ 目录下：
  * testpilot/auth.testpilot.json（登录/注册）
  * testpilot/dashboard.testpilot.json（主功能）
  * testpilot/reports.testpilot.json（报表）
- 更新某模块时只替换该模块文件，不影响其他模块
- 不要在 testpilot/ 目录下堆积多个版本（如 auth_v1、auth_v2）

【规则15：蓝本增量修改（省Token）】
- 已有蓝本时，只修改/新增变更涉及的场景，不要重写整个文件
- 新增功能 → 新增场景追加到对应模块蓝本
- 修改功能 → 更新对应场景的步骤和断言
- 删除功能 → 删除对应场景
- 禁止每次都从零生成全新蓝本覆盖旧文件

【规则16：蓝本备忘录（testpilot/CHANGELOG.md）】
- 首次生成蓝本时，必须同时创建 testpilot/CHANGELOG.md
- 格式如下：
  # 蓝本备忘录
  ## 当前可测功能
  - [x] 登录（用户名+密码）
  - [x] 笔记列表（增删查）
  - [x] 搜索（关键词匹配）
  - [ ] 注册（未实现）
  ## 变更记录
  ### 2026-03-11
  - 初始蓝本：覆盖登录、笔记CRUD、搜索、异常输入
  ### 2026-03-15
  - 新增：标签功能（代码已实现）→ 新增场景3条
  - 修改：搜索支持标签过滤 → 更新搜索场景
- 每次修改代码后更新蓝本时，同步更新CHANGELOG.md
- AI接手项目时，先读CHANGELOG.md了解当前测试范围，避免对未实现功能写用例

重要提醒：以后修改代码时，主动审视并更新对应模块的蓝本和CHANGELOG.md，无需用户提醒！`;

    let prompt = "";
    if (platform === "miniprogram") {
      prompt = `请帮我为当前【微信小程序】项目生成测试蓝本文件 testpilot/testpilot.json。

⚠️ 小程序蓝本与Web蓝本完全不同！WXML不是HTML！必须严格遵守以下规则：

══════ 小程序选择器铁律（最最重要！写错=全部失败） ══════

以下Web选择器在小程序中【全部无效】：
  ❌ #login-btn（WXML不支持id选择器！）
  ❌ button:contains('登录')（不支持:contains伪类！）
  ❌ input[type="text"]（WXML的input没有type attribute！）
  ❌ div > span（WXML里是view/text，不是div/span！）
  ❌ picker:first / picker:nth(1)（不支持这类伪类！）

正确的小程序选择器写法（按优先级）：
  1. 用placeholder区分input：input[placeholder*='用户名']、input[placeholder*='密码']
  2. 用class区分按钮：button.btn-primary（配合description说明按钮文字）
  3. 用class组合定位：.card .form-input（结合父容器缩小范围）
  4. 用data-属性：view[data-tab='profit']、button[data-tab='balance']
  5. 用bindtap确认按钮：找到wxml中bindtap="handleLogin"的button，用它的class

══════ 小程序特有组件操作规则 ══════

【picker组件】不能用click！必须用select动作：
  ✅ {"action": "select", "target": "picker", "value": "收入", "description": "选择交易类型为收入"}
  ❌ {"action": "click", "target": "picker:first"}（picker是原生组件不能click）

【wx.showModal弹窗】蓝本无法操作！（原生弹窗不在DOM中）
  - 删除确认、退出确认等用showModal的功能，蓝本中跳过这些步骤
  - 或建议开发者改用页面内自定义弹窗组件

【wx.showToast提示】短暂显示后自动消失
  - 不要对toast内容做assert_text，用wait后断言页面数据变化

【TabBar页面切换】不能click TabBar！用navigate直接跳转：
  ✅ {"action": "navigate", "value": "pages/reports/reports", "description": "跳转到报表页"}
  ❌ {"action": "click", "target": "text:contains('报表')"}

══════ 小程序蓝本格式 ══════

{
  "app_name": "小程序名称",
  "description": "功能说明（50-200字）",
  "base_url": "miniprogram://D:/projects/项目绝对路径",
  "platform": "miniprogram",
  "pages": [
    {
      "url": "pages/login/login",
      "name": "登录页",
      "scenarios": [
        {
          "name": "正确登录",
          "steps": [
            {"action": "navigate", "value": "pages/login/login", "description": "打开登录页"},
            {"action": "fill", "target": "input[placeholder*='用户名']", "value": "admin", "description": "在用户名输入框输入admin"},
            {"action": "fill", "target": "input[placeholder*='密码']", "value": "admin123", "description": "在密码输入框输入admin123"},
            {"action": "click", "target": "button.btn-primary", "description": "点击登录按钮，按钮文字为'登录'，bindtap='handleLogin'"},
            {"action": "wait", "value": "2000", "description": "等待登录处理和页面跳转"},
            {"action": "assert_text", "expected": "记账台", "description": "验证成功跳转到记账台页面"},
            {"action": "screenshot", "description": "登录成功后的页面"}
          ]
        }
      ]
    }
  ]
}

══════ 小程序蓝本编写流程 ══════

1. 先读所有 .wxml 文件，列出每个页面的所有可操作元素（input/button/picker/switch等）
2. 记录每个元素的 class、placeholder、bindtap/bindchange 等属性
3. 再读对应 .js 文件，理解业务逻辑（登录验证规则、表单校验、页面跳转等）
4. 读 app.json 确认页面路由和tabBar配置
5. 用上面提取的真实选择器写蓝本，禁止凭想象编造选择器

══════ 小程序蓝本自检 ══════

- [ ] 所有target都不含 #id（WXML不支持）
- [ ] 所有target都不含 :contains()（不支持）
- [ ] input用placeholder属性区分，不用id
- [ ] picker用select动作，不用click
- [ ] base_url是 miniprogram://绝对路径
- [ ] TabBar跳转用navigate，不用click
- [ ] 没有操作wx.showModal/wx.showToast等原生弹窗
- [ ] 每个选择器都能在wxml中找到对应元素

${commonRules}`;
    } else if (platform === "android") {
      const androidRules = `
【蓝本格式】
{ "app_name": "应用名称", "description": "功能说明", "base_url": "", "version": "1.0",
  "platform": "android", "app_package": "com.example.myapp", "app_activity": ".MainActivity",
  "pages": [{ "url": "", "title": "页面标题", "scenarios": [{ "name": "场景名", "steps": [
    {"action": "wait", "value": "2000", "description": "等待加载"},
    {"action": "fill", "target": "accessibility_id:et_username", "value": "admin", "description": "输入用户名"},
    {"action": "click", "target": "accessibility_id:btn_login", "description": "点击登录"},
    {"action": "assert_text", "target": "accessibility_id:tv_result", "expected": "预期文本", "description": "验证结果"}
  ]}]}]}

【必填字段】app_package（包名）、app_activity（启动Activity）、platform="android"

【选择器规范（极重要！禁止CSS选择器！）】
- 优先用 accessibility_id:xxx（Android的contentDescription / Flutter的Semantics label）
- 其次用 xpath://android.widget.Button[@text='登录']
- Flutter: 检查 Semantics(label:'xxx') 或 Key('xxx')
- 原生Android: 检查 android:contentDescription="xxx"
- 必须先阅读源代码确认选择器存在！

【支持的action】navigate(value=包名/Activity) / click / fill / wait / screenshot / assert_text(必须有expected) / scroll(value=up/down)

【测试数据规范（必须遵守！）】
- fill的value必须用纯ASCII字符（英文+数字+符号），禁止中文！原因：中文输入法会吞字符
- 示例：admin、admin123、wrong_pass、test@email.com

【节奏控制（必须遵守！）】
- APP启动后 wait 2000；页面跳转后 wait 1500-2000；navigate后 wait 1500
- 对话框操作后 wait 500；fill操作自带等待不需额外加
- 输入速度已在引擎层面放慢，蓝本不需要额外控制

【场景设计（正向验证原则）】
- 第1个场景必须是正常流程（如正确登录），确保进入主页面
- 异常场景放后面，每个用navigate回到起始页
- assert_text的expected写"功能正确时应该显示的值"，不要预知Bug
- 搜索功能必须分别测试：原文搜索、小写搜索、大写搜索、部分匹配，每个都断言能找到结果
  例：数据里有"Hello World" → 搜"Hello"断言找到 + 搜"hello"断言找到 + 搜"HELLO"断言找到
- 数值计算必须用具体值断言：添加30字的笔记 → 断言总字数=30，不要写"大约"
- 截图：每页第1个场景末尾加1张screenshot，其余不加`;

      prompt = `请帮我为当前【Android原生/Flutter】项目生成测试蓝本文件 testpilot/testpilot.json。

⚠️ 移动端蓝本与Web蓝本完全不同！严格遵守以下规则：
${androidRules}

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

    if (projectDir) {
      const dirForPrompt = projectDir.replace(/\\/g, "/");
      prompt = `当前项目路径：${dirForPrompt}\n请直接读取该目录下的源代码生成蓝本，无需再次询问项目路径。\n\n` + prompt;
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
        // 一次性检测设备+Appium Server
        const check = await this._client.mobilePrecheck();
        this._postMessage({
          command: "platformPrecheckResult",
          data: {
            ok: check.ok,
            platform,
            message: check.message,
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

  private async _handleConnectDevice(_msg: { platform?: string }): Promise<void> {
    const { exec, spawn } = require("child_process") as typeof import("child_process");
    const run = (cmd: string): Promise<string> =>
      new Promise((resolve) => {
        exec(cmd, { timeout: 10000 }, (_err, stdout) => resolve(stdout || ""));
      });
    const http = require("http") as typeof import("http");
    const httpCheck = (url: string): Promise<boolean> =>
      new Promise((resolve) => {
        const req = http.get(url, (res: import("http").IncomingMessage) => resolve(res.statusCode === 200));
        req.on("error", () => resolve(false));
        req.setTimeout(3000, () => { req.destroy(); resolve(false); });
      });
    const fail = (message: string) => {
      this._postMessage({ command: "connectDeviceResult", data: { ok: false, message } });
    };
    try {
      // 0. 先检查引擎是否已连接（未连接则提示先启动引擎）
      const engineOk = await httpCheck("http://127.0.0.1:8900/api/v1/health");
      if (!engineOk) {
        fail("引擎未启动，请先点击「启动引擎」按钮，再进行握手");
        return;
      }
      // 1. 检查 adb 是否可用
      const adbVersion = await run("adb version");
      if (!adbVersion.includes("Android Debug Bridge")) {
        fail("未检测到 ADB，请安装 Android SDK Platform-Tools 并添加到 PATH");
        return;
      }
      // 2. 检查设备是否连接
      const devicesOutput = await run("adb devices");
      const deviceLines = devicesOutput.split("\n").filter((l) => l.includes("\tdevice"));
      if (deviceLines.length === 0) {
        fail("未检测到 Android 设备。请：\n1. USB连接手机\n2. 开启USB调试\n3. 手机弹窗点击'允许调试'");
        return;
      }
      const serial = deviceLines[0].split("\t")[0];
      const model = (await run(`adb -s ${serial} shell getprop ro.product.model`)).trim() || serial;
      // 3. 检查手机是否安装 uiautomator2 server（Appium 自动化组件）
      const pkgList = await run(`adb -s ${serial} shell pm list packages`);
      const hasUia2 = pkgList.includes("io.appium.uiautomator2.server");
      if (!hasUia2) {
        fail(`设备 ${model} 未安装 Appium 自动化组件（uiautomator2），首次测试时会自动安装。\n也可手动运行：appium driver install uiautomator2`);
        return;
      }
      // 4. 检查 Appium server 是否运行，未运行则自动启动
      let appiumOk = await httpCheck("http://127.0.0.1:4723/status");
      if (!appiumOk) {
        // 自动启动 Appium
        this._postMessage({
          command: "connectDeviceResult",
          data: { ok: false, message: `设备 ${model} 就绪，Appium 未运行，正在自动启动...` },
        });
        try {
          spawn("appium", ["--port", "4723"], { detached: true, stdio: "ignore", shell: true, windowsHide: true }).unref();
        } catch (spawnErr: unknown) {
          fail(`Appium 启动失败: ${spawnErr instanceof Error ? spawnErr.message : String(spawnErr)}\n请手动运行：appium --port 4723`);
          return;
        }
        // 等待 Appium 启动（最多12秒）
        for (let i = 0; i < 12; i++) {
          await new Promise<void>((r) => setTimeout(r, 1000));
          if (await httpCheck("http://127.0.0.1:4723/status")) { appiumOk = true; break; }
        }
        if (!appiumOk) {
          fail(`设备 ${model} 就绪，但 Appium 启动超时（12秒）。\n请手动运行：appium --port 4723`);
          return;
        }
      }
      // 5. 全部就绪
      this._postMessage({
        command: "connectDeviceResult",
        data: { ok: true, message: `握手成功 ✅ | 设备: ${model} | Appium: 就绪 | 引擎: 就绪` },
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      fail(`握手异常: ${message}`);
    }
  }

  private async _handleCheckDeviceStatus(msg: { platform?: string }): Promise<void> {
    const platform = (msg.platform || "web").toLowerCase();
    if (platform !== "android" && platform !== "ios") { return; }
    const { exec } = require("child_process") as typeof import("child_process");
    const run = (cmd: string): Promise<string> =>
      new Promise((resolve) => {
        exec(cmd, { timeout: 8000 }, (_err, stdout) => resolve(stdout || ""));
      });
    try {
      const output = await run("adb devices");
      const lines = output.split("\n").filter((l) => l.includes("\tdevice"));
      if (lines.length === 0) {
        this._postMessage({
          command: "deviceStatusResult",
          data: { connected: false, message: "未检测到设备，请连接手机并开启USB调试", deviceName: "" },
        });
        return;
      }
      const serial = lines[0].split("\t")[0];
      const model = (await run(`adb -s ${serial} shell getprop ro.product.model`)).trim() || serial;
      const resRaw = (await run(`adb -s ${serial} shell wm size`)).trim();
      const resolution = resRaw.includes(":") ? resRaw.split(":").pop()!.trim() : "";
      const androidVer = (await run(`adb -s ${serial} shell getprop ro.build.version.release`)).trim();
      const infoParts = [model, resolution, androidVer ? `Android ${androidVer}` : ""].filter(Boolean);
      this._postMessage({
        command: "deviceStatusResult",
        data: { connected: true, message: `${infoParts.join("，")}`, deviceName: model },
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      this._postMessage({
        command: "deviceStatusResult",
        data: { connected: false, message: `检测失败: ${message}`, deviceName: "" },
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
    body { position: relative; }
    :root {
      --bg: var(--vscode-sideBar-background, #1e1e1e);
      --fg: var(--vscode-sideBar-foreground, #cccccc);
      --input-bg: var(--vscode-input-background, #3c3c3c);
      --input-border: var(--vscode-input-border, rgba(255,255,255,0.35));
      --input-fg: var(--vscode-input-foreground, #cccccc);
      --btn-bg: var(--vscode-button-background, #0e639c);
      --btn-fg: var(--vscode-button-foreground, #ffffff);
      --btn-hover: var(--vscode-button-hoverBackground, #1177bb);
      --muted: var(--vscode-descriptionForeground, rgba(204,204,204,0.55));
      --success: #4ec9b0;
      --error: #f44747;
      --warn: #cca700;
      --info: var(--vscode-descriptionForeground, #9d9d9d);
      --editor-bg: var(--vscode-editor-background, #252526);
    }
    body.light-mode {
      --bg: #e8e8e8;
      --fg: #1e1e1e;
      --input-bg: #f5f5f5;
      --input-border: rgba(0,0,0,0.2);
      --input-fg: #1e1e1e;
      --btn-bg: #007acc;
      --btn-fg: #ffffff;
      --btn-hover: #005a9e;
      --muted: rgba(0,0,0,0.45);
      --info: #5a5a5a;
      --editor-bg: #dedede;
    }
    body.light-mode { background: var(--bg); color: var(--fg); }
    body.light-mode button {
      border-color: rgba(0,0,0,0.18);
    }
    body.light-mode button:hover {
      border-color: rgba(0,0,0,0.35);
    }
    body.light-mode .btn-secondary {
      background: rgba(0,0,0,0.06);
      border-color: rgba(0,0,0,0.18);
      color: var(--fg);
    }
    body.light-mode .btn-secondary:hover {
      background: rgba(0,0,0,0.12);
      border-color: rgba(0,0,0,0.3);
    }
    /* Toggle switch */
    .toggle-switch { position:relative; display:inline-block; width:40px; height:22px; }
    .toggle-switch input { opacity:0; width:0; height:0; }
    .toggle-slider {
      position:absolute; cursor:pointer; inset:0;
      background:rgba(128,128,128,0.4); border-radius:22px;
      transition:.3s;
    }
    .toggle-slider:before {
      content:""; position:absolute; height:16px; width:16px;
      left:3px; bottom:3px; background:#fff; border-radius:50%;
      transition:.3s;
    }
    .toggle-switch input:checked + .toggle-slider { background:var(--btn-bg); }
    .toggle-switch input:checked + .toggle-slider:before { transform:translateX(18px); }
    /* Settings panel */
    .settings-row {
      display:flex; justify-content:space-between; align-items:center;
      padding:10px 2px; border-bottom:1px solid var(--input-border);
    }
    .settings-row:last-child { border-bottom:none; }
    .settings-row span { font-size:13px; }
    .badge-soon {
      font-size:10px; color:var(--muted);
      background:var(--input-bg); border:1px solid var(--input-border);
      padding:1px 7px; border-radius:8px;
    }
    /* 齿轮按钮（随内容滚动） */
    .gear-btn {
      width:26px; min-width:26px; padding:2px; margin:0;
      background:transparent; border:none;
      font-size:15px; line-height:1; cursor:pointer;
      color:var(--muted); border-radius:4px;
      flex-shrink:0;
    }
    .gear-btn:hover { background:var(--input-bg); color:var(--fg); border:none; }
    .gear-btn.active-gear { color:var(--btn-bg); }
    /* 设置浮动下拉菜单 */
    .settings-dropdown {
      position:absolute; top:100%; right:0; z-index:1000;
      min-width:210px;
      background:var(--input-bg); color:var(--fg);
      border:1px solid var(--input-border);
      border-radius:5px;
      box-shadow:0 4px 20px rgba(0,0,0,0.4);
      padding:4px 0;
      display:none;
    }
    .settings-dropdown.open { display:block; }
    .sdrop-section {
      font-size:10px; color:var(--muted);
      padding:6px 12px 2px; letter-spacing:0.5px;
    }
    .sdrop-item {
      display:flex; justify-content:space-between; align-items:center;
      padding:7px 12px; font-size:12px; color:var(--fg); cursor:pointer;
      gap:12px;
    }
    .sdrop-item:hover { background:var(--hover-bg, rgba(128,128,128,0.15)); }
    .sdrop-item.disabled { opacity:0.5; cursor:default; }
    .sdrop-item.disabled:hover { background:transparent; }
    .sdrop-divider { height:1px; background:var(--input-border); margin:4px 0; }
    .sdrop-sublabel {
      font-size:10px; color:var(--muted);
      padding:0 12px 6px; text-align:right;
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
      border: 1px solid rgba(255,255,255,0.55); border-radius: 3px; cursor: pointer;
    }
    button:hover { background: var(--btn-hover); border-color: rgba(255,255,255,0.85); }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-secondary { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.6); color: var(--fg); }
    .btn-secondary:hover { background: rgba(255,255,255,0.15); border-color: rgba(255,255,255,0.85); }
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
      background: var(--editor-bg);
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
      background: var(--editor-bg);
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

    /* 经验库样式 */
    .exp-item { border:1px solid var(--input-border); border-radius:4px; padding:8px; margin-bottom:6px; font-size:11px; }
    .exp-item:hover { border-color:var(--btn-bg); }
    .exp-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; }
    .exp-title { font-weight:600; color:var(--fg); flex:1; }
    .exp-badges { display:flex; gap:3px; flex-shrink:0; }
    .exp-badge { padding:1px 5px; border-radius:8px; font-size:10px; font-weight:600; }
    .badge-platform { background:#1e40af22; color:#60a5fa; }
    .badge-hard { background:#7f1d1d22; color:#f87171; }
    .badge-medium { background:#78350f22; color:#fbbf24; }
    .badge-easy { background:#14532d22; color:#4ade80; }
    .exp-solution { color:var(--fg); margin-bottom:3px; line-height:1.4; }
    .exp-cause { color:var(--muted); font-size:10px; margin-bottom:3px; }
    .exp-failed { color:#f87171; font-size:10px; margin-bottom:3px; }
    .exp-meta { display:flex; gap:8px; color:var(--muted); font-size:10px; }
    .exp-actions { display:flex; gap:4px; margin-top:5px; }
    .exp-actions button { font-size:10px; padding:2px 6px; flex:0; }
    .exp-empty { text-align:center; color:var(--muted); padding:20px; font-size:12px; }

    /* Bug列表样式 */
    .bug-item {
      background: var(--editor-bg);
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
    <!-- 标题行：引擎字 + 齿轮设置按钮（随页面滚动） -->
    <div style="display:flex;align-items:center;margin-bottom:8px;position:relative">
      <h2 style="margin-bottom:0;flex:1">
        <span class="status-dot disconnected" id="statusDot"></span>
        引擎: <span id="engineStatus">未连接</span>
      </h2>
      <div style="position:relative;flex-shrink:0">
        <button class="gear-btn" id="btnGearSettings" title="设置">⚙️</button>
        <div id="settingsDropdown" class="settings-dropdown">
          <div class="sdrop-section">个性化设置</div>
          <div class="sdrop-item" id="settingsThemeRow">
            <span>🌓 界面主题</span>
            <label class="toggle-switch" onclick="event.stopPropagation()">
              <input type="checkbox" id="themeToggle" />
              <span class="toggle-slider"></span>
            </label>
          </div>
          <div class="sdrop-sublabel" id="themeLabel">🌙 深色模式</div>
          <div class="sdrop-divider"></div>
          <div class="sdrop-item disabled">
            <span>🌐 界面语言</span>
            <span class="badge-soon">即将推出</span>
          </div>
          <div class="sdrop-item disabled">
            <span>🔤 字体大小</span>
            <span class="badge-soon">即将推出</span>
          </div>
          <div class="sdrop-item disabled">
            <span>🔑 账户登录</span>
            <span class="badge-soon">即将推出</span>
          </div>
        </div>
      </div>
    </div>
    <!-- 项目选择器 -->
    <div style="display:flex;gap:4px;align-items:center;margin:6px 0">
      <select id="projectSelect" style="flex:1;font-size:12px;padding:4px 6px" disabled>
        <option value="">暂无测试项目</option>
      </select>
      <button id="btnRefreshProjects" class="btn-secondary" style="width:28px;min-width:28px;margin:0;padding:3px;font-size:13px" title="刷新项目列表">🔄</button>
    </div>
    <button class="btn-secondary hidden" id="btnCheckEngine">检查连接</button>
    <!-- 设备状态提示（仅Android/iOS项目显示） -->
    <div id="deviceStatusRow" class="hidden" style="background:var(--editor-bg);border:1px solid var(--input-border);border-radius:3px;padding:6px 8px;margin:6px 0;font-size:11px">
      <div style="display:flex;align-items:flex-start;gap:4px;margin-bottom:4px">
        <span id="deviceStatusIcon" style="flex-shrink:0;line-height:1.4">📱</span>
        <span id="deviceStatusText" style="color:var(--muted);word-break:break-word;line-height:1.4">检测中...</span>
      </div>
      <div style="display:flex;gap:4px;margin-top:2px">
        <button id="btnDetectDevice" class="btn-secondary" style="font-size:10px;padding:3px 6px;flex:1">检测设备</button>
        <button id="btnHandshake" class="btn-secondary hidden" style="font-size:10px;padding:3px 6px;flex:1">🤝 握手</button>
      </div>
      <div id="handshakeStatusRow" class="hidden" style="display:flex;align-items:center;gap:4px;margin-top:4px;font-size:10px">
        <span id="handshakeIcon">⏳</span>
        <span id="handshakeText" style="color:var(--muted);word-break:break-word">未握手</span>
      </div>
    </div>
    <div style="display:flex;gap:4px;margin-top:6px">
      <button id="btnLaunchEngine" style="background:#22c55e;flex:1">🚀 一键启动引擎</button>
      <button id="btnStopEngine" class="hidden" style="background:#ef4444;flex:1">⏹ 断开引擎</button>
    </div>
  </div>

  <!-- 模式切换Tab -->
  <div class="section">
    <div class="tab-bar">
      <button class="active" id="tabBlueprint">蓝本模式</button>
      <button id="tabExplore">探索模式</button>
      <button id="tabCommunity">经验库</button>
    </div>

    <!-- 蓝本模式 -->
    <div class="tab-content active" id="panelBlueprint">
      <label>蓝本列表
        <span style="font-size:11px;color:var(--muted);margin-left:4px">（勾选要测试的蓝本）</span>
      </label>
      <div id="blueprintList" style="max-height:280px;overflow-y:auto;border:1px solid var(--input-border);border-radius:3px;padding:4px;font-size:11px;margin-bottom:4px;background:var(--editor-bg)"></div>
      <div class="btn-row" style="margin-top:4px">
        <button class="btn-secondary" id="btnScanBp" style="flex:1;font-size:11px;padding:4px">🔍 扫描蓝本</button>
        <button class="btn-secondary" id="btnBrowseBp" style="flex:1;font-size:11px;padding:4px">📂 浏览文件</button>
      </div>
      <input type="text" id="inputBlueprintPath" placeholder="或手动输入路径..." style="font-size:11px;margin-top:4px" />

      <label>覆盖 base_url（可选）</label>
      <input type="text" id="inputBpBaseUrl" placeholder="http://localhost:3000" />

      <button id="btnBlueprintTest" class="btn-secondary">▶ 运行选中蓝本</button>
      <hr style="border:0;border-top:1px solid var(--input-border);margin:10px 0" />
      <button id="btnCopyBlueprintPrompt" class="btn-secondary">📋 复制蓝本生成提示词</button>
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

    <!-- 经验库 -->
    <div class="tab-content" id="panelCommunity">
      <div style="margin-bottom:8px">
        <input type="text" id="communitySearch" placeholder="搜索经验（错误类型、平台...）" style="font-size:11px" />
        <div style="display:flex;gap:4px;margin-top:4px">
          <select id="communityPlatform" style="flex:1;font-size:11px;padding:4px">
            <option value="">全部平台</option>
            <option value="web">Web</option>
            <option value="android">Android</option>
            <option value="desktop">桌面</option>
            <option value="miniprogram">小程序</option>
          </select>
          <button class="btn-secondary" id="btnSearchCommunity" style="flex:1;font-size:11px;padding:4px">🔍 搜索</button>
          <button class="btn-secondary" id="btnRefreshCommunity" style="font-size:11px;padding:4px">↻</button>
        </div>
      </div>
      <div id="communityStats" style="font-size:11px;color:var(--muted);margin-bottom:6px">加载中...</div>
      <div id="communityList" style="max-height:350px;overflow-y:auto"></div>
      <hr style="border:0;border-top:1px solid var(--border);margin:8px 0"/>
      <div style="font-size:11px;color:var(--muted);margin-bottom:4px">📤 分享修复经验</div>
      <input type="text" id="shareErrorType" placeholder="错误类型（如 element_not_found）" style="font-size:11px" />
      <input type="text" id="shareSolution" placeholder="修复方案描述" style="font-size:11px;margin-top:4px" />
      <input type="text" id="shareRootCause" placeholder="根本原因（可选）" style="font-size:11px;margin-top:4px" />
      <select id="sharePlatform" style="font-size:11px;margin-top:4px;width:100%;padding:4px">
        <option value="web">Web</option>
        <option value="android">Android</option>
        <option value="desktop">桌面</option>
        <option value="miniprogram">小程序</option>
      </select>
      <select id="shareDifficulty" style="font-size:11px;margin-top:4px;width:100%;padding:4px">
        <option value="easy">⭐ 简单</option>
        <option value="medium" selected>⭐⭐ 中等</option>
        <option value="hard">⭐⭐⭐ 困难</option>
      </select>
      <button id="btnShareExperience" style="margin-top:6px;background:#8b5cf6">📤 分享到社区</button>
      <div id="shareResult" style="font-size:11px;margin-top:4px;display:none"></div>
    </div>

  </div>

  <!-- 测试控制 -->
  <div class="section hidden" id="controlSection">
    <div class="btn-row">
      <button class="btn-secondary" id="btnPause">⏸ 暂停</button>
      <button class="btn-secondary" id="btnResume">▶ 继续</button>
      <button class="btn-secondary" id="btnStop">⏹ 停止</button>
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
    const tabCommunity = document.getElementById("tabCommunity");
    const panelBlueprint = document.getElementById("panelBlueprint");
    const panelExplore = document.getElementById("panelExplore");
    const panelCommunity = document.getElementById("panelCommunity");
    const allTabs = [tabBlueprint, tabExplore, tabCommunity];
    const allPanels = [panelBlueprint, panelExplore, panelCommunity];
    const btnGear = document.getElementById("btnGearSettings");
    const settingsDropdown = document.getElementById("settingsDropdown");

    function switchTab(activeTab, activePanel) {
      allTabs.filter(Boolean).forEach(t => t.classList.remove("active"));
      allPanels.filter(Boolean).forEach(p => p.classList.remove("active"));
      if (activeTab) activeTab.classList.add("active");
      if (activePanel) activePanel.classList.add("active");
      if (btnGear) btnGear.classList.remove("active-gear");
      if (settingsDropdown) settingsDropdown.classList.remove("open");
    }
    tabBlueprint.addEventListener("click", () => switchTab(tabBlueprint, panelBlueprint));
    tabExplore.addEventListener("click", () => switchTab(tabExplore, panelExplore));
    if (tabCommunity) tabCommunity.addEventListener("click", () => {
      switchTab(tabCommunity, panelCommunity);
      loadCommunityExperiences();
    });
    // 右上角齿轮：弹出浮动下拉菜单
    if (btnGear) btnGear.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = settingsDropdown.classList.contains("open");
      settingsDropdown.classList.toggle("open", !isOpen);
      btnGear.classList.toggle("active-gear", !isOpen);
    });
    // 点击外部关闭下拉菜单
    document.addEventListener("click", (e) => {
      if (settingsDropdown && settingsDropdown.classList.contains("open")) {
        if (!settingsDropdown.contains(e.target) && e.target !== btnGear) {
          settingsDropdown.classList.remove("open");
          if (btnGear) btnGear.classList.remove("active-gear");
        }
      }
    });

    // 主题切换
    const themeToggle = document.getElementById("themeToggle");
    const themeLabel = document.getElementById("themeLabel");
    function applyTheme(isLight) {
      if (isLight) {
        document.body.classList.add("light-mode");
        themeLabel.textContent = "☀️ 浅色模式";
      } else {
        document.body.classList.remove("light-mode");
        themeLabel.textContent = "🌙 深色模式";
      }
    }
    try {
      const savedTheme = localStorage.getItem("tp-theme");
      if (savedTheme === "light") { themeToggle.checked = true; applyTheme(true); }
      else { applyTheme(false); }
    } catch(e) {}
    themeToggle.addEventListener("change", (e) => {
      const isLight = e.target.checked;
      try { localStorage.setItem("tp-theme", isLight ? "light" : "dark"); } catch(e) {}
      applyTheme(isLight);
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

    // 握手按钮（检测设备+自动启动Appium）
    document.getElementById("btnHandshake").addEventListener("click", () => {
      const btn = document.getElementById("btnHandshake");
      const row = document.getElementById("handshakeStatusRow");
      const icon = document.getElementById("handshakeIcon");
      const text = document.getElementById("handshakeText");
      btn.disabled = true;
      btn.textContent = "⏳ 握手中...";
      row.classList.remove("hidden");
      icon.textContent = "⏳";
      text.textContent = "正在检测 Appium 环境...";
      text.style.color = "var(--muted)";
      vscode.postMessage({ command: "connectDevice", platform: getCurrentPlatform() });
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
    // 顽固Bug重试计数：key=签名(步骤号|标题前40字), value=累计出现次数（localStorage持久化，Reload Window不丢失）
    var bugRetryMap = (function() {
      try { return JSON.parse(localStorage.getItem("tp_bug_retry") || "{}"); } catch(e) { return {}; }
    })();
    function saveBugRetryMap() {
      try { localStorage.setItem("tp_bug_retry", JSON.stringify(bugRetryMap)); } catch(e) {}
    }

    // 复制Bug给AI
    document.getElementById("btnCopyBugs").addEventListener("click", () => {
      if (!lastReport) { addLog("暂无测试报告", "error"); return; }
      // 附带蓝本路径，让编程AI知道调run_blueprint_test时传什么路径
      var bpPath = document.getElementById("inputBlueprintPath").value.trim();
      vscode.postMessage({ command: "copyBugs", report: lastReport, blueprintPath: bpPath, retryInfo: bugRetryMap });
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
    let launchTimeoutId = null;  // 防止多次点击导致旧 timer 覆盖按钮状态
    document.getElementById("btnCheckEngine").addEventListener("click", () => {
      vscode.postMessage({ command: "checkEngine" });
    });

    // 一键启动引擎
    btnLaunchEngine.addEventListener("click", () => {
      isStarting = true;
      engineFound = false;
      vscode.postMessage({ command: "launchEngine" });
      btnLaunchEngine.classList.add("hidden");
      btnStopEngine.classList.remove("hidden");
      btnStopEngine.textContent = "⏹ 断开引擎";
      btnStopEngine.disabled = false;
      addLog("正在启动引擎，请稍候（最长约25秒）...", "info");

      // 清除旧 timer，防止多次点击互相干扰
      if (launchTimeoutId) { clearTimeout(launchTimeoutId); launchTimeoutId = null; }

      // 分别在 8s / 16s / 25s 重试检查连接，连接成功后停止后续检查
      const delays = [8000, 16000, 25000];
      function scheduleCheck(idx) {
        if (idx >= delays.length || engineFound) { return; }
        launchTimeoutId = setTimeout(() => {
          if (engineFound) { return; }
          vscode.postMessage({ command: "checkEngine" });
          scheduleCheck(idx + 1);
        }, delays[idx] - (idx > 0 ? delays[idx - 1] : 0));
      }
      scheduleCheck(0);
    });

    // 断开引擎
    btnStopEngine.addEventListener("click", () => {
      isStarting = false;
      wasConnected = false;
      engineFound = false;
      vscode.postMessage({ command: "stopEngine" });
      btnStopEngine.textContent = "⏳ 断开中...";
      btnStopEngine.disabled = true;
      addLog("正在断开引擎...", "info");
      setTimeout(() => {
        btnLaunchEngine.classList.remove("hidden");
        btnStopEngine.classList.add("hidden");
      }, 2000);
    });

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
      const selOpt = sel && sel.selectedOptions[0];
      const platform = selOpt ? (selOpt.dataset.platform || "web") : "web";
      const projectDir = selOpt ? (selOpt.dataset.projectDir || "") : "";
      vscode.postMessage({ command: "copyBlueprintPrompt", platform: platform, projectDir: projectDir });
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
        case "batchTestStarted": onBatchTestStarted(msg.count); break;
        case "testResult": onTestResult(msg.data); break;
        case "testError": onTestError(msg.data); break;
        case "progress": onProgress(msg.data); break;
        case "controlResult": addLog("控制: " + msg.data.action + " → " + msg.data.state, "info"); break;
        case "controlError": addLog("控制失败: " + msg.data.error, "error"); break;
        case "blueprintList": onBlueprintList(msg.data); break;
        case "blueprintSelected": onBlueprintSelected(msg.data); break;
        case "platformPrecheckResult": onPlatformPrecheckResult(msg.data); break;
        case "deviceStatusResult": onDeviceStatusResult(msg.data); break;
        case "connectDeviceResult": onConnectDeviceResult(msg.data); break;
      }
    });

    function onDeviceStatusResult(data) {
      const statusText = document.getElementById("deviceStatusText");
      const statusIcon = document.getElementById("deviceStatusIcon");
      const btnHandshake = document.getElementById("btnHandshake");
      if (!data) return;
      if (data.connected) {
        statusText.textContent = (data.message || "设备已连接") + "（运行蓝本时自动连接）";
        statusText.style.color = "var(--success,#22c55e)";
        statusIcon.textContent = "✅";
        btnHandshake.classList.remove("hidden");
      } else {
        statusText.textContent = data.message || "未检测到设备";
        statusText.style.color = "var(--error,#ef4444)";
        statusIcon.textContent = "❌";
        btnHandshake.classList.add("hidden");
        document.getElementById("handshakeStatusRow").classList.add("hidden");
      }
    }

    function onConnectDeviceResult(data) {
      const row = document.getElementById("handshakeStatusRow");
      const icon = document.getElementById("handshakeIcon");
      const text = document.getElementById("handshakeText");
      const btn = document.getElementById("btnHandshake");
      row.classList.remove("hidden");
      btn.disabled = false;
      btn.textContent = "🤝 握手";
      if (data.ok) {
        icon.textContent = "✅";
        text.textContent = data.message || "握手成功";
        text.style.color = "var(--success,#22c55e)";
      } else {
        icon.textContent = "❌";
        text.textContent = data.message || "握手失败";
        text.style.color = "var(--error,#ef4444)";
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
        });
      } else {
        vscode.postMessage({
          command: "blueprintTest",
          blueprint_path: run.paths[0],
          base_url: run.baseUrl,
          platform: run.platform,
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
        opt.dataset.projectDir = proj.projectDir || "";
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

      // 检测是否全部为空壳蓝本（pages为空）
      var allEmpty = entries.every(function(e) { return (e.scenarioCount || 0) === 0; });
      if (allEmpty) {
        var emptyHint = document.createElement("div");
        emptyHint.style.cssText = "color:var(--warning,#f59e0b);padding:8px;text-align:center;font-size:11px;line-height:1.6;background:rgba(245,158,11,0.08);border-radius:4px;margin-bottom:6px";
        emptyHint.innerHTML = '⚠️ 蓝本为空壳，尚无测试场景<br>请点击下方「📋 复制蓝本生成提示词」<br>粘贴给编程AI自动生成完整蓝本';
        blueprintListEl.appendChild(emptyHint);
      }

      // 全局蓝本选项（固定在顶部）
      var globalItem = document.createElement("label");
      globalItem.style.cssText = "display:flex;align-items:center;gap:4px;padding:4px 4px;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600;background:var(--editor-bg);border:1px solid var(--input-border);margin-bottom:4px";
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
        item.addEventListener("mouseenter", function() { item.style.background = "var(--input-bg)"; });
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

        // 右键菜单：打开蓝本文件
        info.addEventListener("contextmenu", function(e) {
          e.preventDefault();
          e.stopPropagation();
          vscode.postMessage({ command: "openBlueprintFile", filePath: path });
        });
        // 双击也可打开
        info.addEventListener("dblclick", function(e) {
          e.preventDefault();
          vscode.postMessage({ command: "openBlueprintFile", filePath: path });
        });
        info.style.cursor = "pointer";

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
          vscode.postMessage({ command: "scanBlueprints" });
        }
      } else {
        statusDot.className = "status-dot disconnected";
        engineStatus.textContent = isStarting ? "启动中..." : "未连接";
        if (!isStarting) {
          btnLaunchEngine.classList.remove("hidden");
          btnStopEngine.classList.add("hidden");
          wasConnected = false;
        }
        addLog(isStarting ? "引擎尚未就绪，继续等待..." : "引擎未连接，点击「🚀 一键启动引擎」按钮启动", isStarting ? "warn" : "error");
      }
    }

    let testingTimer = null;
    let inBatchMode = false;
    let batchTotal = 0;
    let batchDone = 0;

    function onBatchTestStarted(count) {
      inBatchMode = true;
      batchTotal = count || 0;
      batchDone = 0;
    }

    function onTestStarted() {
      controlSection.classList.remove("hidden");
      resultSection.classList.add("hidden");
      // 批量模式下，每个蓝本的 send_test_started() 都会触发此函数，
      // 绝对不能清除 inBatchMode！否则后续蓝本的 WS test_done 会覆盖合并结果。
      // 仅在非批量模式（真正的新一轮测试）时才清除和重置UI。
      if (!inBatchMode) {
        // 立即清空上一轮的Bug列表和步骤详情
        bugList.innerHTML = "";
        bugTotal.textContent = "0";
        bugSection.classList.add("hidden");
        stepList.innerHTML = "";
        stepSection.classList.add("hidden");
        logArea.innerHTML = "";
        addLog("测试任务已启动，步骤进度将实时显示...", "info");
      }
      if (testingTimer) clearInterval(testingTimer);
      testingTimer = null;
    }

    function onTestResult(report) {
      if (testingTimer) { clearInterval(testingTimer); testingTimer = null; }
      // 注意：不在此处清除 inBatchMode！
      // WS test_done 可能作为宏任务晚于此处到达，会覆盖合并结果。
      // inBatchMode 仅在 onTestStarted（新一轮测试）时清除。
      lastReport = report;
      // 更新顽固Bug计数（签名 = 步骤号|标题前40字）
      (report.bugs || []).forEach(function(bug) {
        var sig = (bug.step_number || "0") + "|" + (bug.title || "").substring(0, 40);
        bugRetryMap[sig] = (bugRetryMap[sig] || 0) + 1;
      });
      // 通过的步骤清零对应sig（Bug已修复，不再计为顽固）
      (report.steps || []).forEach(function(step) {
        if (step.status === "passed") {
          var prefix = String(step.step || "0") + "|";
          Object.keys(bugRetryMap).forEach(function(sig) {
            if (sig.startsWith(prefix)) { delete bugRetryMap[sig]; }
          });
        }
      });
      saveBugRetryMap();
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
      renderBugs(report.bugs || [], bugRetryMap);

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

      if (report.fixed_bug_count > 0) {
        showSharePrompt(report);
      }
    }

    function showSharePrompt(report) {
      const banner = document.createElement("div");
      banner.className = "share-prompt";
      banner.style.cssText = "background:var(--bg-secondary);border:1px solid var(--border);border-radius:6px;padding:8px;margin-top:8px;font-size:11px";
      banner.innerHTML =
        '<div style="margin-bottom:4px">🎉 成功修复 <b>' + report.fixed_bug_count + '</b> 个Bug！分享你的修复经验帮助其他开发者？</div>' +
        '<div style="display:flex;gap:4px">' +
          '<button id="btnAutoShare" class="btn-secondary" style="flex:1;font-size:10px;padding:3px 6px">📤 分享到社区</button>' +
          '<button id="btnDismissShare" class="btn-secondary" style="font-size:10px;padding:3px 6px;opacity:0.6">不了</button>' +
        '</div>';
      resultSection.appendChild(banner);

      document.getElementById("btnDismissShare").onclick = () => banner.remove();
      document.getElementById("btnAutoShare").onclick = () => {
        banner.remove();
        const bugs = report.bugs || [];
        const firstBug = bugs[0] || {};
        document.getElementById("shareErrorType").value = firstBug.title || firstBug.category || "test_bug";
        document.getElementById("shareSolution").value = "修复了 " + report.fixed_bug_count + " 个Bug: " + bugs.map(b => b.title || b.description || "").filter(Boolean).join("; ");
        document.getElementById("shareRootCause").value = firstBug.description || "";

        const tabs = document.querySelectorAll(".tab-btn");
        const panels = document.querySelectorAll(".tab-content");
        tabs.forEach(t => t.classList.remove("active"));
        panels.forEach(p => p.classList.remove("active"));
        tabs[2].classList.add("active");
        document.getElementById("panelCommunity").classList.add("active");
      };
    }

    function renderBugs(bugs, retryMap) {
      retryMap = retryMap || {};
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
        var bugSig = (bug.step_number || "0") + "|" + (bug.title || "").substring(0, 40);
        var rc = retryMap[bugSig] || 0;
        var retryBadge = rc >= 3
          ? ' <span style="color:var(--error,#ef4444);font-size:10px;font-weight:600">🚨×' + rc + ' 需人工介入</span>'
          : rc >= 2
            ? ' <span style="color:var(--warning,#f59e0b);font-size:10px">🔁×' + rc + '</span>'
            : '';
        div.innerHTML =
          '<div class="bug-title">' +
            '<span class="severity-badge ' + sev + '">' + sev.toUpperCase() + '</span>' +
            escapeHtml(bug.title || "Bug #" + (i+1)) +
            retryBadge +
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
        const labelHtml = s.blueprint_label
          ? '<span class="step-bp" title="' + escapeHtml(s.blueprint_label) + '" style="font-size:10px;color:var(--info);flex-shrink:0;max-width:60px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">[' + escapeHtml(s.blueprint_label) + ']</span>'
          : '';
        div.innerHTML =
          '<span class="step-icon">' + icon + '</span>' +
          '<span class="step-num">#' + s.step + '</span>' +
          labelHtml +
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
        test_started: "info",
        step_start: "info", step_done: "success", bug_found: "warn",
        repair_start: "info", repair_done: "success", test_done: "success",
        error: "error", log: "info", state_change: "info", terminal_log: "info",
      };
      // 后端推送test_started时，显示控制按钮（Android/iOS测试）
      if (wsMsg.type === "test_started") {
        onTestStarted();
        return;
      }
      // 截图推送
      if (wsMsg.type === "screenshot" && wsMsg.data?.image) {
        screenshotSection.classList.remove("hidden");
        screenshotImg.src = "data:image/png;base64," + wsMsg.data.image;
        return;
      }
      // test_done: 批量模式下只记日志，不覆盖最终合并结果
      if (wsMsg.type === "test_done" && inBatchMode) {
        batchDone++;
        const pct = wsMsg.data?.pass_rate !== undefined ? wsMsg.data.pass_rate.toFixed(0) + "%" : "?";
        const bugCnt = wsMsg.data?.bug_count ?? "?";
        addLog("[" + batchDone + "/" + batchTotal + "] 蓝本完成 通过率" + pct + " Bug:" + bugCnt, "info");
        return;
      }
      // test_done: render full report if available, otherwise show summary
      if (wsMsg.type === "test_done") {
        if (wsMsg.data?.report) {
          onTestResult(wsMsg.data.report);
          return;
        }
        // Fallback: build a minimal report from WS summary data
        // This ensures result card always shows even if full_report is missing
        if (wsMsg.data?.pass_rate !== undefined) {
          const minimal = {
            test_name: "蓝本测试",
            pass_rate: wsMsg.data.pass_rate,
            passed_steps: 0,
            total_steps: 0,
            bug_count: wsMsg.data.bug_count || 0,
            duration_seconds: 0,
            bugs: [],
            steps: [],
          };
          onTestResult(minimal);
          addLog("⚠️ 结果摘要已显示，完整Bug详情等待HTTP返回...", "warn");
          return;
        }
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

    // ── 社区经验库 ──────────────────────────────────────────
    const communityList = document.getElementById("communityList");
    const communityStats = document.getElementById("communityStats");
    const communitySearch = document.getElementById("communitySearch");
    const communityPlatform = document.getElementById("communityPlatform");
    const btnSearchCommunity = document.getElementById("btnSearchCommunity");
    const btnRefreshCommunity = document.getElementById("btnRefreshCommunity");
    const btnShareExperience = document.getElementById("btnShareExperience");
    const shareResult = document.getElementById("shareResult");

    let engineBaseUrl = "http://127.0.0.1:8900/api/v1";
    const remoteBaseUrl = "https://testpilot.xinzaoai.com/api/v1";

    async function resolveBaseUrl() {
      try {
        const r = await fetch("http://127.0.0.1:8900/api/v1/health", { signal: AbortSignal.timeout(2000) });
        if (r.ok) { engineBaseUrl = "http://127.0.0.1:8900/api/v1"; return; }
      } catch {}
      engineBaseUrl = remoteBaseUrl;
    }

    async function loadCommunityExperiences() {
      await resolveBaseUrl();
      const platform = communityPlatform.value;
      const search = communitySearch.value.trim();
      communityList.innerHTML = '<div class="exp-empty">加载中...</div>';

      try {
        const statsResp = await fetch(engineBaseUrl + "/community/stats");
        if (statsResp.ok) {
          const stats = await statsResp.json();
          communityStats.textContent = "共 " + stats.total_experiences + " 条经验 | 👍 " + (stats.total_upvotes || 0) + " 次点赞 | ✅ " + stats.total_adoptions + " 次采纳";
        }

        let url;
        if (search) {
          url = engineBaseUrl + "/community/experiences/suggest?error_type=" + encodeURIComponent(search);
          if (platform) url += "&platform=" + encodeURIComponent(platform);
          url += "&limit=20";
        } else {
          url = engineBaseUrl + "/community/experiences?per_page=20";
          if (platform) url += "&platform=" + encodeURIComponent(platform);
        }

        const resp = await fetch(url);
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        renderCommunityExperiences(data.items || []);
      } catch (e) {
        communityList.innerHTML = '<div class="exp-empty">⚠️ 无法加载经验库<br><small>本地引擎未启动且无法连接服务器，请检查网络</small></div>';
        communityStats.textContent = "未连接";
      }
    }

    function renderCommunityExperiences(items) {
      if (!items || items.length === 0) {
        communityList.innerHTML = '<div class="exp-empty">暂无经验<br><small>测试后遇到Bug，修复后可分享到这里</small></div>';
        return;
      }
      communityList.innerHTML = "";
      items.slice(0, 10).forEach((exp) => {
        const diffClass = exp.difficulty === "hard" ? "badge-hard" : exp.difficulty === "easy" ? "badge-easy" : "badge-medium";
        const diffLabel = exp.difficulty === "hard" ? "⭐⭐⭐" : exp.difficulty === "easy" ? "⭐" : "⭐⭐";
        const tagsHtml = exp.tags && exp.tags.length > 0
          ? '<span>' + exp.tags.slice(0,3).map(t => '#' + t).join(' ') + '</span>'
          : "";

        const div = document.createElement("div");
        div.className = "exp-item";
        div.innerHTML =
          '<div class="exp-header">' +
            '<span class="exp-title">' + escapeHtml(exp.title || exp.error_type || "未知错误") + '</span>' +
            '<span class="exp-badges">' +
              '<span class="exp-badge badge-platform">' + escapeHtml(exp.platform) + '</span>' +
              '<span class="exp-badge ' + diffClass + '">' + diffLabel + '</span>' +
            '</span>' +
          '</div>' +
          '<div class="exp-solution">💡 ' + escapeHtml(exp.solution_desc || "") + '</div>' +
          (exp.root_cause ? '<div class="exp-cause">🔍 根因: ' + escapeHtml(exp.root_cause) + '</div>' : '') +
          '<div class="exp-meta">' +
            '<span>👍 ' + (exp.upvote_count || 0) + '</span>' +
            '<span>✅ 采纳 ' + (exp.adoption_count || 0) + '</span>' +
            '<span>👁 ' + (exp.view_count || 0) + '</span>' +
            (exp.share_score > 0 ? '<span>📊 ' + exp.share_score + '分</span>' : '') +
            tagsHtml +
          '</div>' +
          '<div class="exp-actions">' +
            '<button data-action="vote" data-id="' + exp.id + '" class="btn-secondary">👍 赞</button>' +
            '<button data-action="adopt" data-id="' + exp.id + '" style="background:#16a34a;font-size:10px;padding:2px 6px">✅ 采纳</button>' +
          '</div>';
        communityList.appendChild(div);
      });
    }

    async function voteExp(expId, up) {
      try {
        const resp = await fetch(engineBaseUrl + "/community/experiences/" + expId + "/vote", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ vote_type: up ? "upvote" : "downvote" }),
        });
        if (resp.ok) { loadCommunityExperiences(); }
      } catch(e) {}
    }

    async function adoptExp(expId) {
      try {
        const resp = await fetch(engineBaseUrl + "/community/experiences/" + expId + "/vote", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ vote_type: "adopt" }),
        });
        if (resp.ok) { loadCommunityExperiences(); }
      } catch(e) {}
    }

    if (communityList) communityList.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-action]");
      if (!btn) return;
      const id = btn.dataset.id;
      if (btn.dataset.action === "vote") voteExp(id, true);
      else if (btn.dataset.action === "adopt") adoptExp(id);
    });

    if (btnSearchCommunity) btnSearchCommunity.addEventListener("click", loadCommunityExperiences);
    if (btnRefreshCommunity) btnRefreshCommunity.addEventListener("click", loadCommunityExperiences);
    if (communitySearch) communitySearch.addEventListener("keydown", (e) => { if (e.key === "Enter") loadCommunityExperiences(); });

    if (btnShareExperience) btnShareExperience.addEventListener("click", async () => {
      const errorType = document.getElementById("shareErrorType").value.trim();
      const solution = document.getElementById("shareSolution").value.trim();
      const rootCause = document.getElementById("shareRootCause").value.trim();
      const platform = document.getElementById("sharePlatform").value;
      const difficulty = document.getElementById("shareDifficulty").value;

      if (!errorType || !solution) {
        shareResult.style.display = "block";
        shareResult.style.color = "#f87171";
        shareResult.textContent = "错误类型和修复方案不能为空";
        return;
      }
      if (solution.length < 10) {
        shareResult.style.display = "block";
        shareResult.style.color = "#f87171";
        shareResult.textContent = "修复方案描述至少 10 个字符";
        return;
      }

      btnShareExperience.disabled = true;
      btnShareExperience.textContent = "预览中...";
      shareResult.style.display = "none";

      const payload = {
        title: errorType,
        platform,
        error_type: errorType,
        problem_desc: errorType + " - " + solution,
        solution_desc: solution,
        root_cause: rootCause,
        difficulty,
        tags: [platform, errorType.split(/[\s_]+/)[0]].filter(Boolean),
      };

      try {
        const previewResp = await fetch(engineBaseUrl + "/community/share/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const preview = await previewResp.json();

        if (!preview.validation.valid) {
          shareResult.style.display = "block";
          shareResult.style.color = "#f87171";
          shareResult.textContent = "❌ 审核不通过: " + preview.validation.reasons.join("; ");
          btnShareExperience.disabled = false;
          btnShareExperience.textContent = "📤 分享到社区";
          return;
        }

        shareResult.style.display = "block";
        shareResult.style.color = "var(--muted)";
        shareResult.innerHTML = "📊 价值评分: <b>" + preview.score + "/10</b> | 匿名化预览: " + escapeHtml((preview.anonymized.solution_desc || "").substring(0, 80)) + "...";

        btnShareExperience.textContent = "✅ 确认分享";
        btnShareExperience.onclick = async function confirmShare() {
          btnShareExperience.disabled = true;
          btnShareExperience.textContent = "上传中...";
          try {
            const resp = await fetch(engineBaseUrl + "/community/share/direct", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });
            const data = await resp.json();
            shareResult.style.display = "block";
            if (data.ok) {
              shareResult.style.color = "#4ade80";
              shareResult.textContent = "✅ 分享成功！评分: " + (data.score_breakdown ? data.score_breakdown.total : "-") + "/10";
              document.getElementById("shareErrorType").value = "";
              document.getElementById("shareSolution").value = "";
              document.getElementById("shareRootCause").value = "";
              loadCommunityExperiences();
            } else {
              shareResult.style.color = "#fbbf24";
              shareResult.textContent = "⚠️ " + (data.error || "分享失败") + (data.reasons ? ": " + data.reasons.join("; ") : "");
            }
          } catch(err) {
            shareResult.style.color = "#f87171";
            shareResult.textContent = "上传失败: " + err.message;
          } finally {
            btnShareExperience.disabled = false;
            btnShareExperience.textContent = "📤 分享到社区";
            btnShareExperience.onclick = null;
          }
        };
        btnShareExperience.disabled = false;
      } catch(e) {
        shareResult.style.display = "block";
        shareResult.style.color = "#f87171";
        shareResult.textContent = "预览失败: " + e.message;
        btnShareExperience.disabled = false;
        btnShareExperience.textContent = "📤 分享到社区";
      }
    });

    // 初始检查 + 轮询（最长60秒/每5秒，连接后自动停止，解决Trae等IDE WebView渲染慢导致按钮状态不更新的问题）
    vscode.postMessage({ command: "checkEngine" });
    let _initPollCount = 0;
    const _initPollId = setInterval(() => {
      _initPollCount++;
      if (wasConnected || _initPollCount >= 12) { clearInterval(_initPollId); return; }
      vscode.postMessage({ command: "checkEngine" });
    }, 5000);
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
