"""
浏览器控制台与网络错误收集器（v5.1）

在测试过程中自动收集浏览器端信息：
1. console.log/warn/error 输出
2. HTTP 4xx/5xx 响应错误
3. 网络请求失败（CORS、超时、DNS等）
4. JavaScript 未捕获异常

收集到的数据可用于：
- 测试报告中附加前端错误上下文
- AI分析时提供额外线索
- 自动检测前端异常

使用方式：
    collector = ConsoleCollector()
    collector.attach(page)          # 绑定到 Playwright Page
    # ... 执行测试 ...
    errors = collector.get_errors()
    summary = collector.summary()
    collector.detach()
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Callable

from loguru import logger


class LogLevel(str, Enum):
    """控制台日志级别。"""
    LOG = "log"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    DEBUG = "debug"


class NetworkErrorType(str, Enum):
    """网络错误类型。"""
    HTTP_4XX = "http_4xx"           # 客户端错误 (400-499)
    HTTP_5XX = "http_5xx"           # 服务端错误 (500-599)
    CORS = "cors"                   # 跨域错误
    TIMEOUT = "timeout"             # 请求超时
    CONNECTION = "connection"       # 连接失败
    DNS = "dns"                     # DNS 解析失败
    OTHER = "other"                 # 其他网络错误


@dataclass
class ConsoleEntry:
    """控制台日志条目。"""
    level: LogLevel
    text: str
    url: str = ""
    line_number: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_error(self) -> bool:
        return self.level in (LogLevel.ERROR, LogLevel.WARN)


@dataclass
class NetworkError:
    """网络请求错误。"""
    error_type: NetworkErrorType
    url: str
    status: int = 0
    status_text: str = ""
    method: str = "GET"
    detail: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class JsException:
    """JavaScript未捕获异常。"""
    message: str
    url: str = ""
    stack: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ConsoleCollector:
    """浏览器控制台与网络错误收集器。

    绑定到 Playwright Page 对象，自动监听：
    - page.on("console") → 控制台输出
    - page.on("response") → HTTP 响应（筛选4xx/5xx）
    - page.on("requestfailed") → 请求失败（CORS/超时等）
    - page.on("pageerror") → JS 未捕获异常
    """

    def __init__(self, max_entries: int = 500) -> None:
        self._console_logs: list[ConsoleEntry] = []
        self._network_errors: list[NetworkError] = []
        self._js_exceptions: list[JsException] = []
        self._max_entries = max_entries
        self._page = None
        self._attached = False
        # 保存handler引用以便detach
        self._console_handler: Optional[Callable] = None
        self._response_handler: Optional[Callable] = None
        self._request_failed_handler: Optional[Callable] = None
        self._page_error_handler: Optional[Callable] = None

    @property
    def is_attached(self) -> bool:
        return self._attached

    @property
    def console_logs(self) -> list[ConsoleEntry]:
        return list(self._console_logs)

    @property
    def network_errors(self) -> list[NetworkError]:
        return list(self._network_errors)

    @property
    def js_exceptions(self) -> list[JsException]:
        return list(self._js_exceptions)

    def attach(self, page) -> None:
        """绑定到 Playwright Page，开始收集。

        Args:
            page: Playwright Page 对象
        """
        if self._attached:
            self.detach()

        self._page = page

        self._console_handler = lambda msg: self._on_console(msg)
        self._response_handler = lambda resp: self._on_response(resp)
        self._request_failed_handler = lambda req: self._on_request_failed(req)
        self._page_error_handler = lambda err: self._on_page_error(err)

        page.on("console", self._console_handler)
        page.on("response", self._response_handler)
        page.on("requestfailed", self._request_failed_handler)
        page.on("pageerror", self._page_error_handler)

        self._attached = True
        logger.info("控制台收集器已绑定")

    def detach(self) -> None:
        """解绑 Page，停止收集。"""
        if self._page and self._attached:
            try:
                self._page.remove_listener("console", self._console_handler)
                self._page.remove_listener("response", self._response_handler)
                self._page.remove_listener("requestfailed", self._request_failed_handler)
                self._page.remove_listener("pageerror", self._page_error_handler)
            except Exception:
                pass  # 页面可能已关闭

        self._page = None
        self._attached = False
        logger.info("控制台收集器已解绑 | 日志{}条 | 网络错误{}条 | JS异常{}条",
                    len(self._console_logs), len(self._network_errors), len(self._js_exceptions))

    def clear(self) -> None:
        """清空所有收集的数据。"""
        self._console_logs.clear()
        self._network_errors.clear()
        self._js_exceptions.clear()

    # ── 事件处理 ──

    def _on_console(self, msg) -> None:
        """处理 console 消息。"""
        if len(self._console_logs) >= self._max_entries:
            return

        level_map = {
            "log": LogLevel.LOG,
            "info": LogLevel.INFO,
            "warning": LogLevel.WARN,
            "error": LogLevel.ERROR,
            "debug": LogLevel.DEBUG,
        }
        level = level_map.get(msg.type, LogLevel.LOG)

        entry = ConsoleEntry(
            level=level,
            text=msg.text,
            url=msg.location.get("url", "") if hasattr(msg, "location") and msg.location else "",
            line_number=msg.location.get("lineNumber", 0) if hasattr(msg, "location") and msg.location else 0,
        )

        self._console_logs.append(entry)

        if level == LogLevel.ERROR:
            logger.debug("浏览器console.error: {}", msg.text[:200])

    def _on_response(self, response) -> None:
        """处理 HTTP 响应，筛选错误状态码。"""
        if len(self._network_errors) >= self._max_entries:
            return

        status = response.status
        if status < 400:
            return

        error_type = NetworkErrorType.HTTP_5XX if status >= 500 else NetworkErrorType.HTTP_4XX

        error = NetworkError(
            error_type=error_type,
            url=response.url,
            status=status,
            status_text=response.status_text,
            method=response.request.method if response.request else "GET",
        )

        self._network_errors.append(error)
        logger.debug("HTTP错误: {} {} | {}", status, response.url[:100], error_type.value)

    def _on_request_failed(self, request) -> None:
        """处理请求失败（CORS、超时、连接失败等）。"""
        if len(self._network_errors) >= self._max_entries:
            return

        failure = request.failure
        failure_text = failure if isinstance(failure, str) else (failure or "unknown")

        error_type = self._classify_failure(str(failure_text))

        error = NetworkError(
            error_type=error_type,
            url=request.url,
            method=request.method,
            detail=str(failure_text)[:500],
        )

        self._network_errors.append(error)
        logger.debug("请求失败: {} {} | {} | {}", request.method, request.url[:100], error_type.value, str(failure_text)[:100])

    def _on_page_error(self, error) -> None:
        """处理 JavaScript 未捕获异常。"""
        if len(self._js_exceptions) >= self._max_entries:
            return

        exc = JsException(
            message=str(error)[:1000],
            stack=getattr(error, "stack", "")[:2000] if hasattr(error, "stack") else "",
        )

        self._js_exceptions.append(exc)
        logger.debug("JS异常: {}", str(error)[:200])

    @staticmethod
    def _classify_failure(failure_text: str) -> NetworkErrorType:
        """根据失败信息分类网络错误类型。"""
        text = failure_text.lower().replace("_", " ")

        if "cors" in text or "cross-origin" in text or "access-control" in text:
            return NetworkErrorType.CORS
        if "timeout" in text or "timed out" in text:
            return NetworkErrorType.TIMEOUT
        if "dns" in text or "name not resolved" in text or "getaddrinfo" in text:
            return NetworkErrorType.DNS
        if "connection" in text or "refused" in text or "reset" in text or "econnrefused" in text:
            return NetworkErrorType.CONNECTION

        return NetworkErrorType.OTHER

    # ── 查询方法 ──

    def get_errors(self) -> list[ConsoleEntry]:
        """获取所有 console.error 和 console.warn 级别的日志。"""
        return [e for e in self._console_logs if e.is_error]

    def get_errors_by_type(self, error_type: NetworkErrorType) -> list[NetworkError]:
        """按类型筛选网络错误。"""
        return [e for e in self._network_errors if e.error_type == error_type]

    def get_context_for_step(self, step_number: int, window: int = 5) -> dict:
        """获取某个测试步骤附近的上下文信息。

        返回最近 N 条日志/错误，用于AI分析时提供额外线索。

        Args:
            step_number: 步骤编号（仅用于日志标识）
            window: 返回最近 N 条记录

        Returns:
            包含 console_logs, network_errors, js_exceptions 的字典
        """
        return {
            "step": step_number,
            "console_logs": [
                {"level": e.level.value, "text": e.text[:200]}
                for e in self._console_logs[-window:]
            ],
            "network_errors": [
                {"type": e.error_type.value, "url": e.url[:200], "status": e.status, "detail": e.detail[:200]}
                for e in self._network_errors[-window:]
            ],
            "js_exceptions": [
                {"message": e.message[:200]}
                for e in self._js_exceptions[-window:]
            ],
        }

    def summary(self) -> dict:
        """生成收集数据摘要。"""
        error_type_counts = {}
        for e in self._network_errors:
            error_type_counts[e.error_type.value] = error_type_counts.get(e.error_type.value, 0) + 1

        console_level_counts = {}
        for e in self._console_logs:
            console_level_counts[e.level.value] = console_level_counts.get(e.level.value, 0) + 1

        return {
            "total_console_logs": len(self._console_logs),
            "total_network_errors": len(self._network_errors),
            "total_js_exceptions": len(self._js_exceptions),
            "console_by_level": console_level_counts,
            "network_by_type": error_type_counts,
            "has_critical_errors": (
                console_level_counts.get("error", 0) > 0
                or len(self._js_exceptions) > 0
                or error_type_counts.get("http_5xx", 0) > 0
            ),
        }
