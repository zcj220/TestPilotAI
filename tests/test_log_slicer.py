"""日志智能切片器单元测试。"""

import time
import unittest

from src.testing.log_slicer import LogEntry, LogSeverity, LogSlicer, LogSource, StepLogSlice, MAX_LINES_PER_STEP


class TestLogEntry(unittest.TestCase):
    def test_to_dict(self):
        entry = LogEntry(
            timestamp=1000.0,
            source=LogSource.CONSOLE,
            severity=LogSeverity.ERROR,
            content="TypeError: x is not defined",
        )
        d = entry.to_dict()
        assert d["source"] == "console"
        assert d["severity"] == "error"
        assert "TypeError" in d["content"]


class TestStepLogSlice(unittest.TestCase):
    def test_empty_slice(self):
        s = StepLogSlice(step_num=1, start_time=1000.0)
        assert s.trimmed() == []
        assert s.to_text() == ""

    def test_trimmed_within_limit(self):
        s = StepLogSlice(step_num=1, start_time=1000.0)
        for i in range(10):
            s.entries.append(LogEntry(1000.0 + i, LogSource.CONSOLE, LogSeverity.INFO, f"log {i}"))
        assert len(s.trimmed()) == 10

    def test_trimmed_over_limit_error_priority(self):
        """超过MAX_LINES_PER_STEP时，error优先。"""
        s = StepLogSlice(step_num=1, start_time=1000.0)
        # 添加100条info
        for i in range(80):
            s.entries.append(LogEntry(1000.0, LogSource.CONSOLE, LogSeverity.INFO, f"info {i}"))
        # 添加20条error
        for i in range(20):
            s.entries.append(LogEntry(1000.0, LogSource.CONSOLE, LogSeverity.ERROR, f"error {i}"))

        trimmed = s.trimmed()
        assert len(trimmed) == MAX_LINES_PER_STEP

        # error应该全部在内
        error_count = sum(1 for e in trimmed if e["severity"] == "error")
        assert error_count == 20

    def test_to_text_format(self):
        s = StepLogSlice(step_num=1, start_time=1000.0)
        s.entries.append(LogEntry(1000.0, LogSource.CONSOLE, LogSeverity.ERROR, "ReferenceError"))
        s.entries.append(LogEntry(1000.1, LogSource.NETWORK, LogSeverity.WARN, "GET /api → 404"))
        text = s.to_text()
        assert "[console][error]" in text
        assert "[network][warn]" in text
        assert "ReferenceError" in text


class TestLogSlicer(unittest.TestCase):
    def test_step_lifecycle(self):
        slicer = LogSlicer()
        slicer.step_start(1)
        slicer.add_console_log("error", "TypeError")
        slicer.step_end(1)

        text = slicer.get_step_log_text(1)
        assert "TypeError" in text
        assert slicer.get_step_log_count(1) == 1

    def test_logs_only_go_to_current_step(self):
        """日志只归入当前执行中的步骤。"""
        slicer = LogSlicer()

        slicer.step_start(1)
        slicer.add_console_log("info", "step1 log")
        slicer.step_end(1)

        slicer.step_start(2)
        slicer.add_console_log("error", "step2 error")
        slicer.step_end(2)

        assert slicer.get_step_log_count(1) == 1
        assert slicer.get_step_log_count(2) == 1
        assert "step1" in slicer.get_step_log_text(1)
        assert "step2" in slicer.get_step_log_text(2)

    def test_network_error_collection(self):
        slicer = LogSlicer()
        slicer.step_start(1)
        slicer.add_network_error("/api/users", 500, "GET")
        slicer.add_network_error("/static/app.js", 404, "GET")
        slicer.step_end(1)

        text = slicer.get_step_log_text(1)
        assert "500" in text
        assert "404" in text
        assert slicer.get_step_log_count(1) == 2

    def test_no_logs_outside_step(self):
        """没有步骤在执行时，日志不归入任何步骤。"""
        slicer = LogSlicer()
        slicer.add_console_log("error", "orphan log")
        assert slicer.get_step_log_count(1) == 0

    def test_inject_terminal_logs(self):
        slicer = LogSlicer()
        slicer.step_start(5)
        slicer.step_end(5)

        terminal_logs = [
            {"timestamp": 1000.0, "level": "stderr", "content": "Error: ENOENT"},
            {"timestamp": 1000.1, "level": "stdout", "content": "Server listening"},
        ]
        slicer.inject_terminal_logs(5, terminal_logs)

        text = slicer.get_step_log_text(5)
        assert "ENOENT" in text
        assert "[terminal][error]" in text
        assert "[terminal][info]" in text

    def test_clear(self):
        slicer = LogSlicer()
        slicer.step_start(1)
        slicer.add_console_log("info", "test")
        slicer.step_end(1)
        slicer.clear()
        assert slicer.get_step_log_count(1) == 0

    def test_severity_mapping(self):
        slicer = LogSlicer()
        slicer.step_start(1)
        slicer.add_console_log("error", "err")
        slicer.add_console_log("warning", "warn")
        slicer.add_console_log("log", "info_msg")
        slicer.step_end(1)

        text = slicer.get_step_log_text(1)
        assert "[console][error]" in text
        assert "[console][warn]" in text
        assert "[console][info]" in text

    def test_content_truncation(self):
        """超长日志内容应被截断到500字符。"""
        slicer = LogSlicer()
        slicer.step_start(1)
        slicer.add_console_log("error", "x" * 1000)
        slicer.step_end(1)

        s = slicer.get_step_logs(1)
        assert s is not None
        assert len(s.entries[0].content) == 500


if __name__ == "__main__":
    unittest.main()
