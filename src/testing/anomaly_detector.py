"""
通用异常检测器

在蓝本测试的每一步之后自动运行，检测蓝本未覆盖的通用异常：
1. 页面崩溃/白屏 — body 为空或只有错误文本
2. JS 控制台错误 — console.error 级别日志
3. 网络请求失败 — 关键 API 返回 4xx/5xx
4. 红色错误提示 — 页面上出现 alert/error 类元素
5. 布局异常 — 元素溢出视口、重叠等

设计原则：
- 不依赖 AI，纯 Playwright 检测，零成本、毫秒级
- 检测结果附加到步骤结果中，和蓝本预期验证并列
- 即使蓝本步骤通过，异常检测发现问题也会上报
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from loguru import logger
from playwright.async_api import Page


class AnomalyType(str, Enum):
    """异常类型枚举。"""
    BLANK_PAGE = "blank_page"
    JS_ERROR = "js_error"
    NETWORK_ERROR = "network_error"
    ERROR_ELEMENT = "error_element"
    LAYOUT_OVERFLOW = "layout_overflow"


class AnomalySeverity(str, Enum):
    """异常严重度。"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Anomaly:
    """一条检测到的异常。"""
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    title: str
    detail: str
    source: str = "anomaly_detector"


@dataclass
class AnomalyReport:
    """单步的异常检测报告。"""
    anomalies: list[Anomaly] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return len(self.anomalies) > 0

    @property
    def critical_count(self) -> int:
        return sum(1 for a in self.anomalies if a.severity == AnomalySeverity.CRITICAL)


class AnomalyDetector:
    """通用异常检测器。

    典型使用：
        detector = AnomalyDetector(page)
        detector.start_monitoring()  # 测试开始前
        ...执行步骤...
        report = await detector.check()  # 每步之后
    """

    # 常见的错误提示 CSS 选择器
    ERROR_SELECTORS = [
        ".error", ".error-message", ".error-text",
        ".alert-danger", ".alert-error",
        "[role='alert']",
        ".toast-error", ".notification-error",
        "#error", "#error-message",
    ]

    # 常见的错误关键词（页面文本中出现则报告）
    ERROR_KEYWORDS = [
        "uncaught exception", "unhandled error",
        "something went wrong", "internal server error",
        "application error", "fatal error",
        "cannot read propert",  # "cannot read properties of undefined/null"
        "is not defined", "is not a function",
        "404 not found", "500 internal",
    ]

    def __init__(self, page: Page) -> None:
        self._page = page
        self._console_errors: list[str] = []
        self._network_errors: list[dict] = []
        self._monitoring = False
        self._reported_errors: set[str] = set()  # 已报告的异常指纹，避免重复
        self._suppress_error_texts: set[str] = set()  # 蓝本故意验证的错误文本，检测时跳过

    def suppress_error_text(self, text: str) -> None:
        """标记某段文本为蓝本预期的错误提示，异常检测时跳过。

        当assert_text步骤故意验证错误提示（如'用户名或密码错误'）并通过时，
        调用此方法避免异常检测器误报。
        """
        if text:
            self._suppress_error_texts.add(text.strip())

    def start_monitoring(self) -> None:
        """开始监控控制台错误和网络失败。在测试开始前调用一次。"""
        if self._monitoring:
            return

        self._console_errors = []
        self._network_errors = []

        # 监听 console.error
        self._page.on("console", self._on_console)
        # 监听网络响应失败
        self._page.on("response", self._on_response)
        # 监听页面崩溃
        self._page.on("pageerror", self._on_page_error)

        self._monitoring = True
        logger.debug("异常检测器已启动监控")

    def stop_monitoring(self) -> None:
        """停止监控。"""
        if not self._monitoring:
            return
        try:
            self._page.remove_listener("console", self._on_console)
            self._page.remove_listener("response", self._on_response)
            self._page.remove_listener("pageerror", self._on_page_error)
        except Exception:
            pass
        self._monitoring = False

    def _on_console(self, msg) -> None:
        """控制台消息回调。"""
        if msg.type == "error":
            text = msg.text[:500]
            self._console_errors.append(text)

    def _on_response(self, response) -> None:
        """网络响应回调。"""
        if response.status >= 400:
            self._network_errors.append({
                "url": response.url[:200],
                "status": response.status,
            })

    def _on_page_error(self, error) -> None:
        """页面未捕获异常回调。"""
        self._console_errors.append(f"[PageError] {str(error)[:500]}")

    async def check(self) -> AnomalyReport:
        """执行所有异常检测，返回报告。每个步骤执行后调用。"""
        report = AnomalyReport()

        # 1. 白屏/崩溃检测
        await self._check_blank_page(report)

        # 2. JS 控制台错误
        self._check_console_errors(report)

        # 3. 网络请求失败
        self._check_network_errors(report)

        # 4. 页面上的错误元素
        await self._check_error_elements(report)

        # 5. 布局溢出
        await self._check_layout_overflow(report)

        # 去重：过滤掉已报告过的异常
        new_anomalies = []
        for a in report.anomalies:
            fingerprint = f"{a.anomaly_type}:{a.title}:{a.detail[:80]}"
            if fingerprint not in self._reported_errors:
                self._reported_errors.add(fingerprint)
                new_anomalies.append(a)
        report.anomalies = new_anomalies

        if report.has_issues:
            logger.info("异常检测发现 {} 个新问题（严重:{}）",
                       len(report.anomalies), report.critical_count)

        return report

    def drain_errors(self) -> None:
        """清空累积的错误，每步检查后调用避免重复报告。"""
        self._console_errors.clear()
        self._network_errors.clear()

    async def _check_blank_page(self, report: AnomalyReport) -> None:
        """检测白屏/空页面。"""
        try:
            body_text = await self._page.evaluate("document.body?.innerText?.trim() || ''")
            body_html = await self._page.evaluate("document.body?.innerHTML?.trim() || ''")

            if len(body_html) < 10:
                report.anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.BLANK_PAGE,
                    severity=AnomalySeverity.CRITICAL,
                    title="页面空白/崩溃",
                    detail=f"页面 body 内容为空（HTML长度={len(body_html)}）",
                ))
                return

            # 检查是否只有错误文本
            lower_text = body_text.lower()
            for keyword in self.ERROR_KEYWORDS:
                if keyword in lower_text:
                    report.anomalies.append(Anomaly(
                        anomaly_type=AnomalyType.BLANK_PAGE,
                        severity=AnomalySeverity.HIGH,
                        title=f"页面显示错误信息",
                        detail=f"页面文本中发现关键词: '{keyword}'",
                    ))
                    break  # 只报第一个匹配

        except Exception as e:
            logger.debug("白屏检测异常: {}", str(e)[:100])

    def _check_console_errors(self, report: AnomalyReport) -> None:
        """检测 JS 控制台错误。"""
        if not self._console_errors:
            return

        # 去重并只取前5条
        unique_errors = list(dict.fromkeys(self._console_errors))[:5]
        for err in unique_errors:
            severity = AnomalySeverity.HIGH if "[PageError]" in err else AnomalySeverity.MEDIUM
            report.anomalies.append(Anomaly(
                anomaly_type=AnomalyType.JS_ERROR,
                severity=severity,
                title="JS控制台错误",
                detail=err[:300],
            ))

    def _check_network_errors(self, report: AnomalyReport) -> None:
        """检测网络请求失败。"""
        if not self._network_errors:
            return

        # 过滤掉常见的非关键请求（favicon、analytics等）
        skip_patterns = ["favicon", "analytics", "tracking", "hot-update", ".map"]

        for err in self._network_errors[:5]:
            url = err["url"]
            if any(p in url.lower() for p in skip_patterns):
                continue

            severity = AnomalySeverity.HIGH if err["status"] >= 500 else AnomalySeverity.MEDIUM
            report.anomalies.append(Anomaly(
                anomaly_type=AnomalyType.NETWORK_ERROR,
                severity=severity,
                title=f"网络请求失败 HTTP {err['status']}",
                detail=f"URL: {url}",
            ))

    async def _check_error_elements(self, report: AnomalyReport) -> None:
        """检测页面上可见的错误提示元素。"""
        try:
            for selector in self.ERROR_SELECTORS:
                elements = await self._page.query_selector_all(selector)
                for el in elements:
                    visible = await el.is_visible()
                    if not visible:
                        continue
                    text = (await el.text_content() or "").strip()[:200]
                    if not text:
                        continue
                    # 跳过蓝本故意验证的错误文本（如assert_text验证'用户名或密码错误'）
                    if any(suppress in text for suppress in self._suppress_error_texts):
                        continue
                    report.anomalies.append(Anomaly(
                        anomaly_type=AnomalyType.ERROR_ELEMENT,
                        severity=AnomalySeverity.MEDIUM,
                        title=f"页面显示错误提示: {selector}",
                        detail=text,
                    ))
                    return  # 只报第一个可见的错误元素
        except Exception as e:
            logger.debug("错误元素检测异常: {}", str(e)[:100])

    async def _check_layout_overflow(self, report: AnomalyReport) -> None:
        """检测布局溢出（增强版）。

        检测项：
        1. 水平滚动条（body.scrollWidth > window.innerWidth）
        2. 具体溢出元素定位（返回tag+class+尺寸）
        3. CSS overflow:hidden 被截断的内容（scrollWidth > clientWidth）
        """
        try:
            result = await self._page.evaluate("""() => {
                const vw = window.innerWidth;
                const docW = document.documentElement.scrollWidth;

                // 1. 水平滚动条检测
                const hasHScroll = docW > vw + 5;

                // 2. 具体溢出元素定位（超出视口右边界）
                const overflowEls = [];
                const all = document.querySelectorAll('body *');
                for (let i = 0; i < Math.min(all.length, 800); i++) {
                    const el = all[i];
                    const rect = el.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) continue;
                    if (rect.right > vw + 20) {
                        const tag = el.tagName.toLowerCase();
                        const cls = el.className ? ('.' + String(el.className).split(' ')[0]) : '';
                        const id = el.id ? ('#' + el.id) : '';
                        overflowEls.push({
                            selector: tag + id + cls,
                            right: Math.round(rect.right),
                            width: Math.round(rect.width),
                        });
                        if (overflowEls.length >= 5) break;
                    }
                }

                // 3. 内容被截断检测（overflow:hidden + scrollWidth > clientWidth）
                const truncated = [];
                for (let i = 0; i < Math.min(all.length, 800); i++) {
                    const el = all[i];
                    const style = getComputedStyle(el);
                    if (style.overflow === 'hidden' || style.overflowX === 'hidden') {
                        if (el.scrollWidth > el.clientWidth + 5) {
                            const tag = el.tagName.toLowerCase();
                            const cls = el.className ? ('.' + String(el.className).split(' ')[0]) : '';
                            const id = el.id ? ('#' + el.id) : '';
                            truncated.push(tag + id + cls);
                            if (truncated.length >= 3) break;
                        }
                    }
                }

                return {
                    hasHScroll: hasHScroll,
                    docWidth: docW,
                    viewportWidth: vw,
                    overflowEls: overflowEls,
                    truncatedEls: truncated,
                };
            }""")

            # 水平滚动条 → 中等严重度
            if result["hasHScroll"]:
                detail_parts = [f"页面宽度({result['docWidth']}px)超出视口({result['viewportWidth']}px)，出现水平滚动条"]
                if result["overflowEls"]:
                    els = ", ".join(e["selector"] for e in result["overflowEls"])
                    detail_parts.append(f"溢出元素: {els}")
                report.anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.LAYOUT_OVERFLOW,
                    severity=AnomalySeverity.MEDIUM,
                    title="页面水平溢出（出现横向滚动条）",
                    detail="; ".join(detail_parts),
                ))
            elif len(result["overflowEls"]) > 3:
                els = ", ".join(e["selector"] for e in result["overflowEls"])
                report.anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.LAYOUT_OVERFLOW,
                    severity=AnomalySeverity.LOW,
                    title="多个元素超出视口",
                    detail=f"{len(result['overflowEls'])} 个元素溢出: {els}",
                ))

            # 内容被截断（overflow:hidden但内容更宽）
            if result["truncatedEls"]:
                report.anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.LAYOUT_OVERFLOW,
                    severity=AnomalySeverity.LOW,
                    title="内容被截断",
                    detail=f"以下元素内容被hidden截断: {', '.join(result['truncatedEls'])}",
                ))

        except Exception as e:
            logger.debug("布局溢出检测异常: {}", str(e)[:100])
