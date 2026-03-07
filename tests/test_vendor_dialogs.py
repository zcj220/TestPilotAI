"""
厂商弹窗选择器库与自动dismiss机制测试（v5.1）
"""

import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from src.controller.vendor_dialogs import (
    DialogDismisser,
    DialogPattern,
    DialogVendor,
    VendorDialogRegistry,
)


class TestDialogVendor:
    """厂商枚举测试。"""

    def test_all_vendors_exist(self):
        assert DialogVendor.AOSP == "aosp"
        assert DialogVendor.HUAWEI == "huawei"
        assert DialogVendor.XIAOMI == "xiaomi"
        assert DialogVendor.OPPO == "oppo"
        assert DialogVendor.VIVO == "vivo"
        assert DialogVendor.SAMSUNG == "samsung"
        assert DialogVendor.GENERIC == "generic"


class TestDialogPattern:
    """弹窗规则测试。"""

    def test_pattern_creation(self):
        p = DialogPattern(
            name="测试弹窗",
            vendor=DialogVendor.HUAWEI,
            detect_xpath='//Button[@text="允许"]',
            dismiss_xpath='//Button[@text="允许"]',
            description="测试用",
            priority=5,
        )
        assert p.name == "测试弹窗"
        assert p.vendor == DialogVendor.HUAWEI
        assert p.priority == 5

    def test_default_values(self):
        p = DialogPattern(
            name="test",
            vendor=DialogVendor.GENERIC,
            detect_xpath="//x",
            dismiss_xpath="//x",
        )
        assert p.description == ""
        assert p.priority == 0


class TestVendorDialogRegistry:
    """弹窗注册表测试。"""

    def test_builtin_patterns_loaded(self):
        reg = VendorDialogRegistry()
        assert reg.count > 0
        # 至少应有AOSP、华为、小米、OPPO、vivo、三星、通用的规则
        vendors = {p.vendor for p in reg.patterns}
        assert DialogVendor.AOSP in vendors
        assert DialogVendor.HUAWEI in vendors
        assert DialogVendor.XIAOMI in vendors
        assert DialogVendor.OPPO in vendors
        assert DialogVendor.VIVO in vendors
        assert DialogVendor.SAMSUNG in vendors
        assert DialogVendor.GENERIC in vendors

    def test_patterns_sorted_by_priority(self):
        reg = VendorDialogRegistry()
        priorities = [p.priority for p in reg.patterns]
        assert priorities == sorted(priorities, reverse=True)

    def test_get_patterns_for_vendor(self):
        reg = VendorDialogRegistry()
        huawei = reg.get_patterns_for_vendor(DialogVendor.HUAWEI)
        # 应该包含华为专用 + 通用规则
        huawei_vendors = {p.vendor for p in huawei}
        assert DialogVendor.HUAWEI in huawei_vendors
        assert DialogVendor.GENERIC in huawei_vendors
        # 不应包含小米专用规则
        assert DialogVendor.XIAOMI not in huawei_vendors

    def test_get_patterns_for_generic(self):
        reg = VendorDialogRegistry()
        generic = reg.get_patterns_for_vendor(DialogVendor.GENERIC)
        # 只有通用规则
        assert all(p.vendor == DialogVendor.GENERIC for p in generic)

    def test_add_custom_pattern(self):
        reg = VendorDialogRegistry()
        original_count = reg.count

        custom = DialogPattern(
            name="自定义弹窗",
            vendor=DialogVendor.HUAWEI,
            detect_xpath='//TextView[@text="自定义"]',
            dismiss_xpath='//Button[@text="关闭"]',
            priority=100,
        )
        reg.add_pattern(custom)

        assert reg.count == original_count + 1
        # 高优先级应该排在最前
        assert reg.patterns[0].name == "自定义弹窗"

    def test_detect_vendor_huawei(self):
        reg = VendorDialogRegistry()
        assert reg.detect_vendor("HUAWEI") == DialogVendor.HUAWEI
        assert reg.detect_vendor("huawei") == DialogVendor.HUAWEI
        assert reg.detect_vendor("HONOR") == DialogVendor.HUAWEI

    def test_detect_vendor_xiaomi(self):
        reg = VendorDialogRegistry()
        assert reg.detect_vendor("Xiaomi") == DialogVendor.XIAOMI
        assert reg.detect_vendor("Redmi") == DialogVendor.XIAOMI

    def test_detect_vendor_oppo(self):
        reg = VendorDialogRegistry()
        assert reg.detect_vendor("OPPO") == DialogVendor.OPPO
        assert reg.detect_vendor("OnePlus") == DialogVendor.OPPO
        assert reg.detect_vendor("realme") == DialogVendor.OPPO

    def test_detect_vendor_vivo(self):
        reg = VendorDialogRegistry()
        assert reg.detect_vendor("vivo") == DialogVendor.VIVO
        assert reg.detect_vendor("iQOO") == DialogVendor.VIVO

    def test_detect_vendor_samsung(self):
        reg = VendorDialogRegistry()
        assert reg.detect_vendor("samsung") == DialogVendor.SAMSUNG

    def test_detect_vendor_google(self):
        reg = VendorDialogRegistry()
        assert reg.detect_vendor("Google") == DialogVendor.AOSP
        assert reg.detect_vendor("Pixel") == DialogVendor.AOSP

    def test_detect_vendor_unknown(self):
        reg = VendorDialogRegistry()
        assert reg.detect_vendor("UnknownBrand") == DialogVendor.GENERIC
        assert reg.detect_vendor("") == DialogVendor.GENERIC


class TestDialogDismisser:
    """弹窗自动dismiss测试。"""

    def _make_mock_controller(self):
        ctrl = MagicMock()
        ctrl._find_element = AsyncMock(side_effect=RuntimeError("not found"))
        ctrl._session_request = MagicMock(return_value={})
        return ctrl

    def test_initial_state(self):
        ctrl = self._make_mock_controller()
        dismisser = DialogDismisser(ctrl)
        assert not dismisser.is_running
        assert dismisser.dismissed_count == 0
        assert dismisser.dismissed_log == []

    @pytest.mark.asyncio
    async def test_dismiss_once_no_dialog(self):
        ctrl = self._make_mock_controller()
        dismisser = DialogDismisser(ctrl)
        result = await dismisser.dismiss_once()
        assert result is None
        assert dismisser.dismissed_count == 0

    @pytest.mark.asyncio
    async def test_dismiss_once_found_dialog(self):
        ctrl = self._make_mock_controller()

        call_count = 0
        async def mock_find(xpath):
            nonlocal call_count
            call_count += 1
            # 第一个pattern匹配成功
            if call_count == 1:
                return "elem_123"
            raise RuntimeError("not found")

        ctrl._find_element = mock_find

        dismisser = DialogDismisser(ctrl)
        result = await dismisser.dismiss_once()

        assert result is not None  # 应该返回弹窗名
        assert dismisser.dismissed_count == 1
        assert len(dismisser.dismissed_log) == 1

    @pytest.mark.asyncio
    async def test_dismiss_specific_vendor(self):
        ctrl = self._make_mock_controller()

        found_xpaths = []
        async def mock_find(xpath):
            found_xpaths.append(xpath)
            raise RuntimeError("not found")

        ctrl._find_element = mock_find

        registry = VendorDialogRegistry()
        dismisser = DialogDismisser(ctrl, registry=registry, vendor=DialogVendor.HUAWEI)
        result = await dismisser.dismiss_once()

        assert result is None
        # 应该只尝试华为 + 通用规则
        huawei_patterns = registry.get_patterns_for_vendor(DialogVendor.HUAWEI)
        assert len(found_xpaths) == len(huawei_patterns)

    def test_start_stop(self):
        ctrl = self._make_mock_controller()
        dismisser = DialogDismisser(ctrl, check_interval=0.1)

        # start
        dismisser.start()
        assert dismisser.is_running

        # stop
        dismisser.stop()
        assert not dismisser.is_running

    def test_start_idempotent(self):
        ctrl = self._make_mock_controller()
        dismisser = DialogDismisser(ctrl)

        dismisser.start()
        task1 = dismisser._task
        dismisser.start()  # 重复调用
        task2 = dismisser._task
        assert task1 is task2  # 不应该创建新任务

        dismisser.stop()

    @pytest.mark.asyncio
    async def test_loop_checks_periodically(self):
        ctrl = self._make_mock_controller()

        check_count = 0
        original_check = DialogDismisser._check_and_dismiss

        async def mock_check(self_ref):
            nonlocal check_count
            check_count += 1
            if check_count >= 3:
                self_ref._running = False  # 3次后停止

        dismisser = DialogDismisser(ctrl, check_interval=0.05)
        with patch.object(DialogDismisser, "_check_and_dismiss", mock_check):
            dismisser.start()
            await asyncio.sleep(0.3)

        assert check_count >= 3
        dismisser.stop()
