"""
Windows 窗口管理器（v7.0）

功能：枚举窗口、查找窗口、聚焦窗口、调整大小、OS级截图。
基于 ctypes 直接调用 Win32 API，零外部依赖。
"""

import ctypes
import ctypes.wintypes
import struct
from pathlib import Path
from typing import Optional

from loguru import logger

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

SW_RESTORE = 9
SRCCOPY = 0x00CC0020
BI_RGB = 0
DIB_RGB_COLORS = 0


class WindowInfo:
    """窗口信息。"""
    def __init__(self, hwnd: int, title: str = "", class_name: str = "", pid: int = 0):
        self.hwnd = hwnd
        self.title = title
        self.class_name = class_name
        self.pid = pid

    def to_dict(self) -> dict:
        return {"hwnd": self.hwnd, "title": self.title,
                "class_name": self.class_name, "pid": self.pid}

    def __repr__(self) -> str:
        return f"<Window hwnd={self.hwnd} title='{self.title[:30]}' class='{self.class_name}'>"


class DesktopConfig:
    """桌面测试配置。"""
    def __init__(
        self,
        target_title: str = "",
        target_class: str = "",
        target_pid: int = 0,
        target_exe: str = "",
        screenshot_dir: str = "screenshots/desktop",
        timeout_ms: int = 10000,
    ):
        self.target_title = target_title
        self.target_class = target_class
        self.target_pid = target_pid
        self.target_exe = target_exe
        self.timeout_ms = timeout_ms
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)


class WindowManager:
    """Windows 窗口管理器。"""

    @staticmethod
    def enumerate_windows(visible_only: bool = True) -> list[WindowInfo]:
        """枚举所有顶层窗口。"""
        windows: list[WindowInfo] = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
        )

        def _cb(hwnd, _lparam):
            if visible_only and not user32.IsWindowVisible(hwnd):
                return True
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            title = buf.value
            if not title:
                return True
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            windows.append(WindowInfo(hwnd, title, cls_buf.value, pid.value))
            return True

        user32.EnumWindows(WNDENUMPROC(_cb), 0)
        return windows

    @staticmethod
    def find_window(title: str = "", class_name: str = "",
                    pid: int = 0) -> Optional[WindowInfo]:
        """按条件查找窗口（模糊匹配标题）。"""
        for w in WindowManager.enumerate_windows():
            if title and title.lower() not in w.title.lower():
                continue
            if class_name and class_name.lower() != w.class_name.lower():
                continue
            if pid and w.pid != pid:
                continue
            return w
        return None

    @staticmethod
    def focus_window(hwnd: int) -> bool:
        """聚焦窗口（恢复+前置）。"""
        try:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            logger.debug("窗口已聚焦 | hwnd={}", hwnd)
            return True
        except Exception as e:
            logger.warning("聚焦窗口失败: {}", e)
            return False

    @staticmethod
    def resize_window(hwnd: int, width: int, height: int) -> bool:
        """调整窗口大小。"""
        try:
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            user32.MoveWindow(hwnd, rect.left, rect.top, width, height, True)
            return True
        except Exception:
            return False

    @staticmethod
    def get_window_rect(hwnd: int) -> dict:
        """获取窗口位置和大小。"""
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return {"left": rect.left, "top": rect.top,
                "right": rect.right, "bottom": rect.bottom,
                "width": rect.right - rect.left,
                "height": rect.bottom - rect.top}

    @staticmethod
    def capture_window(hwnd: int, filepath: Path) -> Path:
        """截取指定窗口为 BMP，然后转存为 PNG（需pillow）或保存BMP。"""
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 0 or h <= 0:
            raise RuntimeError(f"窗口尺寸异常: {w}x{h}")

        hwnd_dc = user32.GetWindowDC(hwnd)
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
        gdi32.SelectObject(mem_dc, bitmap)
        user32.PrintWindow(hwnd, mem_dc, 2)  # PW_RENDERFULLCONTENT

        # 读取像素数据
        bmi = _make_bitmapinfo(w, h)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem_dc, bitmap, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)

        # 写BMP文件
        bmp_path = filepath.with_suffix(".bmp")
        _write_bmp(bmp_path, w, h, buf.raw)

        # 清理GDI资源
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)

        logger.debug("窗口截图已保存 | {} ({}x{})", bmp_path, w, h)
        return bmp_path

    @staticmethod
    def capture_screen(filepath: Path) -> Path:
        """全屏截图。"""
        w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
        h = user32.GetSystemMetrics(1)  # SM_CYSCREEN

        screen_dc = user32.GetDC(0)
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        bitmap = gdi32.CreateCompatibleBitmap(screen_dc, w, h)
        gdi32.SelectObject(mem_dc, bitmap)
        gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, 0, 0, SRCCOPY)

        bmi = _make_bitmapinfo(w, h)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem_dc, bitmap, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)

        bmp_path = filepath.with_suffix(".bmp")
        _write_bmp(bmp_path, w, h, buf.raw)

        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(0, screen_dc)

        logger.debug("全屏截图已保存 | {} ({}x{})", bmp_path, w, h)
        return bmp_path


def _make_bitmapinfo(w: int, h: int):
    """构造 BITMAPINFO 结构。"""

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.wintypes.DWORD),
            ("biWidth", ctypes.wintypes.LONG),
            ("biHeight", ctypes.wintypes.LONG),
            ("biPlanes", ctypes.wintypes.WORD),
            ("biBitCount", ctypes.wintypes.WORD),
            ("biCompression", ctypes.wintypes.DWORD),
            ("biSizeImage", ctypes.wintypes.DWORD),
            ("biXPelsPerMeter", ctypes.wintypes.LONG),
            ("biYPelsPerMeter", ctypes.wintypes.LONG),
            ("biClrUsed", ctypes.wintypes.DWORD),
            ("biClrImportant", ctypes.wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [
            ("bmiHeader", BITMAPINFOHEADER),
            ("bmiColors", ctypes.wintypes.DWORD * 3),
        ]

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h  # 负值=自顶向下
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB
    return bmi


def _write_bmp(path: Path, w: int, h: int, pixel_data: bytes) -> None:
    """写入BMP文件。"""
    row_size = w * 4
    data_size = row_size * h
    file_size = 54 + data_size

    with open(path, "wb") as f:
        # BMP文件头 (14 bytes)
        f.write(b"BM")
        f.write(struct.pack("<I", file_size))
        f.write(struct.pack("<HH", 0, 0))
        f.write(struct.pack("<I", 54))
        # DIB头 (40 bytes)
        f.write(struct.pack("<I", 40))
        f.write(struct.pack("<i", w))
        f.write(struct.pack("<i", -h))  # 自顶向下
        f.write(struct.pack("<HH", 1, 32))
        f.write(struct.pack("<I", BI_RGB))
        f.write(struct.pack("<I", data_size))
        f.write(struct.pack("<ii", 0, 0))
        f.write(struct.pack("<II", 0, 0))
        # 像素数据
        f.write(pixel_data[:data_size])
