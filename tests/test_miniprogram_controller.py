"""
微信小程序控制器测试（v8.0）

覆盖：MiniProgramConfig、MiniProgramController、桥接调用
全部 mock Node.js 子进程调用。
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.controller.miniprogram import MiniProgramConfig, MiniProgramController


# ── MiniProgramConfig 测试 ──────────────────────

class TestMiniProgramConfig:
    def test_defaults(self, tmp_path):
        cfg = MiniProgramConfig(screenshot_dir=str(tmp_path / "shots"))
        assert cfg.project_path == ""
        assert cfg.timeout_ms == 30000
        assert cfg.screenshot_dir.exists()

    def test_custom(self, tmp_path):
        cfg = MiniProgramConfig(
            project_path="D:\\my-mp",
            devtools_path="C:\\devtools\\cli.bat",
            screenshot_dir=str(tmp_path / "mp"),
            timeout_ms=15000,
            account="test@test.com",
        )
        assert cfg.project_path == "D:\\my-mp"
        assert cfg.devtools_path == "C:\\devtools\\cli.bat"
        assert cfg.timeout_ms == 15000
        assert cfg.account == "test@test.com"

    @patch("src.controller.miniprogram.Path.exists")
    def test_detect_devtools_found(self, mock_exists):
        mock_exists.return_value = True
        path = MiniProgramConfig._detect_devtools()
        assert path != ""
        assert "cli.bat" in path

    @patch("src.controller.miniprogram.Path.exists")
    def test_detect_devtools_not_found(self, mock_exists):
        mock_exists.return_value = False
        path = MiniProgramConfig._detect_devtools()
        assert path == ""


# ── MiniProgramController 测试 ──────────────────

class TestMiniProgramController:
    @pytest.fixture
    def config(self, tmp_path):
        return MiniProgramConfig(
            project_path="D:\\test-mp",
            devtools_path="C:\\devtools\\cli.bat",
            screenshot_dir=str(tmp_path / "shots"),
        )

    def test_platform(self, config):
        ctrl = MiniProgramController(config)
        from src.controller.base import Platform
        assert ctrl.platform == Platform.WEB

    def test_device_info(self, config):
        ctrl = MiniProgramController(config)
        assert ctrl.device_info.name == "WeChat MiniProgram"
        assert ctrl.device_info.screen_width == 375

    @pytest.mark.asyncio
    async def test_launch_no_devtools(self, tmp_path):
        cfg = MiniProgramConfig(
            project_path="D:\\test",
            devtools_path="",
            screenshot_dir=str(tmp_path / "s"),
        )
        ctrl = MiniProgramController(cfg)
        with pytest.raises(RuntimeError, match="未找到微信开发者工具"):
            await ctrl.launch()

    @pytest.mark.asyncio
    async def test_launch_no_project(self, tmp_path):
        cfg = MiniProgramConfig(
            project_path="",
            devtools_path="C:\\cli.bat",
            screenshot_dir=str(tmp_path / "s"),
        )
        ctrl = MiniProgramController(cfg)
        with pytest.raises(RuntimeError, match="请指定小程序项目路径"):
            await ctrl.launch()

    @pytest.mark.asyncio
    async def test_launch_success(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge, \
             patch("src.controller.miniprogram.Path.exists", return_value=True):
            mock_bridge.return_value = {"success": True, "page": "/pages/index/index"}
            await ctrl.launch()
            assert ctrl.device_info.is_connected is True

    @pytest.mark.asyncio
    async def test_launch_failure(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge, \
             patch("src.controller.miniprogram.Path.exists", return_value=True):
            mock_bridge.return_value = {"success": False, "error": "连接超时"}
            with pytest.raises(RuntimeError, match="连接失败"):
                await ctrl.launch()

    @pytest.mark.asyncio
    async def test_close(self, config):
        ctrl = MiniProgramController(config)
        ctrl._connected = True
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": True}
            await ctrl.close()
            assert ctrl.device_info.is_connected is False

    @pytest.mark.asyncio
    async def test_navigate(self, config):
        ctrl = MiniProgramController(config)
        ctrl._connected = True
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": True, "page": "/pages/detail/detail"}
            await ctrl.navigate("/pages/detail/detail")
            mock_bridge.assert_called_once_with("navigateTo", {"url": "/pages/detail/detail"})

    @pytest.mark.asyncio
    async def test_navigate_failure(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": False, "error": "页面不存在"}
            with pytest.raises(RuntimeError, match="导航失败"):
                await ctrl.navigate("/pages/notfound")

    @pytest.mark.asyncio
    async def test_tap(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": True}
            await ctrl.tap(".btn-submit")
            mock_bridge.assert_called_once_with("tap", {"selector": ".btn-submit"})

    @pytest.mark.asyncio
    async def test_tap_failure(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": False, "error": "元素未找到"}
            with pytest.raises(RuntimeError, match="点击失败"):
                await ctrl.tap(".nonexistent")

    @pytest.mark.asyncio
    async def test_input_text(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": True}
            await ctrl.input_text(".input-name", "测试文本")
            mock_bridge.assert_called_once_with("input", {"selector": ".input-name", "text": "测试文本"})

    @pytest.mark.asyncio
    async def test_input_failure(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": False, "error": "输入失败"}
            with pytest.raises(RuntimeError, match="输入失败"):
                await ctrl.input_text(".x", "t")

    @pytest.mark.asyncio
    async def test_screenshot(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": True}
            path = await ctrl.screenshot("test_shot")
            assert "test_shot" in str(path)
            assert str(path).endswith(".png")

    @pytest.mark.asyncio
    async def test_screenshot_failure(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": False, "error": "截图失败"}
            with pytest.raises(RuntimeError, match="截图失败"):
                await ctrl.screenshot()

    @pytest.mark.asyncio
    async def test_get_page_source(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": True, "wxml": "<view>hello</view>"}
            source = await ctrl.get_page_source()
            assert "<view>" in source

    @pytest.mark.asyncio
    async def test_get_text(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": True, "text": "Hello World"}
            text = await ctrl.get_text(".title")
            assert text == "Hello World"

    @pytest.mark.asyncio
    async def test_get_text_not_found(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": True, "text": ""}
            text = await ctrl.get_text(".missing")
            assert text == ""

    @pytest.mark.asyncio
    async def test_get_current_page(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": True, "path": "/pages/index/index", "query": {}}
            result = await ctrl.get_current_page()
            assert result["path"] == "/pages/index/index"

    @pytest.mark.asyncio
    async def test_get_page_data(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": True, "data": {"count": 5, "list": [1, 2]}}
            data = await ctrl.get_page_data()
            assert data["count"] == 5

    @pytest.mark.asyncio
    async def test_get_app_data(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": True, "data": {"userInfo": None}}
            data = await ctrl.get_app_data()
            assert "userInfo" in data

    @pytest.mark.asyncio
    async def test_call_wx_api(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": True, "result": {"model": "iPhone"}}
            result = await ctrl.call_wx_api("getSystemInfo")
            assert result["result"]["model"] == "iPhone"

    @pytest.mark.asyncio
    async def test_mock_wx_api(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"success": True}
            await ctrl.mock_wx_api("getLocation", {"latitude": 39.9, "longitude": 116.3})
            mock_bridge.assert_called_once()


# ── 桥接调用测试 ────────────────────────────────

class TestBridgeCall:
    @pytest.fixture
    def config(self, tmp_path):
        return MiniProgramConfig(
            project_path="D:\\test",
            devtools_path="C:\\cli.bat",
            screenshot_dir=str(tmp_path / "s"),
        )

    @pytest.mark.asyncio
    async def test_bridge_success(self, config):
        ctrl = MiniProgramController(config)
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"success": True, "text": "ok"})
        mock_result.stderr = ""
        with patch("src.controller.miniprogram.subprocess.run", return_value=mock_result):
            result = await ctrl._call_bridge("getText", {"selector": ".x"})
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_bridge_timeout(self, config):
        ctrl = MiniProgramController(config)
        import subprocess
        with patch("src.controller.miniprogram.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="node", timeout=30)):
            result = await ctrl._call_bridge("tap", {"selector": ".x"})
            assert result["success"] is False
            assert "超时" in result["error"]

    @pytest.mark.asyncio
    async def test_bridge_no_node(self, config):
        ctrl = MiniProgramController(config)
        with patch("src.controller.miniprogram.subprocess.run",
                   side_effect=FileNotFoundError()):
            result = await ctrl._call_bridge("tap", {"selector": ".x"})
            assert result["success"] is False
            assert "Node.js" in result["error"]

    @pytest.mark.asyncio
    async def test_bridge_bad_json(self, config):
        ctrl = MiniProgramController(config)
        mock_result = MagicMock()
        mock_result.stdout = "not json"
        with patch("src.controller.miniprogram.subprocess.run", return_value=mock_result):
            result = await ctrl._call_bridge("tap", {"selector": ".x"})
            assert result["success"] is False
            assert "JSON" in result["error"]

    @pytest.mark.asyncio
    async def test_bridge_empty_output(self, config):
        ctrl = MiniProgramController(config)
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "some error"
        with patch("src.controller.miniprogram.subprocess.run", return_value=mock_result):
            result = await ctrl._call_bridge("tap", {"selector": ".x"})
            assert result["success"] is False

    @pytest.mark.asyncio
    async def test_wait_for_element_found(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"exists": True}
            await ctrl.wait_for_element(".btn", timeout_ms=2000)

    @pytest.mark.asyncio
    async def test_wait_for_element_timeout(self, config):
        ctrl = MiniProgramController(config)
        with patch.object(ctrl, "_call_bridge") as mock_bridge:
            mock_bridge.return_value = {"exists": False}
            with pytest.raises(RuntimeError, match="等待元素超时"):
                await ctrl.wait_for_element(".btn", timeout_ms=1000)
