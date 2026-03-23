"""测试pywinauto对tkinter NoteApp的操作能力。"""
import sys
import time

def main():
    from pywinauto import Application
    from PIL import Image
    import ctypes, ctypes.wintypes

    # 连接NoteApp
    try:
        app = Application(backend='win32').connect(title_re='.*NoteApp.*')
    except Exception:
        # 通过类名连接
        app = Application(backend='win32').connect(class_name='TkTopLevel')

    win = app.window(title_re='.*NoteApp.*')
    r = win.rectangle()
    print(f"Window: {r.left},{r.top} -> {r.right},{r.bottom} ({r.right-r.left}x{r.bottom-r.top})")
    sys.stdout.flush()

    # 截图函数
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    def capture(hwnd, filename):
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ('biSize', ctypes.c_uint32), ('biWidth', ctypes.c_long),
                ('biHeight', ctypes.c_long), ('biPlanes', ctypes.c_ushort),
                ('biBitCount', ctypes.c_ushort), ('biCompression', ctypes.c_uint32),
                ('biSizeImage', ctypes.c_uint32), ('biXPelsPerMeter', ctypes.c_long),
                ('biYPelsPerMeter', ctypes.c_long), ('biClrUsed', ctypes.c_uint32),
                ('biClrImportant', ctypes.c_uint32),
            ]
        class BITMAPINFO(ctypes.Structure):
            _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', ctypes.c_uint32 * 3)]

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32

        hdc = user32.GetWindowDC(hwnd)
        mem_dc = gdi32.CreateCompatibleDC(hdc)
        bitmap = gdi32.CreateCompatibleBitmap(hdc, w, h)
        gdi32.SelectObject(mem_dc, bitmap)
        user32.PrintWindow(hwnd, mem_dc, 2)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem_dc, bitmap, 0, h, buf, ctypes.byref(bmi), 0)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hdc)

        img = Image.frombytes('RGBA', (w, h), buf.raw, 'raw', 'BGRA')
        img.save(filename, 'PNG')
        print(f"  截图: {filename} ({w}x{h}, {img.size})")
        sys.stdout.flush()

    hwnd = win.handle
    print(f"hwnd: {hwnd}")
    sys.stdout.flush()

    # 截图1：操作前
    capture(hwnd, "desktop-demo/before.png")

    # 聚焦
    win.set_focus()
    time.sleep(0.5)

    # 点击用户名输入框(归一化坐标约0.5, 0.49)
    w = r.right - r.left
    h = r.bottom - r.top
    username_x = int(0.5 * w)
    username_y = int(0.49 * h)
    print(f"点击用户名: ({username_x}, {username_y}) 相对窗口")
    sys.stdout.flush()

    win.click_input(coords=(username_x, username_y))
    time.sleep(0.3)

    # 输入admin
    print("输入: admin")
    sys.stdout.flush()
    win.type_keys('admin', with_spaces=True)
    time.sleep(0.3)

    # Tab切到密码框
    win.type_keys('{TAB}')
    time.sleep(0.2)

    # 输入admin123
    print("输入: admin123")
    sys.stdout.flush()
    win.type_keys('admin123', with_spaces=True)
    time.sleep(0.3)

    # 截图2：输入后
    capture(hwnd, "desktop-demo/after_input.png")

    # 点击Login(归一化约0.5, 0.67)
    login_x = int(0.5 * w)
    login_y = int(0.67 * h)
    print(f"点击Login: ({login_x}, {login_y}) 相对窗口")
    sys.stdout.flush()

    win.click_input(coords=(login_x, login_y))
    time.sleep(1.5)

    # 截图3：登录后
    capture(hwnd, "desktop-demo/after_login.png")

    print("完成！请检查 desktop-demo/ 下的3张截图")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
