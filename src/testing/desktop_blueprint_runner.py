"""
Windows 桌面蓝本执行器（v1.0）

架构：与移动端 MobileBlueprintRunner 对齐的双保险策略
  1. UI Automation 查找控件（Name/AutomationId/ClassName）→ 精确坐标
  2. 截图 + AI 视觉分析 → 归一化坐标降级

许多真实桌面应用（tkinter/Electron/C++原生等）的 UI Automation 属性很差，
因此 AI 视觉降级是桌面测试的关键能力。

典型使用：
    runner = DesktopBlueprintRunner(controller, ai_client)
    report = await runner.run(blueprint)
"""

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

from loguru import logger

from src.controller.desktop import DesktopController
from src.controller.window_manager import DesktopConfig
from src.testing.blueprint import (
    Blueprint,
    BlueprintPage,
    BlueprintStep,
)
from src.testing.models import (
    ActionType,
    BugReport,
    BugSeverity,
    StepResult,
    StepStatus,
    TestReport,
)
from src.testing.controller import TestController

try:
    from src.core.ai_client import AIClient
except ImportError:
    AIClient = None  # type: ignore

try:
    from src.testing.formula_validator import is_formula, validate_formula
except ImportError:
    def is_formula(s: str) -> bool:
        return False
    def validate_formula(formula: str, actual: str):
        return type("R", (), {"passed": True, "detail": ""})()

try:
    from src.testing.smart_value import is_auto_value, generate_smart_value
except ImportError:
    def is_auto_value(v: str) -> bool:
        return False
    def generate_smart_value(v: str) -> str:
        return v


class DesktopBlueprintRunner:
    """Windows 桌面蓝本执行器。

    双保险策略：
      1. UI Automation 精确定位（PowerShell + .NET UI Automation）
      2. AI 视觉截图降级（截图 + AI 分析元素坐标）

    支持的蓝本 action：
      navigate, click, fill, wait, screenshot, assert_text, assert_visible
    """

    ScreenshotCallback = Callable[[int, str], Coroutine[Any, Any, None]]
    StepCallback = Callable[[int, str, str], Coroutine[Any, Any, None]]

    def __init__(
        self,
        controller: DesktopController,
        ai_client: Optional[Any] = None,
        on_screenshot: Optional["DesktopBlueprintRunner.ScreenshotCallback"] = None,
        on_step: Optional["DesktopBlueprintRunner.StepCallback"] = None,
        test_controller: Optional[TestController] = None,
    ) -> None:
        self._ctrl = controller
        self._ai = ai_client
        self._on_screenshot = on_screenshot
        self._on_step = on_step
        self._test_controller = test_controller
        # 跨场景坐标缓存：界面不变时直接复用，不重复发图给AI
        self._page_hash: str = ""
        self._global_coord_cache: dict[str, tuple[int, int]] = {}
        # OCR文字缓存：相同界面的assert_text直接复用，不重复发AI
        self._ocr_hash: str = ""
        self._ocr_text_cache: str = ""
        # 弹窗自愈：记录连续失败步数，用于场景级跳过（第3层防御）
        self._consecutive_failures: int = 0
        self._MAX_CONSECUTIVE_FAILURES: int = 3

    # ── 主入口 ────────────────────────────────────────────

    async def run(self, blueprint: Blueprint) -> TestReport:
        """执行蓝本中的所有场景。"""
        report = TestReport(
            test_name=f"桌面蓝本测试-{blueprint.app_name}",
            url=blueprint.base_url,
        )

        all_results: list[StepResult] = []
        all_bugs: list[BugReport] = []
        step_num = 0

        logger.info("════════════════════════════════════════════")
        logger.info("桌面蓝本测试开始 | {} | 场景={} | 步骤={}",
                    blueprint.app_name,
                    blueprint.total_scenarios,
                    blueprint.total_steps)

        if self._test_controller:
            self._test_controller.start(total_steps=blueprint.total_steps)

        # 连接目标窗口
        try:
            await self._ctrl.connect()
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error("连接目标窗口失败: {}", e)
            report.bugs = [BugReport(
                severity=BugSeverity.HIGH,
                category="启动失败",
                title="无法连接目标窗口",
                description=str(e),
            )]
            return report

        cancelled = False
        for page_idx, page in enumerate(blueprint.pages):
            if cancelled:
                break
            if page.url:
                logger.info("── 页面 {}/{}: {} ──", page_idx + 1, len(blueprint.pages), page.url)
                try:
                    await self._ctrl.navigate(page.url)
                    await asyncio.sleep(1)
                except Exception as nav_err:
                    logger.error("页面导航失败: {} | {}", page.url, nav_err)

            for scenario_idx, scenario in enumerate(page.scenarios):
                if cancelled:
                    break
                logger.info("── 场景: {} ──", scenario.name)
                # 场景切换时重置连续失败计数
                self._consecutive_failures = 0

                # 场景间等待UI稳定（第一个场景除外），防止Logout后截图时机太快
                if scenario_idx > 0:
                    await asyncio.sleep(1.5)

                # 场景开始前预分析页面元素坐标（双保险）
                scene_coords = await self._analyze_page_elements(scenario)

                for step_def in scenario.steps:
                    step_num += 1
                    desc = step_def.description or step_def.action

                    if self._test_controller and self._test_controller.is_cancelled:
                        logger.info("测试被用户停止 | 步骤={}/{}", step_num, blueprint.total_steps)
                        cancelled = True
                        break

                    if self._test_controller:
                        self._test_controller.update_progress(step_num, desc)
                        await self._test_controller.wait_if_paused()

                    self._ctrl._step_counter = step_num - 1

                    if self._on_step:
                        await self._on_step(step_num, "start", desc)

                    result, bug = await self._execute_step(
                        step_num, step_def, page, blueprint, scene_coords
                    )

                    # ── 弹窗自愈：步骤失败时尝试检测并关闭弹窗后重试 ──
                    if bug and step_def.action in ("click", "fill", "assert_text", "assert_visible"):
                        healed = await self._try_heal_popup()
                        if healed:
                            logger.info("  🔄 弹窗已关闭，重试步骤{}", step_num)
                            result, bug = await self._execute_step(
                                step_num, step_def, page, blueprint, scene_coords
                            )
                            if not bug:
                                logger.info("  ✅ 弹窗自愈成功，步骤{}重试通过", step_num)

                    # 更新连续失败计数
                    if bug:
                        self._consecutive_failures += 1
                    else:
                        self._consecutive_failures = 0

                    # ── 第3层防御：连续失败过多则跳过当前场景 ──
                    if self._consecutive_failures >= self._MAX_CONSECUTIVE_FAILURES:
                        logger.warning("  ⚠️ 场景[{}]连续失败{}步，跳到下一场景",
                                       scenario.name, self._consecutive_failures)
                        # 把剩余步骤标记为SKIPPED
                        remaining_idx = scenario.steps.index(step_def) + 1
                        for skip_step in scenario.steps[remaining_idx:]:
                            step_num += 1
                            skip_desc = skip_step.description or skip_step.action
                            try:
                                skip_action = ActionType(skip_step.action)
                            except ValueError:
                                skip_action = ActionType.SCREENSHOT
                            all_results.append(StepResult(
                                step=step_num, action=skip_action,
                                description=f"[跳过-场景blocked] {skip_desc}",
                                status=StepStatus.FAILED, duration_seconds=0,
                                error_message=f"场景'{scenario.name}'连续失败{self._MAX_CONSECUTIVE_FAILURES}步，已跳过",
                            ))
                        all_results.append(result)
                        if bug:
                            all_bugs.append(bug)
                        break

                    all_results.append(result)

                    # navigate后清空预分析坐标
                    if step_def.action == "navigate" and not scene_coords:
                        remaining_steps = scenario.steps[scenario.steps.index(step_def)+1:]
                        if any(s.action in ("click", "fill") for s in remaining_steps):
                            from types import SimpleNamespace
                            fake_scenario = SimpleNamespace(steps=remaining_steps, name=scenario.name)
                            scene_coords.update(await self._analyze_page_elements(fake_scenario))

                    if bug:
                        all_bugs.append(bug)

                    if self._on_step:
                        await self._on_step(step_num, result.status.value, desc)

        # 汇总
        report.step_results = all_results
        report.bugs = all_bugs
        report.total_steps = len(all_results)
        report.passed_steps = sum(1 for r in all_results if r.status == StepStatus.PASSED)
        report.failed_steps = sum(1 for r in all_results if r.status == StepStatus.FAILED)
        report.error_steps = sum(1 for r in all_results if r.status == StepStatus.ERROR)
        report.end_time = datetime.now(timezone.utc)
        report.report_markdown = self._generate_markdown(blueprint, report, all_results, all_bugs)

        if self._test_controller:
            self._test_controller.on_test_complete()

        logger.info("桌面蓝本测试完成 | 通过={}/{} | Bug={}",
                    report.passed_steps, report.total_steps, len(all_bugs))
        return report

    # ── 步骤执行 ──────────────────────────────────────────

    async def _execute_step(
        self,
        step_num: int,
        step_def: BlueprintStep,
        page: BlueprintPage,
        blueprint: Blueprint,
        scene_coords: dict[str, tuple[int, int]] | None = None,
    ) -> tuple[StepResult, Optional[BugReport]]:
        """执行单个蓝本步骤。"""
        desc = step_def.description or f"{step_def.action} {step_def.target or step_def.value or ''}"
        logger.info("  [步骤{}/{}] {} | {}", step_num, blueprint.total_steps, step_def.action, desc)

        start = time.time()
        screenshot_path: Optional[Path] = None

        try:
            action_type = ActionType(step_def.action)
        except ValueError:
            action_type = ActionType.SCREENSHOT

        try:
            target = step_def.target
            raw_value = step_def.value or ""
            value = generate_smart_value(raw_value) if is_auto_value(raw_value) else raw_value

            if step_def.action == "navigate":
                url = value or page.url or blueprint.base_url
                await self._ctrl.navigate(url)
                await asyncio.sleep(1)
                self._invalidate_coord_cache()
                if scene_coords is not None:
                    scene_coords.clear()

            elif step_def.action == "click":
                await self._smart_tap(target, desc, scene_coords)
                # 点击后界面可能变化，清空OCR缓存
                self._ocr_hash = ""
                self._ocr_text_cache = ""

            elif step_def.action == "fill":
                await self._smart_fill(target, value, desc, scene_coords)
                # 输入后界面可能变化，清空OCR缓存
                self._ocr_hash = ""
                self._ocr_text_cache = ""

            elif step_def.action == "wait":
                if target:
                    timeout_ms = step_def.timeout_ms or 5000
                    await self._ctrl.wait_for_element(target, timeout_ms=timeout_ms)
                else:
                    ms = int(value) if value and value.isdigit() else (step_def.timeout_ms or 1000)
                    await asyncio.sleep(ms / 1000)

            elif step_def.action == "assert_text":
                expected = step_def.expected or value or ""
                text = await self._get_text(target) or ""
                if is_formula(expected):
                    formula_result = validate_formula(expected, text)
                    if not formula_result.passed:
                        elapsed = time.time() - start
                        bug = BugReport(
                            severity=BugSeverity.HIGH,
                            category="计算验证失败",
                            title=f"数值计算错误: {target}",
                            description=formula_result.detail,
                            location=target or "",
                            step_number=step_num,
                        )
                        return StepResult(
                            step=step_num, action=action_type, description=desc,
                            status=StepStatus.FAILED, duration_seconds=elapsed,
                            error_message=formula_result.detail,
                        ), bug
                elif expected and expected not in text:
                    elapsed = time.time() - start
                    bug = BugReport(
                        severity=BugSeverity.HIGH,
                        category="文本断言失败",
                        title=f"元素文本不匹配: {target}",
                        description=f"预期包含'{expected}'，实际为'{text}'",
                        location=target or "",
                        step_number=step_num,
                    )
                    return StepResult(
                        step=step_num, action=action_type, description=desc,
                        status=StepStatus.FAILED, duration_seconds=elapsed,
                        error_message=f"文本断言失败: 预期'{expected}'，实际'{text}'",
                    ), bug

            elif step_def.action == "assert_visible":
                # 尝试UI Automation查找元素
                elem = await self._ctrl._find_element_uia(target)
                if not elem:
                    # UI Automation找不到，尝试AI视觉
                    if self._ai:
                        coord = await self._visual_find_element(target, desc)
                        if not coord:
                            elapsed = time.time() - start
                            bug = BugReport(
                                severity=BugSeverity.HIGH,
                                category="可见性断言失败",
                                title=f"元素不可见: {target}",
                                description=f"元素 '{target}' 在页面上不可见（UI Automation和AI视觉均未找到）",
                                location=target or "",
                                step_number=step_num,
                            )
                            return StepResult(
                                step=step_num, action=action_type, description=desc,
                                status=StepStatus.FAILED, duration_seconds=elapsed,
                                error_message=f"元素不可见: {target}",
                            ), bug
                    else:
                        elapsed = time.time() - start
                        bug = BugReport(
                            severity=BugSeverity.HIGH,
                            category="可见性断言失败",
                            title=f"元素不可见: {target}",
                            description=f"元素 '{target}' 未找到（UI Automation未匹配）",
                            location=target or "",
                            step_number=step_num,
                        )
                        return StepResult(
                            step=step_num, action=action_type, description=desc,
                            status=StepStatus.FAILED, duration_seconds=elapsed,
                            error_message=f"元素不可见: {target}",
                        ), bug

            need_screenshot = (step_def.action == "screenshot") or (step_def.expected and self._ai)
            if need_screenshot:
                screenshot_path = await self._ctrl.screenshot(f"step{step_num:03d}_{step_def.action}")

        except Exception as exc:
            elapsed = time.time() - start
            logger.warning("  步骤{}执行失败: {}", step_num, str(exc)[:120])
            bug = BugReport(
                severity=BugSeverity.HIGH,
                category="步骤执行错误",
                title=f"步骤{step_num}执行失败: {desc}",
                description=str(exc),
                location=step_def.target or step_def.value or "",
                step_number=step_num,
            )
            return StepResult(
                step=step_num, action=action_type, description=desc,
                status=StepStatus.ERROR, duration_seconds=elapsed,
                error_message=str(exc),
            ), bug

        elapsed = time.time() - start
        return StepResult(
            step=step_num, action=action_type, description=desc,
            status=StepStatus.PASSED, duration_seconds=elapsed,
            screenshot_path=str(screenshot_path) if screenshot_path else None,
        ), None

    # ── 弹窗自愈（第2层防御） ─────────────────────────────

    async def _try_heal_popup(self) -> bool:
        """尝试检测并关闭意外弹窗。返回True表示成功关闭了弹窗。"""
        if not self._ai:
            return False

        try:
            screenshot_path = await self._ctrl.screenshot("popup_detect")
            win_rect = self._ctrl._device.extra.get("window_rect") or {}
            win_w = win_rect.get("width") or self._ctrl._device.screen_width or 800
            win_h = win_rect.get("height") or self._ctrl._device.screen_height or 600
            win_left = win_rect.get("left", 0)
            win_top = win_rect.get("top", 0)

            prompt = (
                "这是一个Windows桌面应用的截图。请判断截图中是否有模态弹窗/对话框覆盖在主界面上方。\n"
                "如果有弹窗，请找到关闭按钮（如OK、Cancel、Close、Yes、No、确定、取消、X按钮）的中心坐标。\n"
                "坐标为归一化值(0~1)，(0,0)是截图左上角。\n\n"
                "返回JSON格式：\n"
                '- 有弹窗：{"popup": true, "button": "OK", "x": 0.5, "y": 0.7}\n'
                '- 无弹窗：{"popup": false}'
            )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._ai.analyze_screenshot(
                    str(screenshot_path), prompt, reasoning_effort="low", timeout=20
                )
            )

            logger.debug("弹窗检测AI返回(前300字): {}", response[:300])
            json_match = re.search(r"\{.*?\}", response, re.DOTALL)
            if not json_match:
                return False

            result = json.loads(json_match.group().replace("'", '"'))
            if not result.get("popup"):
                return False

            nx = self._normalize_coord(result.get("x"), win_w)
            ny = self._normalize_coord(result.get("y"), win_h)
            if nx is not None and ny is not None:
                abs_x = int(win_left + nx * win_w)
                abs_y = int(win_top + ny * win_h)
                btn_name = result.get("button", "unknown")
                logger.info("  🔧 弹窗自愈：检测到弹窗，点击[{}]按钮 ({}, {})", btn_name, abs_x, abs_y)
                await self._ctrl._click_at(abs_x, abs_y)
                await asyncio.sleep(0.5)
                # 清空缓存，弹窗关闭后界面状态变化
                self._ocr_hash = ""
                self._ocr_text_cache = ""
                self._invalidate_coord_cache()
                return True

        except Exception as e:
            logger.warning("弹窗自愈检测失败: {}", str(e)[:100])

        return False

    # ── 智能操作（双保险） ──────────────────────────────────

    # 弹窗按钮关键词：这些按钮通常出现在动态弹窗上，不能使用预分析缓存
    _DIALOG_BUTTONS = {"name:OK", "name:Ok", "name:ok", "name:Yes", "name:No",
                       "name:Cancel", "name:Close", "name:确定", "name:取消",
                       "name:是", "name:否", "name:关闭"}

    async def _smart_tap(
        self,
        target: str,
        description: str,
        scene_coords: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        """智能点击：UI Automation优先 → 预分析坐标 → AI视觉降级。"""
        # 弹窗按钮跳过预分析缓存，强制实时定位（弹窗是动态出现的，旧坐标无效）
        is_dialog_btn = target in self._DIALOG_BUTTONS

        # 第1层：预分析坐标（场景开始时已缓存）—— 弹窗按钮跳过
        if not is_dialog_btn and scene_coords and target in scene_coords:
            x, y = scene_coords[target]
            logger.debug("  使用预分析坐标点击: ({}, {})", x, y)
            await self._ctrl._click_at(x, y)
            await asyncio.sleep(0.3)
            return

        # 第2层：UI Automation精确定位
        try:
            await self._ctrl.tap(target)
            await asyncio.sleep(0.3)
            return
        except Exception as e:
            err = str(e).lower()
            if "元素未找到" in err or "未找到" in err or "not found" in err:
                logger.debug("  UI Automation未找到 '{}', 尝试AI视觉降级", target)
            else:
                raise

        # 第3层：AI视觉降级
        if self._ai:
            coord = await self._visual_find_element(target, description)
            if coord:
                x, y = coord
                logger.info("  AI视觉定位成功: '{}' → ({}, {})", target, x, y)
                await self._ctrl._click_at(x, y)
                await asyncio.sleep(0.3)
                return

        raise RuntimeError(f"元素未找到（UI Automation + AI视觉均失败）: {target}")

    async def _smart_fill(
        self,
        target: str,
        value: str,
        description: str,
        scene_coords: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        """智能输入：先定位元素，再输入文本。"""
        # 第1层：预分析坐标
        if scene_coords and target in scene_coords:
            x, y = scene_coords[target]
            logger.debug("  使用预分析坐标输入: ({}, {})", x, y)
            await self._ctrl._click_at(x, y)
            await asyncio.sleep(0.3)
            await self._select_all_delete()
            await self._ctrl._send_text_bg(value)
            await asyncio.sleep(0.2)
            return

        # 第2层：UI Automation精确定位
        try:
            await self._ctrl.input_text(target, value)
            await asyncio.sleep(0.3)
            return
        except Exception as e:
            err = str(e).lower()
            if "元素未找到" in err or "未找到" in err or "not found" in err:
                logger.debug("  UI Automation未找到输入框 '{}', 尝试AI视觉降级", target)
            else:
                raise

        # 第3层：AI视觉降级
        if self._ai:
            coord = await self._visual_find_element(target, description)
            if coord:
                x, y = coord
                logger.info("  AI视觉定位输入框: '{}' → ({}, {})", target, x, y)
                await self._ctrl._click_at(x, y)
                await asyncio.sleep(0.3)
                await self._select_all_delete()
                await self._ctrl._send_text_bg(value)
                await asyncio.sleep(0.2)
                return

        raise RuntimeError(f"输入框未找到（UI Automation + AI视觉均失败）: {target}")

    async def _select_all_delete(self) -> None:
        """Ctrl+A 全选 + Backspace 清空输入框。

        优先用 pywinauto.type_keys（对tkinter最稳定），
        fallback 到 SendInput。
        """
        loop = asyncio.get_event_loop()
        pwa_win = getattr(self._ctrl, '_pwa_win', None)

        if pwa_win is not None:
            # pywinauto: Ctrl+A 然后 Backspace
            await loop.run_in_executor(
                None, lambda: pwa_win.type_keys('^a{BACKSPACE}')
            )
        else:
            from src.controller.desktop import (
                WM_KEYDOWN, WM_KEYUP, VK_BACK, user32,
            )
            hwnd = self._ctrl._hwnd
            if not hwnd:
                return
            def _do():
                import time as _time
                VK_CONTROL = 0x11
                VK_A = 0x41
                user32.PostMessageW(hwnd, WM_KEYDOWN, VK_CONTROL, 0)
                _time.sleep(0.02)
                user32.PostMessageW(hwnd, WM_KEYDOWN, VK_A, 0)
                _time.sleep(0.02)
                user32.PostMessageW(hwnd, WM_KEYUP, VK_A, 0)
                _time.sleep(0.02)
                user32.PostMessageW(hwnd, WM_KEYUP, VK_CONTROL, 0)
                _time.sleep(0.05)
                user32.PostMessageW(hwnd, WM_KEYDOWN, VK_BACK, 0)
                _time.sleep(0.02)
                user32.PostMessageW(hwnd, WM_KEYUP, VK_BACK, 0)
            await loop.run_in_executor(None, _do)
        await asyncio.sleep(0.1)

    # ── 页面分析（双保险预加载） ──────────────────────────

    async def _analyze_page_elements(self, scenario) -> dict[str, tuple[int, int]]:
        """场景开始前分析页面，预拿所有需要操作的元素坐标。

        双保险：
          1. UI Automation 查找 → 精确坐标
          2. AI 视觉截图分析 → 归一化坐标降级
        """
        targets = []
        for step in scenario.steps:
            if step.action in ("click", "fill") and step.target:
                desc = step.description or step.action
                targets.append({"target": step.target, "description": desc})

        if not targets:
            return {}

        coords: dict[str, tuple[int, int]] = {}

        # ── 第1层：UI Automation精确匹配 ──
        for t in targets:
            try:
                elem = await self._ctrl._find_element_uia(t["target"])
                if elem and "center_x" in elem and "center_y" in elem:
                    coords[t["target"]] = (elem["center_x"], elem["center_y"])
            except Exception:
                pass

        ui_matched = len(coords)

        # ── 第2层：AI视觉分析（补充UI Automation未匹配的） ──
        if self._ai and targets:
            unmatched = [t for t in targets if t["target"] not in coords]
            if unmatched:
                logger.info("  AI预加载分析 {} 个元素（UI Automation未匹配）", len(unmatched))
                ai_coords = await self._ai_analyze_elements(unmatched)
                for k, v in ai_coords.items():
                    if k not in coords:
                        coords[k] = v
                ai_hit = len([t for t in unmatched if t["target"] in coords])
            else:
                ai_hit = 0
            logger.info("  页面预分析完成 | UIA={} + AI={} / 总共{}",
                         ui_matched, ai_hit, len(targets))
        else:
            logger.info("  页面预分析完成(UIA) | 匹配 {}/{} 个元素", ui_matched, len(targets))

        return coords

    @staticmethod
    def _normalize_coord(val, dimension: int) -> Optional[float]:
        """将AI返回的坐标值归一化到0~1范围。

        兼容多种格式：
          - 标准归一化: 0.5 → 0.5
          - 绝对像素: 219 → 219/dimension
          - 字符串分数: "219/889" → eval → 0.246
        """
        if val is None:
            return None
        # 字符串分数如 "219/889"
        if isinstance(val, str) and "/" in val:
            try:
                parts = val.split("/")
                val = float(parts[0]) / float(parts[1])
            except (ValueError, ZeroDivisionError):
                return None
        try:
            val = float(val)
        except (TypeError, ValueError):
            return None
        # 已经是归一化值
        if 0 <= val <= 1:
            return val
        # 绝对像素值：转归一化
        if dimension > 0 and 1 < val <= dimension * 1.5:
            return val / dimension
        return None

    def _screenshot_hash(self, screenshot_path) -> str:
        """计算截图文件的MD5 hash，用于判断界面是否变化。"""
        try:
            data = Path(screenshot_path).read_bytes()
            return hashlib.md5(data).hexdigest()
        except Exception:
            return ""

    def _invalidate_coord_cache(self):
        """界面发生变化时清空坐标缓存（如navigate/logout后）。"""
        self._page_hash = ""
        self._global_coord_cache.clear()
        logger.debug("坐标缓存已清空（界面变化）")

    async def _ai_analyze_elements(
        self,
        targets: list[dict],
    ) -> dict[str, tuple[int, int]]:
        """截图 + AI 分析元素坐标（归一化坐标 → 屏幕坐标）。

        跨场景缓存策略：
          - 截图hash不变 → 界面未变，直接从全局缓存取坐标，跳过AI调用
          - 截图hash变了 → 界面已变，清缓存，重新AI分析，结果写入缓存
          - 仅分析缓存中没有的新元素（增量分析）
        """
        coords: dict[str, tuple[int, int]] = {}
        try:
            screenshot_path = await self._ctrl.screenshot("ai_analyze")
            current_hash = self._screenshot_hash(screenshot_path)

            rect = self._ctrl._device.extra.get("window_rect") or {}
            win_w = rect.get("width") or self._ctrl._device.screen_width or 800
            win_h = rect.get("height") or self._ctrl._device.screen_height or 600

            # ── 检查界面是否变化 ─────────────────────────
            if current_hash and current_hash == self._page_hash:
                # 界面未变：从全局缓存取已有坐标
                cached_hit = 0
                for t in targets:
                    key = t["target"]
                    if key in self._global_coord_cache:
                        coords[key] = self._global_coord_cache[key]
                        cached_hit += 1

                if cached_hit == len(targets):
                    logger.info("  坐标缓存命中 {}/{} 元素（界面未变，跳过AI）", cached_hit, len(targets))
                    return coords

                # 有新元素不在缓存里，只分析未命中的部分（增量）
                uncached = [t for t in targets if t["target"] not in coords]
                logger.info("  坐标缓存命中 {}/{}，增量分析 {} 个新元素",
                            cached_hit, len(targets), len(uncached))
            else:
                # 界面变了：清旧缓存，分析全部元素
                if current_hash != self._page_hash:
                    self._global_coord_cache.clear()
                    self._page_hash = current_hash
                    logger.debug("界面已变（hash不同），清空坐标缓存")
                uncached = targets

            # ── AI分析未缓存的元素 ───────────────────────
            if not uncached:
                return coords

            descriptions = []
            for i, t in enumerate(uncached):
                descriptions.append(f"{i+1}. target='{t['target']}' description='{t['description']}'")

            prompt = (
                f"这是一个Windows桌面应用的截图（纯内容区，不含标题栏）。请精确定位以下UI元素的中心点位置。\n"
                f"坐标为归一化值（0~1），其中(0,0)是截图左上角，(1,1)是右下角。\n"
                f"返回元素中心点坐标。\n"
                f"只返回JSON数组，不要解释。格式：[{{\"target\": \"...\", \"x\": 0.5, \"y\": 0.3}}]\n\n"
                f"要定位的元素：\n" + "\n".join(descriptions)
            )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._ai.analyze_screenshot(
                    str(screenshot_path), prompt, reasoning_effort="low", timeout=30
                )
            )

            # 解析AI返回的坐标（兼容单引号JSON）
            logger.debug("AI预分析原始返回(前500字): {}", response[:500])
            raw_json = response
            json_match = re.search(r"\[.*\]", raw_json, re.DOTALL)
            if json_match:
                json_str = json_match.group().replace("'", '"')
                try:
                    items = json.loads(json_str)
                except json.JSONDecodeError:
                    items = []
                # 获取窗口在屏幕上的位置
                win_rect = self._ctrl._device.extra.get("window_rect") or {}
                win_left = win_rect.get("left", 0)
                win_top = win_rect.get("top", 0)

                # 构建 target 名称映射（去掉 name: 前缀匹配）
                target_names = {t["target"]: t["target"] for t in uncached}
                for t in uncached:
                    bare = t["target"]
                    if bare.startswith("name:"):
                        target_names[bare[5:]] = bare

                for item in items:
                    t_name = item.get("target", "")
                    matched_key = target_names.get(t_name) or target_names.get(f"name:{t_name}")
                    if not matched_key:
                        continue
                    nx = item.get("x")
                    ny = item.get("y")
                    if nx is None or ny is None:
                        continue
                    try:
                        nx, ny = float(nx), float(ny)
                    except (TypeError, ValueError):
                        continue
                    # 坐标容错：支持分数(219/889)、绝对像素(869)、标准归一化(0.5)
                    nx = self._normalize_coord(nx, win_w)
                    ny = self._normalize_coord(ny, win_h)
                    if nx is not None and ny is not None:
                        abs_x = int(win_left + nx * win_w)
                        abs_y = int(win_top + ny * win_h)
                        coords[matched_key] = (abs_x, abs_y)
                        # 写入全局缓存供后续场景复用
                        self._global_coord_cache[matched_key] = (abs_x, abs_y)

        except Exception as e:
            logger.warning("AI视觉分析失败: {}", str(e)[:100])

        return coords

    async def _visual_find_element(
        self,
        target: str,
        description: str,
    ) -> Optional[tuple[int, int]]:
        """实时截图 + AI定位单个元素。"""
        if not self._ai:
            return None

        try:
            screenshot_path = await self._ctrl.screenshot("visual_find")
            win_rect = self._ctrl._device.extra.get("window_rect") or {}
            win_w = win_rect.get("width") or self._ctrl._device.screen_width or 800
            win_h = win_rect.get("height") or self._ctrl._device.screen_height or 600
            win_left = win_rect.get("left", 0)
            win_top = win_rect.get("top", 0)

            prompt = (
                f"这是一个Windows桌面应用的截图（纯内容区，不含标题栏）。请精确定位这个UI元素的中心点。\n"
                f"target='{target}' description='{description}'\n\n"
                f"坐标为归一化值(0~1)，(0,0)是截图左上角。\n"
                f"只返回JSON，格式：{{\"x\": 0.5, \"y\": 0.3}}"
            )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._ai.analyze_screenshot(
                    str(screenshot_path), prompt, reasoning_effort="low", timeout=30
                )
            )

            logger.debug("AI单元素定位原始返回(前500字): {}", response[:500])
            json_match = re.search(r"\{.*?\}", response, re.DOTALL)
            if json_match:
                json_str = json_match.group().replace("'", '"')
                logger.debug("解析JSON: {}", json_str[:200])
                try:
                    item = json.loads(json_str)
                except json.JSONDecodeError as je:
                    logger.warning("JSON解析失败: {} | 原文: {}", je, json_str[:200])
                    item = {}
                nx = item.get("x")
                ny = item.get("y")
                # 坐标容错：支持分数(219/889)、绝对像素(869)、标准归一化(0.5)
                nx = self._normalize_coord(nx, win_w)
                ny = self._normalize_coord(ny, win_h)
                if nx is not None and ny is not None:
                    abs_x = int(win_left + nx * win_w)
                    abs_y = int(win_top + ny * win_h)
                    return (abs_x, abs_y)

        except Exception as e:
            logger.warning("AI视觉定位失败: {}", str(e)[:100])

        return None

    # ── 文本获取 ──────────────────────────────────────────

    async def _get_text(self, selector: str) -> str:
        """获取元素文本：AI视觉OCR优先（最全面），UI Automation作为补充。

        桌面应用的 UI Automation 文本通常不完整（只有控件Name属性），
        而 AI OCR 能识别所有可见文字（包括列表内容、统计信息等），
        所以优先使用 AI OCR，仅在 AI 不可用时降级到 UI Automation。
        """
        # 1. AI视觉OCR（最全面，能识别所有可见文字）
        if self._ai:
            try:
                screenshot_path = await self._ctrl.screenshot("assert_ocr")
                current_hash = self._screenshot_hash(screenshot_path)
                # 同一界面的OCR直接复用缓存，不重复发AI
                if current_hash and current_hash == self._ocr_hash and self._ocr_text_cache:
                    logger.debug("OCR缓存命中（界面未变，跳过AI）")
                    return self._ocr_text_cache
                loop = asyncio.get_event_loop()
                prompt = (
                    "List ALL visible text in this screenshot, line by line. "
                    "Include every button label, list item, input placeholder, status bar text, and title. "
                    "Output ONLY the raw text, no explanation."
                )
                ocr_text = await loop.run_in_executor(
                    None, lambda: self._ai.analyze_screenshot(
                        str(screenshot_path), prompt, reasoning_effort="low", timeout=30, max_tokens=2048
                    )
                )
                if ocr_text:
                    logger.debug("AI OCR文本: {}", ocr_text[:300])
                    self._ocr_hash = current_hash
                    self._ocr_text_cache = ocr_text
                    return ocr_text
            except Exception as e:
                logger.warning("AI OCR失败: {}", e)

        # 2. AI不可用或失败时，降级到UI Automation
        if selector:
            try:
                text = await self._ctrl.get_text(selector)
                if text:
                    return text
            except Exception:
                pass
        ui_text = await self._ctrl.get_visible_text()
        return ui_text or ""

    # ── 报告生成 ──────────────────────────────────────────

    def _generate_markdown(
        self,
        blueprint: Blueprint,
        report: TestReport,
        results: list[StepResult],
        bugs: list[BugReport],
    ) -> str:
        """生成Markdown格式测试报告。"""
        lines = [
            f"# TestPilot 桌面应用测试报告",
            f"",
            f"**应用**: {blueprint.app_name}",
            f"**平台**: Windows Desktop",
            f"**通过率**: {report.passed_steps}/{report.total_steps} "
            f"({report.passed_steps / report.total_steps * 100:.0f}%)" if report.total_steps > 0 else "",
            f"**耗时**: {report.duration_seconds:.1f}秒",
            f"",
        ]

        if bugs:
            lines.append("## 发现的Bug")
            lines.append("")
            for i, bug in enumerate(bugs, 1):
                severity_tag = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                    bug.severity.value if hasattr(bug.severity, 'value') else str(bug.severity), "⚪"
                )
                lines.append(f"{i}. {severity_tag} **[{bug.category}]** {bug.title}")
                lines.append(f"   {bug.description}")
                lines.append("")

        lines.append("## 步骤详情")
        lines.append("")
        for r in results:
            icon = {"passed": "✅", "failed": "❌", "error": "⚠️"}.get(r.status.value, "")
            lines.append(f"- {icon} 步骤{r.step}: {r.description} ({r.duration_seconds:.1f}s)")
            if r.error_message:
                lines.append(f"  - 错误: {r.error_message}")

        return "\n".join(lines)
