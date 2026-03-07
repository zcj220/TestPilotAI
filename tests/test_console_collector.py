"""
浏览器控制台与网络错误收集器测试（v5.1）
"""

from unittest.mock import MagicMock, PropertyMock

import pytest

from src.browser.console_collector import (
    ConsoleCollector,
    ConsoleEntry,
    JsException,
    LogLevel,
    NetworkError,
    NetworkErrorType,
)


class TestConsoleEntry:
    """控制台日志条目测试。"""

    def test_error_entry(self):
        entry = ConsoleEntry(level=LogLevel.ERROR, text="Uncaught TypeError")
        assert entry.is_error is True

    def test_warn_entry(self):
        entry = ConsoleEntry(level=LogLevel.WARN, text="Deprecation warning")
        assert entry.is_error is True

    def test_log_entry(self):
        entry = ConsoleEntry(level=LogLevel.LOG, text="Hello world")
        assert entry.is_error is False

    def test_info_entry(self):
        entry = ConsoleEntry(level=LogLevel.INFO, text="Info msg")
        assert entry.is_error is False

    def test_timestamp_auto_set(self):
        entry = ConsoleEntry(level=LogLevel.LOG, text="test")
        assert entry.timestamp is not None
        assert len(entry.timestamp) > 0


class TestNetworkError:
    """网络错误测试。"""

    def test_http_4xx(self):
        err = NetworkError(
            error_type=NetworkErrorType.HTTP_4XX,
            url="http://example.com/api",
            status=404,
            status_text="Not Found",
        )
        assert err.error_type == NetworkErrorType.HTTP_4XX
        assert err.status == 404

    def test_cors_error(self):
        err = NetworkError(
            error_type=NetworkErrorType.CORS,
            url="http://other.com/api",
            detail="Cross-Origin Request Blocked",
        )
        assert err.error_type == NetworkErrorType.CORS


class TestClassifyFailure:
    """错误分类测试。"""

    def test_cors(self):
        assert ConsoleCollector._classify_failure("CORS error") == NetworkErrorType.CORS
        assert ConsoleCollector._classify_failure("cross-origin request blocked") == NetworkErrorType.CORS
        assert ConsoleCollector._classify_failure("Access-Control-Allow-Origin") == NetworkErrorType.CORS

    def test_timeout(self):
        assert ConsoleCollector._classify_failure("net::ERR_TIMED_OUT") == NetworkErrorType.TIMEOUT
        assert ConsoleCollector._classify_failure("Request timeout") == NetworkErrorType.TIMEOUT

    def test_dns(self):
        assert ConsoleCollector._classify_failure("DNS lookup failed") == NetworkErrorType.DNS
        assert ConsoleCollector._classify_failure("net::ERR_NAME_NOT_RESOLVED") == NetworkErrorType.DNS
        assert ConsoleCollector._classify_failure("getaddrinfo ENOTFOUND") == NetworkErrorType.DNS

    def test_connection(self):
        assert ConsoleCollector._classify_failure("Connection refused") == NetworkErrorType.CONNECTION
        assert ConsoleCollector._classify_failure("ECONNREFUSED") == NetworkErrorType.CONNECTION
        assert ConsoleCollector._classify_failure("Connection reset") == NetworkErrorType.CONNECTION

    def test_other(self):
        assert ConsoleCollector._classify_failure("some unknown error") == NetworkErrorType.OTHER
        assert ConsoleCollector._classify_failure("") == NetworkErrorType.OTHER


class TestConsoleCollectorInit:
    """初始化测试。"""

    def test_default_state(self):
        cc = ConsoleCollector()
        assert not cc.is_attached
        assert cc.console_logs == []
        assert cc.network_errors == []
        assert cc.js_exceptions == []

    def test_custom_max_entries(self):
        cc = ConsoleCollector(max_entries=10)
        assert cc._max_entries == 10


class TestConsoleCollectorAttachDetach:
    """绑定/解绑测试。"""

    def test_attach(self):
        cc = ConsoleCollector()
        page = MagicMock()
        cc.attach(page)

        assert cc.is_attached
        assert page.on.call_count == 4
        event_names = [call[0][0] for call in page.on.call_args_list]
        assert "console" in event_names
        assert "response" in event_names
        assert "requestfailed" in event_names
        assert "pageerror" in event_names

    def test_detach(self):
        cc = ConsoleCollector()
        page = MagicMock()
        cc.attach(page)
        cc.detach()

        assert not cc.is_attached
        assert page.remove_listener.call_count == 4

    def test_double_attach_detaches_first(self):
        cc = ConsoleCollector()
        page1 = MagicMock()
        page2 = MagicMock()
        cc.attach(page1)
        cc.attach(page2)

        # 第一个page应被解绑
        assert page1.remove_listener.call_count == 4
        assert cc.is_attached


class TestOnConsole:
    """控制台消息处理测试。"""

    def test_log_message(self):
        cc = ConsoleCollector()
        msg = MagicMock()
        msg.type = "log"
        msg.text = "Hello world"
        msg.location = None

        cc._on_console(msg)

        assert len(cc.console_logs) == 1
        assert cc.console_logs[0].level == LogLevel.LOG
        assert cc.console_logs[0].text == "Hello world"

    def test_error_message(self):
        cc = ConsoleCollector()
        msg = MagicMock()
        msg.type = "error"
        msg.text = "Uncaught TypeError: x is undefined"
        msg.location = {"url": "http://localhost/app.js", "lineNumber": 42}

        cc._on_console(msg)

        assert len(cc.console_logs) == 1
        assert cc.console_logs[0].level == LogLevel.ERROR
        assert cc.console_logs[0].url == "http://localhost/app.js"
        assert cc.console_logs[0].line_number == 42

    def test_warning_message(self):
        cc = ConsoleCollector()
        msg = MagicMock()
        msg.type = "warning"
        msg.text = "Deprecation warning"
        msg.location = None

        cc._on_console(msg)

        assert cc.console_logs[0].level == LogLevel.WARN

    def test_max_entries_limit(self):
        cc = ConsoleCollector(max_entries=3)
        for i in range(5):
            msg = MagicMock()
            msg.type = "log"
            msg.text = f"msg {i}"
            msg.location = None
            cc._on_console(msg)

        assert len(cc.console_logs) == 3


class TestOnResponse:
    """HTTP响应处理测试。"""

    def test_success_ignored(self):
        cc = ConsoleCollector()
        resp = MagicMock()
        resp.status = 200
        cc._on_response(resp)
        assert len(cc.network_errors) == 0

    def test_301_ignored(self):
        cc = ConsoleCollector()
        resp = MagicMock()
        resp.status = 301
        cc._on_response(resp)
        assert len(cc.network_errors) == 0

    def test_404_captured(self):
        cc = ConsoleCollector()
        resp = MagicMock()
        resp.status = 404
        resp.status_text = "Not Found"
        resp.url = "http://localhost/api/missing"
        resp.request.method = "GET"

        cc._on_response(resp)

        assert len(cc.network_errors) == 1
        assert cc.network_errors[0].error_type == NetworkErrorType.HTTP_4XX
        assert cc.network_errors[0].status == 404

    def test_500_captured(self):
        cc = ConsoleCollector()
        resp = MagicMock()
        resp.status = 500
        resp.status_text = "Internal Server Error"
        resp.url = "http://localhost/api/crash"
        resp.request.method = "POST"

        cc._on_response(resp)

        assert len(cc.network_errors) == 1
        assert cc.network_errors[0].error_type == NetworkErrorType.HTTP_5XX
        assert cc.network_errors[0].method == "POST"

    def test_max_entries_limit(self):
        cc = ConsoleCollector(max_entries=2)
        for i in range(5):
            resp = MagicMock()
            resp.status = 500
            resp.status_text = "Error"
            resp.url = f"http://localhost/api/{i}"
            resp.request.method = "GET"
            cc._on_response(resp)
        assert len(cc.network_errors) == 2


class TestOnRequestFailed:
    """请求失败处理测试。"""

    def test_cors_failure(self):
        cc = ConsoleCollector()
        req = MagicMock()
        req.failure = "net::ERR_CORS_DISALLOWED"
        req.url = "http://other.com/api"
        req.method = "POST"

        cc._on_request_failed(req)

        assert len(cc.network_errors) == 1
        assert cc.network_errors[0].error_type == NetworkErrorType.CORS

    def test_connection_refused(self):
        cc = ConsoleCollector()
        req = MagicMock()
        req.failure = "net::ERR_CONNECTION_REFUSED"
        req.url = "http://localhost:9999"
        req.method = "GET"

        cc._on_request_failed(req)

        assert cc.network_errors[0].error_type == NetworkErrorType.CONNECTION


class TestOnPageError:
    """JS异常处理测试。"""

    def test_uncaught_error(self):
        cc = ConsoleCollector()
        error = MagicMock()
        error.__str__ = lambda self: "TypeError: Cannot read properties of undefined"
        error.stack = "at app.js:42\n  at main.js:10"

        cc._on_page_error(error)

        assert len(cc.js_exceptions) == 1
        assert "TypeError" in cc.js_exceptions[0].message

    def test_max_entries_limit(self):
        cc = ConsoleCollector(max_entries=2)
        for i in range(5):
            error = MagicMock()
            error.__str__ = lambda self, i=i: f"Error {i}"
            cc._on_page_error(error)
        assert len(cc.js_exceptions) == 2


class TestQueryMethods:
    """查询方法测试。"""

    def _populate(self, cc: ConsoleCollector):
        """填充测试数据。"""
        for level, text in [
            ("log", "normal log"),
            ("error", "big error"),
            ("warning", "some warning"),
            ("log", "another log"),
            ("error", "another error"),
        ]:
            msg = MagicMock()
            msg.type = level
            msg.text = text
            msg.location = None
            cc._on_console(msg)

        for status, url in [(404, "http://x/a"), (500, "http://x/b"), (200, "http://x/c")]:
            resp = MagicMock()
            resp.status = status
            resp.status_text = "X"
            resp.url = url
            resp.request.method = "GET"
            cc._on_response(resp)

        error = MagicMock()
        error.__str__ = lambda self: "JS Error"
        cc._on_page_error(error)

    def test_get_errors(self):
        cc = ConsoleCollector()
        self._populate(cc)
        errors = cc.get_errors()
        assert len(errors) == 3  # 2 errors + 1 warn

    def test_get_errors_by_type(self):
        cc = ConsoleCollector()
        self._populate(cc)
        assert len(cc.get_errors_by_type(NetworkErrorType.HTTP_4XX)) == 1
        assert len(cc.get_errors_by_type(NetworkErrorType.HTTP_5XX)) == 1

    def test_get_context_for_step(self):
        cc = ConsoleCollector()
        self._populate(cc)
        ctx = cc.get_context_for_step(3, window=2)
        assert ctx["step"] == 3
        assert len(ctx["console_logs"]) == 2
        assert len(ctx["network_errors"]) == 2
        assert len(ctx["js_exceptions"]) == 1

    def test_summary(self):
        cc = ConsoleCollector()
        self._populate(cc)
        s = cc.summary()
        assert s["total_console_logs"] == 5
        assert s["total_network_errors"] == 2  # 404 + 500
        assert s["total_js_exceptions"] == 1
        assert s["has_critical_errors"] is True
        assert s["console_by_level"]["error"] == 2
        assert s["network_by_type"]["http_5xx"] == 1

    def test_summary_no_errors(self):
        cc = ConsoleCollector()
        msg = MagicMock()
        msg.type = "log"
        msg.text = "ok"
        msg.location = None
        cc._on_console(msg)

        s = cc.summary()
        assert s["has_critical_errors"] is False

    def test_clear(self):
        cc = ConsoleCollector()
        self._populate(cc)
        cc.clear()
        assert cc.console_logs == []
        assert cc.network_errors == []
        assert cc.js_exceptions == []
