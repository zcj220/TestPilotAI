"""
AndroidController 单元测试（v5.1）

测试权限授予、屏幕保持亮屏等功能。
通过 mock subprocess 避免依赖真实设备。
"""

import asyncio
from unittest.mock import patch, MagicMock

import pytest

from src.controller.android import AndroidController, MobileConfig
from src.controller.base import Platform


class TestAndroidControllerInit:
    """初始化测试。"""

    def test_default_config(self):
        ctrl = AndroidController()
        assert ctrl.platform == Platform.ANDROID
        assert ctrl.device_info.name == "Android Device"
        assert ctrl._original_stay_on is None
        assert ctrl._original_screen_off_timeout is None

    def test_custom_config(self):
        config = MobileConfig(device_name="abc123", app_package="com.test")
        ctrl = AndroidController(config)
        assert ctrl.device_info.name == "abc123"
        assert ctrl._config.app_package == "com.test"


class TestGrantPermissions:
    """权限批量授予测试。"""

    @pytest.mark.asyncio
    async def test_grant_permissions_success(self):
        ctrl = AndroidController(MobileConfig(device_name="device1"))

        # mock _adb_cmd: 成功时返回空字符串
        with patch.object(ctrl, "_adb_cmd", return_value="") as mock_adb:
            granted = await ctrl.grant_permissions("com.example.app", [
                "android.permission.CAMERA",
                "android.permission.ACCESS_FINE_LOCATION",
            ])

        assert len(granted) == 2
        assert "android.permission.CAMERA" in granted
        assert "android.permission.ACCESS_FINE_LOCATION" in granted
        assert mock_adb.call_count == 2

    @pytest.mark.asyncio
    async def test_grant_permissions_partial_failure(self):
        ctrl = AndroidController(MobileConfig(device_name="device1"))

        call_count = 0
        def mock_adb(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return "Exception: Unknown permission"
            return ""

        with patch.object(ctrl, "_adb_cmd", side_effect=mock_adb):
            granted = await ctrl.grant_permissions("com.example.app", [
                "android.permission.CAMERA",
                "android.permission.FAKE_PERM",
                "android.permission.WRITE_EXTERNAL_STORAGE",
            ])

        assert len(granted) == 2
        assert "android.permission.CAMERA" in granted
        assert "android.permission.WRITE_EXTERNAL_STORAGE" in granted

    @pytest.mark.asyncio
    async def test_grant_permissions_auto_prefix(self):
        """缩写权限名自动补全 android.permission. 前缀。"""
        ctrl = AndroidController(MobileConfig(device_name="device1"))

        granted_perms = []
        def mock_adb(*args):
            if args[0] == "shell" and args[1] == "pm":
                granted_perms.append(args[4])  # full permission name
            return ""

        with patch.object(ctrl, "_adb_cmd", side_effect=mock_adb):
            granted = await ctrl.grant_permissions("com.test", ["CAMERA", "LOCATION"])

        assert len(granted) == 2
        assert "android.permission.CAMERA" in granted
        assert "android.permission.LOCATION" in granted

    @pytest.mark.asyncio
    async def test_grant_permissions_empty_list(self):
        ctrl = AndroidController()
        granted = await ctrl.grant_permissions("com.test", [])
        assert granted == []

    @pytest.mark.asyncio
    async def test_grant_permissions_empty_package(self):
        ctrl = AndroidController()
        granted = await ctrl.grant_permissions("", ["android.permission.CAMERA"])
        assert granted == []


class TestKeepScreenAwake:
    """屏幕保持亮屏测试。"""

    @pytest.mark.asyncio
    async def test_keep_screen_awake_saves_originals(self):
        ctrl = AndroidController(MobileConfig(device_name="device1"))

        calls = []
        def mock_adb(*args):
            calls.append(args)
            if args == ("shell", "settings", "get", "global", "stay_on_while_plugged_in"):
                return "0"
            if args == ("shell", "settings", "get", "system", "screen_off_timeout"):
                return "30000"
            return ""

        with patch.object(ctrl, "_adb_cmd", side_effect=mock_adb):
            await ctrl._keep_screen_awake()

        assert ctrl._original_stay_on == "0"
        assert ctrl._original_screen_off_timeout == "30000"
        # 应该有5次调用：2次get + 2次put + 1次wakeup
        assert len(calls) == 5

    @pytest.mark.asyncio
    async def test_restore_screen_settings(self):
        ctrl = AndroidController(MobileConfig(device_name="device1"))
        ctrl._original_stay_on = "3"
        ctrl._original_screen_off_timeout = "60000"

        calls = []
        def mock_adb(*args):
            calls.append(args)
            return ""

        with patch.object(ctrl, "_adb_cmd", side_effect=mock_adb):
            await ctrl._restore_screen_settings()

        assert len(calls) == 2
        # 验证恢复的值
        assert ("shell", "settings", "put", "global", "stay_on_while_plugged_in", "3") in calls
        assert ("shell", "settings", "put", "system", "screen_off_timeout", "60000") in calls

    @pytest.mark.asyncio
    async def test_restore_skips_when_no_originals(self):
        ctrl = AndroidController()
        # 原始值为 None，不应调用 adb
        calls = []
        with patch.object(ctrl, "_adb_cmd", side_effect=lambda *a: calls.append(a) or ""):
            await ctrl._restore_screen_settings()
        assert len(calls) == 0


class TestAdbCmd:
    """adb命令辅助方法测试。"""

    def test_adb_cmd_with_serial(self):
        ctrl = AndroidController(MobileConfig(device_name="abc123"))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="ok\n")
            result = ctrl._adb_cmd("shell", "echo", "hi")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["adb", "-s", "abc123", "shell", "echo", "hi"]
        assert result == "ok"

    def test_adb_cmd_without_serial(self):
        ctrl = AndroidController(MobileConfig(device_name=""))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="result\n")
            result = ctrl._adb_cmd("devices")

        cmd = mock_run.call_args[0][0]
        assert cmd == ["adb", "devices"]
        assert result == "result"

    def test_adb_cmd_exception_returns_empty(self):
        ctrl = AndroidController()

        with patch("subprocess.run", side_effect=Exception("fail")):
            result = ctrl._adb_cmd("shell", "test")

        assert result == ""
