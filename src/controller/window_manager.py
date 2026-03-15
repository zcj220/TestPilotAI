"""
Windows 窗口管理器（v7.0）

功能：枚举窗口、查找窗口、聚焦窗口、调整大小、OS级截图。
基于 ctypes 直接调用 Win32 API，零外部依赖。
"""

import ctypes
import platform
import struct
from pathlib import Path
from typing import Optional

from loguru import logger

if platform.system() == "Windows":
    import ctypes.wintypes
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
else:
    user32 = None
    gdi32 = None

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
        """获取窗口位置和大小（含标题栏和边框）。"""
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return {"left": rect.left, "top": rect.top,
                "right": rect.right, "bottom": rect.bottom,
                "width": rect.right - rect.left,
                "height": rect.bottom - rect.top}

    @staticmethod
    def get_client_rect(hwnd: int) -> dict:
        """获取client区域的屏幕坐标（不含标题栏和边框）。

        返回的left/top是client区域左上角在屏幕上的绝对坐标。
        width/height是client区域的纯内容尺寸。
        """
        # client区域相对于窗口的(0,0)开始
        client_rect = ctypes.wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(client_rect))
        # 将client左上角(0,0)转为屏幕坐标
        pt = ctypes.wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(pt))
        w = client_rect.right
        h = client_rect.bottom
        return {"left": pt.x, "top": pt.y,
                "right": pt.x + w, "bottom": pt.y + h,
                "width": w, "height": h}

    @staticmethod
    def capture_window(hwnd: int, filepath: Path) -> Path:
        """截取窗口client区域为 PNG（不含标题栏和边框，AI坐标更精确）。"""
        # 获取完整窗口和client区域信息
        win_rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(win_rect))
        client_rect = ctypes.wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(client_rect))
        pt = ctypes.wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(pt))

        # client区域相对于窗口左上角的偏移（标题栏+边框的厚度）
        offset_x = pt.x - win_rect.left
        offset_y = pt.y - win_rect.top
        cw = client_rect.right
        ch = client_rect.bottom
        if cw <= 0 or ch <= 0:
            raise RuntimeError(f"client区域尺寸异常: {cw}x{ch}")

        # 先截完整窗口，再裁剪client区域
        full_w = win_rect.right - win_rect.left
        full_h = win_rect.bottom - win_rect.top
        hwnd_dc = user32.GetWindowDC(hwnd)
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, full_w, full_h)
        gdi32.SelectObject(mem_dc, bitmap)
        user32.PrintWindow(hwnd, mem_dc, 2)  # PW_RENDERFULLCONTENT

        # 创建client区域大小的位图，从完整截图中裁剪
        client_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        client_bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, cw, ch)
        gdi32.SelectObject(client_dc, client_bitmap)
        gdi32.BitBlt(client_dc, 0, 0, cw, ch, mem_dc, offset_x, offset_y, SRCCOPY)

        # 读取client区域像素数据
        bmi = _make_bitmapinfo(cw, ch)
        buf = ctypes.create_string_buffer(cw * ch * 4)
        gdi32.GetDIBits(client_dc, client_bitmap, 0, ch, buf, ctypes.byref(bmi), DIB_RGB_COLORS)

        # 清理GDI资源
        gdi32.DeleteObject(client_bitmap)
        gdi32.DeleteDC(client_dc)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)

        # 转换为PNG
        png_path = _save_as_png(filepath, cw, ch, buf.raw)
        logger.debug("窗口截图已保存 | {} ({}x{})", png_path, cw, ch)
        return png_path

    @staticmethod
    def capture_screen(filepath: Path) -> Path:
        """全屏截图（PNG格式）。"""
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

        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(0, screen_dc)

        png_path = _save_as_png(filepath, w, h, buf.raw)
        logger.debug("全屏截图已保存 | {} ({}x{})", png_path, w, h)
        return png_path


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


def _save_as_png(filepath: Path, w: int, h: int, pixel_data: bytes) -> Path:
    """将BGRA像素数据保存为PNG文件（体积远小于BMP）。"""
    png_path = filepath.with_suffix(".png")
    try:
        from PIL import Image
        # GDI返回的是BGRA格式，需要转为RGBA
        img = Image.frombytes("RGBA", (w, h), pixel_data, "raw", "BGRA")
        img.save(png_path, "PNG", optimize=True)
    except ImportError:
        # Pillow不可用时fallback到BMP
        bmp_path = filepath.with_suffix(".bmp")
        _write_bmp(bmp_path, w, h, pixel_data)
        return bmp_path
    return png_path


def _write_bmp(path: Path, w: int, h: int, pixel_data: bytes) -> None:
    """写入BMP文件（Pillow不可用时的fallback）。"""
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
