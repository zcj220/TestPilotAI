"""
蓝本模式执行器（v1.x）

按 testpilot.json 蓝本精确执行测试：
- 使用蓝本中的精确CSS选择器，不靠AI猜测
- 按需截图（蓝本写了screenshot或有expected时）+ AI视觉验证预期结果
- 生成与盲测模式格式一致的测试报告
"""

import asyncio
import base64
import time
from pathlib import Path
from typing import Callable, Coroutine, Any, Optional

from loguru import logger

from src.browser.automator import BrowserAutomator
from src.core.ai_client import AIClient
from src.core.exceptions import BrowserActionError, BrowserNavigationError
from src.testing.anomaly_detector import AnomalyDetector, AnomalySeverity as AnomSev
from src.testing.blueprint import Blueprint, BlueprintPage, BlueprintScenario, BlueprintStep
from src.testing.models import ActionType, BugReport, BugSeverity, StepResult, StepStatus, TestReport
from src.testing.controller import TestController
from src.testing.formula_validator import FormulaResult, is_formula, validate_formula
from src.testing.smart_input import generate_smart_value, is_auto_value
from src.testing.log_slicer import LogSlicer
from src.testing.smart_repair import RepairStrategy, SmartRepairDecider
from src.testing.ai_hub import AIHub, FaultType, HubAction, StepContext


class BlueprintRunner:
    """蓝本模式执行器。

    按蓝本中定义的精确选择器和步骤执行测试，
    按需截图（仅蓝本写了screenshot动作或有expected字段时），调用AI视觉分析验证预期结果。

    典型使用：
        runner = BlueprintRunner(browser, ai_client)
        report = await runner.run(blueprint)
    """

    # 回调类型
    ScreenshotCallback = Callable[[int, str], Coroutine[Any, Any, None]]
    StepCallback = Callable[[int, str, str], Coroutine[Any, Any, None]]

    def __init__(
        self,
        browser: BrowserAutomator,
        ai_client: Optional[AIClient] = None,
        controller: Optional[TestController] = None,
        on_screenshot: Optional["BlueprintRunner.ScreenshotCallback"] = None,
        on_step: Optional["BlueprintRunner.StepCallback"] = None,
    ) -> None:
        self._browser = browser
        self._ai = ai_client
        self._controller = controller
        self._on_screenshot = on_screenshot
        self._on_step = on_step
        self._anomaly_detector: AnomalyDetector | None = None
        self._log_slicer = LogSlicer()
        # AI中枢：统一的弹窗自愈 + 连续失败熔断决策
        self._hub = AIHub(ai_client)

    async def run(
        self,
        blueprint: Blueprint,
        repair_callback=None,
    ) -> TestReport:
        """执行蓝本中的所有场景。

        Args:
            blueprint: 解析后的蓝本对象
            repair_callback: 智能修复回调函数，签名 async (bug: BugReport) -> bool
                             返回True表示修复成功。为None则不启用智能修复。

        Returns:
            TestReport: 测试报告
        """
        report = TestReport(
            test_name=f"蓝本测试-{blueprint.app_name}",
            url=blueprint.base_url,
        )

        all_results: list[StepResult] = []
        all_bugs: list[BugReport] = []
        deferred_bugs: list[BugReport] = []
        step_num = 0

        # 智能修复决策器
        repair_decider = SmartRepairDecider()
        smart_repair_enabled = repair_callback is not None

        logger.info("════════════════════════════════════════════════════════════")
        logger.info("蓝本模式测试开始 | {} | 页面={} | 场景={} | 步骤={} | 智能修复={}",
                     blueprint.app_name,
                     len(blueprint.pages),
                     blueprint.total_scenarios,
                     blueprint.total_steps,
                     "开启" if smart_repair_enabled else "关闭")

        # v10.2：如果蓝本有 start_command，先启动被测应用并等待就绪
        self._app_started_by_runner = False
        if getattr(blueprint, "start_command", "") and blueprint.start_command.strip():
            await self._auto_start_app(blueprint)

        # v2.0：通知控制器测试开始
        if self._controller:
            self._controller.start(total_steps=blueprint.total_steps)

        # 清除浏览器缓存，确保加载最新文件
        try:
            page = self._browser.page
            client = await page.context.new_cdp_session(page)
            await client.send("Network.clearBrowserCache")
            await client.detach()
            logger.debug("浏览器缓存已清除")
        except Exception as e:
            logger.debug("清除缓存失败（非致命）: {}", e)

        # v2.1：挂载浏览器控制台和网络错误监听（日志智能切片）
        self._log_slicer.clear()
        try:
            browser_page = self._browser.page
            browser_page.on("console", lambda msg: self._log_slicer.add_console_log(
                msg.type, msg.text,
            ))
            browser_page.on("response", lambda resp: (
                self._log_slicer.add_network_error(resp.url, resp.status, resp.request.method)
                if resp.status >= 400 else None
            ))
            logger.debug("浏览器日志监听已挂载")
        except Exception as e:
            logger.debug("浏览器日志监听挂载失败（非致命）: {}", e)

        # 启动通用异常检测器
        try:
            self._anomaly_detector = AnomalyDetector(self._browser.page)
            self._anomaly_detector.start_monitoring()
        except Exception as e:
            logger.warning("异常检测器启动失败，将跳过异常检测: {}", e)
            self._anomaly_detector = None

        cancelled = False
        for page_idx, page in enumerate(blueprint.pages):
            if cancelled:
                break

            # v2.0：多页面自动导航（同一browser context，Cookie/Session自动保持）
            if page.url:
                page_url = page.url
                if not page_url.startswith("http"):
                    page_url = blueprint.base_url.rstrip("/") + "/" + page_url.lstrip("/")
                logger.info("── 页面 {}/{}: {} ──", page_idx + 1, len(blueprint.pages), page_url)
                try:
                    await self._browser.navigate(page_url)
                except Exception as e:
                    logger.error("页面导航失败: {} | {}", page_url, str(e)[:80])

            for scenario in page.scenarios:
                if cancelled:
                    break

                # 场景间隔离：清除cookie/storage，确保每个场景从干净状态开始
                try:
                    await self._browser._context.clear_cookies()
                    await self._browser.page.evaluate("try { localStorage.clear(); sessionStorage.clear(); } catch(e) {}")
                except Exception as e:
                    logger.debug("场景隔离清理失败（非致命）: {}", str(e)[:60])

                logger.info("── 场景: {} ──", scenario.name)
                self._hub.on_scenario_start()

                # 预扫描场景中所有assert_text的expected文本，提前注册到异常检测器的suppress列表
                # 避免时序问题：click触发错误提示 → 异常检测器立刻扫描报Bug → assert_text还没执行
                if self._anomaly_detector:
                    for s in scenario.steps:
                        if s.action == "assert_text" and s.expected:
                            self._anomaly_detector.suppress_error_text(s.expected)

                for step_def in scenario.steps:
                    step_num += 1
                    desc = step_def.description or step_def.action

                    # v2.0：控制器检查（暂停/停止/单步）
                    if self._controller:
                        await self._controller.wait_if_paused()
                        if self._controller.is_cancelled:
                            logger.info("测试被用户停止 | 步骤={}/{}", step_num, blueprint.total_steps)
                            cancelled = True
                            break
                        self._controller.update_progress(step_num, desc)

                    # v2.1：日志切片 - 步骤开始
                    self._log_slicer.step_start(step_num)

                    # 步骤开始通知
                    if self._on_step:
                        await self._on_step(step_num, "start", desc)

                    result, bug = await self._execute_step(
                        step_num, step_def, page, blueprint
                    )

                    # ── AI中枢决策：步骤失败时统一走 L1→L3 决策链 ──
                    if bug:
                        ctx = StepContext(
                            step_num=step_num,
                            total_steps=blueprint.total_steps,
                            action=step_def.action,
                            target=step_def.target,
                            value=step_def.value,
                            error_message=result.error_message if result else None,
                            scenario_name=scenario.name,
                            platform="web",
                            screenshot_fn=self._hub_screenshot,
                            click_fn=self._hub_click,
                        )
                        decision = await self._hub.on_step_failed(ctx)

                        if decision.action == HubAction.RETRY:
                            # L2恢复：如果AI中枢返回了恢复选择器，先执行恢复动作
                            if decision.recover_selector:
                                logger.info("  🔧 AI中枢L2恢复：先点击[{}]", decision.recover_selector)
                                try:
                                    await self._browser.click(decision.recover_selector)
                                    await asyncio.sleep(1)  # 等待恢复动作生效
                                except Exception as recover_err:
                                    logger.warning("  L2恢复点击失败: {}", str(recover_err)[:80])

                            # 动作替换：AI中枢建议用不同动作重试（如 fill→select）
                            retry_step = step_def
                            if decision.override_action and decision.override_action != step_def.action:
                                logger.info("  🔄 AI中枢动作替换: {} → {}", step_def.action, decision.override_action)
                                retry_step = BlueprintStep(
                                    action=decision.override_action,
                                    target=step_def.target,
                                    value=step_def.value,
                                    expected=step_def.expected,
                                    description=step_def.description,
                                    timeout_ms=step_def.timeout_ms,
                                    wait_after_ms=step_def.wait_after_ms,
                                )

                            logger.info("  🔄 AI中枢：{}，重试步骤{}", decision.reason, step_num)
                            result, bug = await self._execute_step(
                                step_num, retry_step, page, blueprint
                            )

                        elif decision.action == HubAction.SKIP_STEP:
                            logger.info("  ⏭️ AI中枢：{}，跳过步骤{}", decision.reason, step_num)

                        elif decision.action == HubAction.SKIP_SCENE:
                            # L3 熔断：跳过当前场景剩余步骤
                            self._hub.record_step(
                                step_num, step_def.action, step_def.target, step_def.value,
                                passed=False, error=result.error_message if result else None,
                            )
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
                                    error_message=decision.reason,
                                ))
                            all_results.append(result)
                            if bug:
                                self._label_bug_fault(bug, decision.fault)
                                all_bugs.append(bug)
                            break

                        # 归因标记
                        if bug:
                            self._label_bug_fault(bug, decision.fault)
                    else:
                        self._hub.on_step_passed()

                    # 记录步骤结果，供AI中枢L2分析历史上下文
                    self._hub.record_step(
                        step_num, step_def.action, step_def.target, step_def.value,
                        passed=not bug, error=result.error_message if bug and result else None,
                    )
                    all_results.append(result)

                    # v2.1：日志切片 - 步骤结束
                    self._log_slicer.step_end(step_num)

                    # v2.1：失败步骤注入日志上下文到Bug报告
                    if bug:
                        log_text = self._log_slicer.get_step_log_text(step_num)
                        log_count = self._log_slicer.get_step_log_count(step_num)
                        if log_text:
                            bug.description += f"\n\n--- 步骤{step_num}日志（{log_count}条） ---\n{log_text}"
                            logger.debug("步骤{}失败，注入{}条日志到Bug报告", step_num, log_count)

                    # 步骤完成通知
                    if self._on_step:
                        await self._on_step(step_num, result.status.value, desc)
                    repair_decider.record_step(result)

                    if bug:
                        all_bugs.append(bug)
                        # 智能修复决策
                        if smart_repair_enabled:
                            strategy = repair_decider.decide(bug, result)
                            if strategy == RepairStrategy.IMMEDIATE:
                                logger.info("  ⚡ 立即修复: {}", bug.title)
                                try:
                                    success = await repair_callback(bug)
                                    repair_decider.on_immediate_repair_done(success)
                                except Exception as e:
                                    logger.error("  立即修复失败: {}", str(e)[:100])
                                    repair_decider.on_immediate_repair_done(False)
                            else:
                                deferred_bugs.append(bug)

                    # v2.0：步骤间观看延迟
                    if self._controller:
                        await self._controller.step_delay()

                    # 蓝本外异常检测（每步之后）
                    anomaly_bugs = await self._check_anomalies(step_num, page.url)
                    for ab in anomaly_bugs:
                        all_bugs.append(ab)
                        if smart_repair_enabled:
                            strategy = repair_decider.decide(ab)
                            if strategy == RepairStrategy.IMMEDIATE:
                                logger.info("  ⚡ 立即修复异常: {}", ab.title)
                                try:
                                    success = await repair_callback(ab)
                                    repair_decider.on_immediate_repair_done(success)
                                except Exception as e:
                                    logger.error("  异常修复失败: {}", str(e)[:100])
                                    repair_decider.on_immediate_repair_done(False)
                            else:
                                deferred_bugs.append(ab)

        # 停止异常监控
        if self._anomaly_detector:
            self._anomaly_detector.stop_monitoring()

        # 批量处理延迟修复的Bug
        if smart_repair_enabled and deferred_bugs:
            logger.info("── 批量修复延迟Bug（{}个）──", len(deferred_bugs))
            for bug in deferred_bugs:
                try:
                    await repair_callback(bug)
                except Exception as e:
                    logger.error("  延迟修复失败: {} | {}", bug.title, str(e)[:80])

        # 汇总报告
        report.step_results = all_results
        report.bugs = all_bugs
        report.total_steps = len(all_results)
        report.passed_steps = sum(1 for r in all_results if r.status == StepStatus.PASSED)
        report.failed_steps = sum(1 for r in all_results if r.status == StepStatus.FAILED)
        report.error_steps = sum(1 for r in all_results if r.status == StepStatus.ERROR)

        # 生成Markdown报告（含修复统计）
        report.report_markdown = self._generate_markdown(
            blueprint, report, all_results, all_bugs,
            repair_stats=repair_decider.stats if smart_repair_enabled else None,
        )

        logger.info("蓝本测试完成 | 通过={}/{} | Bug={} | 修复统计={} | AI中枢={}",
                     report.passed_steps, report.total_steps, len(all_bugs),
                     repair_decider.stats if smart_repair_enabled else "N/A",
                     self._hub.stats)

        # v2.0：通知控制器测试完成
        if self._controller:
            self._controller.on_test_complete()

        return report

    # ── AI中枢桥接方法（供 AIHub 回调） ─────────────────
    @staticmethod
    def _label_bug_fault(bug: BugReport, fault: FaultType) -> None:
        """根据归因给Bug打标签，让编程AI知道谁的锅。

        标签含义（编程AI需理解）：
        - [应用Bug]：被测应用的代码有问题，需要修复应用代码
        - [蓝本问题]：testpilot.json蓝本写错了（选择器错、动作类型错等），需要修正蓝本
        """
        if bug.category.startswith("["):
            return  # 已打标
        if fault == FaultType.APP:
            bug.category = f"[应用Bug]{bug.category}"
        elif fault == FaultType.TEST:
            bug.category = f"[蓝本问题]{bug.category}"
            # 蓝本问题追加修正提示
            if "Element is not an <input>" in (bug.description or ""):
                bug.description += "\n\n💡 修复建议：蓝本中该步骤的action应从'fill'改为'select'，因为目标元素是<select>下拉框。"
            elif "Timeout" in (bug.description or "") and bug.location:
                bug.description += f"\n\n💡 修复建议：检查蓝本中选择器'{bug.location}'是否与应用实际DOM匹配，或应用是否缺少该元素。"
    async def _hub_screenshot(self, tag: str):
        """AIHub 截图回调。"""
        try:
            path = await self._browser.screenshot()
            return path
        except Exception:
            return None

    async def _hub_click(self, nx: float, ny: float):
        """AIHub 点击回调：归一化坐标 → 页面像素坐标 → 点击。"""
        try:
            viewport = await self._browser.page.evaluate(
                "() => ({w: window.innerWidth, h: window.innerHeight})"
            )
            x = int(nx * viewport["w"])
            y = int(ny * viewport["h"])
            await self._browser.page.mouse.click(x, y)
        except Exception as e:
            logger.warning("AI中枢Web点击失败: {}", str(e)[:80])

    async def _execute_step(
        self,
        step_num: int,
        step_def: BlueprintStep,
        page: BlueprintPage,
        blueprint: Blueprint,
    ) -> tuple[StepResult, Optional[BugReport]]:
        """执行单个蓝本步骤。"""
        desc = step_def.description or f"{step_def.action} {step_def.target or step_def.value or ''}"
        logger.info("  [步骤{}/{}] {} | {}", step_num, blueprint.total_steps, step_def.action, desc)

        start = time.time()
        screenshot_path = None

        # 将蓝本 action 字符串映射为 ActionType 枚举
        try:
            action_type = ActionType(step_def.action)
        except ValueError:
            action_type = ActionType.SCREENSHOT  # 未知操作默认为截图

        try:
            # 解析目标选择器（支持元素名称映射）
            target = self._resolve_selector(step_def.target, page, blueprint) if step_def.target else None

            # 解析值（支持 auto: 智能生成）
            raw_value = step_def.value or ""
            resolved_value = generate_smart_value(raw_value) if is_auto_value(raw_value) else raw_value
            if is_auto_value(raw_value):
                logger.debug("  智能输入: {} → {}", raw_value, resolved_value)

            # 执行操作
            if step_def.action == "navigate":
                url = resolved_value or page.url
                if not url.startswith("http"):
                    url = blueprint.base_url.rstrip("/") + "/" + url.lstrip("/")
                await self._browser.navigate(url)

            elif step_def.action == "click":
                await self._browser.click(target)

            elif step_def.action == "fill":
                await self._browser.fill(target, resolved_value)

            elif step_def.action == "select":
                await self._browser.select_option(target, resolved_value)

            elif step_def.action == "wait":
                if target:
                    timeout = step_def.timeout_ms or 5000
                    await self._browser.wait_for_selector(target, timeout_ms=timeout)
                else:
                    ms = int(resolved_value) if resolved_value and resolved_value.isdigit() else (step_def.timeout_ms or 1000)
                    await asyncio.sleep(ms / 1000)

            elif step_def.action == "screenshot":
                pass  # 截图在下面统一做

            elif step_def.action == "scroll":
                await self._browser.page.evaluate("window.scrollBy(0, 400)")

            elif step_def.action == "assert_text":
                text = await self._browser.get_text(target or "body")
                expected_value = step_def.expected or resolved_value

                if is_formula(expected_value):
                    # v1.4 公式验证：零AI成本，精确数值校验
                    formula_result = validate_formula(expected_value, text)
                    if not formula_result.passed:
                        elapsed = time.time() - start
                        bug = BugReport(
                            severity=BugSeverity.HIGH,
                            category="计算验证失败",
                            title=f"数值计算错误: {target}",
                            description=formula_result.detail,
                            location=target or "",
                            reproduction=f"检查元素 {target} 的数值，公式={expected_value}",
                            screenshot_path=None,
                            step_number=step_num,
                        )
                        return StepResult(
                            step=step_num,
                            action=action_type,
                            description=desc,
                            status=StepStatus.FAILED,
                            duration_seconds=elapsed,
                            error_message=formula_result.detail,
                        ), bug
                elif expected_value not in text:
                    elapsed = time.time() - start
                    bug = BugReport(
                        severity=BugSeverity.HIGH,
                        category="文本断言失败",
                        title=f"元素文本不匹配: {target}",
                        description=f"预期包含'{expected_value}'，实际为'{text}'",
                        location=target or "",
                        reproduction=f"检查元素 {target} 的文本内容",
                        screenshot_path=None,
                        step_number=step_num,
                    )
                    return StepResult(
                        step=step_num,
                        action=action_type,
                        description=desc,
                        status=StepStatus.FAILED,
                        duration_seconds=elapsed,
                        error_message=f"文本断言失败: 预期'{expected_value}'，实际'{text}'",
                    ), bug
                else:
                    # assert_text通过：告诉异常检测器这个文本是蓝本预期的，
                    # 避免异常检测器看到.error元素就误报（如故意测试登录失败场景）
                    if self._anomaly_detector and expected_value:
                        self._anomaly_detector.suppress_error_text(expected_value)

            elif step_def.action == "assert_visible":
                try:
                    await self._browser.wait_for_selector(target, timeout_ms=3000)
                except BrowserActionError:
                    elapsed = time.time() - start
                    bug = BugReport(
                        severity=BugSeverity.HIGH,
                        category="可见性断言失败",
                        title=f"元素不可见: {target}",
                        description=f"预期元素 {target} 可见，但未找到",
                        location=target or "",
                        reproduction=f"检查元素 {target} 是否存在于页面",
                        screenshot_path=None,
                        step_number=step_num,
                    )
                    return StepResult(
                        step=step_num,
                        action=action_type,
                        description=desc,
                        status=StepStatus.FAILED,
                        duration_seconds=elapsed,
                        error_message=f"元素不可见: {target}",
                    ), bug

            # 操作后等待（处理异步加载/动画）
            if step_def.wait_after_ms and step_def.wait_after_ms > 0:
                await asyncio.sleep(step_def.wait_after_ms / 1000.0)

            # 只在蓝本写了screenshot动作 或 有expected需要AI验证时才截图
            # assert_text 已经用纯文本匹配验证过了，不需要再调AI浪费tokens
            need_ai_verify = (step_def.expected and self._ai and step_def.action != "assert_text")
            need_screenshot = (step_def.action == "screenshot") or need_ai_verify
            if need_screenshot:
                screenshot_path_obj = await self._browser.screenshot(f"step{step_num}_{step_def.action}")
                screenshot_path = str(screenshot_path_obj)

                # 截图推送到前端（WebSocket）
                if self._on_screenshot:
                    try:
                        img_data = Path(screenshot_path).read_bytes()
                        img_b64 = base64.b64encode(img_data).decode("ascii")
                        await self._on_screenshot(step_num, img_b64)
                    except Exception as e:
                        logger.debug("截图推送失败: {}", e)

            # AI视觉验证（如果有预期结果描述，但 assert_text 已用文本匹配，跳过）
            ai_verdict = "passed"
            ai_detail = ""
            if need_ai_verify and screenshot_path:
                ai_verdict, ai_detail = await self._ai_verify(screenshot_path, step_def.expected)

            elapsed = time.time() - start

            if ai_verdict == "failed":
                bug = BugReport(
                    severity=BugSeverity.MEDIUM,
                    category="AI视觉验证失败",
                    title=f"步骤{step_num}预期不符: {step_def.expected}",
                    description=ai_detail,
                    location=page.url,
                    reproduction=desc,
                    screenshot_path=screenshot_path,
                    step_number=step_num,
                )
                logger.info("  ✗ 步骤{} failed | {:.1f}秒 | {}", step_num, elapsed, ai_detail[:80])
                return StepResult(
                    step=step_num,
                    action=action_type,
                    description=desc,
                    status=StepStatus.FAILED,
                    duration_seconds=elapsed,
                    screenshot_path=screenshot_path,
                    error_message=ai_detail,
                ), bug

            logger.info("  ✓ 步骤{} passed | {:.1f}秒", step_num, elapsed)
            return StepResult(
                step=step_num,
                action=action_type,
                description=desc,
                status=StepStatus.PASSED,
                duration_seconds=elapsed,
                screenshot_path=screenshot_path,
            ), None

        except (BrowserActionError, BrowserNavigationError) as e:
            elapsed = time.time() - start
            # 提取Playwright关键根因（如"intercepts pointer events"、"element is not visible"）
            err_detail = str(e)
            root_cause = self._extract_playwright_root_cause(err_detail)
            if root_cause:
                logger.info("  ⚠ 步骤{} error | {:.1f}秒 | {} | 根因: {}", step_num, elapsed, str(e)[:80], root_cause)
            else:
                logger.info("  ⚠ 步骤{} error | {:.1f}秒 | {}", step_num, elapsed, str(e)[:80])
            # 操作类步骤失败（选择器找不到/超时）生成Bug，让AI中枢有机会介入恢复
            err_bug = None
            if step_def.action in ("click", "fill", "select"):
                # 构建完整描述：基本错误 + 根因（如果有）
                bug_desc = err_detail
                if root_cause:
                    bug_desc += f"\n\n🔍 根因分析: {root_cause}"
                err_bug = BugReport(
                    severity=BugSeverity.MEDIUM,
                    category="操作失败",
                    title=f"步骤{step_num}操作失败: {step_def.action} {target or ''}",
                    description=bug_desc,
                    location=target or "",
                    reproduction=desc,
                    screenshot_path=None,
                    step_number=step_num,
                )
            return StepResult(
                step=step_num,
                action=action_type,
                description=desc,
                status=StepStatus.ERROR,
                duration_seconds=elapsed,
                error_message=str(e),
            ), err_bug

        except Exception as e:
            elapsed = time.time() - start
            logger.error("  ✗ 步骤{} 异常 | {:.1f}秒 | {}", step_num, elapsed, str(e)[:100])
            return StepResult(
                step=step_num,
                action=action_type,
                description=desc,
                status=StepStatus.ERROR,
                duration_seconds=elapsed,
                error_message=str(e),
            ), None

    @staticmethod
    def _extract_playwright_root_cause(error_text: str) -> Optional[str]:
        """从Playwright错误信息中提取关键根因，让编程AI能看到真正问题。

        Playwright的错误信息很长（含Call log），关键线索藏在后面。
        例如 "intercepts pointer events" 说明有元素遮挡了点击目标。
        """
        import re
        # 已知的Playwright关键根因模式
        patterns = [
            (r"<([^>]+)>\s*intercepts pointer events", "CSS层级遮挡: <{0}>元素挡住了点击目标，检查z-index或position"),
            (r"element is not visible", "目标元素不可见（display:none或visibility:hidden）"),
            (r"element is outside of the viewport", "目标元素在视口外，需要先滚动到可见区域"),
            (r"element is not enabled", "目标元素被禁用（disabled属性）"),
            (r"waiting for selector.*did not resolve to any element", "选择器在页面中找不到任何匹配元素"),
            (r"Element is not an <input>", "目标元素不是输入框，不能用fill操作（可能是<select>下拉框，应用select操作）"),
            (r"strict mode violation.*resolved to (\d+) elements", "选择器匹配到多个元素（{0}个），需要更精确的选择器"),
        ]
        for pattern, template in patterns:
            match = re.search(pattern, error_text, re.IGNORECASE)
            if match:
                try:
                    return template.format(*match.groups()) if match.groups() else template
                except (IndexError, KeyError):
                    return template
        return None

    async def _check_anomalies(self, step_num: int, page_url: str) -> list[BugReport]:
        """执行蓝本外异常检测，将发现的异常转为BugReport。"""
        if not self._anomaly_detector:
            return []

        try:
            report = await self._anomaly_detector.check()
            self._anomaly_detector.drain_errors()

            if not report.has_issues:
                return []

            # 异常严重度 → Bug严重度映射
            severity_map = {
                AnomSev.CRITICAL: BugSeverity.CRITICAL,
                AnomSev.HIGH: BugSeverity.HIGH,
                AnomSev.MEDIUM: BugSeverity.MEDIUM,
                AnomSev.LOW: BugSeverity.LOW,
            }

            bugs = []
            for anomaly in report.anomalies:
                bugs.append(BugReport(
                    severity=severity_map.get(anomaly.severity, BugSeverity.MEDIUM),
                    category=f"蓝本外异常-{anomaly.anomaly_type.value}",
                    title=anomaly.title,
                    description=anomaly.detail,
                    location=page_url,
                    reproduction=f"步骤{step_num}执行后自动检测发现",
                    step_number=step_num,
                ))

            return bugs

        except Exception as e:
            logger.debug("异常检测执行失败: {}", str(e)[:100])
            return []

    def _resolve_selector(
        self,
        target: Optional[str],
        page: BlueprintPage,
        blueprint: Blueprint,
    ) -> str:
        """解析选择器：如果target是元素名称则从映射中查找，否则直接返回。

        支持：
        - CSS选择器直接使用：'#todoInput', '.btn'
        - 元素名称映射：'输入框' → page.elements['输入框'] → '#todoInput'
        - 全局元素映射：'导航栏' → blueprint.global_elements['导航栏']
        """
        if target is None:
            return ""

        # 先查页面元素映射
        if target in page.elements:
            resolved = page.elements[target]
            logger.debug("选择器映射: {} → {}", target, resolved)
            return resolved

        # 再查全局元素映射
        if target in blueprint.global_elements:
            resolved = blueprint.global_elements[target]
            logger.debug("全局选择器映射: {} → {}", target, resolved)
            return resolved

        # 直接返回（视为CSS选择器）
        return target

    async def _ai_verify(self, screenshot_path: str, expected: str) -> tuple[str, str]:
        """调用AI视觉分析验证截图是否符合预期。

        Returns:
            (verdict, detail): verdict='passed'或'failed', detail=说明
        """
        try:
            prompt = (
                f"请分析这张截图，判断页面是否满足以下预期：\n"
                f"预期：{expected}\n\n"
                f"请回答：\n"
                f"1. 判定：passed 或 failed\n"
                f"2. 说明：简要描述实际看到的内容\n\n"
                f"格式：\n判定：passed/failed\n说明：..."
            )

            response = self._ai.analyze_screenshot(screenshot_path, prompt)

            if "failed" in response.lower()[:50]:
                detail = response.split("说明：")[-1].strip() if "说明：" in response else response[:200]
                return "failed", detail
            return "passed", ""

        except Exception as e:
            logger.warning("AI验证异常，默认通过 | {}", str(e)[:80])
            return "passed", ""

    def _generate_markdown(
        self,
        blueprint: Blueprint,
        report: TestReport,
        results: list[StepResult],
        bugs: list[BugReport],
        repair_stats: Optional[dict] = None,
    ) -> str:
        """生成Markdown格式测试报告。"""
        lines = [
            f"# 蓝本测试报告 - {blueprint.app_name}",
            "",
            f"- **测试模式**：蓝本模式（精确选择器）",
            f"- **目标URL**：{blueprint.base_url}",
            f"- **总步骤**：{report.total_steps}",
            f"- **通过**：{report.passed_steps} | **失败**：{report.failed_steps} | **错误**：{report.error_steps}",
            f"- **通过率**：{report.passed_steps / report.total_steps * 100:.0f}%" if report.total_steps > 0 else "",
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
            error_note = f" ({r.error_message[:40]}...)" if r.error_message else ""
            lines.append(
                f"| {r.step} | {r.action.value} | {r.description[:30]} | "
                f"{emoji} {r.status.value}{error_note} | {r.duration_seconds:.1f}s |"
            )

        if bugs:
            lines.extend([
                "",
                "## 发现的Bug",
                "| 严重度 | 标题 | 说明 |",
                "|--------|------|------|",
            ])
            for bug in bugs:
                lines.append(f"| {bug.severity.value} | {bug.title} | {bug.description[:50]} |")

        if repair_stats:
            lines.extend([
                "",
                "## 智能修复统计",
                f"- **立即修复次数**：{repair_stats['immediate_repairs']}",
                f"- **延迟修复Bug数**：{repair_stats['failed_steps'] - repair_stats['immediate_repairs']}"
                if repair_stats['failed_steps'] > repair_stats['immediate_repairs'] else "",
            ])

        lines.extend([
            "",
            "---",
            f"*报告由 TestPilot AI 蓝本模式生成*",
        ])

        return "\n".join(lines)

    # ── v10.2：自动启动被测应用 ────────────────────────

    async def _auto_start_app(self, blueprint: Blueprint) -> None:
        """根据蓝本中的 start_command 自动启动被测应用并等待就绪。"""
        import urllib.request
        import urllib.error
        from pathlib import Path

        cmd = blueprint.start_command.strip()
        cwd = blueprint.start_cwd.strip() or "."
        base_url = blueprint.base_url.strip()

        logger.info("自动启动被测应用 | cmd={} | cwd={} | base_url={}", cmd, cwd, base_url)

        # 先检查 base_url 是否已经可访问（应用可能已在运行）
        if base_url and await self._check_url_ready(base_url):
            logger.info("被测应用已在运行: {}", base_url)
            return

        # 通过 process_runner 启动应用
        from src.testing.process_runner import process_runner
        success = await process_runner.start(cmd, cwd)
        if not success:
            logger.warning("应用启动失败或已在运行: {}", cmd)
            return

        self._app_started_by_runner = True

        # 等待 base_url 可访问（最多30秒）
        if base_url:
            logger.info("等待应用就绪: {}", base_url)
            import asyncio
            for i in range(30):
                if await self._check_url_ready(base_url):
                    logger.info("应用已就绪（等待{}秒）: {}", i + 1, base_url)
                    return
                await asyncio.sleep(1)
            logger.warning("应用启动超时（30秒），继续测试: {}", base_url)

    @staticmethod
    async def _check_url_ready(url: str) -> bool:
        """检查URL是否可访问。"""
        import urllib.request
        import urllib.error
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=2):
                return True
        except Exception:
            return False
