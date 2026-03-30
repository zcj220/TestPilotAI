/**
 * TestPilot AI — 引擎生命周期管理器
 *
 * 负责：
 * 1. 检测本地引擎是否已运行（ping /api/v1/health）
 * 2. 检查是否已缓存引擎二进制
 * 3. 从 GitHub Release 下载对应平台的二进制（带进度条）
 * 4. 启动引擎进程，等待 "Uvicorn running" 出现
 * 5. 插件停用时干净退出
 */

import * as vscode from "vscode";
import * as https from "https";
import * as http from "http";
import * as fs from "fs";
import * as path from "path";
import * as child_process from "child_process";
import * as os from "os";

// GitHub Release 下载地址模板
const GITHUB_RELEASE_BASE =
  "https://github.com/zcj220/TestPilotAI/releases/latest/download";

/** 根据当前平台返回对应的二进制文件名 */
function getPlatformBinaryName(): string {
  switch (process.platform) {
    case "win32":
      return "testpilot-engine-windows.exe";
    case "darwin":
      return "testpilot-engine-macos";
    default:
      return "testpilot-engine-linux";
  }
}

/** 引擎 HTTP 地址 */
function getEngineUrl(): string {
  return vscode.workspace
    .getConfiguration("testpilotAI")
    .get<string>("engineUrl", "http://127.0.0.1:8900");
}

export class EngineManager {
  private _engineProc: child_process.ChildProcess | null = null;
  private _storageDir: string;
  private _outputChannel: vscode.OutputChannel;
  private _statusBar: vscode.StatusBarItem;

  constructor(private _context: vscode.ExtensionContext) {
    this._storageDir = _context.globalStorageUri.fsPath;
    this._outputChannel = vscode.window.createOutputChannel("TestPilot 引擎");

    // 状态栏项（右侧显示，点击打开引擎日志）
    this._statusBar = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right, 100
    );
    this._statusBar.command = "testpilot-ai.showEngineLog";
    this._setStatus("offline");
    this._statusBar.show();
    _context.subscriptions.push(this._statusBar);

    // 注册点击状态栏打开日志的命令
    _context.subscriptions.push(
      vscode.commands.registerCommand("testpilot-ai.showEngineLog", () => {
        this._outputChannel.show(true);
      })
    );
  }

  /** 更新状态栏显示 */
  private _setStatus(state: "downloading" | "starting" | "ready" | "offline", extra?: string): void {
    const labels: Record<string, string> = {
      downloading: "$(cloud-download~spin) TestPilot: 下载中",
      starting:    "$(sync~spin) TestPilot: 启动中",
      ready:       "$(check) TestPilot: 就绪",
      offline:     "$(error) TestPilot: 离线",
    };
    this._statusBar.text = extra ? `${labels[state]} ${extra}` : labels[state];
    this._statusBar.tooltip = state === "ready"
      ? `TestPilot AI 引擎运行中\n点击查看日志`
      : `点击查看 TestPilot AI 引擎日志`;
    this._statusBar.backgroundColor = state === "offline"
      ? new vscode.ThemeColor("statusBarItem.errorBackground")
      : undefined;
  }

  /** 引擎二进制的完整本地路径 */
  private get binaryPath(): string {
    return path.join(this._storageDir, getPlatformBinaryName());
  }

  /** 检查引擎是否已在运行（HTTP ping） */
  async isEngineRunning(): Promise<boolean> {
    return new Promise((resolve) => {
      const url = getEngineUrl() + "/api/v1/health";
      const mod = url.startsWith("https") ? https : http;
      const req = mod.get(url, { timeout: 2000 }, (res) => {
        resolve(res.statusCode === 200);
        res.resume();
      });
      req.on("error", () => resolve(false));
      req.on("timeout", () => { req.destroy(); resolve(false); });
    });
  }

  /**
   * 确保引擎正在运行。
   * 流程：已运行 → 直接返回；已缓存 → 启动；未缓存 → 先下载再启动。
   */
  async ensureRunning(): Promise<void> {
    // 1. 已有引擎在跑，直接复用
    if (await this.isEngineRunning()) {
      this._outputChannel.appendLine("[引擎] 检测到引擎已运行，直接连接");
      this._setStatus("ready");
      return;
    }

    // 2. globalStorage 目录必须存在
    if (!fs.existsSync(this._storageDir)) {
      fs.mkdirSync(this._storageDir, { recursive: true });
    }

    // 3. 没有缓存的二进制，先下载
    if (!fs.existsSync(this.binaryPath)) {
      this._setStatus("downloading");
      await this._downloadBinary();
    }

    // 4. 启动引擎进程
    this._setStatus("starting");
    await this._spawnEngine();
    this._setStatus("ready");
  }

  /** 从 GitHub Release 下载二进制（带进度条通知） */
  private async _downloadBinary(): Promise<void> {
    const fileName = getPlatformBinaryName();
    const downloadUrl = `${GITHUB_RELEASE_BASE}/${fileName}`;
    const tmpPath = this.binaryPath + ".tmp";

    this._outputChannel.show(true);
    this._outputChannel.appendLine(`[引擎] 开始下载: ${downloadUrl}`);

    await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "TestPilot AI：正在下载引擎",
        cancellable: false,
      },
      (progress) => {
        return new Promise<void>((resolve, reject) => {
          const file = fs.createWriteStream(tmpPath);

          const doGet = (url: string, redirectCount = 0) => {
            if (redirectCount > 5) {
              reject(new Error("下载重定向次数过多"));
              return;
            }
            const mod = url.startsWith("https") ? https : http;
            mod.get(url, (res) => {
              // 处理重定向（GitHub Release 会 302 到 CDN）
              if (res.statusCode === 301 || res.statusCode === 302) {
                res.resume();
                doGet(res.headers.location!, redirectCount + 1);
                return;
              }
              if (res.statusCode !== 200) {
                reject(new Error(`下载失败，HTTP ${res.statusCode}`));
                return;
              }

              const total = parseInt(res.headers["content-length"] || "0", 10);
              let received = 0;
              let lastPercent = 0;

              res.on("data", (chunk: Buffer) => {
                received += chunk.length;
                file.write(chunk);
                if (total > 0) {
                  const pct = Math.floor((received / total) * 100);
                  if (pct >= lastPercent + 5) {
                    const msg = `${pct}%（${Math.round(received / 1024 / 1024)}MB / ${Math.round(total / 1024 / 1024)}MB）`;
                    progress.report({ message: msg, increment: pct - lastPercent });
                    this._setStatus("downloading", `${pct}%`);
                    lastPercent = pct;
                  }
                }
              });

              res.on("end", () => {
                file.end(() => {
                  // 重命名临时文件
                  fs.renameSync(tmpPath, this.binaryPath);
                  // macOS / Linux 需要可执行权限
                  if (process.platform !== "win32") {
                    fs.chmodSync(this.binaryPath, 0o755);
                  }
                  this._outputChannel.appendLine(`[引擎] 下载完成: ${this.binaryPath}`);
                  resolve();
                });
              });

              res.on("error", reject);
            }).on("error", reject);
          };

          doGet(downloadUrl);
        });
      }
    );
  }

  /** 启动引擎子进程，等待监听就绪 */
  private _spawnEngine(): Promise<void> {
    return new Promise((resolve, reject) => {
      this._outputChannel.appendLine(`[引擎] 启动: ${this.binaryPath}`);

      this._engineProc = child_process.spawn(this.binaryPath, [], {
        cwd: os.homedir(),        // 工作目录设为用户主目录，让 data/ logs/ 写到那里
        detached: false,
        stdio: ["ignore", "pipe", "pipe"],
      });

      const onData = (chunk: Buffer) => {
        const text = chunk.toString();
        this._outputChannel.append(text);
        // 检测到 uvicorn 就绪信号
        if (text.includes("Uvicorn running") || text.includes("Application startup complete")) {
          this._engineProc!.stdout?.removeListener("data", onData);
          this._engineProc!.stderr?.removeListener("data", onData);
          resolve();
        }
      };

      this._engineProc.stdout?.on("data", onData);
      this._engineProc.stderr?.on("data", onData);

      this._engineProc.on("error", (err) => {
        reject(new Error(`引擎进程启动失败: ${err.message}`));
      });

      this._engineProc.on("exit", (code) => {
        this._outputChannel.appendLine(`[引擎] 进程已退出，退出码=${code}`);
        this._engineProc = null;
        this._setStatus("offline");
      });

      // 超时保护：30 秒内未就绪视为失败
      setTimeout(() => reject(new Error("引擎启动超时（30s），请检查 Output 面板日志")), 30000);
    });
  }

  /** 停止引擎进程（插件停用时调用） */
  dispose(): void {
    if (this._engineProc) {
      this._outputChannel.appendLine("[引擎] 停止引擎进程");
      this._engineProc.kill();
      this._engineProc = null;
    }
    this._setStatus("offline");
  }
}
