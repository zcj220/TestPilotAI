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
    ):
        self.project_path = project_path
        self.devtools_path = devtools_path or self._detect_devtools()
        self.timeout_ms = timeout_ms
        self.account = account
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

    async def launch(self) -> None:
        """启动小程序自动化连接。"""
        if not self._config.devtools_path:
            raise RuntimeError(
                "未找到微信开发者工具。请安装后在配置中指定路径，"
                "或安装到默认位置。"
            )
        if not self._config.project_path:
            raise RuntimeError("请指定小程序项目路径 (project_path)")

        logger.info("启动小程序自动化 | 项目: {}", self._config.project_path)

        # 通过 Node.js 桥接脚本启动 automator
        bridge_script = Path(__file__).parent / "miniprogram_bridge.js"
        if not bridge_script.exists():
            raise RuntimeError(f"桥接脚本不存在: {bridge_script}")

        result = await self._call_bridge("connect", {
            "projectPath": self._config.project_path,
            "devToolsPath": self._config.devtools_path,
        })

        if result.get("success"):
            self._connected = True
            self._device.is_connected = True
            self._device.extra = {"project": self._config.project_path}
            logger.info("小程序自动化已连接")
        else:
            raise RuntimeError(f"连接失败: {result.get('error', '未知错误')}")

    async def close(self) -> None:
        """关闭小程序自动化连接。"""
        if self._connected:
            await self._call_bridge("disconnect", {})
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
        """调用 Node.js 桥接脚本。"""
        bridge_script = Path(__file__).parent / "miniprogram_bridge.js"
        payload = json.dumps({"action": action, "params": params})

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, lambda: subprocess.run(
                ["node", str(bridge_script), payload],
                capture_output=True, text=True,
                timeout=self._config.timeout_ms // 1000 + 5,
            ))
            if result.stdout.strip():
                return json.loads(result.stdout.strip().split("\n")[-1])
            return {"success": False, "error": result.stderr.strip() or "无输出"}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "桥接脚本超时"}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON解析失败: {e}"}
        except FileNotFoundError:
            return {"success": False, "error": "未找到 Node.js，请确保已安装"}
        except Exception as e:
            return {"success": False, "error": str(e)}
