/**
 * TestPilot AI — VSCode/Windsurf Extension 入口
 *
 * 激活时注册：
 * - 侧边栏 Webview Provider（测试面板）
 * - 命令面板命令（开始测试/停止测试/查看报告/自动修复/检查引擎）
 * - 右键菜单（文件夹 → 用 TestPilot AI 测试）
 * - WebSocket 连接（实时接收测试进度）
 */

import * as vscode from "vscode";
import { EngineClient } from "./engineClient";
import { SidebarProvider } from "./sidebarProvider";

let client: EngineClient;
let outputChannel: vscode.OutputChannel;

export function activate(context: vscode.ExtensionContext): void {
  outputChannel = vscode.window.createOutputChannel("TestPilot AI");
  outputChannel.appendLine("[TestPilot AI] 插件已激活");

  // 初始化引擎客户端
  client = new EngineClient();

  // 注册侧边栏
  const sidebarProvider = new SidebarProvider(context.extensionUri, client);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(SidebarProvider.viewType, sidebarProvider),
  );

  // 尝试连接 WebSocket
  client.connectWs();

  // 监听进度并写入 Output Channel
  context.subscriptions.push(
    client.onProgress((msg) => {
      const text = typeof msg.data?.message === "string" ? msg.data.message : msg.type;
      outputChannel.appendLine(`[${msg.type}] ${text}`);
    }),
  );

  // ── 注册命令 ────────────────────────────────────

  // 开始测试
  context.subscriptions.push(
    vscode.commands.registerCommand("testpilot-ai.startTest", async () => {
      const url = await vscode.window.showInputBox({
        prompt: "请输入被测应用的 URL",
        placeHolder: "http://localhost:3000",
        validateInput: (v) => (v.trim() ? null : "URL 不能为空"),
      });
      if (!url) { return; }

      const description = await vscode.window.showInputBox({
        prompt: "应用描述（可选）",
        placeHolder: "电商网站、管理后台...",
      });

      const focusOptions = ["核心功能", "用户注册登录", "表单验证", "页面导航", "数据展示"];
      const focus = await vscode.window.showQuickPick(focusOptions, {
        placeHolder: "选择测试重点",
      });

      const config = vscode.workspace.getConfiguration("testpilotAI");
      const autoRepair = config.get<boolean>("autoRepair", false);
      const reasoningEffort = config.get<string>("reasoningEffort", "medium");

      let projectPath = "";
      if (autoRepair) {
        const folders = vscode.workspace.workspaceFolders;
        projectPath = folders?.[0]?.uri.fsPath || "";
        if (!projectPath) {
          const picked = await vscode.window.showOpenDialog({
            canSelectFolders: true,
            canSelectFiles: false,
            openLabel: "选择项目根目录",
          });
          projectPath = picked?.[0]?.fsPath || "";
        }
      }

      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "TestPilot AI 测试中...",
          cancellable: false,
        },
        async (progress) => {
          try {
            progress.report({ message: "正在连接引擎..." });
            const report = await client.startTest({
              url,
              description: description || "",
              focus: focus || "核心功能",
              reasoning_effort: reasoningEffort,
              auto_repair: autoRepair,
              project_path: projectPath,
            });

            const passRate = report.pass_rate.toFixed(0);
            const msg = `测试完成 | 通过率 ${passRate}% | Bug ${report.bug_count} 个`;

            if (report.bug_count === 0) {
              vscode.window.showInformationMessage(`✅ ${msg}`);
            } else {
              const action = await vscode.window.showWarningMessage(
                `⚠️ ${msg}`,
                "复制Bug给AI",
                "查看报告",
              );
              if (action === "复制Bug给AI") {
                const bugSummary = formatBugSummaryForAI(report);
                await vscode.env.clipboard.writeText(bugSummary);
                vscode.window.showInformationMessage("Bug摘要已复制到剪贴板，粘贴到聊天窗口让AI修复");
              } else if (action === "查看报告") {
                showReport(report.report_markdown);
              }
            }

            outputChannel.appendLine("─".repeat(40));
            outputChannel.appendLine(report.report_markdown);
          } catch (err: unknown) {
            const message = err instanceof Error ? err.message : String(err);
            vscode.window.showErrorMessage(`TestPilot AI 测试失败: ${message}`);
          }
        },
      );
    }),
  );

  // 蓝本模式测试（v2.3）
  context.subscriptions.push(
    vscode.commands.registerCommand("testpilot-ai.blueprintTest", async () => {
      const folders = vscode.workspace.workspaceFolders;
      const defaultPath = folders?.[0]?.uri.fsPath
        ? `${folders[0].uri.fsPath}/testpilot.json`
        : "";

      const blueprintPath = await vscode.window.showInputBox({
        prompt: "请输入蓝本文件路径（testpilot.json）",
        value: defaultPath,
        validateInput: (v) => (v.trim() ? null : "蓝本路径不能为空"),
      });
      if (!blueprintPath) { return; }

      const baseUrl = await vscode.window.showInputBox({
        prompt: "被测应用 URL（可选，覆盖蓝本中的 base_url）",
        placeHolder: "http://localhost:3000",
      });

      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "TestPilot AI 蓝本测试中...",
          cancellable: false,
        },
        async (progress) => {
          try {
            progress.report({ message: "正在连接引擎..." });
            const report = await client.startBlueprintTest({
              blueprint_path: blueprintPath,
              base_url: baseUrl || undefined,
            });

            const passRate = report.pass_rate.toFixed(0);
            const msg = `蓝本测试完成 | 通过率 ${passRate}% | Bug ${report.bug_count} 个`;

            if (report.bug_count === 0) {
              vscode.window.showInformationMessage(`✅ ${msg}`);
            } else {
              const action = await vscode.window.showWarningMessage(
                `⚠️ ${msg}`,
                "复制Bug给AI",
                "查看报告",
              );
              if (action === "复制Bug给AI") {
                const bugSummary = formatBugSummaryForAI(report);
                await vscode.env.clipboard.writeText(bugSummary);
                vscode.window.showInformationMessage("Bug摘要已复制到剪贴板，粘贴到聊天窗口让AI修复");
              } else if (action === "查看报告") {
                showReport(report.report_markdown);
              }
            }
            outputChannel.appendLine("─".repeat(40));
            outputChannel.appendLine(report.report_markdown);
          } catch (err: unknown) {
            const message = err instanceof Error ? err.message : String(err);
            vscode.window.showErrorMessage(`蓝本测试失败: ${message}`);
          }
        },
      );
    }),
  );

  // 停止测试（v2.3）
  context.subscriptions.push(
    vscode.commands.registerCommand("testpilot-ai.stopTest", async () => {
      try {
        const result = await client.controlTest("stop");
        vscode.window.showInformationMessage(`TestPilot AI: 测试已停止 (${result.state})`);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`停止失败: ${message}`);
      }
    }),
  );

  // 暂停测试（v2.3）
  context.subscriptions.push(
    vscode.commands.registerCommand("testpilot-ai.pauseTest", async () => {
      try {
        const result = await client.controlTest("pause");
        vscode.window.showInformationMessage(`TestPilot AI: 测试已暂停 (${result.state})`);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`暂停失败: ${message}`);
      }
    }),
  );

  // 继续测试（v2.3）
  context.subscriptions.push(
    vscode.commands.registerCommand("testpilot-ai.resumeTest", async () => {
      try {
        const result = await client.controlTest("resume");
        vscode.window.showInformationMessage(`TestPilot AI: 测试已继续 (${result.state})`);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`继续失败: ${message}`);
      }
    }),
  );

  // 查看报告
  context.subscriptions.push(
    vscode.commands.registerCommand("testpilot-ai.viewReport", async () => {
      try {
        const history = await client.getHistory(undefined, 1);
        if (!history || history.length === 0) {
          vscode.window.showInformationMessage("暂无测试报告");
          return;
        }
        const latest = history[0] as Record<string, unknown>;
        const markdown = (latest.report_markdown as string) || "无报告内容";
        showReport(markdown);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`获取报告失败: ${message}`);
      }
    }),
  );

  // 自动修复
  context.subscriptions.push(
    vscode.commands.registerCommand("testpilot-ai.autoRepair", () => {
      vscode.window.showInformationMessage(
        'TestPilot AI: 自动修复功能请在测试配置中勾选「发现Bug后自动修复」，或在设置中开启 testpilotAI.autoRepair',
      );
    }),
  );

  // 右键菜单 → 用 TestPilot AI 测试
  context.subscriptions.push(
    vscode.commands.registerCommand("testpilot-ai.testFolder", async (uri: vscode.Uri) => {
      const folderPath = uri.fsPath;
      const url = await vscode.window.showInputBox({
        prompt: `测试项目: ${folderPath}\n请输入被测应用的 URL`,
        placeHolder: "http://localhost:3000",
        validateInput: (v) => (v.trim() ? null : "URL 不能为空"),
      });
      if (!url) { return; }

      const config = vscode.workspace.getConfiguration("testpilotAI");

      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "TestPilot AI 测试中...",
          cancellable: false,
        },
        async () => {
          try {
            const report = await client.startTest({
              url,
              description: "",
              focus: "核心功能",
              reasoning_effort: config.get<string>("reasoningEffort", "medium"),
              auto_repair: config.get<boolean>("autoRepair", false),
              project_path: folderPath,
            });
            const passRate = report.pass_rate.toFixed(0);
            vscode.window.showInformationMessage(
              `TestPilot AI 完成 | 通过率 ${passRate}% | Bug ${report.bug_count} 个`,
            );
            showReport(report.report_markdown);
          } catch (err: unknown) {
            const message = err instanceof Error ? err.message : String(err);
            vscode.window.showErrorMessage(`测试失败: ${message}`);
          }
        },
      );
    }),
  );

  // 检查引擎状态
  context.subscriptions.push(
    vscode.commands.registerCommand("testpilot-ai.checkEngine", async () => {
      try {
        const health = await client.checkHealth();
        vscode.window.showInformationMessage(
          `✅ 引擎连接正常 | v${health.version} | 沙箱=${health.sandbox_count} | 浏览器=${health.browser_ready ? "就绪" : "未启动"}`,
        );
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`❌ 引擎连接失败: ${message}`);
      }
    }),
  );

  // ── 一键启动引擎（v10.0）──
  context.subscriptions.push(
    vscode.commands.registerCommand("testpilot-ai.launchEngine", () => {
      // 查找项目根目录（优先用工作区，否则用插件设置）
      const folders = vscode.workspace.workspaceFolders;
      let projectRoot = "";

      // 尝试在工作区中找到 TestPilotAI 项目（有 cli.py 的目录）
      if (folders) {
        for (const f of folders) {
          const cliPath = vscode.Uri.joinPath(f.uri, "cli.py");
          // 使用 fs.stat 检测文件是否存在
          try {
            const fs = require("fs");
            if (fs.existsSync(cliPath.fsPath)) {
              projectRoot = f.uri.fsPath;
              break;
            }
          } catch {
            // 忽略
          }
        }
      }

      if (!projectRoot) {
        // 兜底：从配置中读取
        const config = vscode.workspace.getConfiguration("testpilotAI");
        projectRoot = config.get<string>("projectRoot", "");
      }

      if (!projectRoot) {
        vscode.window.showErrorMessage(
          "找不到 TestPilot AI 项目目录（需要包含 cli.py）。请在设置中配置 testpilotAI.projectRoot",
        );
        return;
      }

      // 若旧终端存在，先关闭（避免复用失效终端）
      const existingTerminal = vscode.window.terminals.find(
        (t) => t.name === "TestPilot Engine",
      );
      if (existingTerminal) {
        existingTerminal.dispose();
        outputChannel.appendLine("[TestPilot AI] 关闭旧引擎终端，准备重启");
      }

      const terminal = vscode.window.createTerminal({
        name: "TestPilot Engine",
        cwd: projectRoot,
      });
      terminal.show();
      terminal.sendText("poetry run python cli.py serve --force");
      outputChannel.appendLine(`[TestPilot AI] 引擎启动中... 目录: ${projectRoot}`);
      vscode.window.showInformationMessage("🚀 TestPilot AI 引擎正在启动...");
    }),
  );

  // ── 一键关闭引擎（v10.1）──
  context.subscriptions.push(
    vscode.commands.registerCommand("testpilot-ai.stopEngine", async () => {
      const engineTerminal = vscode.window.terminals.find(
        (t) => t.name === "TestPilot Engine",
      );
      if (engineTerminal) {
        engineTerminal.dispose();
        outputChannel.appendLine("[TestPilot AI] 引擎终端已关闭");
      } else {
        outputChannel.appendLine("[TestPilot AI] 未找到 TestPilot Engine 终端");
      }
      // 断开 WebSocket 连接
      client.disconnectWs();
      // 通知 Sidebar 更新状态
      sidebarProvider.postMessage({ command: "engineStatus", data: { connected: false } });
      vscode.window.showInformationMessage("⏹ TestPilot AI 引擎已断开");
    }),
  );

  // ── 英文别名命令（v9.1）── 每个中文命令都有一个英文版 ──

  const commandAliases: [string, string][] = [
    ["testpilot-ai.startTest.en", "testpilot-ai.startTest"],
    ["testpilot-ai.blueprintTest.en", "testpilot-ai.blueprintTest"],
    ["testpilot-ai.stopTest.en", "testpilot-ai.stopTest"],
    ["testpilot-ai.pauseTest.en", "testpilot-ai.pauseTest"],
    ["testpilot-ai.resumeTest.en", "testpilot-ai.resumeTest"],
    ["testpilot-ai.viewReport.en", "testpilot-ai.viewReport"],
    ["testpilot-ai.autoRepair.en", "testpilot-ai.autoRepair"],
    ["testpilot-ai.checkEngine.en", "testpilot-ai.checkEngine"],
    ["testpilot-ai.launchEngine.en", "testpilot-ai.launchEngine"],
    ["testpilot-ai.stopEngine.en", "testpilot-ai.stopEngine"],
  ];

  for (const [alias, target] of commandAliases) {
    context.subscriptions.push(
      vscode.commands.registerCommand(alias, () => vscode.commands.executeCommand(target)),
    );
  }

  outputChannel.appendLine("[TestPilot AI] 所有命令已注册（中文+英文）");
  outputChannel.appendLine("[TestPilot AI] 💡 Tip: Search 'TestPilot AI' in Command Palette (Ctrl+Shift+P) for all commands");
}

export function deactivate(): void {
  if (client) {
    client.disconnectWs();
  }
  outputChannel?.appendLine("[TestPilot AI] 插件已停用");
}

/** 格式化Bug摘要，方便粘贴给编程AI修复 */
function formatBugSummaryForAI(report: { test_name: string; url: string; pass_rate: number; bug_count: number; bugs?: Array<{ severity: string; title: string; description: string; step_number?: number | null }>; report_markdown: string }): string {
  const lines: string[] = [
    `TestPilot AI 发现 ${report.bug_count} 个Bug，请修复：`,
    `测试: ${report.test_name} | URL: ${report.url} | 通过率: ${report.pass_rate.toFixed(0)}%`,
    "",
  ];

  const bugs = report.bugs || [];
  if (bugs.length > 0) {
    bugs.forEach((bug, i) => {
      const step = bug.step_number ? ` (步骤#${bug.step_number})` : "";
      lines.push(`${i + 1}. [${bug.severity.toUpperCase()}] ${bug.title}${step}`);
      if (bug.description) {
        const desc = bug.description.split("\n")[0].substring(0, 150);
        lines.push(`   ${desc}`);
      }
    });
  } else {
    lines.push(report.report_markdown.substring(0, 1000));
  }

  lines.push("", "修复后请调用 run_blueprint_test 重新测试。");
  return lines.join("\n");
}

/** 在新的编辑器标签页中显示 Markdown 报告 */
function showReport(markdown: string): void {
  const doc = vscode.workspace.openTextDocument({
    content: markdown,
    language: "markdown",
  });
  doc.then((d) => {
    vscode.window.showTextDocument(d, { preview: true });
    // 尝试打开 Markdown 预览
    vscode.commands.executeCommand("markdown.showPreview", d.uri);
  });
}
