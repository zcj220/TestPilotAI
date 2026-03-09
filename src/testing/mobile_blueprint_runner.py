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
    ) -> None:
        self._ctrl = controller
        self._ai = ai_client
        self._on_screenshot = on_screenshot
        self._on_step = on_step

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

        for page_idx, page in enumerate(blueprint.pages):
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
                logger.info("── 场景: {} ──", scenario.name)

                for step_def in scenario.steps:
                    step_num += 1
                    desc = step_def.description or step_def.action

                    if self._on_step:
                        await self._on_step(step_num, "start", desc)

                    result, bug = await self._execute_step(
                        step_num, step_def, page, blueprint
                    )
                    all_results.append(result)

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

            elif step_def.action == "click":
                await self._ctrl.tap(target)

            elif step_def.action == "fill":
                await self._ctrl.input_text(target, value)

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
                text = await self._ctrl.get_text(target)
                if is_formula(value):
                    formula_result = validate_formula(value, text)
                    if not formula_result.passed:
                        elapsed = time.time() - start
                        bug = BugReport(
                            severity=BugSeverity.HIGH,
                            category="计算验证失败",
                            title=f"数值计算错误: {target}",
                            description=formula_result.detail,
                            location=target or "",
                            reproduction=f"检查元素 {target}，公式={value}",
                            screenshot_path=None,
                            step_number=step_num,
                        )
                        return StepResult(
                            step=step_num, action=action_type, description=desc,
                            status=StepStatus.FAILED, duration_seconds=elapsed,
                            error_message=formula_result.detail,
                        ), bug
                elif value and value not in text:
                    elapsed = time.time() - start
                    bug = BugReport(
                        severity=BugSeverity.HIGH,
                        category="文本断言失败",
                        title=f"元素文本不匹配: {target}",
                        description=f"预期包含'{value}'，实际为'{text}'",
                        location=target or "",
                        reproduction=f"检查元素 {target} 的文本内容",
                        screenshot_path=None,
                        step_number=step_num,
                    )
                    return StepResult(
                        step=step_num, action=action_type, description=desc,
                        status=StepStatus.FAILED, duration_seconds=elapsed,
                        error_message=f"文本断言失败: 预期'{value}'，实际'{text}'",
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
            f"# 手机蓝本测试报告",
            f"",
            f"- **应用**: {blueprint.app_name}",
            f"- **设备**: {self._ctrl.device_info.name}",
            f"- **通过率**: {pass_rate:.0f}%（{report.passed_steps}/{report.total_steps}）",
            f"- **Bug数**: {len(bugs)}",
            f"- **耗时**: {report.duration_seconds:.1f}s",
            f"",
        ]

        if bugs:
            lines.append(f"## ⚠️ 发现 {len(bugs)} 个Bug")
            lines.append("")
            for i, bug in enumerate(bugs, 1):
                lines.append(f"### Bug {i}: {bug.title}")
                lines.append(f"- **严重程度**: {bug.severity.value}")
                lines.append(f"- **位置**: {bug.location}")
                lines.append(f"- **描述**: {bug.description[:300]}")
                lines.append("")

        lines.append("## 步骤详情")
        lines.append("")
        for r in results:
            icon = "✅" if r.status == StepStatus.PASSED else ("❌" if r.status == StepStatus.FAILED else "⚠️")
            lines.append(f"{icon} 步骤{r.step}: {r.description} ({r.duration_seconds:.2f}s)")
            if r.error_message:
                lines.append(f"   > {r.error_message[:120]}")

        return "\n".join(lines)
