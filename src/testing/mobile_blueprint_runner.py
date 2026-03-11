"""
手机蓝本模式执行器（v5.0-E）

在真实 Android 设备上按 testpilot.json 蓝本执行测试：
- 通过 Appium + WebView 上下文在手机浏览器中操作 CSS 元素
- 按需截图（蓝本写了screenshot或有expected时才截图）
- 生成与 Web 测试格式完全一致的测试报告
- 收集 adb logcat + 浏览器 JS 日志注入到 Bug 报告
"""

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Coroutine, Any, Optional

from loguru import logger

from src.controller.android import AndroidController
from src.core.ai_client import AIClient
from src.testing.blueprint import Blueprint, BlueprintPage, BlueprintStep
from src.testing.controller import TestController
from src.testing.models import (
    ActionType,
    BugReport,
    BugSeverity,
    StepResult,
    StepStatus,
    TestReport,
)
from src.testing.formula_validator import is_formula, validate_formula
from src.testing.smart_input import generate_smart_value, is_auto_value


class MobileBlueprintRunner:
    """手机蓝本模式执行器。

    使用 AndroidController + Appium WebView 上下文在真实手机浏览器中
    按蓝本精确执行测试步骤，行为与桌面 BlueprintRunner 保持一致。

    典型使用：
        runner = MobileBlueprintRunner(android_ctrl, ai_client)
        report = await runner.run(blueprint)
    """

    ScreenshotCallback = Callable[[int, str], Coroutine[Any, Any, None]]
    StepCallback = Callable[[int, str, str], Coroutine[Any, Any, None]]

    def __init__(
        self,
        controller: AndroidController,
        ai_client: Optional[AIClient] = None,
        on_screenshot: Optional["MobileBlueprintRunner.ScreenshotCallback"] = None,
        on_step: Optional["MobileBlueprintRunner.StepCallback"] = None,
        test_controller: Optional[TestController] = None,
    ) -> None:
        self._ctrl = controller
        self._ai = ai_client
        self._on_screenshot = on_screenshot
        self._on_step = on_step
        self._test_controller = test_controller

    # ── 主入口 ────────────────────────────────────────────

    async def run(self, blueprint: Blueprint) -> TestReport:
        """执行蓝本中的所有场景。

        Returns:
            TestReport：与 Web 端格式一致的测试报告
        """
        report = TestReport(
            test_name=f"手机蓝本测试-{blueprint.app_name}",
            url=blueprint.base_url,
        )

        all_results: list[StepResult] = []
        all_bugs: list[BugReport] = []
        step_num = 0

        logger.info("════════════════════════════════════════════")
        logger.info("手机蓝本测试开始 | {} | 场景={} | 步骤={}",
                    blueprint.app_name,
                    blueprint.total_scenarios,
                    blueprint.total_steps)

        # 启动 test_controller（使 stop/pause 按钮生效）
        if self._test_controller:
            self._test_controller.start(total_steps=blueprint.total_steps)

        # 先停掉弹窗dismisser（避免与后续launch/测试步骤抢占U2）
        if hasattr(self._ctrl, '_dialog_dismisser') and self._ctrl._dialog_dismisser:
            self._ctrl._dialog_dismisser.stop()
            self._ctrl._dialog_dismisser = None

        # 关键：用蓝本的 appPackage/appActivity 重建 Appium Session
        # 握手创建的 Session 不传 appPackage，Appium 无法 instrument Flutter APP，
        # 导致 XPath 看不到 @hint 等属性，所有元素查找都 404。
        # 必须用 launch()（内含 force-stop + 带 appPackage 的 Session 创建）
        # 来确保 Appium 正确绑定到被测 APP。
        if blueprint.app_package:
            logger.info("蓝本指定了 appPackage={}, 重建 Appium Session...", blueprint.app_package)
            # 临时禁用 auto_dismiss，防止 launch() 重启 dismisser
            old_auto_dismiss = self._ctrl._auto_dismiss
            self._ctrl._auto_dismiss = False
            self._ctrl._config.app_package = blueprint.app_package
            self._ctrl._config.app_activity = blueprint.app_activity or ".MainActivity"
            try:
                await self._ctrl.launch()
                await asyncio.sleep(3)  # 等待 Flutter 渲染完成
            except Exception as e:
                logger.error("重建 Appium Session 失败: {}", e)
                # 兜底：至少 adb 拉起 APP
                import subprocess
                component = f"{blueprint.app_package}/{self._ctrl._config.app_activity}"
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None, lambda: subprocess.run(
                            ["adb", "shell", "am", "start", "-n", component],
                            capture_output=True, timeout=10,
                        )
                    )
                    await asyncio.sleep(3)
                except Exception:
                    pass
            finally:
                self._ctrl._auto_dismiss = old_auto_dismiss

        # 确保 launch() 后 dismisser 也已停止（launch 内部可能重启了它）
        if hasattr(self._ctrl, '_dialog_dismisser') and self._ctrl._dialog_dismisser:
            self._ctrl._dialog_dismisser.stop()
            self._ctrl._dialog_dismisser = None

        # 将取消信号注入AndroidController，使 _find_element_with_wait 能及时中断
        if self._test_controller:
            self._ctrl._is_cancelled_fn = lambda: self._test_controller.is_cancelled

        cancelled = False
        for page_idx, page in enumerate(blueprint.pages):
            if cancelled:
                break
            if page.url:
                logger.info("── 页面 {}/{}: {} ──", page_idx + 1, len(blueprint.pages), page.url)
                try:
                    if page.url.startswith("http"):
                        # H5 混合模式：导航到 URL，切换 WebView 上下文
                        await self._ctrl.navigate(page.url)
                        await self._ctrl.switch_to_webview(timeout_s=15)
                    else:
                        # 原生模式：直接启动 Activity，不切 WebView
                        await self._ctrl.navigate(page.url)
                except Exception as nav_err:
                    logger.error("手机页面导航失败: {} | {}", page.url, nav_err)

            for scenario in page.scenarios:
                if cancelled:
                    break
                logger.info("── 场景: {} ──", scenario.name)

                # 场景开始前截图+AI分析当前页面，预拿所有元素坐标
                scene_coords = await self._analyze_page_elements(scenario)

                for step_def in scenario.steps:
                    step_num += 1
                    desc = step_def.description or step_def.action

                    # 检查是否被用户停止
                    if self._test_controller and self._test_controller.is_cancelled:
                        logger.info("测试被用户停止 | 步骤={}/{}", step_num, blueprint.total_steps)
                        cancelled = True
                        break

                    # 更新进度 + 等待暂停
                    if self._test_controller:
                        self._test_controller.update_progress(step_num, desc)
                        await self._test_controller.wait_if_paused()

                    # 同步控制器的步骤编号，避免日志中显示两套不同的步骤号
                    self._ctrl._step_counter = step_num - 1

                    if self._on_step:
                        await self._on_step(step_num, "start", desc)

                    result, bug = await self._execute_step(
                        step_num, step_def, page, blueprint, scene_coords
                    )
                    all_results.append(result)

                    # navigate后scene_coords被清空 → 重新分析剩余步骤
                    if step_def.action == "navigate" and not scene_coords:
                        remaining_steps = scenario.steps[scenario.steps.index(step_def)+1:]
                        if any(s.action in ("click", "fill") for s in remaining_steps):
                            from types import SimpleNamespace
                            fake_scenario = SimpleNamespace(steps=remaining_steps, name=scenario.name)
                            scene_coords.update(await self._analyze_page_elements(fake_scenario))

                    # 失败时注入 logcat 日志
                    if bug:
                        logs = await self._ctrl.get_logcat(last_n=30)
                        if logs:
                            log_text = "\n".join(logs[-20:])
                            bug.description += f"\n\n--- logcat（最近20行） ---\n{log_text}"
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
        report.end_time = datetime.now(timezone.utc)  # duration_seconds 是通过 end_time 计算的属性
        report.report_markdown = self._generate_markdown(blueprint, report, all_results, all_bugs)

        # 测试结束后立即停止弹窗dismisser，避免无限刷错误日志
        if hasattr(self._ctrl, '_dialog_dismisser') and self._ctrl._dialog_dismisser:
            self._ctrl._dialog_dismisser.stop()

        # 通知 test_controller 测试完成（使 stop/pause 按钮恢复）
        if self._test_controller:
            self._test_controller.on_test_complete()

        logger.info("手机蓝本测试完成 | 通过={}/{} | Bug={}",
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
        """执行单个蓝本步骤，失败时自动重试一次（U2崩溃场景）。"""
        result, bug = await self._execute_step_inner(step_num, step_def, page, blueprint, scene_coords=scene_coords)

        # 步骤级重试：仅在U2真正崩溃时恢复Session后重试一次
        if result.status == StepStatus.ERROR and result.error_message:
            err = result.error_message
            is_u2_dead = (
                "instrumentation process is not running" in err
                or "socket hang up" in err
            )
            if is_u2_dead:
                logger.info("  步骤{}因U2崩溃失败，尝试恢复后重试...", step_num)
                try:
                    await self._ctrl._recover_u2_session()
                    await asyncio.sleep(2)
                    result, bug = await self._execute_step_inner(
                        step_num, step_def, page, blueprint, is_retry=True, scene_coords=scene_coords
                    )
                except Exception as retry_err:
                    logger.warning("  步骤{}重试也失败: {}", step_num, str(retry_err)[:80])

        return result, bug

    async def _execute_step_inner(
        self,
        step_num: int,
        step_def: BlueprintStep,
        page: BlueprintPage,
        blueprint: Blueprint,
        is_retry: bool = False,
        scene_coords: dict[str, tuple[int, int]] | None = None,
    ) -> tuple[StepResult, Optional[BugReport]]:
        """执行单个蓝本步骤的内部实现。

        策略：click/fill 操作时
        1. 先查 scene_coords 里有没有预分析的视觉坐标 → 有就直接用坐标操作
        2. 没有则尝试 Appium 精确定位
        3. Appium 也找不到则截图+AI实时定位（视觉降级）
        """
        desc = step_def.description or f"{step_def.action} {step_def.target or step_def.value or ''}"
        retry_tag = " [重试]" if is_retry else ""
        logger.info("  [步骤{}/{}]{} {} | {}", step_num, blueprint.total_steps, retry_tag, step_def.action, desc)

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
                if url and url.startswith("http"):
                    await self._ctrl.navigate(url)
                    try:
                        await self._ctrl.switch_to_webview(timeout_s=15)
                    except Exception:
                        pass
                elif url and ("/" in url or url.startswith(".")):
                    await self._ctrl.navigate(url)
                else:
                    # 重启应用到初始 Activity
                    activity = blueprint.app_activity or ".MainActivity"
                    pkg = blueprint.app_package
                    if pkg:
                        await self._ctrl.navigate(f"{pkg}/{activity}")
                # navigate后页面变了，清空预分析坐标（后续步骤走Appium或视觉降级）
                if scene_coords is not None:
                    scene_coords.clear()

            elif step_def.action == "click":
                await self._smart_tap(target, desc, scene_coords)

            elif step_def.action == "fill":
                await self._smart_fill(target, value, desc, scene_coords)

            elif step_def.action == "wait":
                # 如果有 target 则等待元素，否则直接 sleep
                if target:
                    timeout_ms = step_def.timeout_ms or 5000
                    await self._ctrl.wait_for_element(target, timeout_ms=timeout_ms)
                else:
                    ms = int(value) if value and value.isdigit() else (step_def.timeout_ms or 1000)
                    await asyncio.sleep(ms / 1000)

            elif step_def.action == "scroll":
                h = self._ctrl._device.screen_height or 800
                w = self._ctrl._device.screen_width or 400
                cx = int(w) // 2
                await self._ctrl.swipe(cx, int(h) * 3 // 4, cx, int(h) // 4, duration_ms=400)

            elif step_def.action == "back":
                await self._ctrl.back()

            elif step_def.action == "assert_text":
                # assert_text 的预期值在 expected 字段（不是 value 字段）
                expected = step_def.expected or value or ""
                # 优先用UI树验证（Appium findElement在Flutter上会超时）
                text = await self._get_text_from_ui_tree(target)
                if text is None:
                    # UI树找不到，回退Appium
                    try:
                        text = await self._ctrl.get_text(target)
                    except Exception:
                        text = ""
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
                            reproduction=f"检查元素 {target}，公式={expected}",
                            screenshot_path=None,
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
                        reproduction=f"检查元素 {target} 的文本内容",
                        screenshot_path=None,
                        step_number=step_num,
                    )
                    return StepResult(
                        step=step_num, action=action_type, description=desc,
                        status=StepStatus.FAILED, duration_seconds=elapsed,
                        error_message=f"文本断言失败: 预期'{expected}'，实际'{text}'",
                    ), bug

            # 只在蓝本写了screenshot动作 或 有expected需要AI验证时才截图
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
                reproduction=f"执行步骤{step_num}: {step_def.action} {step_def.target or step_def.value or ''}",
                screenshot_path=None,
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

    # ── 视觉驱动操作 ──────────────────────────────────────

    async def _analyze_page_elements(self, scenario) -> dict[str, tuple[int, int]]:
        """场景开始前分析当前页面，预拿所有需要操作的元素坐标。

        双保险预加载策略：
          1. UI树匹配（Appium /source 或 adb dump）→ 精确bounds坐标
          2. 截图+AI分析 → 始终执行，归一化坐标缓存备用
        UI树坐标优先使用，AI坐标作为兜底（已缓存，无需等待）。

        Returns:
            dict: {选择器: (x, y)} 坐标映射
        """
        # 收集这个场景里所有 click/fill 步骤的目标
        targets = []
        for step in scenario.steps:
            if step.action in ("click", "fill") and step.target:
                desc = step.description or step.action
                targets.append({"target": step.target, "description": desc})

        if not targets:
            return {}

        w = int(self._ctrl._device.screen_width or 1080)
        h = int(self._ctrl._device.screen_height or 2400)
        coords: dict[str, tuple[int, int]] = {}

        # ── 第1层：UI树精确匹配 ──
        xml_str = await self._ctrl.dump_ui_tree()
        ui_matched = 0
        if xml_str:
            coords = self._match_targets_from_ui_tree(xml_str, targets, w, h)
            ui_matched = len(coords)

        # ── 第2层：AI视觉分析（始终执行，双保险预加载） ──
        # 一个应用没多少页面，每页都预分析成本很小，
        # 好处是UI树匹配不到时可以立即取AI坐标，不用再等5-6秒
        if self._ai and targets:
            unmatched = [t for t in targets if t["target"] not in coords]
            if unmatched:
                logger.info("  AI预加载分析 {} 个元素（UI树未匹配）", len(unmatched))
                ai_coords = await self._ai_analyze_elements(unmatched, w, h)
                # AI坐标只补充UI树没有的，不覆盖UI树的精确坐标
                for k, v in ai_coords.items():
                    if k not in coords:
                        coords[k] = v
                ai_hit = len([t for t in unmatched if t["target"] in coords])
            else:
                ai_hit = 0
            logger.info("  页面预分析完成 | UI树={} + AI={} / 总共{}",
                         ui_matched, ai_hit, len(targets))
        else:
            logger.info("  页面预分析完成(UI树) | 匹配 {}/{} 个元素", ui_matched, len(targets))

        return coords

    def _match_targets_from_ui_tree(
        self,
        xml_str: str,
        targets: list[dict],
        screen_w: int,
        screen_h: int,
    ) -> dict[str, tuple[int, int]]:
        """从UI树XML中匹配目标元素，提取bounds中心坐标。

        支持的selector格式：
          - accessibility_id:xxx → content-desc匹配
          - //android.widget.EditText[@hint='xxx'] → XPath属性匹配
          - id:xxx → resource-id匹配
        """
        import re
        import xml.etree.ElementTree as ET

        coords: dict[str, tuple[int, int]] = {}
        self._xpath_order_index = {}  # 重置顺序索引
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as e:
            logger.debug("  UI树XML解析失败: {}", str(e)[:60])
            return coords

        # 遍历所有节点，建立索引
        all_nodes = list(root.iter())

        for t in targets:
            selector = t["target"]
            desc = t["description"]
            matched_node = None

            # accessibility_id:xxx → content-desc匹配，兼容hint/text（Flutter常用hintText做标识）
            if selector.startswith("accessibility_id:"):
                aid = selector[len("accessibility_id:"):]
                for node in all_nodes:
                    cd = node.get("content-desc", "")
                    if cd == aid or cd.startswith(aid):
                        matched_node = node
                        break
                if matched_node is None:
                    for node in all_nodes:
                        hint = node.get("hint", "") or node.get("text", "")
                        if hint == aid:
                            matched_node = node
                            break

            # id:xxx → resource-id匹配
            elif selector.startswith("id:"):
                rid = selector[len("id:"):]
                for node in all_nodes:
                    if rid in (node.get("resource-id", "") or ""):
                        matched_node = node
                        break

            # XPath: //class[@attr='value']
            elif selector.startswith("//"):
                attr_matches = re.findall(r"@(\w+)=['\"]([^'\"]+)['\"]", selector)
                class_match = re.match(r"//(\S+?)[\[@]", selector)
                target_class = class_match.group(1) if class_match else None

                # 检查是否包含hint属性（Flutter的hint不在UI树里）
                has_hint = any(a == "hint" for a, _ in attr_matches)
                non_hint_attrs = [(a, v) for a, v in attr_matches if a != "hint"]

                if has_hint and not non_hint_attrs and target_class:
                    # 只有hint属性 → 按类型+顺序匹配
                    if not hasattr(self, "_xpath_order_index"):
                        self._xpath_order_index = {}
                    order_key = target_class
                    idx = self._xpath_order_index.get(order_key, 0)
                    # Flutter EditText有父子两层，只取叶子（没有同类子节点）+ 去重bounds
                    same_class = [n for n in all_nodes if n.get("class") == target_class]
                    seen_bounds = set()
                    leaf_nodes = []
                    for n in same_class:
                        has_same_child = any(
                            c.get("class") == target_class for c in n
                        )
                        if has_same_child:
                            continue  # 跳过有同类子节点的父节点
                        b = n.get("bounds", "")
                        if b and b not in seen_bounds:
                            seen_bounds.add(b)
                            leaf_nodes.append(n)
                    if idx < len(leaf_nodes):
                        matched_node = leaf_nodes[idx]
                        self._xpath_order_index[order_key] = idx + 1
                else:
                    for node in all_nodes:
                        if target_class and node.get("class", "") != target_class:
                            continue
                        all_match = True
                        for attr_name, attr_val in non_hint_attrs:
                            node_val = node.get(attr_name, "")
                            if node_val != attr_val:
                                all_match = False
                                break
                        if all_match and non_hint_attrs:
                            matched_node = node
                            break

            # 从bounds提取中心坐标
            if matched_node is not None:
                bounds = matched_node.get("bounds", "")
                bm = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if bm:
                    x1, y1, x2, y2 = int(bm.group(1)), int(bm.group(2)), int(bm.group(3)), int(bm.group(4))
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    if 0 < cx <= screen_w and 0 < cy <= screen_h:
                        coords[selector] = (cx, cy)
                        logger.info("  页面分析(UI树): {} → ({}, {}) [bounds={}]", desc, cx, cy, bounds)

        return coords

    async def _ai_analyze_elements(
        self,
        targets: list[dict],
        w: int, h: int,
    ) -> dict[str, tuple[int, int]]:
        """AI视觉分析兜底：截图+归一化坐标。"""
        coords: dict[str, tuple[int, int]] = {}
        try:
            screenshot_path = await self._ctrl.screenshot("scene_analysis")

            target_list = "\n".join(
                f"  {i+1}. 描述: {t['description']} | 标识: {t['target']}"
                for i, t in enumerate(targets)
            )
            prompt = (
                f"分析这张手机截图，找到以下UI元素的中心位置。\n\n"
                f"要找的元素：\n{target_list}\n\n"
                f"重要规则：\n"
                f"- 返回归一化坐标（0到1之间的小数），表示元素在图片中的相对位置\n"
                f"- x=0表示最左边，x=1表示最右边\n"
                f"- y=0表示最上面，y=1表示最下面\n"
                f"- 返回JSON数组：[{{\"index\": 1, \"x\": 0.5, \"y\": 0.48}}, ...]\n"
                f"- 如果元素不存在：{{\"index\": 1, \"not_found\": true}}\n"
                f"- 只返回JSON数组"
            )

            import json
            import re
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._ai.analyze_screenshot(
                    str(screenshot_path), prompt, reasoning_effort="low",
                )
            )

            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if not json_match:
                return coords

            items = json.loads(json_match.group())
            for item in items:
                idx = int(item.get("index", 0)) - 1
                if item.get("not_found") or idx < 0 or idx >= len(targets):
                    continue
                rx, ry = float(item.get("x", 0)), float(item.get("y", 0))
                if rx > 1.0 or ry > 1.0:
                    rx, ry = rx / w, ry / h
                x, y = int(rx * w), int(ry * h)
                if 0 < x <= w and 0 < y <= h:
                    key = targets[idx]["target"]
                    coords[key] = (x, y)
                    logger.info("  页面分析(AI): {} → ({}, {}) [归一化:{:.3f},{:.3f}]",
                                targets[idx]["description"], x, y, rx, ry)
        except Exception as e:
            logger.warning("  AI页面分析异常: {}", str(e)[:100])
        return coords

    async def _smart_tap(
        self,
        target: str,
        desc: str,
        scene_coords: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        """智能点击：视觉坐标 → Appium → 视觉降级。"""
        # 第1层：场景预分析的视觉坐标
        if scene_coords and target in scene_coords:
            x, y = scene_coords[target]
            logger.info("  [视觉] 使用预分析坐标点击 ({}, {}) | {}", x, y, desc)
            await self._ctrl.tap_xy(x, y)
            return

        # 第2层：Appium 精确定位
        try:
            await self._ctrl.tap(target)
            return
        except RuntimeError as e:
            err = str(e)
            # session丢失/U2崩溃/元素找不到 都回退到视觉降级，不直接抛出
            recoverable = ("no such element" in err or "元素查找超时" in err
                           or "session" in err.lower() or "超时" in err
                           or "instrumentation" in err)
            if not recoverable:
                raise

        # 第3层：截图+AI实时定位
        logger.info("  [视觉降级] Appium找不到 {}，截图+AI识别...", target)
        coords = await self._visual_find_element(target, desc)
        if coords:
            await self._ctrl.tap_xy(coords[0], coords[1])
        else:
            raise RuntimeError(f"元素找不到（Appium+视觉均失败）: {target} | {desc}")

    async def _get_text_from_ui_tree(self, selector: str) -> Optional[str]:
        """从UI树中查找元素并返回其文本（content-desc或text属性）。

        Returns:
            找到返回文本字符串（可能为空字符串），找不到返回 None。
        """
        import re
        import xml.etree.ElementTree as ET

        xml_str = await self._ctrl.dump_ui_tree()
        if not xml_str:
            return None

        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return None

        all_nodes = list(root.iter())
        matched = None

        if selector.startswith("accessibility_id:"):
            aid = selector[len("accessibility_id:"):]
            for node in all_nodes:
                cd = node.get("content-desc", "")
                if cd == aid or cd.startswith(aid):
                    matched = node
                    break
            if matched is None:
                for node in all_nodes:
                    hint = node.get("hint", "") or node.get("text", "")
                    if hint == aid:
                        matched = node
                        break
        elif selector.startswith("id:"):
            rid = selector[len("id:"):]
            for node in all_nodes:
                if rid in (node.get("resource-id", "") or ""):
                    matched = node
                    break

        if matched is not None:
            # 返回content-desc或text（取非空的那个）
            cd = matched.get("content-desc", "")
            txt = matched.get("text", "")
            return cd or txt or ""

        return None

    async def _smart_fill(
        self,
        target: str,
        value: str,
        desc: str,
        scene_coords: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        """智能输入：视觉坐标 → Appium → 视觉降级。"""
        # 第1层：场景预分析的视觉坐标
        if scene_coords and target in scene_coords:
            x, y = scene_coords[target]
            logger.info("  [视觉] 使用预分析坐标输入 ({}, {}) | {}", x, y, desc)
            await self._ctrl.input_text_xy(x, y, value)
            return

        # 第2层：Appium 精确定位
        try:
            await self._ctrl.input_text(target, value)
            return
        except RuntimeError as e:
            err = str(e)
            # session丢失/U2崩溃/元素找不到 都回退到视觉降级，不直接抛出
            recoverable = ("no such element" in err or "元素查找超时" in err
                           or "session" in err.lower() or "超时" in err
                           or "instrumentation" in err)
            if not recoverable:
                raise

        # 第3层：截图+AI实时定位
        logger.info("  [视觉降级] Appium找不到 {}，截图+AI识别...", target)
        coords = await self._visual_find_element(target, desc)
        if coords:
            await self._ctrl.input_text_xy(coords[0], coords[1], value)
        else:
            raise RuntimeError(f"元素找不到（Appium+视觉均失败）: {target} | {desc}")

    async def _visual_find_element(
        self,
        selector: str,
        description: str,
        max_scrolls: int = 3,
    ) -> Optional[tuple[int, int]]:
        """视觉降级：截图让AI识别目标元素的坐标。

        当Appium找不到元素时，截图+AI视觉理解来定位。
        如果AI说"当前屏幕没有但可能在下方"，自动滚动再截图再分析。
        最多滚动 max_scrolls 次。

        Returns:
            (x, y) 坐标元组，或 None（AI也找不到）
        """
        if not self._ai:
            logger.warning("  视觉降级失败: AI客户端未配置")
            return None

        import json
        import re

        w = int(self._ctrl._device.screen_width or 1080)
        h = int(self._ctrl._device.screen_height or 2400)

        # 从选择器提取可读名称
        readable_target = selector
        for prefix in ("accessibility_id:", "id:", "class:"):
            if readable_target.startswith(prefix):
                readable_target = readable_target[len(prefix):]
                break
        if readable_target.startswith("//"):
            attr_match = re.search(r"@\w+=['\"]([^'\"]+)['\"]", readable_target)
            if attr_match:
                readable_target = attr_match.group(1)

        for scroll_attempt in range(max_scrolls + 1):  # 0=当前屏幕, 1~N=滚动后
            try:
                suffix = f"_scroll{scroll_attempt}" if scroll_attempt > 0 else ""
                screenshot_path = await self._ctrl.screenshot(f"visual_fallback{suffix}")

                prompt = (
                    f"分析这张手机截图，找到下面描述的UI元素的中心位置。\n\n"
                    f"要找的元素：{description}\n"
                    f"元素标识符：{readable_target}\n\n"
                    f"重要规则：\n"
                    f"- 返回归一化坐标（0到1之间的小数），表示元素在图片中的相对位置\n"
                    f"- x=0表示最左边，x=1表示最右边；y=0表示最上面，y=1表示最下面\n"
                    f"- 找到：返回 {{\"x\": 0.5, \"y\": 0.48}}\n"
                    f"- 当前屏幕没有但页面可能可以滚动：返回 {{\"need_scroll\": true, \"direction\": \"down\"}}\n"
                    f"- 确实不存在（当前页面不是目标页面）：返回 {{\"not_found\": true, \"reason\": \"原因\"}}\n"
                    f"- 只返回JSON"
                )

                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None, lambda p=prompt, sp=str(screenshot_path): self._ai.analyze_screenshot(
                        sp, p, reasoning_effort="low",
                    )
                )

                # 解析AI返回
                json_match = re.search(r'\{[^}]+\}', response)
                if not json_match:
                    logger.warning("  视觉降级: AI返回格式异常: {}", response[:100])
                    return None

                result = json.loads(json_match.group())

                # 找到了
                if result.get("x") is not None and result.get("y") is not None:
                    rx, ry = float(result["x"]), float(result["y"])
                    # 自动检测：如果>1说明AI返回了像素坐标，归一化
                    if rx > 1.0 or ry > 1.0:
                        rx, ry = rx / w, ry / h
                    x, y = int(rx * w), int(ry * h)
                    if 0 < x <= w and 0 < y <= h:
                        logger.info("  视觉降级成功: AI识别到元素在 ({}, {}) [归一化:{:.3f},{:.3f}]{}",
                                    x, y, rx, ry,
                                    f" (滚动{scroll_attempt}次后)" if scroll_attempt > 0 else "")
                        return (x, y)

                # 需要滚动
                if result.get("need_scroll") and scroll_attempt < max_scrolls:
                    direction = result.get("direction", "down")
                    logger.info("  视觉降级: AI建议向{}滚动查找 ({}/{})",
                                direction, scroll_attempt + 1, max_scrolls)
                    await self._ctrl.swipe_screen(direction)
                    await asyncio.sleep(1.0)  # 等滚动动画完成
                    continue

                # 确实不存在
                if result.get("not_found"):
                    logger.info("  视觉降级: AI确认元素不存在 | 原因: {}", result.get("reason", "未知"))
                    return None

                # 其他情况
                logger.warning("  视觉降级: AI返回无法解析: {}", response[:100])
                return None

            except Exception as e:
                logger.warning("  视觉降级异常: {}", str(e)[:100])
                return None

        logger.info("  视觉降级: 滚动{}次后仍未找到 {}", max_scrolls, readable_target)
        return None

    # ── 报告生成 ──────────────────────────────────────────

    def _generate_markdown(
        self,
        blueprint: Blueprint,
        report: TestReport,
        results: list[StepResult],
        bugs: list[BugReport],
    ) -> str:
        """生成 Markdown 格式报告（与 Web 端格式一致）。"""
        pass_rate = (report.passed_steps / report.total_steps * 100) if report.total_steps else 0
        lines = [
            f"# 手机蓝本测试报告 - {blueprint.app_name}",
            "",
            f"- **测试模式**：蓝本模式（精确选择器）",
            f"- **设备**：{self._ctrl.device_info.name}",
            f"- **总步骤**：{report.total_steps}",
            f"- **通过**：{report.passed_steps} | **失败**：{report.failed_steps} | **错误**：{report.error_steps}",
            f"- **通过率**：{pass_rate:.0f}%",
            f"- **耗时**：{report.duration_seconds:.1f}s",
            "",
            "## 步骤详情",
            "| # | 操作 | 说明 | 结果 | 耗时 |",
            "|---|------|------|------|------|",
        ]

        status_emoji = {
            StepStatus.PASSED: "✅",
            StepStatus.FAILED: "❌",
            StepStatus.ERROR: "⚠️",
            StepStatus.SKIPPED: "⏭️",
        }

        for r in results:
            emoji = status_emoji.get(r.status, "❓")
            err = f" ({r.error_message[:60]}...)" if r.error_message else ""
            lines.append(
                f"| {r.step} | {r.action.value} | {r.description[:30]} | "
                f"{emoji} {r.status.value}{err} | {r.duration_seconds:.1f}s |"
            )

        if bugs:
            lines.extend([
                "",
                "## 发现的Bug",
                "| 严重度 | 标题 | 说明 |",
                "|--------|------|------|",
            ])
            for bug in bugs:
                lines.append(
                    f"| {bug.severity.value} | {bug.title} | "
                    f"{bug.description[:80]} |"
                )
            lines.extend(["", "### Bug详情", ""])
            for i, bug in enumerate(bugs, 1):
                lines.append(f"**Bug {i}: {bug.title}**")
                lines.append(f"- 严重程度: {bug.severity.value}")
                lines.append(f"- 位置: {bug.location}")
                lines.append(f"- 描述: {bug.description}")
                lines.append(f"- 复现步骤: {bug.reproduction}")
                lines.append("")

        lines.extend([
            "",
            "---",
            f"*报告由 TestPilot AI 蓝本模式生成*",
        ])

        return "\n".join(lines)
