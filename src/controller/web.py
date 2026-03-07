"""
Web 平台控制器（v5.0）

将现有的 BrowserAutomator 适配为统一的 BaseController 接口。
这是一个轻量适配器，不改动 BrowserAutomator 的任何逻辑。

使用方式：
    controller = WebController(browser_config)
    await controller.launch()
    await controller.navigate("http://localhost:3000")
    await controller.tap("button#login")
    path = await controller.screenshot("登录页")
    await controller.close()
"""

from pathlib import Path
from typing import Optional

from loguru import logger

from src.browser.automator import BrowserAutomator
from src.controller.base import BaseController, DeviceInfo, Platform
from src.core.config import BrowserConfig


class WebController(BaseController):
    """Web 浏览器控制器（Playwright 适配器）。

    将 BrowserAutomator 的接口映射到统一的 BaseController 接口。
    """

    def __init__(self, config: Optional[BrowserConfig] = None) -> None:
        self._automator = BrowserAutomator(config)
        self._config = config or BrowserConfig()

    @property
    def platform(self) -> Platform:
        return Platform.WEB

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            platform=Platform.WEB,
            name="Chromium",
            screen_width=self._config.viewport_width,
            screen_height=self._config.viewport_height,
            is_connected=self._automator._page is not None,
        )

    @property
    def automator(self) -> BrowserAutomator:
        """获取底层 BrowserAutomator（蓝本执行器等需要直接访问）。"""
        return self._automator

    async def launch(self) -> None:
        await self._automator.launch()
        logger.info("WebController 已启动")

    async def close(self) -> None:
        await self._automator.close()
        logger.info("WebController 已关闭")

    async def navigate(self, url_or_activity: str) -> None:
        await self._automator.navigate(url_or_activity)

    async def tap(self, selector: str) -> None:
        await self._automator.click(selector)

    async def input_text(self, selector: str, text: str) -> None:
        await self._automator.fill(selector, text)

    async def screenshot(self, name: str = "") -> Path:
        return await self._automator.screenshot(name)

    async def get_page_source(self) -> str:
        return await self._automator.get_page_content()

    async def get_text(self, selector: str) -> str:
        return await self._automator.get_text(selector)

    async def wait_for_element(self, selector: str, timeout_ms: int = 10000) -> None:
        await self._automator.wait_for_selector(selector, timeout_ms)

    async def select_option(self, selector: str, value: str) -> None:
        await self._automator.select_option(selector, value)

    async def back(self) -> None:
        await self._automator.page.go_back()

    async def swipe(
        self,
        start_x: int, start_y: int,
        end_x: int, end_y: int,
        duration_ms: int = 300,
    ) -> None:
        """Web端滑动 = 滚动页面。"""
        delta_y = end_y - start_y
        await self._automator.page.evaluate(f"window.scrollBy(0, {-delta_y})")
