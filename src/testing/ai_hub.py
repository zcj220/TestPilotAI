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


class FaultType(str, Enum):
    """失败归因：谁的锅？"""
    APP = "app"          # 被测应用的Bug（数据错误、页面崩溃、功能异常）→ 报给编程AI
    TEST = "test"        # 测试脚本/框架问题（选择器错、时序问题、弹窗遮挡）→ 中枢自己处理
    UNKNOWN = "unknown"  # 无法判断


@dataclass
class StepRecord:
    """单步操作记录，用于构建历史上下文。"""
    step_num: int
    action: str
    target: Optional[str] = None
    value: Optional[str] = None
    passed: bool = True
    error: Optional[str] = None

    def describe(self) -> str:
        """用大白话描述这一步做了什么。"""
        parts = {
            "click": f"点击了'{self.target}'",
            "fill": f"在'{self.target}'中输入了'{self.value}'",
            "assert_text": f"检查'{self.target}'的文字",
            "assert_visible": f"检查'{self.target}'是否可见",
            "navigate": f"打开了页面'{self.value or self.target}'",
            "wait": f"等待'{self.target or self.value}'",
            "screenshot": "截了个图",
            "select": f"在'{self.target}'选择了'{self.value}'",
            "scroll": "滚动了页面",
            "hover": f"鼠标移到了'{self.target}'上",
        }
        desc = parts.get(self.action, f"做了{self.action}操作")
        if self.passed:
            return f"第{self.step_num}步: {desc} → 成功"
        return f"第{self.step_num}步: {desc} → 失败({self.error[:60] if self.error else '未知'})"


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
    _cached_screenshot: Optional[str] = field(default=None, repr=False)  # L1/L2 截图缓存
    dom_context: Optional[str] = field(default=None, repr=False)  # Web DOM 元素列表（C1）
    # 蓝本预期流程摘要（第1步到当前步），让L2 AI对比"计划 vs 实际"找出根因
    blueprint_steps_context: Optional[str] = field(default=None, repr=False)


@dataclass
class HubDecision:
    """AI中枢返回的决策。"""
    action: HubAction = HubAction.NONE
    reason: str = ""
    fault: FaultType = FaultType.UNKNOWN  # 失败归因
    popup_closed: bool = False           # 是否关闭了弹窗
    ai_cost_ms: float = 0               # 本次决策的AI调用耗时
    recover_selector: Optional[str] = None  # L2恢复动作：先点击这个选择器再重试
    override_action: Optional[str] = None   # L2动作替换：重试时改用此动作（如 fill→select）
    recover_x: Optional[float] = None   # L2坐标回退：归一化X坐标(0.0-1.0)
    recover_y: Optional[float] = None   # L2坐标回退：归一化Y坐标(0.0-1.0)


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
        # 步骤历史记录（最近N步），供L2分析上下文
        self._step_history: list[StepRecord] = []
        self._MAX_HISTORY: int = 8  # 最多记住最近8步
        # 蓝本修复建议：收集每次L2诊断中发现的蓝本问题，测试结束后反馈给编程AI
        self._blueprint_hints: list[dict] = []
        # 统计
        self._total_heals: int = 0
        self._total_l1_calls: int = 0
        self._total_l2_calls: int = 0
        self._total_rule_judgments: int = 0
        self._total_skipped_scenes: int = 0

    @property
    def blueprint_hints(self) -> list[dict]:
        """返回所有L2诊断中收集到的蓝本修复建议（含已恢复的）。"""
        return self._blueprint_hints

    # ── 公共接口 ──────────────────────────────────────────

    def record_step(self, step_num: int, action: str,
                    target: Optional[str] = None, value: Optional[str] = None,
                    passed: bool = True, error: Optional[str] = None) -> None:
        """记录一步操作结果（无论成败都记）。Runner 每步执行完都要调用。"""
        self._step_history.append(StepRecord(
            step_num=step_num, action=action,
            target=target, value=value,
            passed=passed, error=error,
        ))
        # 只保留最近N步
        if len(self._step_history) > self._MAX_HISTORY:
            self._step_history = self._step_history[-self._MAX_HISTORY:]

    def on_step_passed(self) -> None:
        """步骤通过时调用（L0），重置连续失败计数。"""
        self._consecutive_failures = 0

    def on_scenario_start(self) -> None:
        """场景开始时调用，重置连续失败计数和步骤历史。"""
        self._consecutive_failures = 0
        self._step_history.clear()

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

        # ── L0.5 规则预判：不需要AI就能确定是APP Bug的场景 ──
        rule_decision = self._try_rule_judge(ctx)
        if rule_decision:
            return rule_decision

        # ── 预截图：L1/L2 共用同一张截图，避免重复截图和API调用 ──
        if ctx.screenshot_fn and not ctx._cached_screenshot:
            try:
                ctx._cached_screenshot = await ctx.screenshot_fn("failure_capture")
            except Exception as e:
                logger.debug("预截图失败（非致命）: {}", str(e)[:60])

        # ── L1 弹窗自愈（仅对可能被弹窗遮挡的操作）──
        if ctx.action in ("click", "fill", "assert_text", "assert_visible"):
            decision = await self._try_l1_popup_heal(ctx)
            if decision.popup_closed:
                self._consecutive_failures = 0  # 弹窗关闭后重置计数
                return decision

        # ── L2 失败诊断：像人一样看截图分析原因 ──
        if ctx.action in ("click", "fill", "assert_text", "assert_visible"):
            decision = await self._try_l2_diagnose(ctx)
            if decision.action != HubAction.NONE:
                return decision

        return HubDecision(action=HubAction.NONE, reason="L1/L2未能解决")

    @property
    def stats(self) -> dict:
        """返回中枢运行统计。"""
        return {
            "total_heals": self._total_heals,
            "l1_calls": self._total_l1_calls,
            "l2_calls": self._total_l2_calls,
            "rule_judgments": self._total_rule_judgments,
            "skipped_scenes": self._total_skipped_scenes,
        }

    # ── L0.5: 规则预判（零AI成本）─────────────────────────

    def _try_rule_judge(self, ctx: StepContext) -> Optional[HubDecision]:
        """L0.5：基于错误信息的规则预判，不调AI，零token消耗。

        能100%确定是APP Bug的情况：
        - assert_text：元素找到了，但文字不对 → 应用显示了错误数据
        - 计算验证失败：数值算错了 → 应用计算逻辑有Bug
        这些不需要截图也不需要AI分析，直接判定。

        不能确定的情况（交给L1/L2）：
        - 元素找不到（可能是选择器错，也可能是应用没渲染）
        - 通用异常（需要AI看截图）
        """
        err = ctx.error_message or ""

        # assert_text：找到元素但文字不对 → 100% APP Bug
        if ctx.action == "assert_text" and "文本断言失败" in err:
            self._total_rule_judgments += 1
            logger.info("  📋 AI中枢规则预判: 文本不匹配 → APP Bug（省去AI调用）")
            return HubDecision(
                action=HubAction.NONE,
                fault=FaultType.APP,
                reason=f"规则预判: {err[:120]}",
            )

        # 计算验证失败 → 100% APP Bug
        if ctx.action == "assert_text" and "计算" in err:
            self._total_rule_judgments += 1
            logger.info("  📋 AI中枢规则预判: 计算错误 → APP Bug（省去AI调用）")
            return HubDecision(
                action=HubAction.NONE,
                fault=FaultType.APP,
                reason=f"规则预判: {err[:120]}",
            )

        # fill 对 <select> 元素 → 蓝本写错了动作，自动改用 select 重试
        if ctx.action == "fill" and "Element is not an <input>" in err:
            self._total_rule_judgments += 1
            logger.info("  📋 AI中枢规则修正: fill对<select>元素 → 自动改用select重试（零AI成本）")
            return HubDecision(
                action=HubAction.RETRY,
                fault=FaultType.TEST,
                reason=f"规则修正: <select>元素不能fill，自动改用select",
                override_action="select",
            )

        return None

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
            # 1. 截图（优先复用缓存）
            screenshot_path = ctx._cached_screenshot
            if not screenshot_path:
                screenshot_path = await ctx.screenshot_fn("popup_detect")
            if not screenshot_path:
                return HubDecision(action=HubAction.NONE, reason="截图失败")

            # 2. AI 分析是否有弹窗
            prompt = (
                "看截图：主界面上方有没有弹出对话框/弹窗/提示框？\n"
                "有→找关闭按钮(确定/取消/关闭/X等)，给归一化坐标(0~1)。\n"
                '有弹窗：{"popup":true,"button":"确定","x":0.5,"y":0.7}\n'
                '没弹窗：{"popup":false}\n'
                "只返回JSON。"
            )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._ai.analyze_screenshot(
                    str(screenshot_path), prompt,
                    reasoning_effort="low", timeout=20,
                    max_tokens=300,
                )
            )

            cost_ms = (time.time() - start) * 1000
            logger.debug("AI中枢L1弹窗检测返回(前300字): {}", response[:300])

            # 3. 解析 JSON
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if not json_match:
                return HubDecision(action=HubAction.NONE, reason="AI返回无JSON", ai_cost_ms=cost_ms)

            raw_json = json_match.group()
            raw_json = raw_json.replace("\u201c", '"').replace("\u201d", '"')
            raw_json = raw_json.replace("\u2018", "'").replace("\u2019", "'")
            result = json.loads(raw_json)
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

    # ── L2: 失败诊断（像人一样分析原因）──────────────────

    def _build_history_context(self) -> str:
        """把最近的步骤历史拼成一段大白话，给 AI 当上下文。"""
        if not self._step_history:
            return ""
        lines = ["以下是你之前的操作记录："]
        for rec in self._step_history:
            lines.append(f"  {rec.describe()}")
        return "\n".join(lines)

    async def _try_l2_diagnose(self, ctx: StepContext) -> HubDecision:
        """L2：截图 + 步骤历史 → 直接发给多模态AI，让它看图分析。

        核心思路：测试卡住了 → 截图发给AI → 把前因后果告诉它 →
        让AI像一个坐在你旁边的同事一样看图说话、分析原因。
        """
        self._total_l2_calls += 1

        if not self._ai or not ctx.screenshot_fn:
            return HubDecision(action=HubAction.NONE, reason="缺少AI或截图能力")

        start = time.time()
        try:
            screenshot_path = ctx._cached_screenshot
            if not screenshot_path:
                screenshot_path = await ctx.screenshot_fn("l2_diagnose")
            if not screenshot_path:
                return HubDecision(action=HubAction.NONE, reason="截图失败")

            # 构造当前操作的描述
            action_desc = {
                "click": f"点击'{ctx.target}'",
                "fill": f"在'{ctx.target}'中输入'{ctx.value}'",
                "assert_text": f"检查'{ctx.target}'处是否有文字'{ctx.value}'",
                "assert_visible": f"检查'{ctx.target}'是否可见",
            }.get(ctx.action, f"执行{ctx.action}操作")

            # 拼接步骤历史
            history = self._build_history_context()

            prompt = f"场景「{ctx.scenario_name}」"

            # 蓝本预期流程（第1步到当前步）
            if ctx.blueprint_steps_context:
                prompt += f"\n\n【蓝本预期流程（到当前步为止）】\n{ctx.blueprint_steps_context}"

            if history:
                prompt += f"\n\n【实际执行历史（最近几步）】\n{history}"

            # Web DOM 辅助：将页面可交互元素列表注入 prompt
            if ctx.dom_context:
                prompt += f"\n【DOM元素】{ctx.dom_context}"

            is_click_action = ctx.action == "click"
            coord_hint = (
                "若fault=test且元素可见只是选择器错，给归一化坐标recover_x/recover_y(0~1)。"
            ) if is_click_action else ""

            has_blueprint_ctx = bool(ctx.blueprint_steps_context)
            flow_analysis_hint = (
                "\n【重要】对比上方蓝本预期流程与实际历史：\n"
                "  1. 找出从哪一步开始走偏（蓝本期望去A页面，实际却在B页面）\n"
                "  2. 若当前页面与蓝本预期不符，给出recover_x/recover_y（归一化0~1）和 resume_step\n"
                "  3. blueprint_fix 必须写：错在第几步 + 具体怎么改 + 修改后从第几步继续\n"
            ) if has_blueprint_ctx else ""

            prompt += (
                f"\n\n第{ctx.step_num}步（共{ctx.total_steps}步）：{action_desc} → 失败：{(ctx.error_message or '未知')[:150]}\n"
                "看截图判断失败原因。\n"
                "fault: app=应用Bug(数据错/崩溃/功能缺失) | test=脚本问题(选择器错/加载中/弹窗遮挡)\n"
                + coord_hint
                + flow_analysis_hint +
                "\nblueprint_fix（fault=test时必填，不超过200字）：\n"
                "  - 根本原因：蓝本第几步写错了什么\n"
                "  - 修复方法：把第N步的target改为'xxx' / 在第N步前插入navigate步骤\n"
                "  - 当前恢复：若需要先操作才能继续，写清楚先点哪个元素或坐标，然后从第N步继续\n"
                "\n返回JSON：\n"
                '{"diagnosis":"原因(不超过80字)","fault":"app/test/unknown",'
                '"suggestion":"retry/skip/recover/none",'
                '"blueprint_fix":"蓝本修复指令(fault=test时必填)",'
                '"resume_step":可选数字表示从第几步继续,'
                '"recover_selector":"可选CSS","recover_x":可选,"recover_y":可选}\n'
                "只返回JSON。"
            )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._ai.analyze_screenshot(
                    str(screenshot_path), prompt,
                    reasoning_effort="low", timeout=40,
                    max_tokens=500,
                )
            )

            cost_ms = (time.time() - start) * 1000
            logger.info("  🧠 AI中枢L2诊断返回(前400字): {}", response[:400])

            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if not json_match:
                return HubDecision(action=HubAction.NONE, reason="L2返回无JSON", ai_cost_ms=cost_ms)

            # 容错：去掉中文引号、修复常见JSON格式问题
            raw_json = json_match.group()
            raw_json = raw_json.replace("\u201c", '"').replace("\u201d", '"')  # 中文引号
            raw_json = raw_json.replace("\u2018", "'").replace("\u2019", "'")  # 中文单引号→英文单引号
            result = json.loads(raw_json)
            diagnosis = result.get("diagnosis", "")
            suggestion = result.get("suggestion", "none")
            fault_str = result.get("fault", "unknown")

            # 解析归因
            try:
                fault = FaultType(fault_str)
            except ValueError:
                fault = FaultType.UNKNOWN

            blueprint_fix = result.get("blueprint_fix", "")
            resume_step = result.get("resume_step")
            logger.info("  🧠 AI中枢L2诊断: {} | 归因={} | 建议={}", diagnosis, fault.value, suggestion)
            if blueprint_fix:
                logger.info("  📋 蓝本修复建议: {}", blueprint_fix[:200])

            # 收集蓝本修复建议（无论是否恢复成功，都记录给编程AI）
            if fault == FaultType.TEST and (diagnosis or blueprint_fix):
                hint = {
                    "step": ctx.step_num,
                    "action": ctx.action,
                    "target": ctx.target,
                    "diagnosis": diagnosis,
                    "fix": blueprint_fix,
                }
                if resume_step is not None:
                    hint["resume_step"] = resume_step
                self._blueprint_hints.append(hint)

            # L2坐标回退：当选择器失效但元素可见时，用AI提供的坐标直接点击
            # fill动作也支持：先点坐标切换到正确UI状态（如切换到注册Tab），再重试fill
            recover_x = result.get("recover_x")
            recover_y = result.get("recover_y")
            if (ctx.action in ("click", "fill") and fault == FaultType.TEST
                    and recover_x is not None and recover_y is not None
                    and ctx.click_fn):
                try:
                    nx, ny = float(recover_x), float(recover_y)
                    if 0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0:
                        action_label = "绕过失效选择器" if ctx.action == "click" else "切换到目标UI状态后重试fill"
                        logger.info("  🎯 AI中枢L2坐标回退: 点击({:.2f}, {:.2f}) {}", nx, ny, action_label)
                        await ctx.click_fn(nx, ny)
                        self._total_heals += 1
                        return HubDecision(
                            action=HubAction.RETRY,
                            reason=f"L2坐标回退点击({nx:.2f},{ny:.2f}): {diagnosis}",
                            fault=fault,
                            ai_cost_ms=cost_ms,
                            recover_x=nx,
                            recover_y=ny,
                        )
                except Exception as coord_err:
                    logger.warning("  L2坐标回退失败: {}", str(coord_err)[:80])

            if suggestion == "recover" and result.get("recover_selector"):
                # L2恢复：先执行恢复动作再重试（recover_selector在Runner中点击）
                recover_sel = result["recover_selector"]
                logger.info("  🔧 AI中枢L2恢复: 先点击[{}]再重试", recover_sel)
                return HubDecision(
                    action=HubAction.RETRY,
                    reason=f"L2恢复: {diagnosis}",
                    fault=fault,
                    ai_cost_ms=cost_ms,
                    recover_selector=recover_sel,
                )
            elif suggestion == "retry":
                return HubDecision(
                    action=HubAction.RETRY,
                    reason=f"L2诊断建议重试: {diagnosis}",
                    fault=fault,
                    ai_cost_ms=cost_ms,
                )
            elif suggestion == "skip":
                return HubDecision(
                    action=HubAction.SKIP_STEP,
                    reason=f"L2诊断建议跳过: {diagnosis}",
                    fault=fault,
                    ai_cost_ms=cost_ms,
                )

        except Exception as e:
            logger.warning("AI中枢L2诊断失败: {}", str(e)[:100])

        return HubDecision(action=HubAction.NONE, reason="L2诊断未给出明确建议")

    # ── 工具方法 ──────────────────────────────────────────

    @staticmethod
    def is_dialog_button(target: str) -> bool:
        """判断目标是否是弹窗按钮（各 Runner 可用来跳过缓存）。"""
        return target in DIALOG_BUTTON_KEYWORDS

    @staticmethod
    def build_blueprint_steps_context(steps: list, current_step_num: int) -> str:
        """构建蓝本预期流程摘要字符串（第1步到当前步），注入L2 prompt。

        Args:
            steps: BlueprintStep 列表（已展开 setup 的 effective_steps）
            current_step_num: 当前失败的步骤序号（1-based）

        Returns:
            多行字符串，每行一步，当前步标记为【❌当前失败步】
        """
        lines = []
        for i, step in enumerate(steps, 1):
            if i > current_step_num:
                break  # 只显示到当前步，后续步骤不给AI看
            action = step.action
            target = step.target or ""
            value = step.value or ""
            desc = step.description or ""
            if action in ("click", "fill", "select", "hover"):
                summary = f"{action} {target}" + (f" = '{value[:30]}'" if value else "")
            elif action == "navigate":
                summary = f"navigate → {value or target}"
            elif action in ("assert_text", "assert_visible"):
                summary = f"{action} '{(value or target)[:40]}'"
            else:
                summary = f"{action}" + (f" {target}" if target else "")
            if desc:
                summary += f"  ({desc[:40]})"

            marker = "  ← 【❌当前失败步】" if i == current_step_num else ""
            lines.append(f"  第{i}步: {summary}{marker}")
        return "\n".join(lines)
