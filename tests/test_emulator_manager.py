"""
Docker Android 模拟器管理器测试（v5.1）

通过 mock subprocess 和 urllib 避免依赖真实 Docker 环境。
"""

import asyncio
import json
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from src.controller.emulator_manager import EmulatorManager


class TestEmulatorManagerInit:
    """初始化测试。"""

    def test_default_config(self):
        mgr = EmulatorManager()
        assert mgr.appium_url == "http://127.0.0.1:4723"
        assert mgr.vnc_url == "http://127.0.0.1:6080"
        assert not mgr.is_running

    def test_custom_config(self):
        mgr = EmulatorManager(
            appium_host="192.168.1.10",
            appium_port=4724,
            vnc_port=6081,
            startup_timeout=600,
        )
        assert mgr.appium_url == "http://192.168.1.10:4724"
        assert mgr.vnc_url == "http://192.168.1.10:6081"


class TestEmulatorStart:
    """启动测试。"""

    @pytest.mark.asyncio
    async def test_start_success(self):
        mgr = EmulatorManager()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch.object(mgr, "_run_compose", return_value=mock_result):
            await mgr.start()

        assert mgr.is_running

    @pytest.mark.asyncio
    async def test_start_failure(self):
        mgr = EmulatorManager()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "docker not found"

        with patch.object(mgr, "_run_compose", return_value=mock_result):
            with pytest.raises(RuntimeError, match="启动容器失败"):
                await mgr.start()

        assert not mgr.is_running


class TestEmulatorStop:
    """停止测试。"""

    @pytest.mark.asyncio
    async def test_stop_success(self):
        mgr = EmulatorManager()
        mgr._is_running = True

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch.object(mgr, "_run_compose", return_value=mock_result):
            await mgr.stop()

        assert not mgr.is_running

    @pytest.mark.asyncio
    async def test_stop_failure_still_marks_stopped(self):
        mgr = EmulatorManager()
        mgr._is_running = True

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"

        with patch.object(mgr, "_run_compose", return_value=mock_result):
            await mgr.stop()

        assert not mgr.is_running


class TestWaitReady:
    """等待就绪测试。"""

    @pytest.mark.asyncio
    async def test_wait_ready_immediate(self):
        mgr = EmulatorManager()

        with patch.object(mgr, "_check_appium_status", return_value=True):
            result = await mgr.wait_ready(timeout=10)

        assert result is True

    @pytest.mark.asyncio
    async def test_wait_ready_timeout(self):
        mgr = EmulatorManager(startup_timeout=3)

        with patch.object(mgr, "_check_appium_status", return_value=False):
            with patch("src.controller.emulator_manager.asyncio.sleep", new=AsyncMock(return_value=None)):
                result = await mgr.wait_ready(timeout=1)

        assert result is False

    @pytest.mark.asyncio
    async def test_wait_ready_becomes_ready(self):
        mgr = EmulatorManager()
        call_count = 0

        def mock_check():
            nonlocal call_count
            call_count += 1
            return call_count >= 2  # 第二次检查时就绪

        with patch.object(mgr, "_check_appium_status", side_effect=mock_check):
            with patch("src.controller.emulator_manager.asyncio.sleep", new=AsyncMock(return_value=None)):
                result = await mgr.wait_ready(timeout=30)

        assert result is True
        assert call_count >= 2


class TestHealthCheck:
    """健康检查测试。"""

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(self):
        mgr = EmulatorManager()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '[{"State": "running"}]'

        with patch.object(mgr, "_check_appium_status", return_value=True):
            with patch.object(mgr, "_run_compose", return_value=mock_result):
                health = await mgr.health_check()

        assert health["appium_ready"] is True
        assert health["container_running"] is True
        assert health["appium_url"] == mgr.appium_url

    @pytest.mark.asyncio
    async def test_health_check_not_running(self):
        mgr = EmulatorManager()

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch.object(mgr, "_check_appium_status", return_value=False):
            with patch.object(mgr, "_run_compose", return_value=mock_result):
                health = await mgr.health_check()

        assert health["appium_ready"] is False
        assert health["container_running"] is False


class TestCheckAppiumStatus:
    """Appium状态检测测试。"""

    def test_appium_ready(self):
        mgr = EmulatorManager()
        response_data = json.dumps({"value": {"ready": True, "build": {"version": "2.5.0"}}}).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert mgr._check_appium_status() is True

    def test_appium_not_ready(self):
        mgr = EmulatorManager()
        response_data = json.dumps({"value": {"ready": False}}).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert mgr._check_appium_status() is False

    def test_appium_connection_error(self):
        mgr = EmulatorManager()

        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            assert mgr._check_appium_status() is False


class TestGetEmulatorInfo:
    """模拟器信息获取测试。"""

    @pytest.mark.asyncio
    async def test_get_info_success(self):
        mgr = EmulatorManager()
        response_data = json.dumps({
            "value": {
                "ready": True,
                "build": {"version": "2.5.0"},
            }
        }).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            info = await mgr.get_emulator_info()

        assert info["appium_version"] == "2.5.0"
        assert info["ready"] is True

    @pytest.mark.asyncio
    async def test_get_info_failure(self):
        mgr = EmulatorManager()

        with patch("urllib.request.urlopen", side_effect=Exception("fail")):
            info = await mgr.get_emulator_info()

        assert info["appium_version"] == "unknown"
        assert info["ready"] is False


class TestContextManager:
    """上下文管理器测试。"""

    @pytest.mark.asyncio
    async def test_context_manager_success(self):
        mgr = EmulatorManager()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch.object(mgr, "_run_compose", return_value=mock_result):
            with patch.object(mgr, "_check_appium_status", return_value=True):
                async with mgr:
                    assert mgr.is_running

        assert not mgr.is_running

    @pytest.mark.asyncio
    async def test_context_manager_timeout_raises(self):
        mgr = EmulatorManager(startup_timeout=1)

        mock_start = MagicMock()
        mock_start.returncode = 0
        mock_stop = MagicMock()
        mock_stop.returncode = 0

        def mock_compose(*args, **kwargs):
            if "up" in args:
                return mock_start
            return mock_stop

        with patch.object(mgr, "_run_compose", side_effect=mock_compose):
            with patch.object(mgr, "_check_appium_status", return_value=False):
                with patch("src.controller.emulator_manager.asyncio.sleep", new=AsyncMock(return_value=None)):
                    with pytest.raises(RuntimeError, match="模拟器启动超时"):
                        async with mgr:
                            pass
