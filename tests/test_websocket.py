"""
WebSocket 连接管理器的单元测试
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.websocket import ConnectionManager


@pytest.fixture
def manager():
    return ConnectionManager()


@pytest.fixture
def mock_ws():
    """创建一个 mock WebSocket 连接。"""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


class TestConnectionManager:
    """连接管理器测试。"""

    @pytest.mark.asyncio
    async def test_connect(self, manager, mock_ws):
        await manager.connect(mock_ws)
        assert manager.active_count == 1
        mock_ws.accept.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect(self, manager, mock_ws):
        await manager.connect(mock_ws)
        manager.disconnect(mock_ws)
        assert manager.active_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self, manager, mock_ws):
        """断开未连接的 ws 不应报错。"""
        manager.disconnect(mock_ws)
        assert manager.active_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self, manager):
        """无连接时广播不应报错。"""
        await manager.broadcast("test", {"msg": "hello"})

    @pytest.mark.asyncio
    async def test_broadcast_to_one_client(self, manager, mock_ws):
        await manager.connect(mock_ws)
        await manager.broadcast("step_done", {"step": 1})
        mock_ws.send_text.assert_awaited_once()

        # 验证发送的是 JSON
        sent = mock_ws.send_text.call_args[0][0]
        data = json.loads(sent)
        assert data["type"] == "step_done"
        assert data["data"]["step"] == 1

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_clients(self, manager):
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_text = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        await manager.connect(ws1)
        await manager.connect(ws2)
        assert manager.active_count == 2

        await manager.broadcast("log", {"message": "hello"})
        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self, manager):
        ws_alive = AsyncMock()
        ws_alive.accept = AsyncMock()
        ws_alive.send_text = AsyncMock()

        ws_dead = AsyncMock()
        ws_dead.accept = AsyncMock()
        ws_dead.send_text = AsyncMock(side_effect=Exception("连接断开"))

        await manager.connect(ws_alive)
        await manager.connect(ws_dead)
        assert manager.active_count == 2

        await manager.broadcast("test", {"msg": "ping"})

        # 死连接应被移除
        assert manager.active_count == 1
        ws_alive.send_text.assert_awaited_once()


class TestConvenienceMethods:
    """便捷发送方法测试。"""

    @pytest.mark.asyncio
    async def test_send_log(self, manager, mock_ws):
        await manager.connect(mock_ws)
        await manager.send_log("测试消息")
        sent = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent["type"] == "log"
        assert "测试消息" in sent["data"]["message"]

    @pytest.mark.asyncio
    async def test_send_step_start(self, manager, mock_ws):
        await manager.connect(mock_ws)
        await manager.send_step_start(1, "导航到首页")
        sent = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent["type"] == "step_start"
        assert sent["data"]["step"] == 1

    @pytest.mark.asyncio
    async def test_send_step_done(self, manager, mock_ws):
        await manager.connect(mock_ws)
        await manager.send_step_done(2, "passed", "点击登录")
        sent = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent["type"] == "step_done"
        assert sent["data"]["status"] == "passed"

    @pytest.mark.asyncio
    async def test_send_bug_found(self, manager, mock_ws):
        await manager.connect(mock_ws)
        await manager.send_bug_found("按钮无响应", "high")
        sent = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent["type"] == "bug_found"
        assert "按钮无响应" in sent["data"]["message"]

    @pytest.mark.asyncio
    async def test_send_repair_start(self, manager, mock_ws):
        await manager.connect(mock_ws)
        await manager.send_repair_start("修复登录Bug")
        sent = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent["type"] == "repair_start"

    @pytest.mark.asyncio
    async def test_send_repair_done(self, manager, mock_ws):
        await manager.connect(mock_ws)
        await manager.send_repair_done("修复Bug", True)
        sent = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent["type"] == "repair_done"
        assert sent["data"]["success"] is True

    @pytest.mark.asyncio
    async def test_send_test_done(self, manager, mock_ws):
        await manager.connect(mock_ws)
        await manager.send_test_done(0.85, 2)
        sent = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent["type"] == "test_done"
        assert sent["data"]["pass_rate"] == 0.85
        assert sent["data"]["bug_count"] == 2
