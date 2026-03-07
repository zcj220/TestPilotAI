"""
平台控制器模块（v5.0 + v7.0 + v8.0）

统一的多平台控制器抽象层：
- BaseController: 抽象基类
- WebController: Web浏览器（Playwright）
- AndroidController: Android设备（Appium）
- DesktopController: Windows桌面应用（UI Automation）— v7.0
- MiniProgramController: 微信小程序（miniprogram-automator）— v8.0
- Platform/DeviceInfo: 数据模型
"""

from src.controller.base import BaseController, DeviceInfo, ElementInfo, Platform
from src.controller.web import WebController
from src.controller.android import AndroidController
from src.controller.desktop import DesktopController
from src.controller.window_manager import WindowManager, WindowInfo, DesktopConfig
from src.controller.miniprogram import MiniProgramController, MiniProgramConfig

__all__ = [
    "BaseController",
    "WebController",
    "AndroidController",
    "DesktopController",
    "MiniProgramController",
    "MiniProgramConfig",
    "WindowManager",
    "WindowInfo",
    "DesktopConfig",
    "DeviceInfo",
    "ElementInfo",
    "Platform",
]
