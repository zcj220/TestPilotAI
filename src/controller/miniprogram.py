"""
微信小程序控制器（v8.0）

通过微信开发者工具 + miniprogram-automator SDK 实现自动化。
架构：Python → Node.js子进程 → miniprogram-automator → 开发者工具

选择器格式（与小程序 automator SDK 一致）：
- .class-name       → CSS类选择器
- #id               → ID选择器
- view              → 标签选择器
- .parent .child    → 后代选择器

前置条件：
1. 安装微信开发者工具（https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html）
2. 开发者工具开启"服务端口"（设置 → 安全设置 → 打开服务端口）
3. npm install miniprogram-automator（项目内已含桥接脚本）
"""

import asyncio
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

from src.controller.base import BaseController, DeviceInfo, Platform


class MiniProgramConfig:
    """小程序测试配置。"""

    def __init__(
        self,
        project_path: str = "",
        devtools_path: str = "",
        screenshot_dir: str = "screenshots/miniprogram",
        timeout_ms: int = 30000,
        account: str = "",
        automation_port: int = 0,  # 新增：自动化端口，0表示自动检测
    ):
        self.project_path = project_path
        self.devtools_path = devtools_path or self._detect_devtools()
        self.timeout_ms = timeout_ms
        self.account = account
        self.automation_port = automation_port
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _detect_devtools() -> str:
        """自动检测微信开发者工具路径。"""
        candidates = [
            r"C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat",
            r"C:\Program Files\Tencent\微信web开发者工具\cli.bat",
            r"D:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat",
            r"D:\微信web开发者工具\cli.bat",
        ]
        for p in candidates:
            if Path(p).exists():
                return p
        return ""

    @staticmethod
    def _detect_automation_port() -> int:
        """检测微信开发者工具当前的自动化端口。"""
        import socket
        import subprocess
        
        # 方法1：从netstat检测微信开发者工具的WebSocket端口
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # 查找微信开发者工具进程的监听端口
            # 端口通常在 9420-65535 之间
            for line in result.stdout.split('\n'):
                if 'LISTENING' in line and '127.0.0.1:' in line:
                    parts = line.split()
                    for part in parts:
                        if '127.0.0.1:' in part:
                            try:
                                port = int(part.split(':')[1])
                                # 微信开发者工具的自动化端口通常 > 9000
                                if 9000 <= port <= 65535:
                                    # 尝试连接验证
                                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                                    sock.settimeout(0.5)
                                    if sock.connect_ex(('127.0.0.1', port)) == 0:
                                        sock.close()
                                        logger.info(f"检测到可能的自动化端口: {port}")
                                        return port
                                    sock.close()
                            except (ValueError, IndexError):
                                continue
        except Exception as e:
            logger.warning(f"端口检测失败: {e}")
        
        # 默认返回 9420
        return 9420


class MiniProgramController(BaseController):
    """微信小程序控制器。

    通过 Node.js 桥接脚本调用 miniprogram-automator SDK，
    实现小程序页面导航、元素点击、文本输入、截图等操作。
    """

    def __init__(self, config: Optional[MiniProgramConfig] = None) -> None:
        self._config = config or MiniProgramConfig()
        self._connected = False
        self._step_counter = 0
        self._bridge_proc: Optional[subprocess.Popen] = None
        self._device = DeviceInfo(
            platform=Platform.WEB,  # 小程序基于WebView，复用WEB平台
            name="WeChat MiniProgram",
            screen_width=375,
            screen_height=667,
        )

    @property
    def platform(self) -> Platform:
        return Platform.WEB

    @property
    def device_info(self) -> DeviceInfo:
        return self._device

    def _next_step(self) -> int:
        self._step_counter += 1
        return self._step_counter

    # ── BaseController 实现 ──────────────────────

    def _run_cli(self, cmd_name: str, args: list, timeout: int = 15) -> bool:
        """执行CLI命令，返回是否成功。"""
        try:
            r = subprocess.run(
                args, capture_output=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
            logger.info("cli {} 完成 (rc={})", cmd_name, r.returncode)
            return True
        except Exception as e:
            logger.warning("cli {} 失败: {}", cmd_name, e)
            return False

    async def launch(self) -> None:
        """启动小程序自动化连接（长连接模式 v8.3）。

        流程（参考test_connect.js和官方CLI文档）：
        阶段1: cli auto 开启自动化（若项目未打开则先open再auto）
        阶段2: TCP探测WS端口就绪（最多20秒）
        阶段3: 启动桥接HTTP服务器
        阶段4: 等HTTP就绪
        阶段5: POST connect触发automator连接（重试8次x5秒=40秒）

        重要：官方文档要求先在设置→安全设置中开启服务端口！
        导航全部使用evaluate(wx.xxx())原生API（SDK方法会超时！）
        """
        import socket
        import urllib.request

        if not self._config.project_path:
            raise RuntimeError("请指定小程序项目路径 (project_path)")

        ws_port = self._config.automation_port or 9420
        cli_path = self._config.devtools_path
        project_path = self._config.project_path

        if not cli_path:
            raise RuntimeError(
                "未找到微信开发者工具cli，请安装微信开发者工具"
            )

        # ═══ 阶段1: 检测或启动自动化 ═══
        logger.info("═══ 阶段1: 检测或启动自动化 ═══")
        logger.info("cli: {} | 项目: {} | 端口: {}", cli_path, project_path, ws_port)

        # 先探测端口：如果9420已通，说明auto已经开启，跳过cli auto（避免重载模拟器！）
        port_ok = self._check_tcp_port(ws_port)
        if port_ok:
            logger.info("WS端口 {} 已通，跳过cli auto（避免重载模拟器）", ws_port)
        else:
            # 端口未通，才执行cli auto
            logger.info("WS端口 {} 未通，执行cli auto...", ws_port)
            self._run_cli("auto", [
                cli_path, "auto", "--project", project_path,
                "--auto-port", str(ws_port),
            ])
            await asyncio.sleep(3)

            # 再检查
            if not self._check_tcp_port(ws_port):
                # 项目可能没打开，先open再auto
                logger.info("端口仍未通，尝试 cli open + cli auto ...")
                self._run_cli("open", [cli_path, "open", "--project", project_path])
                logger.info("等待模拟器启动（15秒）...")
                await asyncio.sleep(15)
                self._run_cli("auto", [
                    cli_path, "auto", "--project", project_path,
                    "--auto-port", str(ws_port),
                ])
                await asyncio.sleep(5)

        # ═══ 阶段2: 等待WS端口就绪（TCP探测，最多20秒） ═══
        logger.info("═══ 阶段2: 等待WS端口 {} 就绪 ═══", ws_port)
        port_ready = False
        for i in range(20):
            if self._check_tcp_port(ws_port):
                port_ready = True
                logger.info("WS端口 {} 已就绪（第{}秒）", ws_port, i + 1)
                break
            await asyncio.sleep(1)

        if not port_ready:
            raise RuntimeError(
                f"WebSocket端口 {ws_port} 未就绪（等了20秒）。\n"
                f"请确认：1) 微信开发者工具已打开项目 "
                f"2) 设置→安全设置→已开启服务端口"
            )

        # ═══ 阶段3: 启动桥接服务器 ═══
        self._http_port = 9421
        self._http_base = f"http://127.0.0.1:{self._http_port}"

        logger.info("═══ 阶段3: 启动桥接服务器 ═══ WS:{} HTTP:{}", ws_port, self._http_port)

        bridge_server = Path(__file__).parent / "miniprogram_bridge_server.js"
        if not bridge_server.exists():
            raise RuntimeError(f"桥接服务器脚本不存在: {bridge_server}")

        self._bridge_proc = subprocess.Popen(
            ["node", str(bridge_server), str(ws_port), str(self._http_port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # ═══ 阶段4: 等HTTP服务器就绪（最多5秒） ═══
        logger.info("═══ 阶段4: 等待HTTP服务器就绪 ═══")
        http_ready = False
        for i in range(10):
            await asyncio.sleep(0.5)
            try:
                req = urllib.request.Request(self._http_base)
                with urllib.request.urlopen(req, timeout=2) as resp:
                    json.loads(resp.read())
                    http_ready = True
                    logger.info("HTTP服务器已就绪（{:.1f}秒）", (i + 1) * 0.5)
                    break
            except Exception:
                continue

        if not http_ready:
            self._kill_bridge()
            raise RuntimeError("桥接服务器HTTP端口9421未响应")

        # ═══ 阶段5: POST connect（重试8次x5秒=40秒） ═══
        logger.info("═══ 阶段5: 发送connect命令（最多重试8次） ═══")
        last_err = ""
        for i in range(8):
            try:
                payload = json.dumps({"action": "connect", "params": {}}).encode()
                req = urllib.request.Request(
                    self._http_base, data=payload,
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                    if data.get("success"):
                        self._connected = True
                        self._device.is_connected = True
                        self._device.extra = {"project": project_path, "port": ws_port}
                        logger.info("小程序自动化已连接 | 端口:{} | 第{}次", ws_port, i + 1)
                        return
                    last_err = data.get("error", "未知错误")
                    logger.warning("connect失败: {}（第{}次）", last_err, i + 1)
            except Exception as e:
                last_err = str(e)
                logger.warning("connect异常: {}（第{}次）", last_err, i + 1)
            await asyncio.sleep(5)

        self._kill_bridge()
        raise RuntimeError(
            f"automator连接8次均失败（最后错误: {last_err}）。\n"
            f"WS端口{ws_port}已通但连接失败。请确认模拟器已完全启动。"
        )

    @staticmethod
    def _check_tcp_port(port: int, host: str = "127.0.0.1") -> bool:
        """检查TCP端口是否可连接。"""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((host, port))
            s.close()
            return True
        except Exception:
            try:
                s.close()
            except Exception:
                pass
            return False

    def _kill_bridge(self) -> None:
        """清理桥接服务器进程。"""
        if self._bridge_proc and self._bridge_proc.poll() is None:
            self._bridge_proc.terminate()
            try:
                self._bridge_proc.wait(timeout=3)
            except Exception:
                self._bridge_proc.kill()
        self._bridge_proc = None

    async def close(self) -> None:
        """关闭小程序自动化连接。"""
        if self._connected:
            try:
                await self._call_bridge("disconnect", {})
            except Exception:
                pass
        # 关闭桥接服务器进程
        if self._bridge_proc and self._bridge_proc.poll() is None:
            self._bridge_proc.terminate()
            self._bridge_proc.wait(timeout=5)
        self._bridge_proc = None
        self._connected = False
        self._device.is_connected = False
        logger.info("小程序自动化已关闭")

    async def navigate(self, url_or_page: str) -> None:
        """导航到小程序页面。"""
        step = self._next_step()
        logger.info("[步骤{}] 导航: {}", step, url_or_page)
        result = await self._call_bridge("navigateTo", {"url": url_or_page})
        if not result.get("success"):
            raise RuntimeError(f"导航失败: {result.get('error')}")

    async def tap(self, selector: str) -> None:
        """点击小程序元素。"""
        step = self._next_step()
        logger.info("[步骤{}] 点击: {}", step, selector)
        result = await self._call_bridge("tap", {"selector": selector})
        if not result.get("success"):
            raise RuntimeError(f"点击失败: {result.get('error')}")

    async def input_text(self, selector: str, text: str) -> None:
        """在小程序输入框中输入文本。"""
        step = self._next_step()
        display = text[:15] + "..." if len(text) > 15 else text
        logger.info("[步骤{}] 输入: {} -> '{}'", step, selector, display)
        result = await self._call_bridge("input", {
            "selector": selector, "text": text,
        })
        if not result.get("success"):
            raise RuntimeError(f"输入失败: {result.get('error')}")

    async def screenshot(self, name: str = "") -> Path:
        """截取小程序当前页面。"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        step_str = f"step{self._step_counter:03d}"
        safe_name = name.replace(" ", "_")[:50] if name else "capture"
        filename = f"{timestamp}_{step_str}_{safe_name}.png"
        filepath = self._config.screenshot_dir / filename

        result = await self._call_bridge("screenshot", {
            "path": str(filepath),
        })
        if result.get("success"):
            logger.debug("小程序截图已保存 | {}", filepath)
            return filepath
        else:
            raise RuntimeError(f"截图失败: {result.get('error')}")

    async def get_page_source(self) -> str:
        """获取小程序当前页面的 WXML 结构。"""
        result = await self._call_bridge("getWxml", {})
        return result.get("wxml", "<empty>")

    async def get_text(self, selector: str) -> str:
        """获取小程序元素文本。"""
        result = await self._call_bridge("getText", {"selector": selector})
        return result.get("text", "")

    async def wait_for_element(self, selector: str, timeout_ms: int = 10000) -> None:
        """等待小程序元素出现。"""
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            result = await self._call_bridge("elementExists", {
                "selector": selector,
            })
            if result.get("exists"):
                return
            await asyncio.sleep(0.5)
        raise RuntimeError(f"等待元素超时: {selector}")

    # ── 小程序特有方法 ────────────────────────────

    async def get_current_page(self) -> dict:
        """获取当前页面路径和参数。"""
        result = await self._call_bridge("getCurrentPage", {})
        return result

    async def call_wx_api(self, method: str, params: dict = None) -> dict:
        """调用微信API（如 wx.getSystemInfo）。"""
        result = await self._call_bridge("callWxApi", {
            "method": method, "params": params or {},
        })
        return result

    async def mock_wx_api(self, method: str, result: dict) -> None:
        """模拟微信API返回（如模拟定位、支付等）。"""
        await self._call_bridge("mockWxApi", {
            "method": method, "result": result,
        })

    async def get_app_data(self) -> dict:
        """获取小程序 App 级别的 globalData。"""
        result = await self._call_bridge("getAppData", {})
        return result.get("data", {})

    async def get_page_data(self) -> dict:
        """获取当前页面的 data。"""
        result = await self._call_bridge("getPageData", {})
        return result.get("data", {})

    # ── 桥接通信 ──────────────────────────────────

    async def _call_bridge(self, action: str, params: dict) -> dict:
        """通过 HTTP 请求调用桥接服务器。"""
        import urllib.request
        payload = json.dumps({"action": action, "params": params}).encode("utf-8")

        loop = asyncio.get_event_loop()
        try:
            def do_request():
                req = urllib.request.Request(
                    self._http_base,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                timeout = self._config.timeout_ms // 1000 + 5
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read())

            return await loop.run_in_executor(None, do_request)
        except Exception as e:
            return {"success": False, "error": str(e)}
