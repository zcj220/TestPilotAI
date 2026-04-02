"""
TestPilot AI 启动入口

使用方式：
    poetry run python main.py
    或
    poetry run uvicorn src.app:app --reload
"""

import os
import subprocess
import sys

import uvicorn

from src.core.config import get_config


def _ensure_playwright_browsers() -> None:
    """PyInstaller 打包模式下，设置浏览器路径并检查/安装。"""
    # 设置 PLAYWRIGHT_BROWSERS_PATH 指向标准缓存位置，
    # 避免 Playwright 在 PyInstaller 临时目录中找浏览器
    if sys.platform == "win32":
        cache = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
    else:
        cache = os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright")
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", cache)

    try:
        chromium_dirs = [
            d for d in os.listdir(cache) if d.startswith("chromium")
        ] if os.path.isdir(cache) else []

        if chromium_dirs:
            print(f"[Engine] Playwright browsers ready: {', '.join(chromium_dirs)}")
            return

        print("[Engine] First run, installing Playwright Chromium browser...")
        from playwright._impl._driver import compute_driver_executable
        driver = str(compute_driver_executable())
        subprocess.run(
            [driver, "install", "chromium"],
            timeout=300, check=True,
        )
        print("[Engine] Playwright browser installed successfully")
    except Exception as e:
        print(f"[Engine] Playwright browser check/install failed: {e}")
        print("[Engine] Testing may not work, please run manually: playwright install chromium")


def main() -> None:
    """启动 TestPilot AI 核心引擎服务。"""
    config = get_config()

    if getattr(sys, "frozen", False):
        # PyInstaller 打包模式：确保浏览器可用，然后启动服务
        _ensure_playwright_browsers()
        from src.app import app as _app
        uvicorn.run(
            _app,
            host=config.server.host,
            port=config.server.port,
            reload=False,
            log_level=config.server.log_level.lower(),
        )
    else:
        # 开发模式：字符串方式支持 --reload 热重载
        uvicorn.run(
            "src.app:app",
            host=config.server.host,
            port=config.server.port,
            reload=config.server.reload,
            log_level=config.server.log_level.lower(),
        )


if __name__ == "__main__":
    main()
