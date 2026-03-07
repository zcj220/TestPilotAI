"""
多浏览器上下文池（v2.0-rc）

管理多个隔离的 BrowserContext，支持并发测试。
每个 context 拥有独立的 Cookie、Session、LocalStorage，
适用于多页面/多用户并发测试场景。

典型使用：
    pool = ContextPool(browser, config)
    ctx1 = await pool.acquire("user-a")
    ctx2 = await pool.acquire("user-b")
    # 并发操作...
    await pool.release("user-a")
    await pool.release_all()
"""

from typing import Optional

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page

from src.core.config import BrowserConfig


class ManagedContext:
    """受管理的浏览器上下文，包含 context + page。"""

    def __init__(self, name: str, context: BrowserContext, page: Page) -> None:
        self.name = name
        self.context = context
        self.page = page

    async def close(self) -> None:
        """关闭此上下文。"""
        try:
            await self.context.close()
        except Exception:
            pass


class ContextPool:
    """浏览器上下文池。

    管理多个命名的 BrowserContext，每个 context 完全隔离。
    """

    def __init__(self, browser: Browser, config: Optional[BrowserConfig] = None) -> None:
        self._browser = browser
        self._config = config or BrowserConfig()
        self._contexts: dict[str, ManagedContext] = {}

    @property
    def size(self) -> int:
        """当前活跃上下文数量。"""
        return len(self._contexts)

    @property
    def names(self) -> list[str]:
        """所有活跃上下文名称。"""
        return list(self._contexts.keys())

    def get(self, name: str) -> Optional[ManagedContext]:
        """按名称获取上下文。"""
        return self._contexts.get(name)

    async def acquire(self, name: str) -> ManagedContext:
        """获取或创建一个命名上下文。

        如果同名 context 已存在则直接返回，否则创建新的。

        Args:
            name: 上下文名称（如 "user-a", "admin"）
        Returns:
            ManagedContext 实例
        """
        if name in self._contexts:
            return self._contexts[name]

        context = await self._browser.new_context(
            viewport={
                "width": self._config.viewport_width,
                "height": self._config.viewport_height,
            },
        )
        context.set_default_timeout(self._config.default_timeout_ms)
        page = await context.new_page()

        managed = ManagedContext(name=name, context=context, page=page)
        self._contexts[name] = managed

        logger.info("ContextPool | 创建上下文 '{}' | 当前数量={}", name, self.size)
        return managed

    async def release(self, name: str) -> bool:
        """释放并关闭指定上下文。

        Args:
            name: 上下文名称
        Returns:
            是否成功释放
        """
        managed = self._contexts.pop(name, None)
        if managed is None:
            return False

        await managed.close()
        logger.info("ContextPool | 释放上下文 '{}' | 剩余={}", name, self.size)
        return True

    async def release_all(self) -> int:
        """释放所有上下文。

        Returns:
            释放的数量
        """
        count = len(self._contexts)
        for managed in self._contexts.values():
            await managed.close()
        self._contexts.clear()
        logger.info("ContextPool | 释放全部 | 共{}个", count)
        return count

    def status_dict(self) -> dict:
        """状态信息。"""
        return {
            "size": self.size,
            "contexts": self.names,
        }
