"""多浏览器上下文池（ContextPool）单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.browser.context_pool import ContextPool, ManagedContext
from src.core.config import BrowserConfig


def make_mock_browser():
    """创建模拟Browser对象。"""
    browser = AsyncMock()

    async def mock_new_context(**kwargs):
        ctx = AsyncMock()
        ctx.set_default_timeout = MagicMock()

        async def mock_new_page():
            page = AsyncMock()
            return page

        ctx.new_page = mock_new_page
        ctx.close = AsyncMock()
        return ctx

    browser.new_context = mock_new_context
    return browser


class TestManagedContext:
    """ManagedContext测试。"""

    @pytest.mark.asyncio
    async def test_close(self):
        ctx = AsyncMock()
        page = AsyncMock()
        mc = ManagedContext(name="test", context=ctx, page=page)
        assert mc.name == "test"
        await mc.close()
        ctx.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_error_swallowed(self):
        ctx = AsyncMock()
        ctx.close.side_effect = RuntimeError("boom")
        page = AsyncMock()
        mc = ManagedContext(name="test", context=ctx, page=page)
        # 不应抛异常
        await mc.close()


class TestContextPool:
    """ContextPool测试。"""

    @pytest.mark.asyncio
    async def test_initial_state(self):
        browser = make_mock_browser()
        pool = ContextPool(browser)
        assert pool.size == 0
        assert pool.names == []

    @pytest.mark.asyncio
    async def test_acquire_creates_context(self):
        browser = make_mock_browser()
        pool = ContextPool(browser)
        mc = await pool.acquire("user-a")
        assert mc.name == "user-a"
        assert pool.size == 1
        assert "user-a" in pool.names

    @pytest.mark.asyncio
    async def test_acquire_same_name_returns_existing(self):
        browser = make_mock_browser()
        pool = ContextPool(browser)
        mc1 = await pool.acquire("user-a")
        mc2 = await pool.acquire("user-a")
        assert mc1 is mc2
        assert pool.size == 1

    @pytest.mark.asyncio
    async def test_acquire_multiple(self):
        browser = make_mock_browser()
        pool = ContextPool(browser)
        await pool.acquire("user-a")
        await pool.acquire("user-b")
        await pool.acquire("admin")
        assert pool.size == 3
        assert set(pool.names) == {"user-a", "user-b", "admin"}

    @pytest.mark.asyncio
    async def test_get_existing(self):
        browser = make_mock_browser()
        pool = ContextPool(browser)
        mc = await pool.acquire("x")
        assert pool.get("x") is mc

    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        browser = make_mock_browser()
        pool = ContextPool(browser)
        assert pool.get("nope") is None

    @pytest.mark.asyncio
    async def test_release(self):
        browser = make_mock_browser()
        pool = ContextPool(browser)
        await pool.acquire("user-a")
        result = await pool.release("user-a")
        assert result is True
        assert pool.size == 0

    @pytest.mark.asyncio
    async def test_release_nonexistent(self):
        browser = make_mock_browser()
        pool = ContextPool(browser)
        result = await pool.release("nope")
        assert result is False

    @pytest.mark.asyncio
    async def test_release_all(self):
        browser = make_mock_browser()
        pool = ContextPool(browser)
        await pool.acquire("a")
        await pool.acquire("b")
        await pool.acquire("c")
        count = await pool.release_all()
        assert count == 3
        assert pool.size == 0

    @pytest.mark.asyncio
    async def test_release_all_empty(self):
        browser = make_mock_browser()
        pool = ContextPool(browser)
        count = await pool.release_all()
        assert count == 0

    @pytest.mark.asyncio
    async def test_status_dict(self):
        browser = make_mock_browser()
        pool = ContextPool(browser)
        await pool.acquire("x")
        await pool.acquire("y")
        d = pool.status_dict()
        assert d["size"] == 2
        assert set(d["contexts"]) == {"x", "y"}

    @pytest.mark.asyncio
    async def test_custom_config(self):
        browser = make_mock_browser()
        config = BrowserConfig(viewport_width=1920, viewport_height=1080)
        pool = ContextPool(browser, config)
        mc = await pool.acquire("hd")
        assert mc is not None
        assert pool.size == 1
