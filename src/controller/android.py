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
        bundle_id: str = "",
        udid: str = "",
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
        self.bundle_id = bundle_id
        self.udid = udid


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
        self._u2_dead = False  # U2被杀后置True，避免反复等/source超时
        self._original_ime: Optional[str] = None  # 输入法备份，测试结束后恢复
        self._ime_switched = False  # 是否已切换过输入法
        self._use_adb_keyboard = False  # 是否使用ADB Keyboard（broadcast输入）
        self._original_screen_off_timeout: Optional[str] = None
        self._original_stay_on: Optional[str] = None
        self._auto_dismiss = auto_dismiss_dialogs
        self._dialog_dismisser: Optional[DialogDismisser] = None
        # logcat 后台收集
        self._logcat_proc: Optional[subprocess.Popen] = None
        self._logcat_buffer: list[str] = []
        self._logcat_lock = threading.Lock()
        # 外部取消信号（由 MobileBlueprintRunner 设置）
        self._is_cancelled_fn: object = None

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
            # 404=元素不存在（正常），用DEBUG；500=U2崩溃，用WARNING
            if e.code == 404:
                logger.debug("Appium元素未找到: {} {} | {}", method, path, error_body[:120])
            else:
                logger.warning("Appium请求异常: {} {} | {} | {}", method, path, e.code, error_body[:200])
            raise RuntimeError(f"Appium请求失败: {e.code} {error_body[:200]}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"无法连接Appium Server ({self._config.appium_url}): {e}")
        except (TimeoutError, OSError) as e:
            raise RuntimeError(f"Appium请求超时: {e}")

    def _session_request(self, method: str, path: str, body: Optional[dict] = None, timeout: int = 0) -> dict:
        """发送带 session ID 的请求。"""
        if not self._session_id:
            raise RuntimeError("Appium session 未创建，请先调用 launch()")
        return self._request(method, f"/session/{self._session_id}{path}", body, timeout=timeout)

    async def _safe_session_call(
        self, method: str, path: str, body: Optional[dict] = None, timeout: int = 0,
    ) -> dict:
        """带 U2 死亡自动恢复的 _session_request（async 版）。

        如果请求超时（U2 无响应），自动重建 Session 后重试一次。
        """
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(
                None, lambda: self._session_request(method, path, body, timeout=timeout)
            )
        except RuntimeError as e:
            if "超时" not in str(e):
                raise
            logger.warning("U2疑似无响应({}), 尝试自动恢复...", str(e)[:40])
            await self._recover_u2_session()
            return await loop.run_in_executor(
                None, lambda: self._session_request(method, path, body, timeout=timeout)
            )

    # ── 握手检测 ────────────────────────────────

    async def check_appium_server(self) -> dict:
        """检测 Appium Server 是否可达，返回状态信息。

        Returns:
            {"ok": True/False, "message": str, "appium_url": str}
        """
        appium_url = self._config.appium_url
        try:
            req = urllib.request.Request(f"{appium_url}/status", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                build = data.get("value", {}).get("build", {})
                version = build.get("version", "unknown")
                return {
                    "ok": True,
                    "message": f"Appium Server 就绪 (v{version})",
                    "appium_url": appium_url,
                }
        except urllib.error.URLError:
            return {
                "ok": False,
                "message": f"无法连接 Appium Server ({appium_url})。请先启动 Appium：appium --address 127.0.0.1 --port 4723",
                "appium_url": appium_url,
            }
        except Exception as e:
            return {
                "ok": False,
                "message": f"Appium Server 检测异常: {e}",
                "appium_url": appium_url,
            }

    # 类变量：缓存 Appium 进程引用（防止重复启动）
    _appium_process: subprocess.Popen = None
    _appium_starting: bool = False

    async def ensure_appium_server(self, timeout: int = 30) -> dict:
        """确保 Appium Server 运行：未启动则自动启动，等待就绪。

        Returns:
            {"ok": True/False, "message": str}
        """
        # 先检测是否已经在运行
        check = await self.check_appium_server()
        if check["ok"]:
            return {"ok": True, "message": check["message"]}

        # 防止并发重复启动（多次点击precheck）
        if AndroidController._appium_starting:
            logger.info("Appium 正在启动中，等待...")
            import time
            deadline = time.time() + timeout
            while time.time() < deadline:
                await asyncio.sleep(1)
                check = await self.check_appium_server()
                if check["ok"]:
                    return {"ok": True, "message": check["message"]}
            return {"ok": False, "message": "Appium 启动等待超时"}

        # 如果之前启动的进程还活着但端口没响应，先杀掉
        if AndroidController._appium_process and AndroidController._appium_process.poll() is None:
            logger.warning("发现未响应的 Appium 旧进程，正在终止...")
            AndroidController._appium_process.kill()
            AndroidController._appium_process = None

        # 未运行 → 自动启动
        AndroidController._appium_starting = True
        try:
            return await self._start_appium_process(timeout)
        finally:
            AndroidController._appium_starting = False

    async def _start_appium_process(self, timeout: int) -> dict:
        """内部方法：实际启动 Appium 进程。"""
        appium_url = self._config.appium_url
        import re
        port_match = re.search(r":(\d+)$", appium_url)
        port = port_match.group(1) if port_match else "4723"

        logger.info("Appium Server 未运行，正在自动启动 (port={})...", port)
        try:
            import shutil
            appium_path = shutil.which("appium")
            if not appium_path:
                return {
                    "ok": False,
                    "message": "appium 命令未找到。请先安装：npm install -g appium && appium driver install uiautomator2",
                }

            cmd = [appium_path, "--address", "127.0.0.1", "--port", port,
                   "--log-no-colors", "--relaxed-security"]
            logger.info("启动命令: {}", " ".join(cmd))
            # stdout/stderr 重定向到 DEVNULL 避免管道缓冲区满导致进程卡死
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            AndroidController._appium_process = proc
        except Exception as e:
            return {"ok": False, "message": f"启动 Appium 失败: {e}"}

        # 轮询等待 Appium 就绪
        import time
        deadline = time.time() + timeout
        last_err = ""
        while time.time() < deadline:
            await asyncio.sleep(1)
            check = await self.check_appium_server()
            if check["ok"]:
                logger.info("Appium Server 自动启动成功: {}", check["message"])
                return {"ok": True, "message": f"Appium Server 已自动启动 ({check['message']})"}
            last_err = check.get("message", "")
            # 检查进程是否已退出（启动失败）
            if proc.poll() is not None:
                return {
                    "ok": False,
                    "message": f"Appium 进程启动后退出(code={proc.returncode})",
                }

        return {"ok": False, "message": f"Appium Server 启动超时({timeout}秒)。最后状态: {last_err}"}

    async def check_device(self) -> dict:
        """检测是否有设备连接（Android 用 adb devices，iOS 用 idevice_id / xcrun）。

        Returns:
            {"ok": True/False, "message": str, "devices": list}
        """
        if self._config.platform_name == "iOS":
            return await self._check_ios_device()

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, lambda: subprocess.run(
                    ["adb", "devices"], capture_output=True, text=True, timeout=5,
                )
            )
            lines = result.stdout.strip().split("\n")[1:]
            devices = [l.split()[0] for l in lines if "device" in l and "offline" not in l]
            if devices:
                # 获取设备详情（型号、分辨率、Android版本）—— 握手时就拿到，用户友好
                device_info = await self._get_device_info(devices[0])
                info_str = ""
                if device_info:
                    parts = []
                    if device_info.get("model"):
                        parts.append(device_info["model"])
                    if device_info.get("resolution"):
                        parts.append(device_info["resolution"])
                    if device_info.get("android_version"):
                        parts.append(f"Android {device_info['android_version']}")
                    if parts:
                        info_str = f" ({', '.join(parts)})"
                return {
                    "ok": True,
                    "message": f"已连接 {len(devices)} 台设备: {devices[0]}{info_str}",
                    "devices": devices,
                    "device_info": device_info,
                }
            else:
                return {"ok": False, "message": "未检测到已连接的 Android 设备。请用 USB 连接手机并启用 USB 调试。", "devices": []}
        except FileNotFoundError:
            return {"ok": False, "message": "adb 未安装或不在 PATH 中。请安装 Android SDK Platform Tools。", "devices": []}
        except Exception as e:
            return {"ok": False, "message": f"设备检测异常: {e}", "devices": []}

    async def _get_device_info(self, device_serial: str) -> dict:
        """通过adb获取设备详情（型号、分辨率、Android版本）。握手时调用，用户友好。"""
        info: dict[str, str] = {}
        loop = asyncio.get_event_loop()
        adb_prefix = ["adb", "-s", device_serial, "shell"]

        def _run(cmd_suffix: list[str]) -> str:
            try:
                r = subprocess.run(
                    adb_prefix + cmd_suffix,
                    capture_output=True, text=True, timeout=5,
                )
                return r.stdout.strip()
            except Exception:
                return ""

        try:
            model = await loop.run_in_executor(None, lambda: _run(["getprop", "ro.product.model"]))
            if model:
                info["model"] = model
            resolution = await loop.run_in_executor(None, lambda: _run(["wm", "size"]))
            if resolution and ":" in resolution:
                info["resolution"] = resolution.split(":")[-1].strip()
            version = await loop.run_in_executor(None, lambda: _run(["getprop", "ro.build.version.release"]))
            if version:
                info["android_version"] = version
        except Exception:
            pass
        return info

    async def _check_ios_device(self) -> dict:
        """检测 iOS 设备连接状态（优先 idevice_id，回退 xcrun xctrace）。"""
        loop = asyncio.get_event_loop()

        def _detect():
            # 方法 1：libimobiledevice idevice_id
            try:
                r = subprocess.run(
                    ["idevice_id", "-l"], capture_output=True, text=True, timeout=5
                )
                udids = [u.strip() for u in r.stdout.strip().split("\n") if u.strip()]
                if udids:
                    return {"ok": True, "message": f"已连接 {len(udids)} 台 iOS 设备: {', '.join(udids)}", "devices": udids}
            except FileNotFoundError:
                pass
            # 方法 2：xcrun xctrace list devices
            try:
                r = subprocess.run(
                    ["xcrun", "xctrace", "list", "devices"],
                    capture_output=True, text=True, timeout=10,
                )
                lines = r.stdout.strip().split("\n")
                # 跳过模拟器行（含 Simulator），找含 UDID 括号的真机行
                real_devices = [
                    ln.strip() for ln in lines
                    if "Simulator" not in ln and "(" in ln and ")" in ln
                    and not ln.strip().startswith("===") and len(ln.strip()) > 20
                ]
                if real_devices:
                    return {"ok": True, "message": f"iOS设备已连接: {real_devices[0]}", "devices": real_devices}
            except Exception:
                pass
            return {
                "ok": False,
                "message": "未检测到 iOS 设备。请用 USB 连接 iPhone，在手机上点击【信任此电脑】，并确认开发者模式已开启（设置→隐私与安全→开发者模式）。",
                "devices": [],
            }

        return await loop.run_in_executor(None, _detect)

    # ── BaseController 实现 ──────────────────────

    async def launch(self) -> None:
        """创建 Appium Session（连接设备）。iOS/Android 分支处理。"""
        if self._config.platform_name == "iOS":
            await self._launch_ios()
            return

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

        # 先杀掉可能残留的 APP 和 U2 进程
        # Flutter app 如果已在运行且有活跃动画，XPath 策略会因 waitForIdle 卡死
        loop = asyncio.get_event_loop()
        if self._config.app_package:
            await loop.run_in_executor(
                None, lambda: subprocess.run(
                    ["adb", "shell", "am", "force-stop", self._config.app_package],
                    capture_output=True, timeout=5,
                )
            )
        for u2_pkg in ("io.appium.uiautomator2.server",
                        "io.appium.uiautomator2.server.test"):
            await loop.run_in_executor(
                None, lambda pkg=u2_pkg: subprocess.run(
                    ["adb", "shell", "am", "force-stop", pkg],
                    capture_output=True, timeout=5,
                )
            )
        await asyncio.sleep(1)

        logger.info("正在创建Appium Session | 设备={}", self._config.device_name or "auto")

        # Appium请求可能阻塞，用线程池执行
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, lambda: self._request("POST", "/session", body)
        )

        self._session_id = resp.get("value", {}).get("sessionId")
        if not self._session_id:
            raise RuntimeError(f"Appium Session 创建失败: {resp}")
        self._u2_dead = False  # Session新建成功，U2可用

        # 更新设备信息
        caps = resp.get("value", {}).get("capabilities", {})
        self._device.name = caps.get("deviceName", self._device.name)
        self._device.os_version = caps.get("platformVersion", "")
        screen_size = caps.get("deviceScreenSize", "0x0")
        if isinstance(screen_size, str) and "x" in screen_size:
            parts = screen_size.split("x")
            self._device.screen_width = int(parts[0])
            self._device.screen_height = int(parts[1])
        self._device.is_connected = True

        logger.info("Appium Session 创建成功 | ID={} | 设备={}",
                     self._session_id[:8], self._device.name)

        # 关键：将 waitForIdleTimeout 设为极短值
        # Flutter 的动画循环导致设备永远不"空闲"，UiAutomator2 的
        # waitForIdle 会卡死。设为 0 后 accessibility_id 策略不再 hang。
        try:
            await loop.run_in_executor(
                None, lambda: self._session_request(
                    "POST", "/appium/settings",
                    {"settings": {"waitForIdleTimeout": 0, "waitForSelectorTimeout": 0}},
                )
            )
            logger.info("UiAutomator2 waitForIdle 已禁用（Flutter兼容）")
        except Exception as e:
            logger.warning("设置waitForIdleTimeout失败（非致命）: {}", e)

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

        # 用adb确保APP在前台（Appium noReset模式下APP可能不在前台）
        if self._config.app_package and self._config.app_activity:
            component = f"{self._config.app_package}/{self._config.app_activity}"
            try:
                loop2 = asyncio.get_event_loop()
                await loop2.run_in_executor(
                    None, lambda: subprocess.run(
                        ["adb", "shell", "am", "start", "-n", component],
                        capture_output=True, timeout=10,
                    )
                )
                logger.info("APP已通过adb拉到前台 | {}", component)
                await asyncio.sleep(3)  # 等待Flutter渲染
            except Exception as e:
                logger.warning("adb启动APP失败（非致命）: {}", e)

        # 启动 logcat 后台收集
        try:
            await self.start_logcat()
        except Exception as e:
            logger.warning("logcat 启动失败（非致命）: {}", e)

    def is_session_alive(self) -> bool:
        """检查当前 Appium Session 是否仍然有效。"""
        if not self._session_id:
            return False
        try:
            resp = self._request("GET", f"/session/{self._session_id}", timeout=5)
            return "value" in resp
        except Exception:
            return False

    async def close(self) -> None:
        """关闭 Appium Session 并恢复屏幕设置。"""
        # 恢复输入法
        await self._restore_ime()

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
        """打开URL、Activity 或（iOS）重启 app。

        如果是URL（http开头），在手机浏览器中打开。
        如果平台是 iOS，通过 terminateApp + activateApp 重启 app。
        如果是 Android Activity 名，重建 Session 并启动 Activity。
        """
        step = self._next_step()

        if url_or_activity.startswith("http"):
            logger.info("[步骤{}] 打开URL: {}", step, url_or_activity)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: self._session_request("POST", "/url", {"url": url_or_activity})
            )
        elif self._config.platform_name == "iOS":
            # iOS：用 mobile: terminateApp + mobile: launchApp（Appium 2 标准方式）
            # 确保 app 从头冷启动，回到初始登录页
            bundle = self._config.bundle_id
            logger.info("[步骤{}] iOS冷启动App: {}", step, bundle)
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(
                    None, lambda: self._session_request(
                        "POST", "/execute/sync",
                        {"script": "mobile: terminateApp", "args": [{"bundleId": bundle}]},
                    )
                )
                logger.debug("iOS terminateApp 成功")
            except Exception as e:
                logger.warning("iOS terminateApp 失败（非致命）: {}", e)
            await asyncio.sleep(1)
            try:
                await loop.run_in_executor(
                    None, lambda: self._session_request(
                        "POST", "/execute/sync",
                        {"script": "mobile: launchApp", "args": [{"bundleId": bundle}]},
                    )
                )
                logger.debug("iOS launchApp 成功")
            except Exception as e:
                logger.warning("iOS launchApp 失败，重建 Session: {}", e)
                await self._launch_ios()
            await asyncio.sleep(3)
        else:
            # 重启 app 并重建 Appium Session
            # 原因：Flutter app 被 terminate 后，UiAutomator2 Server 内部线程
            #       会死锁（所有HTTP请求hang住），只有销毁并重建 Session
            #       才能获得全新的 UiAutomator2 Server 实例
            logger.info("[步骤{}] 启动Activity（重建Session）: {}", step, url_or_activity)
            parts = url_or_activity.split("/")
            if len(parts) == 2:
                pkg, activity = parts[0], parts[1]
            else:
                pkg = self._config.app_package
                activity = url_or_activity

            component = f"{pkg}/{activity}"
            loop = asyncio.get_event_loop()
            await self._rebuild_session_and_launch(loop, pkg, component)

    async def _rebuild_session_and_launch(
        self, loop: asyncio.AbstractEventLoop, pkg: str, component: str
    ) -> None:
        """销毁旧 Session 并创建全新 Session，然后启动 app。

        解决 Flutter app 重启后 UiAutomator2 Server 死锁的问题。
        """
        # 1. adb force-stop 杀掉 app
        await loop.run_in_executor(
            None, lambda: subprocess.run(
                ["adb", "shell", "am", "force-stop", pkg],
                capture_output=True, timeout=10,
            )
        )

        # 2. 尝试删除旧 Session（短超时，失败也继续）
        old_sid = self._session_id
        if old_sid:
            self._session_id = None
            try:
                await loop.run_in_executor(
                    None, lambda: self._request(
                        "DELETE", f"/session/{old_sid}", timeout=3)
                )
                logger.debug("旧Session已删除: {}", old_sid[:8])
            except Exception as e:
                logger.warning("删除旧Session超时（用adb清理）: {}", e)

        # 3. 用 adb 强杀设备上的 UiAutomator2 Server 进程
        #    DELETE /session 可能超时（旧Server死锁），导致旧Server还在运行
        #    新Session会复用死锁的Server，所以必须手动杀掉
        def _kill_uia2():
            subprocess.run(
                ["adb", "shell", "am", "force-stop",
                 "io.appium.uiautomator2.server"],
                capture_output=True, timeout=5,
            )
            subprocess.run(
                ["adb", "shell", "am", "force-stop",
                 "io.appium.uiautomator2.server.test"],
                capture_output=True, timeout=5,
            )

        await loop.run_in_executor(None, _kill_uia2)
        logger.info("UiAutomator2 Server 旧进程已清理")
        await asyncio.sleep(1)  # 等待进程完全终止

        # 4. 创建全新 Session（全新 UiAutomator2 Server 实例）
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

        body = {"capabilities": {"alwaysMatch": capabilities}}
        resp = await loop.run_in_executor(
            None, lambda: self._request("POST", "/session", body)
        )
        self._session_id = resp.get("value", {}).get("sessionId")
        if not self._session_id:
            raise RuntimeError(f"Session重建失败: {resp}")
        self._u2_dead = False  # Session重建成功，U2可用
        logger.info("Session重建成功 | ID={}", self._session_id[:8])

        # 5. 设置 waitForIdleTimeout=0（Flutter 动画循环兼容）
        try:
            await loop.run_in_executor(
                None, lambda: self._session_request(
                    "POST", "/appium/settings",
                    {"settings": {
                        "waitForIdleTimeout": 0,
                        "waitForSelectorTimeout": 0,
                    }},
                )
            )
        except Exception as e:
            logger.warning("设置waitForIdleTimeout失败: {}", e)

        # 6. 确保 APP 在前台
        await loop.run_in_executor(
            None, lambda: subprocess.run(
                ["adb", "shell", "am", "start", "-n", component],
                capture_output=True, timeout=10,
            )
        )

        # 7. 等待 Flutter 引擎重新初始化 + 渲染
        await asyncio.sleep(3)

    async def _launch_ios(self) -> None:
        """iOS 专用 launch：设置 XCUITest capabilities 并创建 Appium Session。

        与 Android 路径的主要差异：
        - 使用 XCUITest automationName
        - 通过 bundleId 定位 app（无需 appPackage/appActivity）
        - terminate app 后重建Session，而不是 force-stop
        - 不需要 waitForIdleTimeout（XCUITest 没有 UiAutomator2 的空闲问题）
        - 不需要 adb 保持亮屏（WDA 连接期间 iOS 屏幕不会自动锁定）
        """
        capabilities = {
            "platformName": "iOS",
            "appium:automationName": "XCUITest",
            "appium:bundleId": self._config.bundle_id,
            "appium:noReset": True,
            "appium:newCommandTimeout": 300,
            "appium:autoAcceptAlerts": True,
            "appium:wdaLocalPort": 8100,
            # WDA 签名配置（已在 Xcode GUI 中构建完成，直接复用构建产物）
            "appium:xcodeOrgId": "SS9YJ95QFV",
            "appium:xcodeSigningId": "Apple Development",
            "appium:allowProvisioningDeviceRegistration": True,
            "appium:updatedWDABundleId": "com.wxzao.wda.runner",
            # 直接使用 Xcode GUI 已构建好的 WDA，跳过 xcodebuild 编译步骤
            "appium:usePrebuiltWDA": True,
            "appium:derivedDataPath": "/Users/zcj/Library/Developer/Xcode/DerivedData/WebDriverAgent-cgmjtgwhyundavaoywlwoknvbfhl",
        }
        if self._config.device_name:
            capabilities["appium:deviceName"] = self._config.device_name
        if self._config.udid:
            capabilities["appium:udid"] = self._config.udid

        body = {"capabilities": {"alwaysMatch": capabilities}}

        # 先 terminate 旧的 app 进程并删除旧 Session
        if self._session_id:
            try:
                loop0 = asyncio.get_event_loop()
                await loop0.run_in_executor(
                    None, lambda: self._session_request(
                        "POST", "/execute/sync",
                        {"script": "mobile: terminateApp", "args": [{"bundleId": self._config.bundle_id}]},
                    )
                )
                await asyncio.sleep(1)
            except Exception:
                pass
            # 删除旧 Session
            try:
                old_sid = self._session_id
                self._session_id = None
                loop0 = asyncio.get_event_loop()
                await loop0.run_in_executor(
                    None, lambda: self._request("DELETE", f"/session/{old_sid}", timeout=5)
                )
            except Exception:
                self._session_id = None

        logger.info("正在创建 iOS Appium Session | bundleId={}", self._config.bundle_id)
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, lambda: self._request("POST", "/session", body)
        )

        self._session_id = resp.get("value", {}).get("sessionId")
        if not self._session_id:
            raise RuntimeError(f"iOS Appium Session 创建失败: {resp}")

        caps = resp.get("value", {}).get("capabilities", {})
        self._device.name = caps.get("deviceName", self._device.name)
        self._device.os_version = caps.get("platformVersion", "")
        self._device.is_connected = True

        logger.info("iOS Appium Session 创建成功 | ID={} | 设备={} iOS={}",
                    self._session_id[:8], self._device.name, self._device.os_version)

    async def tap(self, selector: str) -> None:
        """点击元素。"""
        step = self._next_step()
        logger.info("[步骤{}] 点击: {}", step, selector)

        element_id = await self._find_element_with_wait(selector, timeout_s=15)
        await self._safe_session_call("POST", f"/element/{element_id}/click")

    async def tap_xy(self, x: int, y: int) -> None:
        """通过坐标点击屏幕（视觉降级时使用，走adb不走Appium，100%可靠）。"""
        logger.info("坐标点击: ({}, {})", x, y)
        device_serial = self._device.extra.get("serial", "") or self._config.device_name
        cmd = ["adb"]
        if device_serial:
            cmd.extend(["-s", device_serial])
        cmd.extend(["shell", "input", "tap", str(x), str(y)])
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: subprocess.run(cmd, capture_output=True, timeout=5)
        )
        await asyncio.sleep(0.3)

    async def input_text_xy(self, x: int, y: int, text: str) -> None:
        """通过坐标点击输入框后输入文本。

        策略：adb tap → 等键盘弹出 → 清空旧内容 → adb input text。
        已验证：只要键盘弹出（focused=true），adb input text 对 Flutter/原生都有效。
        不使用 Appium findElement（在 Flutter 上会超时卡死）。
        """
        display = text[:15] + "..." if len(text) > 15 else text
        logger.info("坐标输入: ({}, {}) -> '{}'", x, y, display)
        device_serial = self._device.extra.get("serial", "") or self._config.device_name
        adb_base = ["adb"]
        if device_serial:
            adb_base.extend(["-s", device_serial])
        loop = asyncio.get_event_loop()

        async def _adb(args: list[str], timeout: int = 5) -> None:
            await loop.run_in_executor(
                None, lambda: subprocess.run(
                    adb_base + args, capture_output=True, timeout=timeout,
                )
            )

        # 1. 点击输入框获焦点
        await self.tap_xy(x, y)
        await asyncio.sleep(1.5)  # 等键盘弹出动画完成

        # 2. 再点一次确保光标在正确位置（Flutter有时首次tap只选中widget不弹键盘）
        await self.tap_xy(x, y)
        await asyncio.sleep(1.0)

        # 2.5 重新检查输入法（Android密码框可能自动切回中文输入法）
        await self._ensure_latin_ime(adb_base, loop, _adb)
        await asyncio.sleep(0.3)

        # 3. 清空旧内容（10次退格，简单可靠）
        await _adb(["shell", "input", "keyevent",
                     "KEYCODE_DEL", "KEYCODE_DEL", "KEYCODE_DEL", "KEYCODE_DEL", "KEYCODE_DEL"])
        await asyncio.sleep(0.3)
        await _adb(["shell", "input", "keyevent",
                     "KEYCODE_DEL", "KEYCODE_DEL", "KEYCODE_DEL", "KEYCODE_DEL", "KEYCODE_DEL"])
        await asyncio.sleep(0.5)

        # 4. 输入文本（统一用 adb input text，ADB Keyboard broadcast在密码框不生效）
        chunk_size = 4
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            await _adb(["shell", "input", "text", chunk], timeout=10)
            await asyncio.sleep(0.3)
        logger.info("坐标输入完成(adb): ({}, {}) -> '{}'", x, y, display)

        # 5. 强制隐藏键盘（无条件执行 + 等待动画完成）
        # 根因：键盘没关掉时，下一步点击坐标会打到键盘按键上（Y/S键Bug的根因）
        await asyncio.sleep(0.3)
        await _adb(["shell", "input", "keyevent", "KEYCODE_BACK"])
        await asyncio.sleep(1.2)  # 等键盘收起动画完全结束（0.8秒不够）
        # 验证键盘确实关闭，没关的话再发一次
        try:
            kb_check = await loop.run_in_executor(
                None, lambda: subprocess.run(
                    adb_base + ["shell", "dumpsys", "input_method"],
                    capture_output=True, timeout=3,
                )
            )
            stdout = kb_check.stdout.decode(errors="ignore")
            if "mInputShown=true" in stdout:
                await _adb(["shell", "input", "keyevent", "KEYCODE_BACK"])
                await asyncio.sleep(1.0)
                logger.debug("键盘仍未关闭，再发一次BACK")
        except Exception:
            pass
        logger.debug("键盘已强制关闭")

    async def input_text(self, selector: str, text: str) -> None:
        """输入文本。"""
        step = self._next_step()
        display = text[:15] + "..." if len(text) > 15 else text
        logger.info("[步骤{}] 输入: {} -> '{}'", step, selector, display)

        element_id = await self._find_element_with_wait(selector, timeout_s=15)
        await self._safe_session_call("POST", f"/element/{element_id}/clear")
        await self._safe_session_call("POST", f"/element/{element_id}/value", {
            "text": text,
        })
        # 输入完毕后收起键盘，避免软键盘遮挡下一个元素
        await self.hide_keyboard()
        # 等待键盘收起动画完成，否则下一个元素可能还被遮挡
        await asyncio.sleep(0.5)

    async def hide_keyboard(self) -> None:
        """收起软键盘。Android 用 adb ESCAPE 键；iOS 用 Appium hideKeyboard API。"""
        if self._config.platform_name == "iOS":
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(
                    None, lambda: self._session_request(
                        "POST", f"/session/{self._session_id}/appium/device/hide_keyboard", {}
                    )
                )
            except Exception:
                pass
            return
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None, lambda: subprocess.run(
                    ["adb", "shell", "input", "keyevent", "111"],
                    capture_output=True, timeout=5,
                )
            )
        except Exception:
            pass

    async def _ensure_latin_ime(self, adb_base: list[str], loop, _adb) -> None:
        """确保输入法不会干扰 adb input text（中文输入法会吞数字键）。

        策略：首次调用时检测当前输入法，如果不是安全的就切换。
        优先级：ADB Keyboard > Latin/AOSP > 当前输入法（不得已）
        整个测试期间只切一次，测试结束时 close() 会恢复原输入法。
        """
        # 不再跳过——每次都检查（Android密码框可能自动切回中文输入法）

        try:
            result = await loop.run_in_executor(
                None, lambda: subprocess.run(
                    adb_base + ["shell", "settings", "get", "secure", "default_input_method"],
                    capture_output=True, timeout=3,
                )
            )
            current_ime = result.stdout.decode(errors="ignore").strip()

            safe_keywords = ["adbkeyboard", "adbime", "latin", "aosp", "leanback", "tv.ime"]
            is_safe = any(s in current_ime.lower() for s in safe_keywords)

            if not is_safe and current_ime:
                self._original_ime = current_ime
                list_result = await loop.run_in_executor(
                    None, lambda: subprocess.run(
                        adb_base + ["shell", "ime", "list", "-s"],
                        capture_output=True, timeout=3,
                    )
                )
                all_imes = [x.strip() for x in list_result.stdout.decode(errors="ignore").strip().split("\n") if x.strip()]

                # 优先找 ADB Keyboard（专为自动化设计，零干扰）
                target_ime = None
                for ime in all_imes:
                    if "adbkeyboard" in ime.lower() or "adbime" in ime.lower():
                        target_ime = ime
                        break
                # 其次找 Latin/AOSP 键盘
                if not target_ime:
                    for ime in all_imes:
                        if any(s in ime.lower() for s in ["latin", "aosp", "leanback"]):
                            target_ime = ime
                            break

                if target_ime:
                    # 先 enable 再 set（有些设备需要先启用）
                    await _adb(["shell", "ime", "enable", target_ime], timeout=3)
                    await asyncio.sleep(0.2)
                    await _adb(["shell", "ime", "set", target_ime], timeout=3)
                    self._ime_switched = True
                    self._use_adb_keyboard = "adbkeyboard" in target_ime.lower() or "adbime" in target_ime.lower()
                    logger.info("输入法切换: {} → {} (避免中文输入法干扰)",
                                current_ime.split("/")[-1], target_ime.split("/")[-1])
                else:
                    logger.warning("未找到安全输入法！当前: {} | 可能影响输入准确性", current_ime)
                    self._ime_switched = True
            else:
                self._ime_switched = True
                self._use_adb_keyboard = "adbkeyboard" in current_ime.lower() or "adbime" in current_ime.lower()
        except Exception as e:
            logger.debug("输入法检测失败: {}", str(e)[:60])

    async def _restore_ime(self) -> None:
        """恢复原始输入法（测试结束时调用）。"""
        if self._original_ime:
            try:
                loop = asyncio.get_event_loop()
                device_serial = self._device.extra.get("serial", "") or self._config.device_name
                adb_base = ["adb"]
                if device_serial:
                    adb_base.extend(["-s", device_serial])
                await loop.run_in_executor(
                    None, lambda: subprocess.run(
                        adb_base + ["shell", "ime", "set", self._original_ime],
                        capture_output=True, timeout=3,
                    )
                )
                logger.info("输入法已恢复: {}", self._original_ime.split("/")[-1])
            except Exception:
                pass
            self._original_ime = None
            self._ime_switched = False

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

        # iOS 直接用 Appium 截图（无 adb）
        if self._config.platform_name != "iOS":
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
        resp = await self._safe_session_call("GET", "/source")
        return resp.get("value", "")

    async def dump_ui_tree(self) -> str:
        """获取UI树XML。优先走Appium /source（U2已在运行），失败走adb uiautomator dump。

        注意：adb uiautomator dump 和 UiAutomator2 Server 冲突（都需要UiAutomation实例），
        所以当Appium Session活跃时，adb dump会返回空。必须优先用Appium。

        Returns:
            UI树XML字符串，失败返回空字符串
        """
        # 方式A：通过Appium /source（U2已经在运行，不会冲突）
        # 超时设10秒：Flutter页面跳转后U2可能崩溃，不要等60秒
        # 如果U2已被标记为死亡，跳过/source直接走adb dump
        if self._session_id and not self._u2_dead:
            try:
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(
                    None, lambda: self._session_request("GET", "/source", timeout=10)
                )
                xml_str = resp.get("value", "")
                if xml_str and "<hierarchy" in xml_str:
                    logger.debug("UI树获取成功(Appium) | 大小={}字节", len(xml_str))
                    return xml_str
            except Exception as e:
                logger.debug("Appium /source失败: {}", str(e)[:60])
                self._u2_dead = True  # 标记U2已死，后续跳过/source

        # 方式B：adb uiautomator dump（Appium /source失败时使用）
        # 注意：U2 Server 可能还活着但无响应，必须先杀掉才能让 adb dump 获取新鲜XML
        # 重要：不要清空 _session_id！后续 click/fill 用纯 adb tap 不需要 session，
        #       而 get_text 等需要 session 的操作会通过 _safe_session_call 自动恢复
        device_serial = self._device.extra.get("serial", "") or self._config.device_name
        adb_base = ["adb"]
        if device_serial:
            adb_base.extend(["-s", device_serial])
        loop = asyncio.get_event_loop()
        try:
            # 先杀掉可能僵死的 U2 Server，释放 UiAutomation 实例
            await loop.run_in_executor(
                None, lambda: subprocess.run(
                    adb_base + ["shell", "am", "force-stop", "io.appium.uiautomator2.server"],
                    capture_output=True, timeout=5,
                )
            )
            await asyncio.sleep(0.5)
            # 先删旧文件避免读到缓存
            await loop.run_in_executor(
                None, lambda: subprocess.run(
                    adb_base + ["shell", "rm", "-f", "/sdcard/tp_ui_dump.xml"],
                    capture_output=True, timeout=3,
                )
            )
            await loop.run_in_executor(
                None, lambda: subprocess.run(
                    adb_base + ["shell", "uiautomator", "dump", "/sdcard/tp_ui_dump.xml"],
                    capture_output=True, timeout=10,
                )
            )
            result = await loop.run_in_executor(
                None, lambda: subprocess.run(
                    adb_base + ["shell", "cat", "/sdcard/tp_ui_dump.xml"],
                    capture_output=True, timeout=5,
                )
            )
            xml_str = result.stdout.decode(errors="ignore")
            if xml_str and "<hierarchy" in xml_str:
                logger.debug("UI树dump成功(adb) | 大小={}字节", len(xml_str))
                return xml_str
            logger.debug("UI树dump为空或格式异常")
            return ""
        except Exception as e:
            logger.debug("UI树dump失败: {}", str(e)[:80])
            return ""

    async def get_text(self, selector: str) -> str:
        """获取元素文本。"""
        element_id = await self._find_element_with_wait(selector, timeout_s=5)
        resp = await self._safe_session_call("GET", f"/element/{element_id}/text")
        return resp.get("value", "")

    async def swipe_screen(self, direction: str = "down") -> None:
        """通过adb滑动屏幕（不走Appium，100%可靠）。

        direction: "down"=下滑看更多, "up"=上滑回顶
        """
        w = int(self._device.screen_width or 1080)
        h = int(self._device.screen_height or 2400)
        cx = w // 2
        if direction == "down":
            sy, ey = int(h * 0.7), int(h * 0.3)  # 从下往上滑 = 页面向下滚动
        elif direction == "up":
            sy, ey = int(h * 0.3), int(h * 0.7)  # 从上往下滑 = 页面向上滚动
        else:
            sy, ey = int(h * 0.7), int(h * 0.3)

        logger.info("adb滑动: {} | ({},{}) -> ({},{})", direction, cx, sy, cx, ey)
        device_serial = self._device.extra.get("serial", "") or self._config.device_name
        cmd = ["adb"]
        if device_serial:
            cmd.extend(["-s", device_serial])
        cmd.extend(["shell", "input", "swipe", str(cx), str(sy), str(cx), str(ey), "300"])
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: subprocess.run(cmd, capture_output=True, timeout=10)
        )
        await asyncio.sleep(0.5)

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
            except Exception:
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
        iOS：WDA 连接期间屏幕不会自动锁定，无需 adb 操作；
             但需用户手动将 iPhone 设置→显示与亮度→自动锁定→从不。
        """
        if self._config.platform_name == "iOS":
            logger.info("iOS 测试：请确认 iPhone 已设置「自动锁定→从不」，WDA 连接期间屏幕将保持亮屏")
            return

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
        """恢复设备屏幕设置到测试前的状态（iOS 跳过）。"""
        if self._config.platform_name == "iOS":
            return
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

    # ── U2 存活检测与自动恢复 ────────────────────

    def _is_u2_process_alive(self) -> bool:
        """同步检测设备上 UiAutomator2 Server 进程是否存活。"""
        try:
            r = subprocess.run(
                ["adb", "shell", "ps", "-A"],
                capture_output=True, text=True, timeout=5,
            )
            return "uiautomator" in r.stdout
        except Exception:
            return False

    async def _recover_u2_session(self) -> None:
        """U2 Server 被 Flutter 杀死后，重建 Session（不杀 app、不重启 Activity）。

        Flutter 的 setState/pushReplacementNamed 等操作会导致
        UiAutomator2 Server 进程被系统杀死（SIGKILL）。
        此方法在不终止被测 app 的前提下重建 Appium Session，
        让 Appium 重新启动一个全新的 U2 Server 实例。

        如果 config 中有 appPackage，则传给新 Session 以保证 Appium 能正确
        instrument 该 APP（读取 Flutter 的 @hint 等属性）。同时设置
        dontStopAppOnReset + noReset 避免重启 Activity。
        """
        logger.warning("UiAutomator2 Server 进程已死亡，正在重建Session...")
        loop = asyncio.get_event_loop()

        # 1. 丢弃旧 session（不等DELETE响应，U2已死必然超时）
        self._session_id = None

        # 2. 清理残留的 U2 进程
        def _kill_uia2():
            for pkg in ("io.appium.uiautomator2.server",
                        "io.appium.uiautomator2.server.test"):
                subprocess.run(
                    ["adb", "shell", "am", "force-stop", pkg],
                    capture_output=True, timeout=5,
                )
        await loop.run_in_executor(None, _kill_uia2)
        await asyncio.sleep(1)

        # 3. 创建新 Session
        #    传 appPackage 让 Appium 绑定到被测 APP（XPath 才能看到 @hint 等属性）
        #    dontStopAppOnReset=true 避免 Appium 重启 Activity（保留当前页面状态）
        caps = {
            "platformName": self._config.platform_name,
            "appium:automationName": self._config.automation_name,
            "appium:noReset": True,
            "appium:dontStopAppOnReset": True,
            "appium:newCommandTimeout": 300,
            "appium:autoGrantPermissions": True,
        }
        if self._config.device_name:
            caps["appium:deviceName"] = self._config.device_name
        if self._config.app_package:
            caps["appium:appPackage"] = self._config.app_package
        if self._config.app_activity:
            caps["appium:appActivity"] = self._config.app_activity

        resp = await loop.run_in_executor(
            None, lambda: self._request(
                "POST", "/session",
                {"capabilities": {"alwaysMatch": caps}},
            )
        )
        self._session_id = resp.get("value", {}).get("sessionId")
        if not self._session_id:
            raise RuntimeError(f"U2恢复失败: Session重建失败: {resp}")
        self._u2_dead = False  # U2恢复成功

        # 4. 重新设置 waitForIdleTimeout=0（Flutter 兼容）
        try:
            await loop.run_in_executor(
                None, lambda: self._session_request(
                    "POST", "/appium/settings",
                    {"settings": {"waitForIdleTimeout": 0,
                                  "waitForSelectorTimeout": 0}},
                )
            )
        except Exception:
            pass

        await asyncio.sleep(2)
        logger.info("U2 Session 自动恢复成功 | ID={}", self._session_id[:8])

    # ── 内部方法 ─────────────────────────────────

    async def _find_element_with_wait(self, selector: str, timeout_s: float = 15) -> str:
        """带重试的元素查找，等待元素出现后返回element ID。

        Flutter等框架渲染或键盘收起后UI树可能需要较长时间才就绪，
        此方法每1秒轮询一次直到找到或超时。

        策略：
        - 404（元素不存在）：正常等待重试，不触发U2恢复
        - 500 + instrumentation not running：U2真崩了，恢复后继续
        - 请求超时（timed out）：U2可能hang了，恢复后继续
        - 恢复U2后不重置计时器，总时间始终15秒封顶
        - 最多恢复U2 Session 1次，避免在元素确实不存在时反复恢复浪费时间
        """
        import time as _time
        start = _time.time()
        last_err: Exception | None = None
        u2_recover_count = 0
        max_u2_recovers = 1  # 最多恢复1次（防止元素不存在时反复恢复空转）
        while True:
            # 检查是否被用户取消
            if self._is_cancelled_fn and callable(self._is_cancelled_fn) and self._is_cancelled_fn():
                raise RuntimeError("测试已被用户取消")

            # 超时检查（放在循环开头，确保总时间封顶）
            if _time.time() - start >= timeout_s:
                raise last_err or RuntimeError(f"元素查找超时({timeout_s}s): {selector}")

            try:
                return await self._find_element(selector)
            except RuntimeError as e:
                err_str = str(e)
                last_err = e

                # 区分错误类型：
                # - 500 + "instrumentation not running" = U2 真崩了
                # - "timed out" / "socket hang up" = U2 无响应（可能hang了）
                # - 404 "no such element" = 元素不存在（正常等待即可）
                is_u2_crash = ("instrumentation process is not running" in err_str
                               or ("500" in err_str[:20] and "socket hang up" in err_str))
                is_u2_timeout = "超时" in err_str or "timed out" in err_str.lower()

                if (is_u2_crash or is_u2_timeout) and u2_recover_count < max_u2_recovers:
                    u2_recover_count += 1
                    logger.warning("U2异常({}/{}次恢复): {}", u2_recover_count, max_u2_recovers, err_str[:80])
                    try:
                        await self._recover_u2_session()
                    except Exception as recover_err:
                        logger.error("U2 Session恢复失败: {}", recover_err)
                        raise last_err from recover_err
                    # 注意：不重置start，总时间仍然封顶在timeout_s
                    await asyncio.sleep(2)
                    continue

                await asyncio.sleep(1)  # 重试间隔1秒（减少对U2的压力）

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
        if selector.startswith("xpath:"):
            # 蓝本可能写 xpath://... 或 xpath:...
            strategy, value = "xpath", selector[6:]
        elif selector.startswith("//"):
            strategy, value = "xpath", selector
        elif selector.startswith("id:"):
            strategy, value = "id", selector[3:]
        elif selector.startswith("accessibility_id:"):
            desc_value = selector[17:]
            if self._config.platform_name == "iOS":
                # iOS XCUITest 直接支持 accessibility id 策略（对应 accessibilityIdentifier）
                strategy, value = "accessibility id", desc_value
            else:
                # Android：转为 UiSelector.descriptionStartsWith() — 避免 accessibility id 策略内部的
                # waitForIdle() 调用，在 Flutter 等持续动画的 app 上会卡死
                # 用 StartsWith 而非精确匹配：Flutter Semantics label + child 文本
                # 会合并为 "label\n子文本"（如 "txt_error\n用户名或密码错误"）
                strategy = "-android uiautomator"
                value = f'new UiSelector().descriptionStartsWith("{desc_value}")'
        elif selector.startswith("class:"):
            strategy, value = "class name", selector[6:]
        elif selector.startswith("uia:"):
            strategy, value = "-android uiautomator", selector[4:]
        elif selector.startswith("css:"):
            strategy, value = "css selector", selector[4:]
        elif selector.startswith(("#", ".")) or ("[" in selector and "]" in selector and not selector.startswith("//")):
            # 常见 CSS 选择器模式（WebView 上下文下有效）
            strategy, value = "css selector", selector
        else:
            # 默认当xpath处理
            strategy, value = "xpath", selector

        logger.debug("_find_element: strategy={!r} value={!r}", strategy, value[:80])
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, lambda: self._session_request("POST", "/element", {
                "using": strategy,
                "value": value,
            }, timeout=5)
        )

        element = resp.get("value", {})
        # W3C 协议返回格式
        if isinstance(element, dict):
            for key in element:
                if key.startswith("element-") or key == "ELEMENT":
                    return element[key]
        raise RuntimeError(f"元素未找到: {selector}")
