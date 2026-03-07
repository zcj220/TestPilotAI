"""
厂商弹窗选择器库与自动dismiss机制（v5.1）

Android 各厂商（华为/小米/OPPO/vivo/三星等）在系统层面会弹出自定义权限弹窗、
电池优化提示、后台运行确认等对话框，这些不属于标准 Android 权限系统，
Appium 的 autoGrantPermissions 无法覆盖。

本模块提供：
1. VendorDialogRegistry - 厂商弹窗选择器数据库
2. DialogDismisser - 后台自动检测并点掉弹窗的任务

使用方式：
    dismisser = DialogDismisser(android_controller)
    dismisser.start()       # 启动后台自动dismiss
    # ... 执行测试 ...
    dismisser.stop()        # 测试结束时停止
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from loguru import logger


class DialogVendor(str, Enum):
    """厂商枚举。"""
    AOSP = "aosp"           # 原生 Android / Google Pixel
    HUAWEI = "huawei"       # 华为 / 荣耀（EMUI / HarmonyOS）
    XIAOMI = "xiaomi"       # 小米 / 红米（MIUI / HyperOS）
    OPPO = "oppo"           # OPPO / 一加（ColorOS）
    VIVO = "vivo"           # vivo / iQOO（OriginOS / FuntouchOS）
    SAMSUNG = "samsung"     # 三星（One UI）
    MEIZU = "meizu"         # 魅族（Flyme）
    GENERIC = "generic"     # 通用规则（所有厂商共用）


@dataclass
class DialogPattern:
    """单条弹窗匹配规则。"""
    name: str                           # 规则名称，如"华为电池优化弹窗"
    vendor: DialogVendor                # 所属厂商
    detect_xpath: str                   # 用于检测弹窗是否出现的xpath
    dismiss_xpath: str                  # 用于点击关闭的xpath
    description: str = ""               # 规则说明
    priority: int = 0                   # 优先级（越大越先检查）


class VendorDialogRegistry:
    """厂商弹窗选择器注册表。

    内置主流厂商常见弹窗规则，并支持自定义追加。
    """

    def __init__(self) -> None:
        self._patterns: list[DialogPattern] = []
        self._load_builtin()

    def _load_builtin(self) -> None:
        """加载内置弹窗规则。"""
        builtins = [
            # ── AOSP / 原生 Android ──
            DialogPattern(
                name="AOSP权限弹窗-允许",
                vendor=DialogVendor.AOSP,
                detect_xpath='//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_button"]',
                dismiss_xpath='//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_button"]',
                description="标准Android权限弹窗的'允许'按钮",
                priority=10,
            ),
            DialogPattern(
                name="AOSP权限弹窗-仅使用时允许",
                vendor=DialogVendor.AOSP,
                detect_xpath='//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_foreground_only_button"]',
                dismiss_xpath='//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_foreground_only_button"]',
                description="标准Android权限弹窗的'仅在使用中允许'按钮",
                priority=9,
            ),
            DialogPattern(
                name="AOSP允许按钮-文本匹配",
                vendor=DialogVendor.GENERIC,
                detect_xpath='//android.widget.Button[@text="允许" or @text="Allow" or @text="ALLOW"]',
                dismiss_xpath='//android.widget.Button[@text="允许" or @text="Allow" or @text="ALLOW"]',
                description="通过文本匹配的通用允许按钮",
                priority=5,
            ),

            # ── 华为 / EMUI / HarmonyOS ──
            DialogPattern(
                name="华为权限弹窗-允许",
                vendor=DialogVendor.HUAWEI,
                detect_xpath='//android.widget.Button[@resource-id="com.android.packageinstaller:id/permission_allow_button"]',
                dismiss_xpath='//android.widget.Button[@resource-id="com.android.packageinstaller:id/permission_allow_button"]',
                description="华为EMUI权限弹窗的允许按钮",
                priority=10,
            ),
            DialogPattern(
                name="华为电池优化弹窗",
                vendor=DialogVendor.HUAWEI,
                detect_xpath='//android.widget.TextView[contains(@text, "电池优化") or contains(@text, "耗电")]',
                dismiss_xpath='//android.widget.Button[@text="取消" or @text="不再提醒" or @text="Cancel"]',
                description="华为电池优化/高耗电提示弹窗",
                priority=8,
            ),
            DialogPattern(
                name="华为后台运行弹窗",
                vendor=DialogVendor.HUAWEI,
                detect_xpath='//android.widget.TextView[contains(@text, "后台运行") or contains(@text, "后台活动")]',
                dismiss_xpath='//android.widget.Button[@text="允许" or @text="确定"]',
                description="华为后台运行确认弹窗",
                priority=8,
            ),

            # ── 小米 / MIUI / HyperOS ──
            DialogPattern(
                name="小米权限弹窗-允许",
                vendor=DialogVendor.XIAOMI,
                detect_xpath='//android.widget.Button[@resource-id="android:id/button1" or @resource-id="com.lbe.security.miui:id/permission_allow_button"]',
                dismiss_xpath='//android.widget.Button[@resource-id="android:id/button1" or @resource-id="com.lbe.security.miui:id/permission_allow_button"]',
                description="小米MIUI权限弹窗的允许按钮",
                priority=10,
            ),
            DialogPattern(
                name="小米安全中心权限",
                vendor=DialogVendor.XIAOMI,
                detect_xpath='//android.widget.TextView[contains(@text, "权限请求")]',
                dismiss_xpath='//android.widget.Button[@text="允许" or @text="同意"]',
                description="小米安全中心的权限请求弹窗",
                priority=9,
            ),
            DialogPattern(
                name="小米应用商店评分弹窗",
                vendor=DialogVendor.XIAOMI,
                detect_xpath='//android.widget.TextView[contains(@text, "评分") or contains(@text, "好评")]',
                dismiss_xpath='//android.widget.Button[@text="取消" or @text="以后再说"]',
                description="小米应用商店评分提示",
                priority=6,
            ),

            # ── OPPO / ColorOS ──
            DialogPattern(
                name="OPPO权限弹窗-允许",
                vendor=DialogVendor.OPPO,
                detect_xpath='//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_button" or @resource-id="com.coloros.securepay:id/btn_allow"]',
                dismiss_xpath='//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_button" or @resource-id="com.coloros.securepay:id/btn_allow"]',
                description="OPPO ColorOS权限弹窗",
                priority=10,
            ),
            DialogPattern(
                name="OPPO省电提示",
                vendor=DialogVendor.OPPO,
                detect_xpath='//android.widget.TextView[contains(@text, "省电") or contains(@text, "电量")]',
                dismiss_xpath='//android.widget.Button[@text="取消" or @text="忽略"]',
                description="OPPO省电/电量优化提示弹窗",
                priority=7,
            ),

            # ── vivo / OriginOS ──
            DialogPattern(
                name="vivo权限弹窗-允许",
                vendor=DialogVendor.VIVO,
                detect_xpath='//android.widget.Button[@resource-id="com.android.packageinstaller:id/permission_allow_button" or @resource-id="com.vivo.permissionmanager:id/btn_allow"]',
                dismiss_xpath='//android.widget.Button[@resource-id="com.android.packageinstaller:id/permission_allow_button" or @resource-id="com.vivo.permissionmanager:id/btn_allow"]',
                description="vivo权限弹窗",
                priority=10,
            ),
            DialogPattern(
                name="vivo后台弹窗",
                vendor=DialogVendor.VIVO,
                detect_xpath='//android.widget.TextView[contains(@text, "后台弹出界面")]',
                dismiss_xpath='//android.widget.Button[@text="允许" or @text="确定"]',
                description="vivo后台弹出界面权限确认",
                priority=8,
            ),

            # ── 三星 / One UI ──
            DialogPattern(
                name="三星权限弹窗-允许",
                vendor=DialogVendor.SAMSUNG,
                detect_xpath='//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_button" or @resource-id="com.samsung.android.permissioncontroller:id/permission_allow_button"]',
                dismiss_xpath='//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_button" or @resource-id="com.samsung.android.permissioncontroller:id/permission_allow_button"]',
                description="三星One UI权限弹窗",
                priority=10,
            ),

            # ── 通用规则 ──
            DialogPattern(
                name="通用确定/OK按钮",
                vendor=DialogVendor.GENERIC,
                detect_xpath='//android.widget.Button[@text="确定" or @text="OK" or @text="ok" or @text="确认"]',
                dismiss_xpath='//android.widget.Button[@text="确定" or @text="OK" or @text="ok" or @text="确认"]',
                description="通用确认按钮（低优先级兜底）",
                priority=1,
            ),
            DialogPattern(
                name="通用关闭/跳过按钮",
                vendor=DialogVendor.GENERIC,
                detect_xpath='//android.widget.Button[@text="跳过" or @text="Skip" or @text="关闭" or @text="Close"]',
                dismiss_xpath='//android.widget.Button[@text="跳过" or @text="Skip" or @text="关闭" or @text="Close"]',
                description="通用跳过/关闭按钮（最低优先级兜底）",
                priority=0,
            ),
        ]

        self._patterns.extend(builtins)
        self._patterns.sort(key=lambda p: p.priority, reverse=True)

    @property
    def patterns(self) -> list[DialogPattern]:
        return list(self._patterns)

    @property
    def count(self) -> int:
        return len(self._patterns)

    def get_patterns_for_vendor(self, vendor: DialogVendor) -> list[DialogPattern]:
        """获取指定厂商 + 通用规则。"""
        return [p for p in self._patterns
                if p.vendor == vendor or p.vendor == DialogVendor.GENERIC]

    def add_pattern(self, pattern: DialogPattern) -> None:
        """添加自定义弹窗规则。"""
        self._patterns.append(pattern)
        self._patterns.sort(key=lambda p: p.priority, reverse=True)

    def detect_vendor(self, manufacturer: str) -> DialogVendor:
        """根据设备制造商名称推断厂商。"""
        mfr = manufacturer.lower()
        mapping = {
            "huawei": DialogVendor.HUAWEI,
            "honor": DialogVendor.HUAWEI,
            "xiaomi": DialogVendor.XIAOMI,
            "redmi": DialogVendor.XIAOMI,
            "oppo": DialogVendor.OPPO,
            "oneplus": DialogVendor.OPPO,
            "realme": DialogVendor.OPPO,
            "vivo": DialogVendor.VIVO,
            "iqoo": DialogVendor.VIVO,
            "samsung": DialogVendor.SAMSUNG,
            "meizu": DialogVendor.MEIZU,
            "google": DialogVendor.AOSP,
            "pixel": DialogVendor.AOSP,
        }
        for key, vendor in mapping.items():
            if key in mfr:
                return vendor
        return DialogVendor.GENERIC


class DialogDismisser:
    """后台弹窗自动dismiss任务。

    在测试过程中周期性检查屏幕上是否有已知弹窗，
    如果检测到则自动点击dismiss按钮。

    使用：
        dismisser = DialogDismisser(controller)
        dismisser.start()
        # ... 测试执行 ...
        dismisser.stop()
    """

    def __init__(
        self,
        controller: "AndroidController",
        registry: Optional[VendorDialogRegistry] = None,
        check_interval: float = 2.0,
        vendor: Optional[DialogVendor] = None,
    ) -> None:
        self._controller = controller
        self._registry = registry or VendorDialogRegistry()
        self._check_interval = check_interval
        self._vendor = vendor
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._dismissed_count = 0
        self._dismissed_log: list[str] = []

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def dismissed_count(self) -> int:
        return self._dismissed_count

    @property
    def dismissed_log(self) -> list[str]:
        return list(self._dismissed_log)

    def start(self) -> None:
        """启动后台dismiss任务。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._loop())
        logger.info("弹窗自动dismiss已启动 | 间隔={}s", self._check_interval)

    def stop(self) -> None:
        """停止后台dismiss任务。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("弹窗自动dismiss已停止 | 共处理{}个弹窗", self._dismissed_count)

    async def _loop(self) -> None:
        """周期性检查并dismiss弹窗的主循环。"""
        while self._running:
            try:
                await self._check_and_dismiss()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("弹窗检测出错(忽略): {}", e)
            await asyncio.sleep(self._check_interval)

    async def _check_and_dismiss(self) -> None:
        """检查当前屏幕是否有已知弹窗，有则dismiss。"""
        if self._vendor:
            patterns = self._registry.get_patterns_for_vendor(self._vendor)
        else:
            patterns = self._registry.patterns

        for pattern in patterns:
            try:
                # 尝试查找弹窗检测元素
                element_id = await self._controller._find_element(pattern.detect_xpath)
                # 找到了，说明弹窗出现
                logger.info("检测到弹窗: {} | 正在dismiss...", pattern.name)

                # 点击dismiss按钮
                if pattern.dismiss_xpath == pattern.detect_xpath:
                    # 检测和dismiss是同一个元素，直接点
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda eid=element_id: self._controller._session_request(
                            "POST", f"/element/{eid}/click"
                        ),
                    )
                else:
                    # dismiss是不同元素，需要重新查找
                    dismiss_id = await self._controller._find_element(pattern.dismiss_xpath)
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda did=dismiss_id: self._controller._session_request(
                            "POST", f"/element/{did}/click"
                        ),
                    )

                self._dismissed_count += 1
                self._dismissed_log.append(pattern.name)
                logger.info("弹窗已dismiss: {} | 累计{}个", pattern.name, self._dismissed_count)

                # dismiss一个后短暂等待再继续检查（可能有连续弹窗）
                await asyncio.sleep(0.5)
                return  # 每轮只处理一个，避免误操作

            except RuntimeError:
                # 元素未找到 = 该弹窗没出现，继续检查下一个
                continue

    async def dismiss_once(self) -> Optional[str]:
        """手动执行一次弹窗检测+dismiss。

        Returns:
            被dismiss的弹窗名称，None表示没有检测到弹窗
        """
        if self._vendor:
            patterns = self._registry.get_patterns_for_vendor(self._vendor)
        else:
            patterns = self._registry.patterns

        for pattern in patterns:
            try:
                element_id = await self._controller._find_element(pattern.detect_xpath)
                if pattern.dismiss_xpath == pattern.detect_xpath:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda eid=element_id: self._controller._session_request(
                            "POST", f"/element/{eid}/click"
                        ),
                    )
                else:
                    dismiss_id = await self._controller._find_element(pattern.dismiss_xpath)
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda did=dismiss_id: self._controller._session_request(
                            "POST", f"/element/{did}/click"
                        ),
                    )
                self._dismissed_count += 1
                self._dismissed_log.append(pattern.name)
                return pattern.name
            except RuntimeError:
                continue
        return None
