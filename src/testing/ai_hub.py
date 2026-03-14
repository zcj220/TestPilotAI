"""
AI 中枢决策层（v12.0）

跨平台统一的 AI 大脑，为所有 Blueprint Runner（Web / Desktop / Mobile）
提供步骤失败后的智能决策能力。

分层策略：
  L0 - 直通：步骤通过，零AI成本
  L1 - 弹窗自愈：截图→AI检测弹窗→点击关闭→重试原步骤
  L2 - 失败诊断：截图→AI分析失败原因→建议重试/跳过/调整
  L3 - 场景级熔断：连续失败超阈值→跳过当前场景剩余步骤

使用方式：
    hub = AIHub(ai_client)
    # Runner 在步骤失败后调用：
    decision = await hub.on_step_failed(context)
    # 根据 decision.action 执行对应操作
"""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

from loguru import logger


class HubAction(str, Enum):
    """AI中枢决策动作。"""
    RETRY = "retry"            # 重试当前步骤（弹窗已关闭或环境已修复）
    SKIP_STEP = "skip_step"    # 跳过当前步骤
    SKIP_SCENE = "skip_scene"  # 跳过当前场景剩余步骤（熔断）
    NONE = "none"              # 无额外操作，按原逻辑走


@dataclass
class StepContext:
    """步骤上下文，Runner 传给 AIHub 的信息包。"""
    step_num: int
    total_steps: int
    action: str                          # click / fill / assert_text / ...
    target: Optional[str] = None
    value: Optional[str] = None
    error_message: Optional[str] = None
    scenario_name: str = ""
    platform: str = ""                   # web / desktop / mobile

    # Runner 提供的能力回调（由各平台 Runner 注入）
    screenshot_fn: Optional[Callable[..., Coroutine]] = field(default=None, repr=False)
    click_fn: Optional[Callable[..., Coroutine]] = field(default=None, repr=False)


@dataclass
class HubDecision:
    """AI中枢返回的决策。"""
    action: HubAction = HubAction.NONE
    reason: str = ""
    popup_closed: bool = False           # 是否关闭了弹窗
    ai_cost_ms: float = 0               # 本次决策的AI调用耗时


# ═══════════════════════════════════════════════════════════
#   弹窗按钮关键词（跨平台通用）
# ═══════════════════════════════════════════════════════════

DIALOG_BUTTON_KEYWORDS = frozenset({
    "name:OK", "name:Ok", "name:ok",
    "name:Yes", "name:yes", "name:YES",
    "name:No", "name:no", "name:NO",
    "name:Cancel", "name:cancel",
    "name:Close", "name:close",
    "name:确定", "name:取消",
    "name:是", "name:否", "name:关闭",
    # Android accessibility_id 格式
    "accessibility_id:OK", "accessibility_id:Cancel",
    "accessibility_id:Yes", "accessibility_id:No",
    "accessibility_id:确定", "accessibility_id:取消",
})


class AIHub:
    """跨平台 AI 中枢决策层。

    所有 Runner 在步骤失败时调用 `on_step_failed()`，
    由 Hub 统一执行 L1→L2→L3 决策链。

    使用方式：
        hub = AIHub(ai_client)

        # 在 Runner 的 run() 循环中：
        if bug:
            decision = await hub.on_step_failed(ctx)
            if decision.action == HubAction.RETRY:
                result, bug = await self._execute_step(...)  # 重试
            elif decision.action == HubAction.SKIP_SCENE:
                break  # 跳出当前 scenario
    """

    MAX_CONSECUTIVE_FAILURES = 3

    def __init__(self, ai_client: Optional[Any] = None) -> None:
        self._ai = ai_client
        self._consecutive_failures: int = 0
        # 统计
        self._total_heals: int = 0
        self._total_l1_calls: int = 0
        self._total_l2_calls: int = 0
        self._total_skipped_scenes: int = 0

    # ── 公共接口 ──────────────────────────────────────────

    def on_step_passed(self) -> None:
        """步骤通过时调用（L0），重置连续失败计数。"""
        self._consecutive_failures = 0

    def on_scenario_start(self) -> None:
        """场景开始时调用，重置连续失败计数。"""
        self._consecutive_failures = 0

    async def on_step_failed(self, ctx: StepContext) -> HubDecision:
        """步骤失败时的统一决策入口。

        决策链：L1 弹窗自愈 → L2 失败诊断 → L3 熔断
        """
        self._consecutive_failures += 1

        # ── L3 熔断检查（优先级最高，避免在已崩溃场景中浪费AI调用）──
        if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            self._total_skipped_scenes += 1
            logger.warning(
                "  ⚠️ AI中枢L3熔断 | 场景[{}]连续失败{}步，跳到下一场景",
                ctx.scenario_name, self._consecutive_failures
            )
            return HubDecision(
                action=HubAction.SKIP_SCENE,
                reason=f"连续失败{self._consecutive_failures}步，场景级熔断",
            )

        # ── L1 弹窗自愈（仅对可能被弹窗遮挡的操作）──
        if ctx.action in ("click", "fill", "assert_text", "assert_visible"):
            decision = await self._try_l1_popup_heal(ctx)
            if decision.popup_closed:
                self._consecutive_failures = 0  # 弹窗关闭后重置计数
                return decision

        # ── L2 失败诊断（预留，当前返回 NONE）──
        # 未来：截图 + AI 分析失败原因，判断是否可重试
        # decision = await self._try_l2_diagnose(ctx)
        # if decision.action != HubAction.NONE:
        #     return decision

        return HubDecision(action=HubAction.NONE, reason="L1/L2未能解决")

    @property
    def stats(self) -> dict:
        """返回中枢运行统计。"""
        return {
            "total_heals": self._total_heals,
            "l1_calls": self._total_l1_calls,
            "l2_calls": self._total_l2_calls,
            "skipped_scenes": self._total_skipped_scenes,
        }

    # ── L1: 弹窗自愈 ─────────────────────────────────────

    async def _try_l1_popup_heal(self, ctx: StepContext) -> HubDecision:
        """L1：截图 → AI 检测弹窗 → 点击关闭按钮。

        这是从 DesktopBlueprintRunner._try_heal_popup() 提取的跨平台版本。
        依赖 Runner 通过 ctx.screenshot_fn / ctx.click_fn 注入平台能力。
        """
        self._total_l1_calls += 1

        if not self._ai or not ctx.screenshot_fn or not ctx.click_fn:
            return HubDecision(action=HubAction.NONE, reason="缺少AI或平台回调")

        start = time.time()
        try:
            # 1. 截图
            screenshot_path = await ctx.screenshot_fn("popup_detect")
            if not screenshot_path:
                return HubDecision(action=HubAction.NONE, reason="截图失败")

            # 2. AI 分析是否有弹窗
            prompt = (
                "这是一个应用的截图。请判断截图中是否有模态弹窗/对话框覆盖在主界面上方。\n"
                "如果有弹窗，请找到关闭按钮（如OK、Cancel、Close、Yes、No、确定、取消、X按钮）的中心坐标。\n"
                "坐标为归一化值(0~1)，(0,0)是截图左上角。\n\n"
                "返回JSON格式：\n"
                '- 有弹窗：{"popup": true, "button": "OK", "x": 0.5, "y": 0.7}\n'
                '- 无弹窗：{"popup": false}'
            )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._ai.analyze_screenshot(
                    str(screenshot_path), prompt,
                    reasoning_effort="low", timeout=20,
                )
            )

            cost_ms = (time.time() - start) * 1000
            logger.debug("AI中枢L1弹窗检测返回(前300字): {}", response[:300])

            # 3. 解析 JSON
            json_match = re.search(r"\{.*?\}", response, re.DOTALL)
            if not json_match:
                return HubDecision(action=HubAction.NONE, reason="AI返回无JSON", ai_cost_ms=cost_ms)

            result = json.loads(json_match.group().replace("'", '"'))
            if not result.get("popup"):
                return HubDecision(action=HubAction.NONE, reason="未检测到弹窗", ai_cost_ms=cost_ms)

            # 4. 点击关闭按钮
            nx = result.get("x")
            ny = result.get("y")
            if nx is not None and ny is not None:
                btn_name = result.get("button", "unknown")
                logger.info("  🔧 AI中枢L1：检测到弹窗，点击[{}] ({:.2f}, {:.2f})",
                            btn_name, float(nx), float(ny))
                await ctx.click_fn(float(nx), float(ny))
                await asyncio.sleep(0.5)
                self._total_heals += 1
                return HubDecision(
                    action=HubAction.RETRY,
                    reason=f"弹窗已关闭(按钮:{btn_name})",
                    popup_closed=True,
                    ai_cost_ms=cost_ms,
                )

        except Exception as e:
            logger.warning("AI中枢L1弹窗检测失败: {}", str(e)[:100])

        return HubDecision(action=HubAction.NONE, reason="L1弹窗自愈未成功")

    # ── 工具方法 ──────────────────────────────────────────

    @staticmethod
    def is_dialog_button(target: str) -> bool:
        """判断目标是否是弹窗按钮（各 Runner 可用来跳过缓存）。"""
        return target in DIALOG_BUTTON_KEYWORDS
