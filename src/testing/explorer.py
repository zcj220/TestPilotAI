"""
意外模式：快速扫描探索器（v1.x）

不依赖蓝本，自动发现页面可交互元素并快速操作，
批量截图后一次性交给AI分析，发现蓝本覆盖不到的意外Bug。

设计思路（解决"探索太慢"问题）：
1. Playwright 直接抓取所有可交互元素（按钮、链接、输入框等）
2. 快速依次操作：点击按钮、填写输入框，每步只截图不调AI
3. 全部操作完成后，所有截图+操作日志打包，一次性发AI分析
4. AI只调用1次，整个流程几秒到十几秒

触发方式：
- MCP: run_quick_test(url, focus="核心功能")
- API: POST /api/v1/test/explore
"""

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from src.browser.automator import BrowserAutomator
from src.core.ai_client import AIClient
from src.testing.anomaly_detector import AnomalyDetector
from src.testing.models import BugReport, BugSeverity, StepResult, StepStatus, ActionType, TestReport


@dataclass
class ExploreAction:
    """一次探索操作的记录。"""
    step: int
    action: str
    target: str
    description: str
    screenshot_path: str = ""
    duration_seconds: float = 0.0
    error: str = ""


class PageExplorer:
    """快速页面探索器。

    典型使用：
        explorer = PageExplorer(browser, ai_client)
        report = await explorer.explore("http://localhost:3000", description="Todo应用")
    """

    # 可交互元素的选择器（按优先级排序）
    INTERACTIVE_SELECTORS = [
        "button:visible",
        "a[href]:visible",
        "input:visible",
        "select:visible",
        "textarea:visible",
        "[role='button']:visible",
        "[onclick]:visible",
    ]

    # 输入框的智能填充值
    DEFAULT_INPUTS = {
        "email": "test@example.com",
        "password": "Test1234!",
        "tel": "13800138000",
        "number": "42",
        "search": "测试搜索",
        "url": "https://example.com",
        "date": "2026-03-04",
    }
    DEFAULT_TEXT = "TestPilot自动探索"

    MAX_ACTIONS = 15  # 单次探索最多操作数

    def __init__(
        self,
        browser: BrowserAutomator,
        ai_client: Optional[AIClient] = None,
    ) -> None:
        self._browser = browser
        self._ai = ai_client

    async def explore(
        self,
        url: str,
        description: str = "",
        max_actions: int = 0,
    ) -> TestReport:
        """快速探索页面。

        Args:
            url: 目标URL
            description: 应用描述（帮助AI理解上下文）
            max_actions: 最大操作数（0=使用默认值）

        Returns:
            TestReport: 探索测试报告
        """
        limit = max_actions or self.MAX_ACTIONS
        report = TestReport(test_name=f"快速探索-{url}", url=url)
        actions: list[ExploreAction] = []

        logger.info("════════════════════════════════════════════════════════════")
        logger.info("快速探索开始 | URL={} | 最大操作={}", url, limit)

        # 1. 导航到目标页面
        try:
            await self._browser.navigate(url)
            await asyncio.sleep(1)  # 等待页面稳定
        except Exception as e:
            logger.error("导航失败: {}", e)
            report.report_markdown = f"# 探索失败\n\n无法打开 {url}: {e}"
            return report

        # 2. 启动异常检测器
        detector = AnomalyDetector(self._browser.page)
        detector.start_monitoring()

        # 3. 初始截图
        init_shot = await self._safe_screenshot("explore_init")
        actions.append(ExploreAction(
            step=0, action="navigate", target=url,
            description="打开目标页面", screenshot_path=init_shot,
        ))

        # 4. 发现并快速操作可交互元素
        step_num = 0
        visited_targets: set[str] = set()

        elements = await self._discover_elements()
        logger.info("发现 {} 个可交互元素，开始快速操作...", len(elements))

        for elem_info in elements:
            if step_num >= limit:
                break

            tag = elem_info.get("tag", "")
            elem_type = elem_info.get("type", "")
            selector = elem_info.get("selector", "")
            text = elem_info.get("text", "")[:30]

            # 去重：同一个选择器不重复操作
            if selector in visited_targets:
                continue
            visited_targets.add(selector)

            step_num += 1
            start = time.time()
            action_desc = ""
            error = ""

            try:
                if tag in ("input", "textarea"):
                    # 输入框：根据类型填充
                    fill_value = self.DEFAULT_INPUTS.get(elem_type, self.DEFAULT_TEXT)
                    await self._browser.fill(selector, fill_value)
                    action_desc = f"填写 {selector} = '{fill_value}'"
                elif tag == "select":
                    # 下拉框：选第一个非空选项
                    await self._safe_select(selector)
                    action_desc = f"选择 {selector}"
                else:
                    # 按钮/链接：点击
                    await self._browser.click(selector)
                    action_desc = f"点击 {selector}" + (f" ({text})" if text else "")
                    await asyncio.sleep(0.5)  # 点击后短暂等待

            except Exception as e:
                error = str(e)[:100]
                action_desc = f"操作失败 {selector}: {error}"

            # 每步截图
            shot = await self._safe_screenshot(f"explore_step{step_num}")
            elapsed = time.time() - start

            actions.append(ExploreAction(
                step=step_num,
                action="fill" if tag in ("input", "textarea") else "click",
                target=selector,
                description=action_desc,
                screenshot_path=shot,
                duration_seconds=elapsed,
                error=error,
            ))

            logger.info("  [{}] {} | {:.1f}s{}", step_num, action_desc[:60], elapsed,
                        f" ⚠{error[:30]}" if error else "")

        # 5. 异常检测汇总
        anomaly_report = await detector.check()
        detector.stop_monitoring()

        # 6. AI批量分析（一次调用）
        ai_bugs = []
        if self._ai and actions:
            ai_bugs = await self._batch_ai_analysis(url, description, actions)

        # 7. 合并异常检测Bug和AI分析Bug
        all_bugs = ai_bugs[:]
        for anomaly in anomaly_report.anomalies:
            all_bugs.append(BugReport(
                severity=BugSeverity.MEDIUM,
                category=f"蓝本外异常-{anomaly.anomaly_type.value}",
                title=anomaly.title,
                description=anomaly.detail,
                location=url,
            ))

        # 8. 组装报告
        step_results = []
        for a in actions:
            status = StepStatus.PASSED if not a.error else StepStatus.ERROR
            try:
                action_type = ActionType(a.action)
            except ValueError:
                action_type = ActionType.SCREENSHOT
            step_results.append(StepResult(
                step=a.step,
                action=action_type,
                description=a.description,
                status=status,
                duration_seconds=a.duration_seconds,
                screenshot_path=a.screenshot_path,
                error_message=a.error or None,
            ))

        report.step_results = step_results
        report.bugs = all_bugs
        report.total_steps = len(step_results)
        report.passed_steps = sum(1 for r in step_results if r.status == StepStatus.PASSED)
        report.failed_steps = sum(1 for r in step_results if r.status == StepStatus.FAILED)
        report.error_steps = sum(1 for r in step_results if r.status == StepStatus.ERROR)
        report.report_markdown = self._generate_markdown(url, description, actions, all_bugs, report)

        logger.info("快速探索完成 | 操作={} | Bug={}", len(actions), len(all_bugs))
        return report

    async def _discover_elements(self) -> list[dict]:
        """发现页面上所有可交互元素，返回元素信息列表。"""
        try:
            elements = await self._browser.page.evaluate("""() => {
                const results = [];
                const seen = new Set();

                // 按钮
                document.querySelectorAll('button, [role="button"], [type="submit"], [type="button"]').forEach(el => {
                    if (!el.offsetParent && el.style.display !== 'contents') return;
                    const id = el.id ? '#' + el.id : null;
                    const cls = el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).join('.') : null;
                    const selector = id || cls || `button:nth-of-type(${results.filter(r => r.tag === 'button').length + 1})`;
                    if (seen.has(selector)) return;
                    seen.add(selector);
                    results.push({ tag: 'button', type: el.type || '', selector, text: (el.textContent || '').trim().substring(0, 50) });
                });

                // 输入框
                document.querySelectorAll('input:not([type="hidden"]), textarea').forEach(el => {
                    if (!el.offsetParent && el.style.display !== 'contents') return;
                    const id = el.id ? '#' + el.id : null;
                    const name = el.name ? `[name="${el.name}"]` : null;
                    const placeholder = el.placeholder ? `[placeholder="${el.placeholder}"]` : null;
                    const selector = id || name || placeholder || `input:nth-of-type(${results.filter(r => r.tag === 'input').length + 1})`;
                    if (seen.has(selector)) return;
                    seen.add(selector);
                    results.push({ tag: el.tagName.toLowerCase(), type: el.type || 'text', selector, text: '' });
                });

                // 下拉框
                document.querySelectorAll('select').forEach(el => {
                    if (!el.offsetParent) return;
                    const id = el.id ? '#' + el.id : null;
                    const name = el.name ? `select[name="${el.name}"]` : null;
                    const selector = id || name || `select:nth-of-type(${results.filter(r => r.tag === 'select').length + 1})`;
                    if (seen.has(selector)) return;
                    seen.add(selector);
                    results.push({ tag: 'select', type: '', selector, text: '' });
                });

                // 链接（只取前几个有意义的）
                document.querySelectorAll('a[href]').forEach(el => {
                    if (!el.offsetParent) return;
                    const href = el.getAttribute('href') || '';
                    if (href === '#' || href.startsWith('javascript:') || href.startsWith('mailto:')) return;
                    const id = el.id ? '#' + el.id : null;
                    const selector = id || `a[href="${href}"]`;
                    if (seen.has(selector)) return;
                    seen.add(selector);
                    results.push({ tag: 'a', type: '', selector, text: (el.textContent || '').trim().substring(0, 50) });
                });

                return results.slice(0, 30);
            }""")
            return elements
        except Exception as e:
            logger.warning("元素发现失败: {}", str(e)[:100])
            return []

    async def _safe_screenshot(self, name: str) -> str:
        """安全截图，失败返回空字符串。"""
        try:
            path = await self._browser.screenshot(name)
            return str(path)
        except Exception:
            return ""

    async def _safe_select(self, selector: str) -> None:
        """安全选择下拉框第一个非空选项。"""
        try:
            options = await self._browser.page.evaluate(f"""() => {{
                const el = document.querySelector('{selector}');
                if (!el) return [];
                return Array.from(el.options).filter(o => o.value).map(o => o.value).slice(0, 1);
            }}""")
            if options:
                await self._browser.select_option(selector, options[0])
        except Exception:
            pass

    async def _batch_ai_analysis(
        self,
        url: str,
        description: str,
        actions: list[ExploreAction],
    ) -> list[BugReport]:
        """批量截图+操作日志一次性发AI分析。"""
        # 构建操作日志
        log_lines = [f"目标URL: {url}", f"应用描述: {description or '未知'}", ""]
        for a in actions:
            status = "✓" if not a.error else f"✗ {a.error}"
            log_lines.append(f"步骤{a.step}: {a.description} [{status}]")

        operation_log = "\n".join(log_lines)

        # 找最后一张有效截图
        last_screenshot = ""
        for a in reversed(actions):
            if a.screenshot_path:
                last_screenshot = a.screenshot_path
                break

        if not last_screenshot:
            return []

        prompt = (
            f"我在测试一个Web应用，以下是我的自动探索操作记录：\n\n"
            f"{operation_log}\n\n"
            f"这是探索结束后的页面截图。请分析：\n"
            f"1. 页面是否有明显的Bug或异常（崩溃、报错、布局破坏等）\n"
            f"2. 是否有不符合常规用户预期的行为\n"
            f"3. 操作记录中的错误是否反映了真实的Bug\n\n"
            f"如果发现Bug，请按以下JSON格式返回：\n"
            f'{{"bugs": [{{"title": "Bug标题", "severity": "high/medium/low", "description": "描述"}}]}}\n\n'
            f"如果没有发现Bug，返回：\n"
            f'{{"bugs": []}}'
        )

        try:
            response = self._ai.analyze_screenshot(last_screenshot, prompt)
            return self._parse_ai_bugs(response, url)
        except Exception as e:
            logger.warning("AI批量分析失败: {}", str(e)[:100])
            return []

    def _parse_ai_bugs(self, response: str, url: str) -> list[BugReport]:
        """从AI响应中解析Bug列表。"""
        import json

        try:
            # 尝试提取JSON
            start = response.find("{")
            end = response.rfind("}") + 1
            if start < 0 or end <= 0:
                return []
            data = json.loads(response[start:end])
            bugs_data = data.get("bugs", [])

            severity_map = {"high": BugSeverity.HIGH, "medium": BugSeverity.MEDIUM, "low": BugSeverity.LOW}

            bugs = []
            for b in bugs_data:
                if not b.get("title"):
                    continue
                bugs.append(BugReport(
                    severity=severity_map.get(b.get("severity", "medium"), BugSeverity.MEDIUM),
                    category="AI探索发现",
                    title=b["title"],
                    description=b.get("description", ""),
                    location=url,
                ))
            return bugs

        except (json.JSONDecodeError, KeyError, TypeError):
            return []

    def _generate_markdown(
        self,
        url: str,
        description: str,
        actions: list[ExploreAction],
        bugs: list[BugReport],
        report: TestReport,
    ) -> str:
        """生成探索报告Markdown。"""
        lines = [
            f"# 快速探索报告",
            f"",
            f"- **模式**：意外模式（AI快速扫描）",
            f"- **目标URL**：{url}",
            f"- **应用描述**：{description or '未提供'}",
            f"- **操作数**：{len(actions)}",
            f"- **发现Bug**：{len(bugs)}",
            f"",
            f"## 探索操作记录",
            f"| # | 操作 | 说明 | 耗时 |",
            f"|---|------|------|------|",
        ]

        for a in actions:
            status = "✓" if not a.error else f"⚠ {a.error[:20]}"
            lines.append(f"| {a.step} | {a.action} | {a.description[:40]} | {a.duration_seconds:.1f}s |")

        if bugs:
            lines.extend([
                "",
                "## 发现的Bug",
                "| 严重度 | 标题 | 说明 |",
                "|--------|------|------|",
            ])
            for bug in bugs:
                lines.append(f"| {bug.severity.value} | {bug.title} | {bug.description[:50]} |")

        lines.extend([
            "",
            "---",
            "*报告由 TestPilot AI 快速探索模式生成*",
        ])

        return "\n".join(lines)
