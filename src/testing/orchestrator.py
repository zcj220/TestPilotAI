"""
测试编排引擎

TestOrchestrator 是 TestPilot AI 的核心大脑，协调完整的测试流程：
1. 接收测试任务（URL + 描述）→ AI生成测试脚本
2. 解析脚本为可执行步骤 → 逐步执行浏览器操作
3. 每步截图 → AI视觉分析 → Bug检测
4. 汇总生成测试报告
"""

import json
import time
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from src.api.websocket import ws_manager
from src.billing.models import OperationType
from src.billing.tracker import CreditTracker
from src.browser.automator import BrowserAutomator
from src.core.ai_client import AIClient
from src.core.exceptions import BrowserError, BrowserNavigationError
from src.memory.store import MemoryStore
from src.repair.loop import RepairLoop
from src.repair.models import RepairReport
from src.testing.cross_validator import CrossValidator
from src.core.prompts import (
    PROMPT_ANALYZE_SCREENSHOT,
    PROMPT_DETECT_BUGS,
    PROMPT_GENERATE_REPORT,
    PROMPT_GENERATE_TEST,
    SYSTEM_BUG_DETECTOR,
    SYSTEM_REPORT_GENERATOR,
    SYSTEM_SCREENSHOT_ANALYZER,
    SYSTEM_TEST_GENERATOR,
)
from src.testing.models import (
    ActionType,
    BugReport,
    BugSeverity,
    ScreenshotAnalysis,
    StepResult,
    StepStatus,
    TestReport,
    TestScript,
    TestStep,
)
from src.testing.parser import (
    parse_bug_detection,
    parse_screenshot_analysis,
    parse_test_script,
)


class TestOrchestrator:
    """测试编排引擎。

    典型使用：
        orchestrator = TestOrchestrator(ai_client, browser)
        report = await orchestrator.run_test(
            url="http://localhost:3000",
            description="React Todo应用",
            focus="增删改查功能",
        )
    """

    def __init__(
        self,
        ai_client: AIClient,
        browser: BrowserAutomator,
        memory: Optional[MemoryStore] = None,
        enable_cross_validation: bool = True,
    ) -> None:
        self._ai = ai_client
        self._browser = browser
        self._memory = memory
        self._cross_validator = CrossValidator(ai_client) if enable_cross_validation else None
        self._last_script: Optional[TestScript] = None
        self._tracker = CreditTracker()

    async def run_test(
        self,
        url: str,
        description: str = "",
        focus: str = "核心功能",
        reasoning_effort: Optional[str] = None,
        auto_repair: bool = False,
        project_path: str = "",
    ) -> TestReport:
        """执行完整的自动化测试流程。"""
        logger.info("═" * 60)
        logger.info("开始测试任务 | URL={} | 重点={}", url, focus)
        await ws_manager.send_log(f"开始测试: {url} | 重点: {focus}")

        self._tracker.start_test(f"测试-{description or url}", url)

        report = TestReport(
            test_name=f"测试-{description or url}",
            url=url,
        )

        # 阶段1：AI生成测试脚本
        logger.info("【阶段1/4】AI 正在生成测试脚本...")
        await ws_manager.send_log("【阶段1】AI 正在生成测试脚本...")
        script = self._generate_test_script(url, description, focus, reasoning_effort)
        self._tracker.record(OperationType.GENERATE_SCRIPT, "生成测试脚本")
        if script is None:
            report.end_time = datetime.now(timezone.utc)
            report.report_markdown = "# 测试失败\n\nAI 无法生成测试脚本。"
            return report

        self._last_script = script
        report.test_name = script.test_name
        report.total_steps = len(script.steps)

        # 阶段2：逐步执行
        logger.info("【阶段2/5】执行 {} 个测试步骤...", len(script.steps))
        await ws_manager.send_log(f"【阶段2】开始执行 {len(script.steps)} 个测试步骤")
        step_results = await self._execute_steps(script.steps, reasoning_effort)

        # 阶段3：交叉验证（多轮分析提升可信度）
        if self._cross_validator:
            logger.info("【阶段3/5】交叉验证中...")
            await ws_manager.send_log("【阶段3】交叉验证中...")
            for i, result in enumerate(step_results):
                step = script.steps[i] if i < len(script.steps) else None
                if result.screenshot_path and step and step.expected:
                    step_results[i] = self._cross_validator.validate_step(
                        result, step.expected,
                    )

        report.step_results = step_results

        for r in step_results:
            if r.status == StepStatus.PASSED:
                report.passed_steps += 1
            elif r.status == StepStatus.FAILED:
                report.failed_steps += 1
            elif r.status == StepStatus.ERROR:
                report.error_steps += 1

        # 阶段4：Bug 检测
        logger.info("【阶段4/5】AI 正在检测 Bug...")
        await ws_manager.send_log("【阶段4】AI 正在检测 Bug...")
        report.bugs = await self._detect_bugs(step_results, reasoning_effort)
        for bug in report.bugs:
            await ws_manager.send_bug_found(bug.title, bug.severity.value)

        # 阶段5：生成报告
        logger.info("【阶段5/5】生成测试报告...")
        await ws_manager.send_log("【阶段5】生成测试报告...")
        report.end_time = datetime.now(timezone.utc)
        report.report_markdown = self._generate_report(report, reasoning_effort)
        self._tracker.record(OperationType.GENERATE_REPORT, "生成测试报告")

        logger.info(
            "测试完成 | 通过={}/{} | Bug={} | 耗时={:.1f}秒",
            report.passed_steps, report.total_steps,
            len(report.bugs), report.duration_seconds,
        )

        # 账单结算
        bill = self._tracker.finish_test()
        if bill:
            await ws_manager.send_log(
                f"积分消耗: {bill.total_credits} 积分 | 估算成本: {bill.total_api_cost:.3f}元"
            )

        # 保存到记忆系统
        if self._memory:
            self._save_to_memory(report)

        # 阶段6（可选）：自动修复闭环
        if auto_repair and report.bugs and project_path:
            logger.info("【阶段6】自动修复闭环...")
            report.repair_report = await self._run_repair_loop(
                report, project_path, script, reasoning_effort,
            )

        return report

    def _generate_test_script(
        self, url: str, description: str, focus: str,
        reasoning_effort: Optional[str],
    ) -> Optional[TestScript]:
        """调用 AI 生成测试脚本。"""
        prompt = PROMPT_GENERATE_TEST.format(
            url=url, description=description or "未提供描述", focus=focus,
        )
        try:
            resp = self._ai.chat(prompt, SYSTEM_TEST_GENERATOR, reasoning_effort)
            return parse_test_script(resp)
        except Exception as e:
            logger.error("测试脚本生成失败: {}", e)
            return None

    async def _execute_steps(
        self, steps: list[TestStep], reasoning_effort: Optional[str],
    ) -> list[StepResult]:
        """逐步执行测试。"""
        results: list[StepResult] = []
        nav_failed = False

        for step in steps:
            if nav_failed and step.action != ActionType.NAVIGATE:
                results.append(StepResult(
                    step=step.step, action=step.action,
                    status=StepStatus.SKIPPED, description=step.description,
                    error_message="导航失败，跳过后续步骤",
                ))
                continue

            logger.info("  [步骤{}/{}] {} | {}", step.step, len(steps),
                       step.action.value, step.description)
            await ws_manager.send_step_start(step.step, step.description)

            t0 = time.time()
            result = await self._execute_single_step(step, reasoning_effort)
            result.duration_seconds = time.time() - t0
            results.append(result)
            self._tracker.record(OperationType.EXECUTE_STEP, f"步骤{step.step}: {step.description}")

            if step.action == ActionType.NAVIGATE and result.status in (
                StepStatus.FAILED, StepStatus.ERROR,
            ):
                nav_failed = True

            icon = {"passed": "✓", "failed": "✗", "error": "⚠", "skipped": "→"
                   }.get(result.status.value, "?")
            logger.info("  {} 步骤{} {} | {:.1f}秒", icon, step.step,
                       result.status.value, result.duration_seconds)
            await ws_manager.send_step_done(step.step, result.status.value, step.description)

        return results

    async def _execute_single_step(
        self, step: TestStep, reasoning_effort: Optional[str],
    ) -> StepResult:
        """执行单个步骤：浏览器操作 → 截图 → AI分析。"""
        result = StepResult(
            step=step.step, action=step.action,
            status=StepStatus.RUNNING, description=step.description,
        )
        try:
            await self._perform_action(step)
            ss = await self._browser.screenshot(name=f"step{step.step}_{step.action.value}")
            result.screenshot_path = str(ss)

            if step.expected:
                analysis = self._analyze_screenshot(
                    str(ss), step.description, step.expected, reasoning_effort,
                )
                result.analysis = analysis
                result.status = StepStatus.PASSED if analysis.matches_expected else StepStatus.FAILED
                if not analysis.matches_expected:
                    result.error_message = "; ".join(analysis.issues) if analysis.issues else "页面不符合预期"
            else:
                result.status = StepStatus.PASSED

        except BrowserNavigationError as e:
            result.status = StepStatus.FAILED
            result.error_message = str(e)
        except BrowserError as e:
            result.status = StepStatus.ERROR
            result.error_message = str(e)
        except Exception as e:
            result.status = StepStatus.ERROR
            result.error_message = f"意外错误: {e}"

        return result

    async def _perform_action(self, step: TestStep) -> None:
        """执行浏览器操作。"""
        match step.action:
            case ActionType.NAVIGATE:
                await self._browser.navigate(step.target)
            case ActionType.CLICK:
                await self._browser.click(step.target)
            case ActionType.FILL:
                await self._browser.fill(step.target, step.value)
            case ActionType.SELECT:
                await self._browser.select_option(step.target, step.value)
            case ActionType.WAIT:
                await self._browser.wait_for_selector(step.target)
            case ActionType.SCREENSHOT:
                pass
            case ActionType.SCROLL:
                d = step.target or "down"
                px = int(step.value) if step.value else 500
                await self._browser.page.mouse.wheel(0, px if d == "down" else -px)

    def _analyze_screenshot(
        self, path: str, desc: str, expected: str,
        reasoning_effort: Optional[str],
    ) -> ScreenshotAnalysis:
        """AI 视觉分析截图。"""
        prompt = PROMPT_ANALYZE_SCREENSHOT.format(
            step_description=desc, expected=expected,
        )
        try:
            resp = self._ai.analyze_screenshot(
                image_path=path, prompt=prompt,
                system_prompt=SYSTEM_SCREENSHOT_ANALYZER,
                reasoning_effort=reasoning_effort or "low",
            )
            return ScreenshotAnalysis(**parse_screenshot_analysis(resp))
        except Exception as e:
            logger.warning("截图分析失败: {}", e)
            return ScreenshotAnalysis(
                matches_expected=True, confidence=0.0,
                page_description=f"分析失败: {e}",
            )

    async def _detect_bugs(
        self, results: list[StepResult], reasoning_effort: Optional[str],
    ) -> list[BugReport]:
        """对失败步骤做深度 Bug 检测。"""
        bugs: list[BugReport] = []
        failed = [r for r in results
                  if r.status in (StepStatus.FAILED, StepStatus.ERROR) and r.screenshot_path]

        if not failed:
            logger.info("没有失败步骤，跳过 Bug 检测")
            return bugs

        for r in failed:
            prompt = PROMPT_DETECT_BUGS.format(
                page_description=r.description,
                user_action=f"步骤{r.step}: {r.action.value}",
            )
            try:
                resp = self._ai.analyze_screenshot(
                    image_path=r.screenshot_path, prompt=prompt,
                    system_prompt=SYSTEM_BUG_DETECTOR,
                    reasoning_effort=reasoning_effort or "medium",
                )
                data = parse_bug_detection(resp)
                for bd in data.get("bugs_found", []):
                    try:
                        bugs.append(BugReport(
                            severity=BugSeverity(bd.get("severity", "medium")),
                            category=bd.get("category", ""),
                            title=bd.get("title", ""),
                            description=bd.get("description", ""),
                            location=bd.get("location", ""),
                            reproduction=bd.get("reproduction", ""),
                            screenshot_path=r.screenshot_path,
                            step_number=r.step,
                        ))
                    except Exception as e:
                        logger.warning("Bug 解析失败: {}", e)
            except Exception as e:
                logger.warning("步骤 {} Bug 检测失败: {}", r.step, e)

        return bugs

    def _generate_report(
        self, report: TestReport, reasoning_effort: Optional[str],
    ) -> str:
        """AI 生成 Markdown 测试报告。"""
        steps_text = ""
        for r in report.step_results:
            icon = {"passed": "✅", "failed": "❌", "error": "⚠️", "skipped": "⏭️"
                   }.get(r.status.value, "❓")
            steps_text += f"- {icon} 步骤{r.step}: {r.description} [{r.status.value}]"
            if r.error_message:
                steps_text += f" — {r.error_message}"
            steps_text += "\n"

        bugs_text = ""
        if report.bugs:
            for b in report.bugs:
                bugs_text += f"- [{b.severity.value}] {b.title}: {b.description}\n"
        else:
            bugs_text = "无"

        prompt = PROMPT_GENERATE_REPORT.format(
            test_name=report.test_name,
            url=report.url,
            execution_time=f"{report.duration_seconds:.1f}秒",
            steps_results=steps_text,
            bugs_summary=bugs_text,
        )
        try:
            return self._ai.chat(prompt, SYSTEM_REPORT_GENERATOR, reasoning_effort)
        except Exception as e:
            logger.error("报告生成失败: {}", e)
            return self._fallback_report(report)

    def _save_to_memory(self, report: TestReport) -> None:
        """将测试结果保存到记忆系统。"""
        try:
            # 序列化步骤和Bug
            steps_data = []
            for r in report.step_results:
                steps_data.append({
                    "step": r.step, "action": r.action.value,
                    "status": r.status.value, "description": r.description,
                    "error": r.error_message,
                })
            bugs_data = []
            for b in report.bugs:
                bugs_data.append({
                    "severity": b.severity.value, "title": b.title,
                    "description": b.description, "category": b.category,
                })

            self._memory.save_test_result(
                test_name=report.test_name,
                url=report.url,
                total_steps=report.total_steps,
                passed_steps=report.passed_steps,
                failed_steps=report.failed_steps,
                bug_count=len(report.bugs),
                pass_rate=report.pass_rate,
                duration_seconds=report.duration_seconds,
                report_markdown=report.report_markdown,
                steps_json=json.dumps(steps_data, ensure_ascii=False),
                bugs_json=json.dumps(bugs_data, ensure_ascii=False),
            )

            # v1.3：规则压缩提取Bug模式记忆
            from src.memory.compressor import MemoryCompressor
            compressor = MemoryCompressor(self._memory)
            compressor.extract_from_report(report)

        except Exception as e:
            logger.warning("保存到记忆系统失败: {}", e)

    @staticmethod
    def _fallback_report(report: TestReport) -> str:
        """AI报告生成失败时的兜底报告。"""
        lines = [
            f"# 测试报告: {report.test_name}",
            f"\n- **URL**: {report.url}",
            f"- **耗时**: {report.duration_seconds:.1f}秒",
            f"- **通过率**: {report.passed_steps}/{report.total_steps}",
            f"- **Bug数**: {len(report.bugs)}",
            "\n## 步骤结果\n",
        ]
        for r in report.step_results:
            lines.append(f"- 步骤{r.step} [{r.status.value}]: {r.description}")
        if report.bugs:
            lines.append("\n## 发现的Bug\n")
            for b in report.bugs:
                lines.append(f"- **[{b.severity.value}]** {b.title}: {b.description}")
        return "\n".join(lines)

    async def _run_repair_loop(
        self,
        report: TestReport,
        project_path: str,
        script: TestScript,
        reasoning_effort: Optional[str],
    ) -> RepairReport:
        """执行自动修复闭环。"""

        async def retest_steps(step_numbers: list[int]) -> list[StepResult]:
            """重测指定步骤的回调函数。"""
            steps_to_retest = [
                s for s in script.steps if s.step in step_numbers
            ]
            if not steps_to_retest:
                return []
            return await self._execute_steps(steps_to_retest, reasoning_effort)

        loop = RepairLoop(
            ai_client=self._ai,
            project_path=project_path,
            retest_func=retest_steps,
        )
        try:
            return await loop.run(report, reasoning_effort)
        except Exception as e:
            logger.error("修复闭环执行失败: {}", e)
            return RepairReport(
                project_path=project_path,
                total_bugs=len(report.bugs),
                summary=f"修复闭环执行失败: {e}",
            )
