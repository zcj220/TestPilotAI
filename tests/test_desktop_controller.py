"""
Windows 桌面控制器测试（v7.0）

覆盖：DesktopConfig、WindowInfo、WindowManager、DesktopController
因为 ctypes.windll 在 CI/Linux 不可用，全部 mock Win32 API。
"""

import json
import struct
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

from src.controller.base import Platform, DeviceInfo
from src.controller.window_manager import WindowInfo, WindowManager, DesktopConfig


# ── WindowInfo 测试 ─────────────────────────────

class TestWindowInfo:
    def test_create(self):
        w = WindowInfo(hwnd=12345, title="记事本", class_name="Notepad", pid=100)
        assert w.hwnd == 12345
        assert w.title == "记事本"
        assert w.class_name == "Notepad"
        assert w.pid == 100

    def test_to_dict(self):
        w = WindowInfo(hwnd=1, title="T", class_name="C", pid=2)
        d = w.to_dict()
        assert d["hwnd"] == 1
        assert d["title"] == "T"

    def test_repr(self):
        w = WindowInfo(hwnd=1, title="Test Window", class_name="Cls", pid=3)
        r = repr(w)
        assert "Test Window" in r
        assert "Cls" in r


class TestDesktopConfig:
    def test_defaults(self, tmp_path):
        cfg = DesktopConfig(screenshot_dir=str(tmp_path / "shots"))
        assert cfg.target_title == ""
        assert cfg.target_pid == 0
        assert cfg.timeout_ms == 10000
        assert cfg.screenshot_dir.exists()

    def test_custom(self, tmp_path):
        cfg = DesktopConfig(
            target_title="记事本",
            target_class="Notepad",
            target_pid=1234,
            target_exe="notepad.exe",
            screenshot_dir=str(tmp_path / "custom"),
            timeout_ms=5000,
        )
        assert cfg.target_title == "记事本"
        assert cfg.target_class == "Notepad"
        assert cfg.target_pid == 1234
        assert cfg.target_exe == "notepad.exe"
        assert cfg.timeout_ms == 5000


# ── WindowManager 测试（mock Win32 API）──────────

class TestWindowManager:
    @patch("src.controller.window_manager.user32")
    def test_enumerate_windows(self, mock_user32):
        """模拟 EnumWindows 回调。"""
        # 让 EnumWindows 直接调用回调函数
        def fake_enum(callback, _):
            # 模拟两个窗口
            callback(100, 0)
            callback(200, 0)
            return True

        mock_user32.EnumWindows.side_effect = fake_enum
        mock_user32.IsWindowVisible.return_value = True
        mock_user32.GetWindowTextW.side_effect = _make_text_writer(["记事本", "计算器"])
        mock_user32.GetClassNameW.side_effect = _make_text_writer(["Notepad", "CalcFrame"])
        mock_user32.GetWindowThreadProcessId.side_effect = _make_pid_writer([100, 200])

        windows = WindowManager.enumerate_windows()
        assert len(windows) == 2
        assert windows[0].title == "记事本"
        assert windows[1].class_name == "CalcFrame"

    @patch("src.controller.window_manager.user32")
    def test_find_window_by_title(self, mock_user32):
        def fake_enum(callback, _):
            callback(100, 0)
            callback(200, 0)
            return True

        mock_user32.EnumWindows.side_effect = fake_enum
        mock_user32.IsWindowVisible.return_value = True
        mock_user32.GetWindowTextW.side_effect = _make_text_writer(["记事本 - test.txt", "计算器"])
        mock_user32.GetClassNameW.side_effect = _make_text_writer(["Notepad", "CalcFrame"])
        mock_user32.GetWindowThreadProcessId.side_effect = _make_pid_writer([100, 200])

        w = WindowManager.find_window(title="记事本")
        assert w is not None
        assert w.hwnd == 100

    @patch("src.controller.window_manager.user32")
    def test_find_window_not_found(self, mock_user32):
        def fake_enum(callback, _):
            callback(100, 0)
            return True

        mock_user32.EnumWindows.side_effect = fake_enum
        mock_user32.IsWindowVisible.return_value = True
        mock_user32.GetWindowTextW.side_effect = _make_text_writer(["记事本"])
        mock_user32.GetClassNameW.side_effect = _make_text_writer(["Notepad"])
        mock_user32.GetWindowThreadProcessId.side_effect = _make_pid_writer([100])

        w = WindowManager.find_window(title="不存在")
        assert w is None

    @patch("src.controller.window_manager.user32")
    def test_focus_window(self, mock_user32):
        mock_user32.IsIconic.return_value = False
        mock_user32.SetForegroundWindow.return_value = True
        assert WindowManager.focus_window(123) is True

    @patch("src.controller.window_manager.user32")
    def test_focus_minimized_window(self, mock_user32):
        mock_user32.IsIconic.return_value = True
        mock_user32.ShowWindow.return_value = True
        mock_user32.SetForegroundWindow.return_value = True
        assert WindowManager.focus_window(123) is True
        mock_user32.ShowWindow.assert_called_once()

    @patch("src.controller.window_manager.user32")
    def test_get_window_rect(self, mock_user32):
        import ctypes.wintypes

        def fake_get_rect(hwnd, rect_ptr):
            rect = rect_ptr._obj if hasattr(rect_ptr, '_obj') else rect_ptr
            rect.left = 100
            rect.top = 50
            rect.right = 900
            rect.bottom = 650
            return True

        mock_user32.GetWindowRect.side_effect = fake_get_rect
        rect = WindowManager.get_window_rect(123)
        assert rect["width"] == 800
        assert rect["height"] == 600

    @patch("src.controller.window_manager.user32")
    def test_resize_window(self, mock_user32):
        import ctypes.wintypes

        def fake_get_rect(hwnd, rect_ptr):
            rect = rect_ptr._obj if hasattr(rect_ptr, '_obj') else rect_ptr
            rect.left = 0
            rect.top = 0
            return True

        mock_user32.GetWindowRect.side_effect = fake_get_rect
        mock_user32.MoveWindow.return_value = True
        assert WindowManager.resize_window(123, 1024, 768) is True


# ── DesktopController 测试（mock 所有系统调用）──────

class TestDesktopController:
    @pytest.fixture
    def mock_user32(self):
        with patch("src.controller.desktop.user32") as m:
            m.GetSystemMetrics.side_effect = lambda i: 1920 if i == 0 else 1080
            yield m

    @pytest.fixture
    def mock_wm(self):
        with patch("src.controller.desktop.WindowManager") as m:
            yield m

    @pytest.fixture
    def config(self, tmp_path):
        return DesktopConfig(
            target_title="记事本",
            screenshot_dir=str(tmp_path / "shots"),
        )

    @pytest.mark.asyncio
    async def test_launch_success(self, mock_user32, mock_wm, config):
        from src.controller.desktop import DesktopController

        mock_window = WindowInfo(hwnd=999, title="记事本", class_name="Notepad", pid=50)
        mock_wm.find_window.return_value = mock_window
        mock_wm.focus_window.return_value = True
        mock_wm.get_window_rect.return_value = {"width": 800, "height": 600}

        ctrl = DesktopController(config)
        await ctrl.launch()

        assert ctrl.target_hwnd == 999
        assert ctrl.device_info.is_connected is True
        assert ctrl.device_info.platform == Platform.WINDOWS

    @pytest.mark.asyncio
    async def test_launch_not_found(self, mock_user32, mock_wm, config):
        from src.controller.desktop import DesktopController

        mock_wm.find_window.return_value = None
        ctrl = DesktopController(config)
        with pytest.raises(RuntimeError, match="找不到目标窗口"):
            await ctrl.launch()

    @pytest.mark.asyncio
    async def test_close(self, mock_user32, mock_wm, config):
        from src.controller.desktop import DesktopController

        mock_window = WindowInfo(hwnd=999, title="记事本", class_name="Notepad", pid=50)
        mock_wm.find_window.return_value = mock_window
        mock_wm.focus_window.return_value = True
        mock_wm.get_window_rect.return_value = {"width": 800, "height": 600}

        ctrl = DesktopController(config)
        await ctrl.launch()
        await ctrl.close()
        assert ctrl.target_hwnd is None
        assert ctrl.device_info.is_connected is False

    @pytest.mark.asyncio
    async def test_platform_and_device_info(self, mock_user32, config):
        from src.controller.desktop import DesktopController

        ctrl = DesktopController(config)
        assert ctrl.platform == Platform.WINDOWS
        assert ctrl.device_info.platform == Platform.WINDOWS
        assert ctrl.device_info.screen_width == 1920

    @pytest.mark.asyncio
    async def test_tap_point(self, mock_user32, mock_wm, config):
        from src.controller.desktop import DesktopController

        mock_window = WindowInfo(hwnd=999, title="记事本", class_name="Notepad", pid=50)
        mock_wm.find_window.return_value = mock_window
        mock_wm.focus_window.return_value = True
        mock_wm.get_window_rect.return_value = {"width": 800, "height": 600}

        ctrl = DesktopController(config)
        await ctrl.launch()

        # point:X,Y 格式直接坐标点击
        with patch("src.controller.desktop._click_screen") as mock_click:
            await ctrl.tap("point:100,200")
            mock_click.assert_called_once_with(100, 200)

    @pytest.mark.asyncio
    async def test_tap_name_selector(self, mock_user32, mock_wm, config):
        from src.controller.desktop import DesktopController

        mock_window = WindowInfo(hwnd=999, title="记事本", class_name="Notepad", pid=50)
        mock_wm.find_window.return_value = mock_window
        mock_wm.focus_window.return_value = True
        mock_wm.get_window_rect.return_value = {"width": 800, "height": 600}

        ctrl = DesktopController(config)
        await ctrl.launch()

        with patch("src.controller.desktop._find_element_ps") as mock_find, \
             patch("src.controller.desktop._click_screen") as mock_click:
            mock_find.return_value = {"name": "保存", "center_x": 300, "center_y": 400}
            await ctrl.tap("name:保存")
            mock_click.assert_called_once_with(300, 400)

    @pytest.mark.asyncio
    async def test_tap_element_not_found(self, mock_user32, mock_wm, config):
        from src.controller.desktop import DesktopController

        mock_window = WindowInfo(hwnd=999, title="记事本", class_name="Notepad", pid=50)
        mock_wm.find_window.return_value = mock_window
        mock_wm.focus_window.return_value = True
        mock_wm.get_window_rect.return_value = {"width": 800, "height": 600}

        ctrl = DesktopController(config)
        await ctrl.launch()

        with patch("src.controller.desktop._find_element_ps") as mock_find:
            mock_find.return_value = None
            with pytest.raises(RuntimeError, match="元素未找到"):
                await ctrl.tap("name:不存在的按钮")

    @pytest.mark.asyncio
    async def test_get_text(self, mock_user32, mock_wm, config):
        from src.controller.desktop import DesktopController

        mock_window = WindowInfo(hwnd=999, title="记事本", class_name="Notepad", pid=50)
        mock_wm.find_window.return_value = mock_window
        mock_wm.focus_window.return_value = True
        mock_wm.get_window_rect.return_value = {"width": 800, "height": 600}

        ctrl = DesktopController(config)
        await ctrl.launch()

        with patch("src.controller.desktop._find_element_ps") as mock_find:
            mock_find.return_value = {"name": "Hello World"}
            text = await ctrl.get_text("name:label1")
            assert text == "Hello World"

    @pytest.mark.asyncio
    async def test_get_text_not_found(self, mock_user32, mock_wm, config):
        from src.controller.desktop import DesktopController

        mock_window = WindowInfo(hwnd=999, title="记事本", class_name="Notepad", pid=50)
        mock_wm.find_window.return_value = mock_window
        mock_wm.focus_window.return_value = True
        mock_wm.get_window_rect.return_value = {"width": 800, "height": 600}

        ctrl = DesktopController(config)
        await ctrl.launch()

        with patch("src.controller.desktop._find_element_ps") as mock_find:
            mock_find.return_value = None
            text = await ctrl.get_text("name:missing")
            assert text == ""

    @pytest.mark.asyncio
    async def test_screenshot_window(self, mock_user32, mock_wm, config, tmp_path):
        from src.controller.desktop import DesktopController

        mock_window = WindowInfo(hwnd=999, title="记事本", class_name="Notepad", pid=50)
        mock_wm.find_window.return_value = mock_window
        mock_wm.focus_window.return_value = True
        mock_wm.get_window_rect.return_value = {"width": 800, "height": 600}
        mock_wm.capture_window.return_value = tmp_path / "shot.bmp"
        mock_user32.IsWindow.return_value = True

        ctrl = DesktopController(config)
        await ctrl.launch()
        path = await ctrl.screenshot("test_shot")
        mock_wm.capture_window.assert_called_once()

    @pytest.mark.asyncio
    async def test_screenshot_fullscreen_no_hwnd(self, mock_user32, mock_wm, config, tmp_path):
        from src.controller.desktop import DesktopController

        ctrl = DesktopController(config)
        ctrl._hwnd = None
        mock_wm.capture_screen.return_value = tmp_path / "full.bmp"
        path = await ctrl.screenshot("full")
        mock_wm.capture_screen.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate_switch_window(self, mock_user32, mock_wm, config):
        from src.controller.desktop import DesktopController

        mock_window = WindowInfo(hwnd=999, title="记事本", class_name="Notepad", pid=50)
        mock_wm.find_window.return_value = mock_window
        mock_wm.focus_window.return_value = True
        mock_wm.get_window_rect.return_value = {"width": 800, "height": 600}

        ctrl = DesktopController(config)
        await ctrl.launch()

        calc_window = WindowInfo(hwnd=888, title="计算器", class_name="CalcFrame", pid=60)
        mock_wm.find_window.return_value = calc_window
        await ctrl.navigate("计算器")
        assert ctrl.target_hwnd == 888

    @pytest.mark.asyncio
    async def test_navigate_window_not_found(self, mock_user32, mock_wm, config):
        from src.controller.desktop import DesktopController

        mock_window = WindowInfo(hwnd=999, title="记事本", class_name="Notepad", pid=50)
        mock_wm.find_window.return_value = mock_window
        mock_wm.focus_window.return_value = True
        mock_wm.get_window_rect.return_value = {"width": 800, "height": 600}

        ctrl = DesktopController(config)
        await ctrl.launch()

        mock_wm.find_window.return_value = None
        with pytest.raises(RuntimeError, match="找不到窗口"):
            await ctrl.navigate("不存在的窗口")

    @pytest.mark.asyncio
    async def test_get_page_source(self, mock_user32, mock_wm, config):
        from src.controller.desktop import DesktopController

        mock_window = WindowInfo(hwnd=999, title="记事本", class_name="Notepad", pid=50)
        mock_wm.find_window.return_value = mock_window
        mock_wm.focus_window.return_value = True
        mock_wm.get_window_rect.return_value = {"width": 800, "height": 600}

        ctrl = DesktopController(config)
        await ctrl.launch()

        with patch("src.controller.desktop._get_ui_tree") as mock_tree:
            mock_tree.return_value = "[Root] Name='记事本'\n  [Edit] Name=''"
            source = await ctrl.get_page_source()
            assert "[Root]" in source

    @pytest.mark.asyncio
    async def test_get_page_source_no_window(self, mock_user32, config):
        from src.controller.desktop import DesktopController

        ctrl = DesktopController(config)
        source = await ctrl.get_page_source()
        assert "no target" in source


# ── PS 查找元素测试 ─────────────────────────────

class TestFindElementPS:
    @patch("src.controller.desktop.subprocess.run")
    def test_find_by_name(self, mock_run):
        from src.controller.desktop import _find_element_ps

        mock_run.return_value = MagicMock(
            stdout=json.dumps({"name": "保存", "center_x": 100, "center_y": 200, "width": 80, "height": 30}),
        )
        result = _find_element_ps(999, "name:保存")
        assert result is not None
        assert result["center_x"] == 100
        assert result["name"] == "保存"

    @patch("src.controller.desktop.subprocess.run")
    def test_find_by_automationid(self, mock_run):
        from src.controller.desktop import _find_element_ps

        mock_run.return_value = MagicMock(
            stdout=json.dumps({"name": "", "automation_id": "btnSave", "center_x": 50, "center_y": 60}),
        )
        result = _find_element_ps(999, "automationid:btnSave")
        assert result is not None

    @patch("src.controller.desktop.subprocess.run")
    def test_find_not_found(self, mock_run):
        from src.controller.desktop import _find_element_ps

        mock_run.return_value = MagicMock(stdout="null")
        result = _find_element_ps(999, "name:不存在")
        assert result is None

    @patch("src.controller.desktop.subprocess.run")
    def test_find_timeout(self, mock_run):
        from src.controller.desktop import _find_element_ps

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ps", timeout=10)
        result = _find_element_ps(999, "name:超时")
        assert result is None


class TestBmpWriter:
    def test_write_bmp(self, tmp_path):
        from src.controller.window_manager import _write_bmp

        filepath = tmp_path / "test.bmp"
        pixels = b"\x00\x00\xff\xff" * 4  # 2x2 red pixels
        _write_bmp(filepath, 2, 2, pixels)
        assert filepath.exists()
        data = filepath.read_bytes()
        assert data[:2] == b"BM"
        assert len(data) == 54 + 16  # 头+像素


# ── 辅助函数 ────────────────────────────────────

import subprocess

def _make_text_writer(titles: list[str]):
    """创建模拟 GetWindowTextW / GetClassNameW 的 side_effect。"""
    index = [0]

    def writer(hwnd, buf, size):
        if index[0] < len(titles):
            text = titles[index[0]]
            index[0] += 1
            # 直接设置 ctypes 缓冲区的值
            for i, ch in enumerate(text):
                buf[i] = ch
            buf[len(text)] = '\0'
        return len(titles[index[0] - 1]) if index[0] > 0 else 0

    return writer


def _make_pid_writer(pids: list[int]):
    """创建模拟 GetWindowThreadProcessId 的 side_effect。"""
    index = [0]

    def writer(hwnd, pid_ptr):
        if index[0] < len(pids):
            # pid_ptr 是 ctypes.byref() 返回的指针
            import ctypes
            ctypes.cast(pid_ptr, ctypes.POINTER(ctypes.wintypes.DWORD)).contents.value = pids[index[0]]
            index[0] += 1
        return 0  # thread id

    return writer
