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

// 引擎二进制下载地址（托管在 testpilot.xinzaoai.com 服务器）
const GITHUB_RELEASE_BASE =
  "https://testpilot.xinzaoai.com/downloads";

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
  /** 互斥锁：防止并发调用 ensureRunning() 导致重复下载 */
  private _ensureRunningPromise: Promise<void> | null = null;

  constructor(private _context: vscode.ExtensionContext) {
    this._storageDir = _context.globalStorageUri.fsPath;
    this._outputChannel = vscode.window.createOutputChannel("TestPilot Engine");

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
      downloading: "$(cloud-download~spin) TestPilot: Downloading",
      starting:    "$(sync~spin) TestPilot: Starting",
      ready:       "$(check) TestPilot: Ready",
      offline:     "$(error) TestPilot: Offline",
    };
    this._statusBar.text = extra ? `${labels[state]} ${extra}` : labels[state];
    this._statusBar.tooltip = state === "ready"
      ? `TestPilot AI Engine running\nClick to view logs`
      : `Click to view TestPilot AI Engine logs`;
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
   * 使用互斥锁防止并发调用导致重复下载（EBUSY）。
   */
  async ensureRunning(): Promise<void> {
    if (this._ensureRunningPromise) {
      return this._ensureRunningPromise;
    }
    this._ensureRunningPromise = this._doEnsureRunning().finally(() => {
      this._ensureRunningPromise = null;
    });
    return this._ensureRunningPromise;
  }

  private async _doEnsureRunning(): Promise<void> {
    // 0. 版本检查（异步，不阻塞启动，但强制更新会提示）
    this._checkVersion().catch(() => {});

    // 1. 已有引擎在跑
    if (await this.isEngineRunning()) {
      // 检查 Playwright 浏览器是否可用，如果不可用说明是旧版引擎（未设置PLAYWRIGHT_BROWSERS_PATH）
      const browserOk = await this._checkBrowserAvailable();
      if (browserOk) {
        this._outputChannel.appendLine("[Engine] Already running, connecting directly");
        this._setStatus("ready");
        return;
      }
      // 浏览器不可用 → 停掉旧引擎，用新参数重新启动
      this._outputChannel.appendLine("[Engine] Running but browser unavailable, restarting to fix...");
      await this._killExistingEngine();
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

  /** 检查 Playwright 浏览器是否存在于系统缓存 */
  private _checkBrowserAvailable(): Promise<boolean> {
    return new Promise((resolve) => {
      const url = getEngineUrl() + "/api/v1/health";
      const mod = url.startsWith("https") ? https : http;
      const req = mod.get(url, { timeout: 2000 }, (res) => {
        let body = "";
        res.on("data", (chunk: Buffer) => { body += chunk.toString(); });
        res.on("end", () => {
          try {
            const data = JSON.parse(body);
            resolve(data.browser_available !== false);
          } catch {
            resolve(true); // 旧版引擎无此字段，不强制重启
          }
        });
        res.resume();
      });
      req.on("error", () => resolve(true));
      req.on("timeout", () => { req.destroy(); resolve(true); });
    });
  }

  /** 杀掉端口 8900 上正在运行的引擎进程 */
  private _killExistingEngine(): Promise<void> {
    return new Promise((resolve) => {
      if (this._engineProc) {
        this._engineProc.kill();
        this._engineProc = null;
        setTimeout(resolve, 1000);
        return;
      }
      // 用 HTTP DELETE 或直接让它自然停止（引擎暂无 shutdown 接口）
      // 通过端口找进程并杀掉（仅 Windows）
      if (process.platform === "win32") {
        child_process.exec(
          `for /f "tokens=5" %a in ('netstat -ano ^| findstr :8900') do taskkill /F /PID %a`,
          () => setTimeout(resolve, 1500),
        );
      } else {
        child_process.exec(
          `fuser -k 8900/tcp`,
          () => setTimeout(resolve, 1500),
        );
      }
    });
  }

  /** 从 GitHub Release 下载二进制（带进度条通知） */
  private async _downloadBinary(): Promise<void> {
    const fileName = getPlatformBinaryName();
    const downloadUrl = `${GITHUB_RELEASE_BASE}/${fileName}`;
    const tmpPath = this.binaryPath + ".tmp";

    this._outputChannel.show(true);
    this._outputChannel.appendLine(`[Engine] Downloading: ${downloadUrl}`);

    await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "TestPilot AI: Downloading engine",
        cancellable: false,
      },
      (progress) => {
        return new Promise<void>((resolve, reject) => {
          const file = fs.createWriteStream(tmpPath);

          const doGet = (url: string, redirectCount = 0) => {
            if (redirectCount > 5) {
              reject(new Error("Too many download redirects"));
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
                reject(new Error(`Download failed, HTTP ${res.statusCode}`));
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
                  // 删旧文件再重命名（Windows 上 rename 覆盖有时报 EBUSY）
                  try {
                    if (fs.existsSync(this.binaryPath)) {
                      fs.unlinkSync(this.binaryPath);
                    }
                    fs.renameSync(tmpPath, this.binaryPath);
                  } catch (e) {
                    // 第二次尝试（等 500ms 让杀毒软件释放文件锁）
                    setTimeout(() => {
                      try { fs.renameSync(tmpPath, this.binaryPath); } catch {}
                    }, 500);
                  }
                  // macOS / Linux 需要可执行权限
                  if (process.platform !== "win32") {
                    fs.chmodSync(this.binaryPath, 0o755);
                  }
                  this._outputChannel.appendLine(`[Engine] Download complete: ${this.binaryPath}`);
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
      this._outputChannel.appendLine(`[Engine] Starting: ${this.binaryPath}`);

      // 注入 PLAYWRIGHT_BROWSERS_PATH，确保 PyInstaller 打包的引擎能找到已安装的浏览器
      const browsersPath = process.platform === "win32"
        ? path.join(process.env["LOCALAPPDATA"] || os.homedir(), "ms-playwright")
        : path.join(os.homedir(), ".cache", "ms-playwright");
      this._outputChannel.appendLine(`[引擎] PLAYWRIGHT_BROWSERS_PATH=${browsersPath}`);

      const spawnOptions: child_process.SpawnOptions = {
        cwd: os.homedir(),
        detached: false,
        stdio: ["ignore", "pipe", "pipe"],
        env: {
          ...process.env,
          PLAYWRIGHT_BROWSERS_PATH: browsersPath,
          PYTHONIOENCODING: "utf-8",
          PYTHONLEGACYWINDOWSSTDIO: "utf-8",
        },
      };

      // 尝试 spawn，遇到 EBUSY（Windows Defender 扫描中）最多重试 3 次
      const trySpawn = (attempt: number) => {
        const proc = child_process.spawn(this.binaryPath, [], spawnOptions);

        proc.on("error", (err: NodeJS.ErrnoException) => {
          if (err.code === "EBUSY" && attempt < 3) {
            this._outputChannel.appendLine(`[Engine] File busy (EBUSY), retrying in 3s (${attempt}/3)...`);
            setTimeout(() => trySpawn(attempt + 1), 3000);
          } else {
            reject(new Error(`Engine process start failed: ${err.message}`));
          }
        });

        proc.on("exit", (code) => {
          this._outputChannel.appendLine(`[Engine] Process exited, code=${code}`);
          this._engineProc = null;
          this._setStatus("offline");
        });

        const onData = (chunk: Buffer) => {
          const text = chunk.toString();
          this._outputChannel.append(text);
          if (text.includes("Uvicorn running") || text.includes("Application startup complete")) {
            proc.stdout?.removeListener("data", onData);
            proc.stderr?.removeListener("data", onData);
            resolve();
          }
        };
        proc.stdout?.on("data", onData);
        proc.stderr?.on("data", onData);

        this._engineProc = proc;
      };

      trySpawn(1);

      // 超时保护
      setTimeout(() => reject(new Error("Engine start timeout (120s), check Output panel logs")), 120000);
    });
  }

  /** 停止引擎进程 */
  dispose(): void {
    if (this._engineProc) {
      this._outputChannel.appendLine("[Engine] Stopping engine subprocess");
      this._engineProc.kill();
      this._engineProc = null;
    }
    // 无论是否有子进程引用，都通过端口找到并杀掉 8900 上的进程
    this._killExistingEngine().catch(() => {});
    this._setStatus("offline");
  }

  /** 版本检查：低于最低版本强制提示，低于最新版本弱提示 */
  private async _checkVersion(): Promise<void> {
    const VERSION_URL = "https://testpilot.xinzaoai.com/api/v1/version/check";
    const currentVersion = vscode.extensions.getExtension("wenzhouxinzao.testpilot-ai")
      ?.packageJSON?.version as string | undefined;
    if (!currentVersion) { return; }

    try {
      const data = await new Promise<{ latest: string; minimum: string; changelog?: string }>(
        (resolve, reject) => {
          const mod = VERSION_URL.startsWith("https") ? https : http;
          mod.get(VERSION_URL, { timeout: 8000 }, (res) => {
            if (res.statusCode !== 200) { reject(new Error(`HTTP ${res.statusCode}`)); return; }
            let body = "";
            res.on("data", (c: Buffer) => (body += c.toString()));
            res.on("end", () => { try { resolve(JSON.parse(body)); } catch (e) { reject(e); } });
          }).on("error", reject).on("timeout", () => reject(new Error("timeout")));
        }
      );

      const cmp = (a: string, b: string) => {
        const pa = a.split(".").map(Number);
        const pb = b.split(".").map(Number);
        for (let i = 0; i < 3; i++) {
          if ((pa[i] || 0) < (pb[i] || 0)) { return -1; }
          if ((pa[i] || 0) > (pb[i] || 0)) { return 1; }
        }
        return 0;
      };

      if (cmp(currentVersion, data.minimum) < 0) {
        // 强制更新：弹出模态提示
        const action = await vscode.window.showErrorMessage(
          `TestPilot AI v${currentVersion} is no longer supported, please update to v${data.latest}.`,
          { modal: true },
          "Download"
        );
        if (action === "Download") {
          vscode.env.openExternal(
            vscode.Uri.parse("https://testpilot.xinzaoai.com/downloads/testpilot-ai-" + data.latest + ".vsix")
          );
        }
      } else if (cmp(currentVersion, data.latest) < 0) {
        // 弱提示：状态栏提醒，不阻塞
        const action = await vscode.window.showInformationMessage(
          `TestPilot AI v${data.latest} available (current: v${currentVersion})`,
          "Update", "Dismiss"
        );
        if (action === "Update") {
          vscode.env.openExternal(
            vscode.Uri.parse("https://testpilot.xinzaoai.com/downloads/testpilot-ai-" + data.latest + ".vsix")
          );
        }
      }
    } catch {
      // 版本检查失败不影响正常使用，静默忽略
    }
  }
}
