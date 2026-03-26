"""
浏览器自动化引擎

基于 Playwright 实现 UI 交互，模拟人类操作：
- 页面导航（打开URL、前进、后退）
- 元素交互（点击、输入、选择、滚动）
- 状态捕获（截图、获取页面内容、获取元素属性）
- 录屏（记录完整测试过程）

设计原则：
1. 所有操作自带等待机制，自动等待元素可交互
2. 每次操作自动记录日志，便于回溯
3. 截图文件名带时间戳和步骤编号，方便排序
4. 支持连接到沙箱内的远程浏览器，也支持本地浏览器
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from src.core.config import BrowserConfig
from src.core.exceptions import (
    BrowserActionError,
    BrowserLaunchError,
    BrowserNavigationError,
    BrowserScreenshotError,
)
from src.browser.console_collector import ConsoleCollector


class BrowserAutomator:
    """Playwright 浏览器自动化引擎。

    支持两种模式：
    1. 本地模式：直接启动本地 Chromium
    2. 远程模式：连接沙箱内的浏览器（通过 CDP）

    典型使用流程：
        async with BrowserAutomator(config) as bot:
            await bot.navigate("http://localhost:3000")
            await bot.click("button#login")
            screenshot = await bot.screenshot("登录页面")
    """

    def __init__(self, config: Optional[BrowserConfig] = None) -> None:
        """初始化浏览器自动化引擎。

        Args:
            config: 浏览器配置。如果不传则使用默认配置。
        """
        self._config = config or BrowserConfig()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._step_counter: int = 0
        self._console_collector = ConsoleCollector()

        # 确保截图和录屏目录存在
        self._config.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._config.video_dir.mkdir(parents=True, exist_ok=True)

    async def __aenter__(self) -> "BrowserAutomator":
        """异步上下文管理器入口，启动浏览器。"""
        await self.launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        """异步上下文管理器出口，关闭浏览器。"""
        await self.close()

    async def launch(self, cdp_url: Optional[str] = None) -> None:
        """启动或连接浏览器。

        Args:
            cdp_url: Chrome DevTools Protocol URL。
                     如果提供则连接远程浏览器（沙箱内），
                     否则启动本地 Chromium。

        Raises:
            BrowserLaunchError: 浏览器启动或连接失败
        """
        try:
            self._playwright = await async_playwright().start()

            if cdp_url:
                logger.info("正在连接远程浏览器 | CDP={}", cdp_url)
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    cdp_url
                )
            else:
                logger.info(
                    "正在启动本地浏览器 | 无头模式={}",
                    self._config.headless,
                )
                self._browser = await self._playwright.chromium.launch(
                    headless=self._config.headless,
                )

            # 创建浏览器上下文（含视口大小和录屏配置）
            self._context = await self._browser.new_context(
                viewport={
                    "width": self._config.viewport_width,
                    "height": self._config.viewport_height,
                },
                record_video_dir=str(self._config.video_dir),
                record_video_size={
                    "width": self._config.viewport_width,
                    "height": self._config.viewport_height,
                },
            )

            # 设置默认超时
            self._context.set_default_timeout(self._config.default_timeout_ms)

            # 创建页面
            self._page = await self._context.new_page()
            self._step_counter = 0

            # 绑定控制台收集器
            self._console_collector.attach(self._page)

            logger.info("浏览器启动成功 | 视口={}x{}", 
                       self._config.viewport_width,
                       self._config.viewport_height)

        except Exception as e:
            await self.close()
            raise BrowserLaunchError(
                message="浏览器启动失败",
                detail=str(e),
            )

    @property
    def page(self) -> Page:
        """获取当前页面对象。

        Returns:
            Page: Playwright 页面对象

        Raises:
            BrowserLaunchError: 浏览器尚未启动
        """
        if self._page is None:
            raise BrowserLaunchError(
                message="浏览器尚未启动",
                detail="请先调用 launch() 或使用 async with 语法",
            )
        return self._page

    def _next_step(self) -> int:
        """递增并返回步骤编号。"""
        self._step_counter += 1
        return self._step_counter

    async def navigate(self, url: str, wait_until: str = "load") -> None:
        """导航到指定 URL。

        Args:
            url: 目标 URL
            wait_until: 等待条件 - load/domcontentloaded/networkidle/commit

        Raises:
            BrowserNavigationError: 页面导航失败
        """
        step = self._next_step()
        logger.debug("[ctrl-{}] 导航到: {}", step, url)

        try:
            response = await self.page.goto(url, wait_until=wait_until)
            if response and response.status >= 400:
                logger.warning(
                    "[步骤{}] 页面返回错误状态码: {}",
                    step,
                    response.status,
                )
            logger.debug("[ctrl-{}] 导航完成 | 标题: {}", step, await self.page.title())
        except Exception as e:
            raise BrowserNavigationError(
                message=f"导航到 {url} 失败",
                detail=str(e),
            )

    async def click(self, selector: str) -> None:
        """点击指定元素。

        Args:
            selector: CSS 选择器或 Playwright 选择器

        Raises:
            BrowserActionError: 元素不存在或无法点击
        """
        step = self._next_step()
        logger.debug("[ctrl-{}] 点击元素: {}", step, selector)

        try:
            await self.page.click(selector)
            logger.debug("[步骤{}] 点击成功", step)
        except Exception as e:
            raise BrowserActionError(
                message=f"点击元素失败: {selector}",
                detail=str(e),
            )

    async def fill(self, selector: str, text: str) -> None:
        """在输入框中填入文本（先清空再输入）。

        Args:
            selector: 输入框的 CSS 选择器
            text: 要输入的文本

        Raises:
            BrowserActionError: 输入操作失败
        """
        step = self._next_step()
        # 日志中隐藏可能的密码
        display_text = text if len(text) <= 20 else text[:10] + "..."
        logger.debug("[ctrl-{}] 输入文本: {} -> '{}'", step, selector, display_text)

        try:
            await self.page.fill(selector, text)
            logger.debug("[步骤{}] 输入成功", step)
        except Exception as e:
            raise BrowserActionError(
                message=f"输入文本失败: {selector}",
                detail=str(e),
            )

    async def select_option(self, selector: str, value: str) -> None:
        """在下拉框中选择选项。

        Args:
            selector: 下拉框的 CSS 选择器
            value: 要选择的值

        Raises:
            BrowserActionError: 选择操作失败
        """
        step = self._next_step()
        logger.debug("[ctrl-{}] 选择选项: {} -> '{}'", step, selector, value)

        try:
            await self.page.select_option(selector, value)
            logger.debug("[步骤{}] 选择成功", step)
        except Exception as e:
            raise BrowserActionError(
                message=f"选择选项失败: {selector}",
                detail=str(e),
            )

    async def wait_for_selector(
        self, selector: str, timeout_ms: Optional[int] = None
    ) -> None:
        """等待元素出现。

        Args:
            selector: CSS 选择器
            timeout_ms: 超时时间（毫秒），默认使用全局配置

        Raises:
            BrowserActionError: 等待超时
        """
        effective_timeout = timeout_ms or self._config.default_timeout_ms
        logger.debug("等待元素出现: {} | 超时={}ms", selector, effective_timeout)

        try:
            await self.page.wait_for_selector(selector, timeout=effective_timeout)
        except Exception as e:
            raise BrowserActionError(
                message=f"等待元素超时: {selector}",
                detail=str(e),
            )

    async def get_text(self, selector: str) -> str:
        """获取元素的文本内容。

        Args:
            selector: CSS 选择器

        Returns:
            str: 元素的文本内容

        Raises:
            BrowserActionError: 获取文本失败
        """
        try:
            text = await self.page.text_content(selector) or ""
            return text.strip()
        except Exception as e:
            raise BrowserActionError(
                message=f"获取文本失败: {selector}",
                detail=str(e),
            )

    async def get_page_content(self) -> str:
        """获取当前页面的完整 HTML 内容。

        Returns:
            str: 页面 HTML 内容
        """
        return await self.page.content()

    async def get_current_url(self) -> str:
        """获取当前页面 URL。

        Returns:
            str: 当前 URL
        """
        return self.page.url

    async def screenshot(
        self, 
        name: str = "", 
        full_page: bool = False,
    ) -> Path:
        """截取当前页面的截图。

        Args:
            name: 截图名称（用于文件名，便于识别）
            full_page: 是否截取完整页面（包括滚动区域）

        Returns:
            Path: 截图文件的绝对路径

        Raises:
            BrowserScreenshotError: 截图失败
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        step_str = f"step{self._step_counter:03d}"
        safe_name = name.replace(" ", "_").replace("/", "_")[:50] if name else "capture"
        filename = f"{timestamp}_{step_str}_{safe_name}.png"
        filepath = self._config.screenshot_dir / filename

        logger.info("截图 | 文件={} | 全页={}", filename, full_page)

        try:
            await self.page.screenshot(path=str(filepath), full_page=full_page)
            logger.debug("截图保存成功: {}", filepath)
            return filepath
        except Exception as e:
            raise BrowserScreenshotError(
                message=f"截图失败: {name}",
                detail=str(e),
            )

    @property
    def console_collector(self) -> ConsoleCollector:
        """获取控制台收集器。"""
        return self._console_collector

    async def close(self) -> None:
        """关闭浏览器，释放所有资源。"""
        try:
            self._console_collector.detach()
            if self._context:
                await self._context.close()
                self._context = None
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            self._page = None
            logger.info("浏览器已关闭")
        except Exception as e:
            logger.warning("关闭浏览器时出错: {}", e)

    async def ensure_healthy(self) -> None:
        """确保浏览器处于健康可用状态，否则自动重置。

        在每次测试开始前调用，避免因上次测试异常退出导致浏览器
        处于损坏状态（页面崩溃/挂起/导航失败）时仍复用坏页面。
        重置时只关闭旧 context，不关闭 Playwright/Browser 进程，
        速度远快于完整 close() + launch()。
        """
        if self._page is None:
            # 浏览器尚未启动，正常 launch
            await self.launch()
            return

        # 健康探测：向页面发一个轻量 JS 求值
        try:
            await self._page.evaluate("1 + 1", timeout=3000)
            # 页面响应正常，无需重置
        except Exception as e:
            logger.warning("浏览器页面健康检查失败，自动重置: {}", str(e)[:80])
            # 只重置 context + page，保留底层浏览器进程
            try:
                self._console_collector.detach()
                if self._context:
                    await self._context.close()
                    self._context = None
                self._page = None
            except Exception:
                pass
            # 如果浏览器进程也挂了，做完整重启
            if self._browser is None or not self._browser.is_connected():
                logger.warning("浏览器进程断开，完整重启")
                await self.close()
                await self.launch()
                return
            # 浏览器进程正常，只重建 context + page
            try:
                viewport = {"width": self._config.viewport_width, "height": self._config.viewport_height}
                self._context = await self._browser.new_context(viewport=viewport)
                self._page = await self._context.new_page()
                self._console_collector.attach(self._page)
                logger.info("浏览器 context 已重置（引擎无需重启）")
            except Exception as e2:
                logger.error("重置 context 失败，完整重启浏览器: {}", e2)
                await self.close()
                await self.launch()
