"""
Android 平台控制器（v5.0）

基于 Appium 实现 Android 设备/模拟器的自动化控制：
- 连接 Android 设备或模拟器
- 元素交互（点击、输入、滑动、长按）
- 截图和页面源码获取
- 手势操作（滑动、捏合缩放）

前置条件：
- 安装 Appium Server: npm install -g appium
- 安装 UiAutomator2 驱动: appium driver install uiautomator2
- Android SDK（adb 可用）
- 设备已连接或模拟器已启动

使用方式：
    controller = AndroidController(config)
    await controller.launch()
    await controller.navigate("com.example.app/.MainActivity")
    await controller.tap('//android.widget.Button[@text="登录"]')
    path = await controller.screenshot("登录页")
    await controller.close()
"""

import asyncio
import json
import subprocess
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import base64

from loguru import logger

from src.controller.base import BaseController, DeviceInfo, Platform
from src.controller.vendor_dialogs import DialogDismisser, VendorDialogRegistry


class MobileConfig:
    """移动端测试配置。"""

    def __init__(
        self,
        appium_url: str = "http://127.0.0.1:4723",
        platform_name: str = "Android",
        device_name: str = "",
        app_package: str = "",
        app_activity: str = "",
        app_path: str = "",
        automation_name: str = "UiAutomator2",
        no_reset: bool = True,
        timeout_ms: int = 30000,
        screenshot_dir: str = "screenshots",
    ):
        self.appium_url = appium_url
        self.platform_name = platform_name
        self.device_name = device_name
        self.app_package = app_package
        self.app_activity = app_activity
        self.app_path = app_path
        self.automation_name = automation_name
        self.no_reset = no_reset
        self.timeout_ms = timeout_ms
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)


class AndroidController(BaseController):
    """Android 控制器（通过 Appium HTTP API）。

    直接通过 HTTP 调用 Appium Server 的 WebDriver 协议，
    不依赖 appium-python-client 库，减少依赖。
    """

    def __init__(self, config: Optional[MobileConfig] = None, auto_dismiss_dialogs: bool = True) -> None:
        self._config = config or MobileConfig()
        self._session_id: Optional[str] = None
        self._device = DeviceInfo(
            platform=Platform.ANDROID,
            name=self._config.device_name or "Android Device",
        )
        self._step_counter = 0
        self._original_screen_off_timeout: Optional[str] = None
        self._original_stay_on: Optional[str] = None
        self._auto_dismiss = auto_dismiss_dialogs
        self._dialog_dismisser: Optional[DialogDismisser] = None
        # logcat 后台收集
        self._logcat_proc: Optional[subprocess.Popen] = None
        self._logcat_buffer: list[str] = []
        self._logcat_lock = threading.Lock()

    @property
    def platform(self) -> Platform:
        return Platform.ANDROID

    @property
    def device_info(self) -> DeviceInfo:
        return self._device

    def _next_step(self) -> int:
        self._step_counter += 1
        return self._step_counter

    # ── Appium HTTP 通信 ─────────────────────────

    def _request(self, method: str, path: str, body: Optional[dict] = None, timeout: int = 0) -> dict:
        """发送 Appium WebDriver 协议请求。"""
        url = f"{self._config.appium_url}{path}"
        data = json.dumps(body).encode() if body else None
        headers = {"Content-Type": "application/json"}
        effective_timeout = timeout or max(self._config.timeout_ms // 1000, 60)

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            logger.error("Appium请求失败: {} {} | {} | {}", method, path, e.code, error_body[:200])
            raise RuntimeError(f"Appium请求失败: {e.code} {error_body[:200]}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"无法连接Appium Server ({self._config.appium_url}): {e}")

    def _session_request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        """发送带 session ID 的请求。"""
        if not self._session_id:
            raise RuntimeError("Appium session 未创建，请先调用 launch()")
        return self._request(method, f"/session/{self._session_id}{path}", body)

    # ── BaseController 实现 ──────────────────────

    async def launch(self) -> None:
        """创建 Appium Session（连接设备）。"""
        capabilities = {
            "platformName": self._config.platform_name,
            "appium:automationName": self._config.automation_name,
            "appium:noReset": self._config.no_reset,
            "appium:newCommandTimeout": 300,
            "appium:autoGrantPermissions": True,
        }

        if self._config.device_name:
            capabilities["appium:deviceName"] = self._config.device_name
        if self._config.app_package:
            capabilities["appium:appPackage"] = self._config.app_package
        if self._config.app_activity:
            capabilities["appium:appActivity"] = self._config.app_activity
        if self._config.app_path:
            capabilities["appium:app"] = self._config.app_path

        body = {
            "capabilities": {
                "alwaysMatch": capabilities,
            },
        }

        # 自动保持亮屏（测试前设置，测试后恢复）
        await self._keep_screen_awake()

        logger.info("正在创建Appium Session | 设备={}", self._config.device_name or "auto")

        # Appium请求可能阻塞，用线程池执行
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, lambda: self._request("POST", "/session", body)
        )

        self._session_id = resp.get("value", {}).get("sessionId")
        if not self._session_id:
            raise RuntimeError(f"Appium Session 创建失败: {resp}")

        # 更新设备信息
        caps = resp.get("value", {}).get("capabilities", {})
        self._device.name = caps.get("deviceName", self._device.name)
        self._device.os_version = caps.get("platformVersion", "")
        self._device.screen_width = caps.get("deviceScreenSize", "0x0").split("x")[0] if isinstance(caps.get("deviceScreenSize"), str) else 0
        self._device.is_connected = True

        logger.info("Appium Session 创建成功 | ID={} | 设备={}",
                     self._session_id[:8], self._device.name)

        # 启动厂商弹窗自动dismiss
        if self._auto_dismiss:
            registry = VendorDialogRegistry()
            manufacturer = caps.get("deviceManufacturer", "")
            vendor = registry.detect_vendor(manufacturer) if manufacturer else None
            self._dialog_dismisser = DialogDismisser(
                self, registry=registry, vendor=vendor
            )
            self._dialog_dismisser.start()
            logger.info("厂商弹窗自动dismiss已启动 | 制造商={} | 厂商={}",
                        manufacturer, vendor.value if vendor else "generic")

        # 启动 logcat 后台收集
        try:
            await self.start_logcat()
        except Exception as e:
            logger.warning("logcat 启动失败（非致命）: {}", e)

    async def close(self) -> None:
        """关闭 Appium Session 并恢复屏幕设置。"""
        # 停止 logcat
        await self.stop_logcat()

        # 停止弹窗自动dismiss
        if self._dialog_dismisser:
            self._dialog_dismisser.stop()
            logger.info("弹窗dismiss统计: 共处理{}个", self._dialog_dismisser.dismissed_count)
            self._dialog_dismisser = None

        if self._session_id:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, lambda: self._request("DELETE", f"/session/{self._session_id}")
                )
                logger.info("Appium Session 已关闭")
            except Exception as e:
                logger.warning("关闭Appium Session时出错: {}", e)
            finally:
                self._session_id = None
                self._device.is_connected = False

        # 恢复屏幕设置
        await self._restore_screen_settings()

    async def navigate(self, url_or_activity: str) -> None:
        """打开Activity或URL。

        如果是URL（http开头），在手机浏览器中打开。
        如果是Activity名，直接启动对应Activity。
        """
        step = self._next_step()

        if url_or_activity.startswith("http"):
            logger.info("[步骤{}] 打开URL: {}", step, url_or_activity)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: self._session_request("POST", "/url", {"url": url_or_activity})
            )
        else:
            # 启动指定Activity
            logger.info("[步骤{}] 启动Activity: {}", step, url_or_activity)
            parts = url_or_activity.split("/")
            if len(parts) == 2:
                pkg, activity = parts[0], parts[1]
            else:
                pkg = self._config.app_package
                activity = url_or_activity

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: self._session_request("POST", "/appium/device/start_activity", {
                    "appPackage": pkg,
                    "appActivity": activity,
                })
            )

    async def tap(self, selector: str) -> None:
        """点击元素。"""
        step = self._next_step()
        logger.info("[步骤{}] 点击: {}", step, selector)

        element_id = await self._find_element(selector)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._session_request("POST", f"/element/{element_id}/click")
        )

    async def input_text(self, selector: str, text: str) -> None:
        """输入文本。"""
        step = self._next_step()
        display = text[:15] + "..." if len(text) > 15 else text
        logger.info("[步骤{}] 输入: {} -> '{}'", step, selector, display)

        element_id = await self._find_element(selector)
        # 先清空
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._session_request("POST", f"/element/{element_id}/clear")
        )
        await loop.run_in_executor(
            None, lambda: self._session_request("POST", f"/element/{element_id}/value", {
                "text": text,
            })
        )

    async def screenshot(self, name: str = "") -> Path:
        """截取手机屏幕。

        优先使用 adb 截图（快速可靠），失败时回退到 Appium 截图。
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        step_str = f"step{self._step_counter:03d}"
        safe_name = name.replace(" ", "_").replace("/", "_")[:50] if name else "capture"
        filename = f"{timestamp}_{step_str}_{safe_name}.png"
        filepath = self._config.screenshot_dir / filename

        logger.info("截图 | 文件={}", filename)

        # 优先用adb截图（更快更稳定）
        try:
            return await self._adb_screenshot(filepath)
        except Exception as e:
            logger.debug("adb截图失败({}), 尝试Appium截图...", e)

        # 回退到Appium截图
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, lambda: self._session_request("GET", "/screenshot")
        )

        b64_data = resp.get("value", "")
        if b64_data:
            filepath.write_bytes(base64.b64decode(b64_data))
            logger.debug("截图保存成功: {}", filepath)
        else:
            raise RuntimeError("截图失败：Appium未返回图片数据")

        return filepath

    async def _adb_screenshot(self, filepath: Path) -> Path:
        """通过 adb 直接截图（快速可靠）。"""
        device_serial = self._device.extra.get("serial", "") or self._config.device_name
        remote_path = "/sdcard/testpilot_screenshot.png"

        loop = asyncio.get_event_loop()

        # adb shell screencap
        def _capture():
            cmd_base = ["adb"]
            if device_serial:
                cmd_base.extend(["-s", device_serial])

            subprocess.run(
                cmd_base + ["shell", "screencap", "-p", remote_path],
                capture_output=True, timeout=10, check=True,
            )
            subprocess.run(
                cmd_base + ["pull", remote_path, str(filepath)],
                capture_output=True, timeout=10, check=True,
            )
            subprocess.run(
                cmd_base + ["shell", "rm", remote_path],
                capture_output=True, timeout=5,
            )

        await loop.run_in_executor(None, _capture)
        logger.debug("adb截图保存成功: {}", filepath)
        return filepath

    # ── Logcat 日志收集 ──────────────────────────────────

    def _adb_args(self) -> list[str]:
        """构建带设备序列号的 adb 命令前缀。"""
        cmd = ["adb"]
        serial = self._config.device_name
        if serial:
            cmd.extend(["-s", serial])
        return cmd

    async def start_logcat(self, tag_filter: str = "*:V") -> None:
        """启动 adb logcat 后台收集（守护线程持续读取）。

        Args:
            tag_filter: logcat 过滤器，如 "*:E" 只收错误，"*:V" 全量
        """
        # 先清空设备缓冲区
        subprocess.run(
            self._adb_args() + ["logcat", "-c"],
            capture_output=True, timeout=5,
        )
        with self._logcat_lock:
            self._logcat_buffer = []

        cmd = self._adb_args() + ["logcat", "-v", "threadtime", tag_filter]
        self._logcat_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # 守护线程持续读取输出
        def _reader() -> None:
            try:
                for line in self._logcat_proc.stdout:  # type: ignore[union-attr]
                    with self._logcat_lock:
                        self._logcat_buffer.append(line.rstrip())
                        # 防止内存无限增长：保留最近 5000 行
                        if len(self._logcat_buffer) > 5000:
                            self._logcat_buffer = self._logcat_buffer[-5000:]
            except Exception:
                pass

        t = threading.Thread(target=_reader, daemon=True, name="logcat-reader")
        t.start()
        logger.info("Logcat 已启动 | 过滤={}", tag_filter)

    async def stop_logcat(self) -> None:
        """停止 adb logcat 收集。"""
        if self._logcat_proc:
            try:
                self._logcat_proc.terminate()
                self._logcat_proc.wait(timeout=3)
            except Exception:
                pass
            self._logcat_proc = None
            with self._logcat_lock:
                count = len(self._logcat_buffer)
            logger.debug("Logcat 已停止，共收集 {} 行", count)

    async def get_logcat(self, last_n: int = 50) -> list[str]:
        """获取最近 N 行 logcat 日志。

        Args:
            last_n: 返回最后 N 行，默认 50

        Returns:
            日志行列表（最新的在最后）
        """
        with self._logcat_lock:
            return list(self._logcat_buffer[-last_n:])

    async def get_browser_log(self) -> list[dict]:
        """通过 Appium 获取手机浏览器的 JS 控制台日志。

        需要 Appium 支持 browser log type，仅部分设备/浏览器可用。

        Returns:
            日志条目列表，每条格式：{"timestamp": ms, "level": str, "message": str}
        """
        if not self._session_id:
            return []
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self._session_request("POST", "/log", {"type": "browser"}),
            )
            return resp.get("value", [])
        except Exception as e:
            logger.debug("获取浏览器日志失败（设备可能不支持）: {}", e)
            return []

    # ── WebView 上下文切换 ────────────────────────────────

    async def get_contexts(self) -> list[str]:
        """获取当前可用的 Appium 上下文列表。

        Returns:
            上下文名称列表，如 ["NATIVE_APP", "WEBVIEW_com.android.browser"]
        """
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._session_request("GET", "/contexts"),
        )
        return resp.get("value", [])

    async def get_current_context(self) -> str:
        """获取当前激活的上下文名称。"""
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._session_request("GET", "/context"),
        )
        return resp.get("value", "NATIVE_APP")

    async def switch_context(self, context_name: str) -> None:
        """切换到指定上下文。

        Args:
            context_name: 上下文名称，如 "NATIVE_APP" 或
                          "WEBVIEW_chrome" / "WEBVIEW_com.android.browser"
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._session_request("POST", "/context", {"name": context_name}),
        )
        logger.info("已切换上下文: {}", context_name)

    async def switch_to_webview(self, timeout_s: int = 10) -> bool:
        """尝试切换到 WebView 上下文（轮询等待）。

        切换成功后可以使用 CSS 选择器操作网页元素。

        Args:
            timeout_s: 等待 WebView 出现的最长秒数

        Returns:
            True=切换成功，False=无 WebView 上下文
        """
        import time
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            contexts = await self.get_contexts()
            webview_ctx = next(
                (c for c in contexts if c.startswith("WEBVIEW")),
                None,
            )
            if webview_ctx:
                await self.switch_context(webview_ctx)
                logger.info("已切换到 WebView 上下文: {}", webview_ctx)
                return True
            await asyncio.sleep(1)
        logger.warning("等待 WebView 上下文超时 ({}s)，继续使用 NATIVE 上下文", timeout_s)
        return False

    async def switch_to_native(self) -> None:
        """切换回 NATIVE_APP 上下文。"""
        await self.switch_context("NATIVE_APP")

    async def get_page_source(self) -> str:
        """获取 UI 层级 XML。"""
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, lambda: self._session_request("GET", "/source")
        )
        return resp.get("value", "")

    async def get_text(self, selector: str) -> str:
        """获取元素文本。"""
        element_id = await self._find_element(selector)
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, lambda: self._session_request("GET", f"/element/{element_id}/text")
        )
        return resp.get("value", "")

    async def swipe(
        self,
        start_x: int, start_y: int,
        end_x: int, end_y: int,
        duration_ms: int = 300,
    ) -> None:
        """手机滑动操作。"""
        step = self._next_step()
        logger.info("[步骤{}] 滑动: ({},{}) -> ({},{})", step, start_x, start_y, end_x, end_y)

        actions = {
            "actions": [{
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {"type": "pointerMove", "duration": 0, "x": start_x, "y": start_y},
                    {"type": "pointerDown", "button": 0},
                    {"type": "pause", "duration": 10},
                    {"type": "pointerMove", "duration": duration_ms, "x": end_x, "y": end_y},
                    {"type": "pointerUp", "button": 0},
                ],
            }]
        }

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._session_request("POST", "/actions", actions)
        )

    async def long_press(self, selector: str, duration_ms: int = 1000) -> None:
        """长按元素。"""
        step = self._next_step()
        logger.info("[步骤{}] 长按: {} ({}ms)", step, selector, duration_ms)

        # 先获取元素位置
        element_id = await self._find_element(selector)
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, lambda: self._session_request("GET", f"/element/{element_id}/rect")
        )
        rect = resp.get("value", {})
        cx = rect.get("x", 0) + rect.get("width", 0) // 2
        cy = rect.get("y", 0) + rect.get("height", 0) // 2

        actions = {
            "actions": [{
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {"type": "pointerMove", "duration": 0, "x": cx, "y": cy},
                    {"type": "pointerDown", "button": 0},
                    {"type": "pause", "duration": duration_ms},
                    {"type": "pointerUp", "button": 0},
                ],
            }]
        }

        await loop.run_in_executor(
            None, lambda: self._session_request("POST", "/actions", actions)
        )

    async def back(self) -> None:
        """按返回键。"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._session_request("POST", "/back")
        )

    async def wait_for_element(self, selector: str, timeout_ms: int = 10000) -> None:
        """等待元素出现。"""
        import time
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            try:
                await self._find_element(selector)
                return
            except RuntimeError:
                await asyncio.sleep(0.5)
        raise RuntimeError(f"等待元素超时: {selector}")

    # ── 权限批量授予 ─────────────────────────────

    async def grant_permissions(self, app_package: str, permissions: list[str]) -> list[str]:
        """通过 adb 批量授予 Android 运行时权限。

        Args:
            app_package: 应用包名，如 com.example.app
            permissions: 权限列表，如 ["android.permission.CAMERA", "android.permission.ACCESS_FINE_LOCATION"]

        Returns:
            实际成功授予的权限列表
        """
        if not app_package or not permissions:
            return []

        loop = asyncio.get_event_loop()
        granted: list[str] = []

        def _grant():
            for perm in permissions:
                full_perm = perm if perm.startswith("android.permission.") else f"android.permission.{perm}"
                result = self._adb_cmd("shell", "pm", "grant", app_package, full_perm)
                # pm grant 成功时无输出，失败时有错误信息
                if "Exception" not in result and "Unknown permission" not in result:
                    granted.append(full_perm)
                    logger.debug("权限已授予: {} → {}", app_package, full_perm)
                else:
                    logger.warning("权限授予失败: {} → {} | {}", app_package, full_perm, result[:100])

        await loop.run_in_executor(None, _grant)
        logger.info("批量授权完成 | {} | 成功{}/{}个", app_package, len(granted), len(permissions))
        return granted

    # ── 屏幕保持亮屏 ─────────────────────────────

    def _adb_cmd(self, *args: str) -> str:
        """执行adb命令并返回stdout。"""
        cmd = ["adb"]
        serial = self._config.device_name
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(args)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return result.stdout.strip()
        except Exception:
            return ""

    async def _keep_screen_awake(self) -> None:
        """设置设备充电时保持亮屏，并将熄屏超时设为最大值。

        测试结束后通过 _restore_screen_settings() 恢复原始值。
        """
        loop = asyncio.get_event_loop()

        def _setup():
            # 保存原始值
            self._original_stay_on = self._adb_cmd(
                "shell", "settings", "get", "global", "stay_on_while_plugged_in"
            )
            self._original_screen_off_timeout = self._adb_cmd(
                "shell", "settings", "get", "system", "screen_off_timeout"
            )

            # 充电时保持亮屏（USB=2, AC=1, Wireless=4, 全部=7）
            self._adb_cmd("shell", "settings", "put", "global", "stay_on_while_plugged_in", "7")
            # 熄屏超时设为最大值（约24.8天）
            self._adb_cmd("shell", "settings", "put", "system", "screen_off_timeout", "2147483647")
            # 确保屏幕亮着
            self._adb_cmd("shell", "input", "keyevent", "KEYCODE_WAKEUP")

        await loop.run_in_executor(None, _setup)
        logger.info("屏幕保持亮屏已设置 | 原stay_on={} 原timeout={}",
                    self._original_stay_on, self._original_screen_off_timeout)

    async def _restore_screen_settings(self) -> None:
        """恢复设备屏幕设置到测试前的状态。"""
        loop = asyncio.get_event_loop()

        def _restore():
            if self._original_stay_on is not None:
                self._adb_cmd("shell", "settings", "put", "global",
                              "stay_on_while_plugged_in", self._original_stay_on or "0")
            if self._original_screen_off_timeout is not None:
                self._adb_cmd("shell", "settings", "put", "system",
                              "screen_off_timeout", self._original_screen_off_timeout or "60000")

        try:
            await loop.run_in_executor(None, _restore)
            logger.info("屏幕设置已恢复")
        except Exception as e:
            logger.warning("恢复屏幕设置时出错: {}", e)

    # ── 内部方法 ─────────────────────────────────

    async def _find_element(self, selector: str) -> str:
        """查找元素，返回 element ID。

        自动判断选择器类型：
        - 以 // 开头 → xpath
        - 以 id: 开头 → resource-id
        - 以 accessibility_id: 开头 → accessibility id
        - 以 class: 开头 → class name
        - 以 css: 开头 → css selector (WebView 上下文)
        - 以 # 或 . 开头，或包含 CSS 属性选择器 → css selector (WebView 上下文)
        - 其他 → xpath
        """
        if selector.startswith("//"):
            strategy, value = "xpath", selector
        elif selector.startswith("id:"):
            strategy, value = "id", selector[3:]
        elif selector.startswith("accessibility_id:"):
            strategy, value = "accessibility id", selector[17:]
        elif selector.startswith("class:"):
            strategy, value = "class name", selector[6:]
        elif selector.startswith("css:"):
            strategy, value = "css selector", selector[4:]
        elif selector.startswith(("#", ".")) or ("[" in selector and "]" in selector and not selector.startswith("//")):
            # 常见 CSS 选择器模式（WebView 上下文下有效）
            strategy, value = "css selector", selector
        else:
            # 默认当xpath处理
            strategy, value = "xpath", selector

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, lambda: self._session_request("POST", "/element", {
                "using": strategy,
                "value": value,
            })
        )

        element = resp.get("value", {})
        # W3C 协议返回格式
        if isinstance(element, dict):
            for key in element:
                if key.startswith("element-") or key == "ELEMENT":
                    return element[key]
        raise RuntimeError(f"元素未找到: {selector}")
