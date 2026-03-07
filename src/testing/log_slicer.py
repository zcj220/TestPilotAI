"""
日志智能切片器（v2.1）

按步骤时间戳切片日志，只把失败步骤的日志喂给AI，节省99% token。

核心策略：
- 每步开始时记录时间戳，结束时收割这段时间的日志
- passed的步骤日志直接丢弃，不发给AI
- 每步最多保留最后50行（避免刷屏日志占满）
- 优先级过滤：error > warn > info
- 收集三种日志源：终端日志 + 浏览器控制台 + 网络请求错误
"""

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from loguru import logger


class LogSource(str, Enum):
    """日志来源。"""
    TERMINAL = "terminal"
    CONSOLE = "console"
    NETWORK = "network"


class LogSeverity(str, Enum):
    """日志严重级别（用于优先级过滤）。"""
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


@dataclass
class LogEntry:
    """单条日志记录。"""
    timestamp: float
    source: LogSource
    severity: LogSeverity
    content: str

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "source": self.source.value,
            "severity": self.severity.value,
            "content": self.content,
        }


MAX_LINES_PER_STEP = 50


@dataclass
class StepLogSlice:
    """单个步骤的日志切片。"""
    step_num: int
    start_time: float
    end_time: float = 0.0
    entries: list[LogEntry] = field(default_factory=list)

    def trimmed(self) -> list[dict]:
        """返回裁剪后的日志（最多MAX_LINES_PER_STEP行，error优先）。"""
        if len(self.entries) <= MAX_LINES_PER_STEP:
            return [e.to_dict() for e in self.entries]

        # error优先，然后warn，最后info
        errors = [e for e in self.entries if e.severity == LogSeverity.ERROR]
        warns = [e for e in self.entries if e.severity == LogSeverity.WARN]
        infos = [e for e in self.entries if e.severity == LogSeverity.INFO]

        result = []
        remaining = MAX_LINES_PER_STEP
        for group in [errors, warns, infos]:
            take = min(len(group), remaining)
            result.extend(group[:take])
            remaining -= take
            if remaining <= 0:
                break

        return [e.to_dict() for e in result]

    def to_text(self) -> str:
        """格式化为可读文本（用于喂给AI）。"""
        lines = self.trimmed()
        if not lines:
            return ""
        parts = []
        for entry in lines:
            tag = f"[{entry['source']}][{entry['severity']}]"
            parts.append(f"{tag} {entry['content']}")
        return "\n".join(parts)


class LogSlicer:
    """日志智能切片器。

    在测试执行期间收集多种来源的日志，按步骤切片，
    只在步骤失败时提取对应日志给AI分析。

    使用方式：
        slicer = LogSlicer()
        slicer.step_start(1)
        slicer.add_console_log("error", "TypeError: ...")
        slicer.step_end(1)
        logs = slicer.get_failed_step_logs(1)  # 只在失败时调用
    """

    def __init__(self) -> None:
        self._slices: dict[int, StepLogSlice] = {}
        self._current_step: Optional[int] = None
        self._console_buffer: deque[LogEntry] = deque(maxlen=500)

    def step_start(self, step_num: int) -> None:
        """标记步骤开始，记录时间戳。"""
        self._current_step = step_num
        self._slices[step_num] = StepLogSlice(
            step_num=step_num,
            start_time=time.time(),
        )

    def step_end(self, step_num: int) -> None:
        """标记步骤结束。"""
        if step_num in self._slices:
            self._slices[step_num].end_time = time.time()
        self._current_step = None

    def add_console_log(self, level: str, text: str) -> None:
        """添加浏览器控制台日志。

        Args:
            level: "error", "warning", "log", "info", "debug"
            text: 日志内容
        """
        severity = self._map_console_severity(level)
        entry = LogEntry(
            timestamp=time.time(),
            source=LogSource.CONSOLE,
            severity=severity,
            content=text[:500],  # 截断超长日志
        )
        self._console_buffer.append(entry)

        # 如果当前有步骤在执行，直接归入该步骤
        if self._current_step and self._current_step in self._slices:
            self._slices[self._current_step].entries.append(entry)

    def add_network_error(self, url: str, status: int, method: str = "GET") -> None:
        """添加网络请求错误（4xx/5xx）。

        Args:
            url: 请求URL
            status: HTTP状态码
            method: HTTP方法
        """
        severity = LogSeverity.ERROR if status >= 500 else LogSeverity.WARN
        entry = LogEntry(
            timestamp=time.time(),
            source=LogSource.NETWORK,
            severity=severity,
            content=f"{method} {url} → {status}",
        )

        if self._current_step and self._current_step in self._slices:
            self._slices[self._current_step].entries.append(entry)

    def inject_terminal_logs(self, step_num: int, terminal_logs: list[dict]) -> None:
        """从process_runner注入终端日志到指定步骤。

        Args:
            step_num: 步骤编号
            terminal_logs: process_runner.get_context_logs() 的返回值
        """
        if step_num not in self._slices:
            return

        for log in terminal_logs:
            severity = LogSeverity.ERROR if log.get("level") == "stderr" else LogSeverity.INFO
            entry = LogEntry(
                timestamp=log.get("timestamp", time.time()),
                source=LogSource.TERMINAL,
                severity=severity,
                content=log.get("content", "")[:500],
            )
            self._slices[step_num].entries.append(entry)

    def get_step_logs(self, step_num: int) -> Optional[StepLogSlice]:
        """获取指定步骤的日志切片。"""
        return self._slices.get(step_num)

    def get_step_log_text(self, step_num: int) -> str:
        """获取指定步骤的日志文本（用于喂给AI）。"""
        slice_ = self._slices.get(step_num)
        if not slice_:
            return ""
        return slice_.to_text()

    def get_step_log_count(self, step_num: int) -> int:
        """获取指定步骤的日志条数。"""
        slice_ = self._slices.get(step_num)
        return len(slice_.entries) if slice_ else 0

    def clear(self) -> None:
        """清空所有日志。"""
        self._slices.clear()
        self._console_buffer.clear()
        self._current_step = None

    @staticmethod
    def _map_console_severity(level: str) -> LogSeverity:
        """映射浏览器控制台级别到内部严重级别。"""
        level_lower = level.lower()
        if level_lower in ("error",):
            return LogSeverity.ERROR
        if level_lower in ("warning", "warn"):
            return LogSeverity.WARN
        return LogSeverity.INFO
