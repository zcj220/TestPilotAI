"""
终端日志收集器（v2.0-beta）

用 subprocess 包裹用户的应用启动命令（如 npm start），
捕获 stdout/stderr 并实时推送到前端。

核心功能：
- 启动/停止被测应用进程
- 每行日志带时间戳，存入环形缓冲区（最近1000行）
- 通过 WebSocket 实时推送 terminal_log 消息
- 提供 Bug发生前后N秒的终端日志 能力
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from loguru import logger


class ProcessState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class LogLevel(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass
class TerminalLogEntry:
    timestamp: float
    level: LogLevel
    content: str

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "level": self.level.value,
            "content": self.content,
        }


MAX_BUFFER_SIZE = 1000


class ProcessRunner:
    """应用进程管理器，捕获终端输出。"""

    def __init__(self, ws_broadcast=None) -> None:
        """
        Args:
            ws_broadcast: 异步广播函数，签名 async (type, data) -> None
        """
        self._process: Optional[asyncio.subprocess.Process] = None
        self._state: ProcessState = ProcessState.IDLE
        self._buffer: deque[TerminalLogEntry] = deque(maxlen=MAX_BUFFER_SIZE)
        self._ws_broadcast = ws_broadcast
        self._tasks: list[asyncio.Task] = []
        self._command: str = ""
        self._start_time: float = 0

    @property
    def state(self) -> ProcessState:
        return self._state

    @property
    def command(self) -> str:
        return self._command

    def status_dict(self) -> dict:
        return {
            "state": self._state.value,
            "command": self._command,
            "log_count": len(self._buffer),
            "uptime": time.time() - self._start_time if self._state == ProcessState.RUNNING else 0,
        }

    async def start(self, command: str, cwd: str = ".") -> bool:
        """启动被测应用。

        Args:
            command: 启动命令，如 "npm start"
            cwd: 工作目录
        Returns:
            是否启动成功
        """
        if self._state == ProcessState.RUNNING:
            logger.warning("进程已在运行: {}", self._command)
            return False

        self._command = command
        self._state = ProcessState.STARTING
        self._buffer.clear()
        self._start_time = time.time()

        try:
            self._process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            self._state = ProcessState.RUNNING
            logger.info("应用进程已启动 | PID={} | cmd={}", self._process.pid, command)

            # 启动读取任务
            self._tasks = [
                asyncio.create_task(self._read_stream(self._process.stdout, LogLevel.STDOUT)),
                asyncio.create_task(self._read_stream(self._process.stderr, LogLevel.STDERR)),
                asyncio.create_task(self._wait_exit()),
            ]
            return True

        except Exception as e:
            self._state = ProcessState.ERROR
            logger.error("应用进程启动失败: {}", e)
            return False

    async def stop(self) -> None:
        """停止被测应用。"""
        if self._process is None:
            return

        try:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        except ProcessLookupError:
            pass

        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

        self._state = ProcessState.STOPPED
        self._process = None
        logger.info("应用进程已停止 | cmd={}", self._command)

    async def _read_stream(self, stream, level: LogLevel) -> None:
        """持续读取进程输出流。"""
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\n\r")
                if not text:
                    continue

                entry = TerminalLogEntry(
                    timestamp=time.time(),
                    level=level,
                    content=text,
                )
                self._buffer.append(entry)

                # WebSocket 推送
                if self._ws_broadcast:
                    try:
                        await self._ws_broadcast("terminal_log", entry.to_dict())
                    except Exception:
                        pass
        except asyncio.CancelledError:
            pass

    async def _wait_exit(self) -> None:
        """等待进程退出。"""
        if self._process is None:
            return
        try:
            code = await self._process.wait()
            if self._state == ProcessState.RUNNING:
                self._state = ProcessState.STOPPED
                logger.info("应用进程退出 | code={} | cmd={}", code, self._command)
                if self._ws_broadcast:
                    await self._ws_broadcast("terminal_log", {
                        "timestamp": time.time(),
                        "level": "system",
                        "content": f"进程退出，退出码: {code}",
                    })
        except asyncio.CancelledError:
            pass

    def get_all_logs(self) -> list[dict]:
        """获取缓冲区内所有日志。"""
        return [e.to_dict() for e in self._buffer]

    def get_recent_logs(self, count: int = 50) -> list[dict]:
        """获取最近N条日志。"""
        entries = list(self._buffer)[-count:]
        return [e.to_dict() for e in entries]

    def get_context_logs(self, timestamp: float, seconds: float = 5.0) -> list[dict]:
        """获取指定时间点前后N秒的日志（用于Bug报告）。

        Args:
            timestamp: 中心时间戳
            seconds: 前后各取多少秒
        Returns:
            时间范围内的日志列表
        """
        start = timestamp - seconds
        end = timestamp + seconds
        return [
            e.to_dict() for e in self._buffer
            if start <= e.timestamp <= end
        ]


# 全局单例
process_runner = ProcessRunner()
