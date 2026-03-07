"""
平台控制器抽象基类（v5.0）

定义所有平台控制器（Web/Android/iOS/Windows/Mac）的统一接口。
测试引擎只依赖这个抽象接口，不关心底层是Playwright还是Appium。

架构：
    BaseController (抽象接口)
    ├── WebController    ← Playwright (已有 BrowserAutomator 适配)
    ├── AndroidController ← Appium (v5.0)
    ├── iOSController    ← Appium + XCTest (v5.0)
    ├── WindowsController ← UI Automation (v6.0)
    └── MacController    ← Accessibility API (v6.0)
"""

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class Platform(str, Enum):
    """支持的测试平台。"""
    WEB = "web"
    ANDROID = "android"
    IOS = "ios"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


class DeviceInfo(BaseModel):
    """设备信息。"""
    platform: Platform
    name: str = ""
    os_version: str = ""
    screen_width: int = 0
    screen_height: int = 0
    is_connected: bool = False
    extra: dict = Field(default_factory=dict)


class ElementInfo(BaseModel):
    """元素信息（跨平台通用）。"""
    selector: str = ""
    text: str = ""
    visible: bool = True
    enabled: bool = True
    bounds: dict = Field(default_factory=dict)
    platform_attrs: dict = Field(default_factory=dict)


class BaseController(ABC):
    """平台控制器抽象基类。

    所有平台控制器必须实现这些方法。
    测试引擎（BlueprintRunner/TestOrchestrator）只调用这些接口。

    典型使用：
        controller = WebController(config)  # 或 AndroidController
        await controller.launch()
        await controller.navigate("http://localhost:3000")
        await controller.tap("button#login")
        screenshot = await controller.screenshot("登录页")
        await controller.close()
    """

    @property
    @abstractmethod
    def platform(self) -> Platform:
        """返回当前平台类型。"""
        ...

    @property
    @abstractmethod
    def device_info(self) -> DeviceInfo:
        """返回设备信息。"""
        ...

    @abstractmethod
    async def launch(self) -> None:
        """启动控制器（连接设备/启动浏览器）。"""
        ...

    @abstractmethod
    async def close(self) -> None:
        """关闭控制器，释放资源。"""
        ...

    @abstractmethod
    async def navigate(self, url_or_activity: str) -> None:
        """导航到URL（Web）或打开Activity/页面（手机）。

        Args:
            url_or_activity: Web时为URL，手机时为Activity名或深链接
        """
        ...

    @abstractmethod
    async def tap(self, selector: str) -> None:
        """点击/轻触元素。

        Args:
            selector: Web时为CSS选择器，手机时为xpath/id/accessibility_id
        """
        ...

    @abstractmethod
    async def input_text(self, selector: str, text: str) -> None:
        """在输入框中输入文本。

        Args:
            selector: 元素选择器
            text: 要输入的文本
        """
        ...

    @abstractmethod
    async def screenshot(self, name: str = "") -> Path:
        """截取当前屏幕。

        Args:
            name: 截图名称

        Returns:
            Path: 截图文件路径
        """
        ...

    @abstractmethod
    async def get_page_source(self) -> str:
        """获取当前页面源码。

        Web: HTML源码
        手机: UI层级XML
        """
        ...

    @abstractmethod
    async def get_text(self, selector: str) -> str:
        """获取元素文本。"""
        ...

    # ── 可选方法（有默认实现）─────────────────────

    async def swipe(
        self,
        start_x: int, start_y: int,
        end_x: int, end_y: int,
        duration_ms: int = 300,
    ) -> None:
        """滑动操作（手机专用，Web默认为滚动）。"""
        raise NotImplementedError(f"{self.platform.value} 不支持滑动操作")

    async def long_press(self, selector: str, duration_ms: int = 1000) -> None:
        """长按操作。"""
        raise NotImplementedError(f"{self.platform.value} 不支持长按操作")

    async def back(self) -> None:
        """返回上一页。"""
        raise NotImplementedError(f"{self.platform.value} 不支持返回操作")

    async def wait_for_element(self, selector: str, timeout_ms: int = 10000) -> None:
        """等待元素出现。"""
        raise NotImplementedError(f"{self.platform.value} 不支持等待元素")

    async def select_option(self, selector: str, value: str) -> None:
        """选择下拉选项（Web专用）。"""
        raise NotImplementedError(f"{self.platform.value} 不支持选择选项")

    async def __aenter__(self) -> "BaseController":
        await self.launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
