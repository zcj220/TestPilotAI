"""
Windows 桌面控制器（v7.0）

基于 ctypes + Win32 API 实现，零外部依赖。
支持：Win32 / WPF / WinForms / UWP 原生应用测试。

选择器格式：
- name:XXX         → 按窗口标题/控件名称查找
- automationid:XXX → 通过 PowerShell UI Automation 查找
- class:XXX        → 按 ClassName 查找
- point:X,Y        → 直接坐标点击
"""

import asyncio
import ctypes
import ctypes.wintypes
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

from src.controller.base import BaseController, DeviceInfo, ElementInfo, Platform
from src.controller.window_manager import (
    WindowManager, WindowInfo, DesktopConfig,
)

user32 = ctypes.windll.user32

# SendInput 常量
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_MOVE = 0x0001
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_BACK = 0x08
VK_ESCAPE = 0x1B


class DesktopController(BaseController):
    """Windows 桌面应用控制器。

    通过 Win32 API 操作窗口，通过 PowerShell 调用 UI Automation
    查找控件，通过 SendInput 模拟键鼠操作。
    """

    def __init__(self, config: Optional[DesktopConfig] = None) -> None:
        self._config = config or DesktopConfig()
        self._hwnd: Optional[int] = None
        self._target_window: Optional[WindowInfo] = None
        self._step_counter = 0
        self._device = DeviceInfo(
            platform=Platform.WINDOWS,
            name="Windows Desktop",
            screen_width=user32.GetSystemMetrics(0),
            screen_height=user32.GetSystemMetrics(1),
        )

    @property
    def platform(self) -> Platform:
        return Platform.WINDOWS

    @property
    def device_info(self) -> DeviceInfo:
        return self._device

    @property
    def target_hwnd(self) -> Optional[int]:
        return self._hwnd

    def _next_step(self) -> int:
        self._step_counter += 1
        return self._step_counter

    # ── BaseController 实现 ──────────────────────

    async def launch(self) -> None:
        """启动控制器：查找或启动目标窗口。"""
        # 如果配置了exe，先启动它
        if self._config.target_exe:
            logger.info("启动应用: {}", self._config.target_exe)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: subprocess.Popen(
                self._config.target_exe, shell=True
            ))
            await asyncio.sleep(2)  # 等待窗口出现

        # 查找目标窗口
        window = self._find_target()
        if not window:
            raise RuntimeError(
                f"找不到目标窗口 (title='{self._config.target_title}' "
                f"class='{self._config.target_class}' pid={self._config.target_pid})"
            )

        self._hwnd = window.hwnd
        self._target_window = window
        self._device.is_connected = True
        self._device.extra = {"hwnd": self._hwnd, "pid": window.pid}

        # 聚焦窗口
        WindowManager.focus_window(self._hwnd)

        # 更新屏幕尺寸为窗口尺寸
        rect = WindowManager.get_window_rect(self._hwnd)
        self._device.screen_width = rect["width"]
        self._device.screen_height = rect["height"]

        logger.info("DesktopController 已启动 | {} | {}x{}",
                     window, rect["width"], rect["height"])

    async def close(self) -> None:
        """关闭控制器（不关闭目标窗口）。"""
        self._hwnd = None
        self._target_window = None
        self._device.is_connected = False
        logger.info("DesktopController 已关闭")

    async def navigate(self, url_or_activity: str) -> None:
        """打开应用或切换窗口。

        - 如果是.exe路径，启动应用
        - 如果是窗口标题，切换到该窗口
        """
        step = self._next_step()

        if url_or_activity.endswith(".exe") or "\\" in url_or_activity:
            logger.info("[步骤{}] 启动应用: {}", step, url_or_activity)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: subprocess.Popen(
                url_or_activity, shell=True
            ))
            await asyncio.sleep(2)
            # 重新查找窗口
            await self._refresh_target()
        else:
            logger.info("[步骤{}] 切换窗口: {}", step, url_or_activity)
            window = WindowManager.find_window(title=url_or_activity)
            if window:
                self._hwnd = window.hwnd
                self._target_window = window
                WindowManager.focus_window(self._hwnd)
            else:
                raise RuntimeError(f"找不到窗口: {url_or_activity}")

    async def tap(self, selector: str) -> None:
        """点击元素。"""
        step = self._next_step()
        logger.info("[步骤{}] 点击: {}", step, selector)

        if selector.startswith("point:"):
            # 直接坐标点击
            parts = selector[6:].split(",")
            x, y = int(parts[0].strip()), int(parts[1].strip())
            await self._click_at(x, y)
        else:
            # 通过 UI Automation 查找元素并点击
            elem = await self._find_element_uia(selector)
            if elem and "center_x" in elem and "center_y" in elem:
                await self._click_at(elem["center_x"], elem["center_y"])
            else:
                raise RuntimeError(f"元素未找到或无法定位: {selector}")

    async def input_text(self, selector: str, text: str) -> None:
        """在控件中输入文本。"""
        step = self._next_step()
        display = text[:15] + "..." if len(text) > 15 else text
        logger.info("[步骤{}] 输入: {} -> '{}'", step, selector, display)

        # 先点击定位
        await self.tap(selector)
        await asyncio.sleep(0.2)

        # 用 SendInput 逐字输入（支持中文/Unicode）
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _send_text(text))

    async def screenshot(self, name: str = "") -> Path:
        """截取目标窗口。"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        step_str = f"step{self._step_counter:03d}"
        safe_name = name.replace(" ", "_").replace("/", "_")[:50] if name else "capture"
        filename = f"{timestamp}_{step_str}_{safe_name}"
        filepath = self._config.screenshot_dir / filename

        if self._hwnd and user32.IsWindow(self._hwnd):
            WindowManager.focus_window(self._hwnd)
            await asyncio.sleep(0.1)
            return WindowManager.capture_window(self._hwnd, filepath)
        else:
            return WindowManager.capture_screen(filepath)

    async def get_page_source(self) -> str:
        """获取窗口 UI 树（通过 PowerShell + UI Automation）。"""
        if not self._hwnd:
            return "<no target window>"

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: _get_ui_tree(self._hwnd))

    async def get_text(self, selector: str) -> str:
        """获取元素文本。"""
        elem = await self._find_element_uia(selector)
        return elem.get("name", "") if elem else ""

    async def wait_for_element(self, selector: str, timeout_ms: int = 10000) -> None:
        """等待元素出现。"""
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            try:
                elem = await self._find_element_uia(selector)
                if elem:
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)
        raise RuntimeError(f"等待元素超时: {selector}")

    # ── 内部方法 ──────────────────────────────────

    def _find_target(self) -> Optional[WindowInfo]:
        """查找目标窗口。"""
        return WindowManager.find_window(
            title=self._config.target_title,
            class_name=self._config.target_class,
            pid=self._config.target_pid,
        )

    async def _refresh_target(self) -> None:
        """重新查找目标窗口。"""
        for _ in range(10):
            window = self._find_target()
            if window:
                self._hwnd = window.hwnd
                self._target_window = window
                WindowManager.focus_window(self._hwnd)
                return
            await asyncio.sleep(0.5)

    async def _click_at(self, x: int, y: int) -> None:
        """在屏幕坐标点击。"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _click_screen(x, y))

    async def _find_element_uia(self, selector: str) -> Optional[dict]:
        """通过 PowerShell UI Automation 查找元素。"""
        if not self._hwnd:
            return None
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: _find_element_ps(self._hwnd, selector)
        )


# ── Win32 输入模拟 ────────────────────────────────

def _click_screen(x: int, y: int) -> None:
    """在屏幕坐标 (x, y) 处点击。"""
    # 先移动鼠标
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)
    abs_x = int(x * 65535 / screen_w)
    abs_y = int(y * 65535 / screen_h)

    # 构造 INPUT 结构体数组
    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.wintypes.LONG), ("dy", ctypes.wintypes.LONG),
            ("mouseData", ctypes.wintypes.DWORD), ("dwFlags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.wintypes.DWORD), ("union", INPUT_UNION)]

    inputs = (INPUT * 3)()
    # 移动
    inputs[0].type = INPUT_MOUSE
    inputs[0].union.mi.dx = abs_x
    inputs[0].union.mi.dy = abs_y
    inputs[0].union.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
    # 按下
    inputs[1].type = INPUT_MOUSE
    inputs[1].union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
    # 抬起
    inputs[2].type = INPUT_MOUSE
    inputs[2].union.mi.dwFlags = MOUSEEVENTF_LEFTUP

    user32.SendInput(3, ctypes.pointer(inputs[0]), ctypes.sizeof(INPUT))


def _send_text(text: str) -> None:
    """通过 SendInput 输入文本（Unicode支持）。"""

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.wintypes.WORD), ("wScan", ctypes.wintypes.WORD),
            ("dwFlags", ctypes.wintypes.DWORD), ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.wintypes.DWORD), ("union", INPUT_UNION)]

    for ch in text:
        code = ord(ch)
        inputs = (INPUT * 2)()
        # KeyDown
        inputs[0].type = INPUT_KEYBOARD
        inputs[0].union.ki.wScan = code
        inputs[0].union.ki.dwFlags = KEYEVENTF_UNICODE
        # KeyUp
        inputs[1].type = INPUT_KEYBOARD
        inputs[1].union.ki.wScan = code
        inputs[1].union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        user32.SendInput(2, ctypes.pointer(inputs[0]), ctypes.sizeof(INPUT))


# ── PowerShell UI Automation ──────────────────────

def _find_element_ps(hwnd: int, selector: str) -> Optional[dict]:
    """通过 PowerShell 调用 .NET UI Automation 查找元素。

    返回 {"name": ..., "class": ..., "center_x": ..., "center_y": ...}
    """
    if selector.startswith("name:"):
        prop = "Name"
        value = selector[5:]
    elif selector.startswith("automationid:"):
        prop = "AutomationId"
        value = selector[13:]
    elif selector.startswith("class:"):
        prop = "ClassName"
        value = selector[6:]
    else:
        # 默认按Name搜索
        prop = "Name"
        value = selector

    ps_script = f"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$ae = [System.Windows.Automation.AutomationElement]::FromHandle({hwnd})
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::{prop}Property, "{value}")
$el = $ae.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
if ($el) {{
    $rect = $el.Current.BoundingRectangle
    @{{
        name = $el.Current.Name
        class_name = $el.Current.ClassName
        automation_id = $el.Current.AutomationId
        center_x = [int]($rect.X + $rect.Width / 2)
        center_y = [int]($rect.Y + $rect.Height / 2)
        width = [int]$rect.Width
        height = [int]$rect.Height
    }} | ConvertTo-Json
}} else {{ "null" }}
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout.strip()
        if output and output != "null":
            import json
            return json.loads(output)
    except Exception as e:
        logger.debug("UI Automation查找失败: {}", e)
    return None


def _get_ui_tree(hwnd: int) -> str:
    """获取窗口 UI 树的简要结构。"""
    ps_script = f"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$ae = [System.Windows.Automation.AutomationElement]::FromHandle({hwnd})
function Get-Children($el, $depth) {{
    if ($depth -gt 3) {{ return }}
    $children = $el.FindAll([System.Windows.Automation.TreeScope]::Children,
        [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($c in $children) {{
        $indent = "  " * $depth
        $n = $c.Current.Name
        $cls = $c.Current.ClassName
        $aid = $c.Current.AutomationId
        "$indent[$cls] Name='$n' AutomationId='$aid'"
        Get-Children $c ($depth + 1)
    }}
}}
$n = $ae.Current.Name
"[Root] Name='$n'"
Get-Children $ae 1
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout
    except Exception as e:
        return f"<error: {e}>"
