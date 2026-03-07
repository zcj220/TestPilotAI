"""
Watch模式 + Regression循环（v2.0-rc）

监听 testpilot.json 变化自动重新测试，
以及修复后自动重跑蓝本确认无回归。

核心功能：
- watch模式：轮询检测蓝本文件修改时间，变化后自动触发测试
- regression模式：修复后自动重跑蓝本，最多N轮，直到0 Bug或达上限
"""

import asyncio
import os
import time
from enum import Enum
from typing import Callable, Coroutine, Any, Optional

from loguru import logger


class WatcherState(str, Enum):
    IDLE = "idle"
    WATCHING = "watching"
    STOPPED = "stopped"


class RegressionResult(str, Enum):
    ALL_PASSED = "all_passed"
    BUGS_REMAIN = "bugs_remain"
    MAX_ROUNDS = "max_rounds"
    CANCELLED = "cancelled"


# 测试回调类型：接收蓝本路径，返回 (通过数, 总数, Bug数)
TestCallback = Callable[[str], Coroutine[Any, Any, tuple[int, int, int]]]
# 通知回调：接收消息类型和数据
NotifyCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


class BlueprintWatcher:
    """蓝本文件监听器。

    轮询检测 testpilot.json 的修改时间，
    变化后调用回调执行测试。
    """

    def __init__(
        self,
        test_callback: TestCallback,
        notify_callback: Optional[NotifyCallback] = None,
        poll_interval: float = 2.0,
    ) -> None:
        self._test_callback = test_callback
        self._notify = notify_callback
        self._poll_interval = poll_interval
        self._state: WatcherState = WatcherState.IDLE
        self._watch_task: Optional[asyncio.Task] = None
        self._blueprint_path: str = ""
        self._last_mtime: float = 0
        self._run_count: int = 0

    @property
    def state(self) -> WatcherState:
        return self._state

    @property
    def run_count(self) -> int:
        return self._run_count

    def status_dict(self) -> dict:
        return {
            "state": self._state.value,
            "blueprint_path": self._blueprint_path,
            "run_count": self._run_count,
            "poll_interval": self._poll_interval,
        }

    async def start(self, blueprint_path: str) -> bool:
        """开始监听蓝本文件。"""
        if self._state == WatcherState.WATCHING:
            return False

        if not os.path.isfile(blueprint_path):
            logger.error("Watch模式 | 蓝本文件不存在: {}", blueprint_path)
            return False

        self._blueprint_path = blueprint_path
        self._last_mtime = os.path.getmtime(blueprint_path)
        self._run_count = 0
        self._state = WatcherState.WATCHING

        self._watch_task = asyncio.create_task(self._poll_loop())
        logger.info("Watch模式 | 开始监听 | 文件={} | 间隔={}s", blueprint_path, self._poll_interval)

        if self._notify:
            await self._notify("watch_start", {"path": blueprint_path})

        return True

    async def stop(self) -> None:
        """停止监听。"""
        if self._watch_task and not self._watch_task.done():
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

        self._state = WatcherState.STOPPED
        logger.info("Watch模式 | 停止监听 | 共执行{}次", self._run_count)

        if self._notify:
            await self._notify("watch_stop", {"run_count": self._run_count})

    async def _poll_loop(self) -> None:
        """轮询检测文件变化。"""
        try:
            while self._state == WatcherState.WATCHING:
                await asyncio.sleep(self._poll_interval)

                try:
                    current_mtime = os.path.getmtime(self._blueprint_path)
                except OSError:
                    continue

                if current_mtime > self._last_mtime:
                    self._last_mtime = current_mtime
                    self._run_count += 1
                    logger.info("Watch模式 | 检测到变化 | 第{}次执行", self._run_count)

                    if self._notify:
                        await self._notify("watch_triggered", {
                            "run": self._run_count,
                            "path": self._blueprint_path,
                        })

                    try:
                        passed, total, bugs = await self._test_callback(self._blueprint_path)
                        logger.info("Watch模式 | 测试完成 | 通过={}/{} | Bug={}", passed, total, bugs)
                    except Exception as e:
                        logger.error("Watch模式 | 测试执行失败: {}", str(e)[:100])

        except asyncio.CancelledError:
            pass


class RegressionRunner:
    """回归测试循环。

    修复后自动重跑蓝本确认无回归，最多N轮。
    """

    def __init__(
        self,
        test_callback: TestCallback,
        notify_callback: Optional[NotifyCallback] = None,
        max_rounds: int = 5,
    ) -> None:
        self._test_callback = test_callback
        self._notify = notify_callback
        self._max_rounds = max_rounds
        self._cancelled = False
        self._current_round = 0

    @property
    def current_round(self) -> int:
        return self._current_round

    @property
    def max_rounds(self) -> int:
        return self._max_rounds

    def cancel(self) -> None:
        """取消回归循环。"""
        self._cancelled = True

    async def run(self, blueprint_path: str) -> RegressionResult:
        """执行回归循环。

        每轮测试后如果仍有Bug，继续下一轮（假设外部会修复）。
        直到0 Bug或达到最大轮数。

        Args:
            blueprint_path: 蓝本文件路径
        Returns:
            回归结果
        """
        self._cancelled = False
        self._current_round = 0

        logger.info("Regression | 开始 | 蓝本={} | 最大轮数={}", blueprint_path, self._max_rounds)

        if self._notify:
            await self._notify("regression_start", {
                "path": blueprint_path,
                "max_rounds": self._max_rounds,
            })

        for round_num in range(1, self._max_rounds + 1):
            if self._cancelled:
                logger.info("Regression | 被取消 | 在第{}轮", round_num)
                return RegressionResult.CANCELLED

            self._current_round = round_num
            logger.info("Regression | 第{}/{}轮", round_num, self._max_rounds)

            if self._notify:
                await self._notify("regression_round", {
                    "round": round_num,
                    "max_rounds": self._max_rounds,
                })

            try:
                passed, total, bugs = await self._test_callback(blueprint_path)
            except Exception as e:
                logger.error("Regression | 第{}轮测试失败: {}", round_num, str(e)[:100])
                continue

            logger.info("Regression | 第{}轮结果 | 通过={}/{} | Bug={}", round_num, passed, total, bugs)

            if bugs == 0:
                logger.info("Regression | 全部通过！零Bug确认")
                if self._notify:
                    await self._notify("regression_done", {
                        "result": "all_passed",
                        "rounds": round_num,
                    })
                return RegressionResult.ALL_PASSED

            # 还有Bug，等待一小段时间让修复生效
            if round_num < self._max_rounds:
                logger.info("Regression | 仍有{}个Bug，等待修复后重试...", bugs)
                await asyncio.sleep(2.0)

        logger.info("Regression | 达到最大轮数 | 仍有Bug")
        if self._notify:
            await self._notify("regression_done", {
                "result": "max_rounds",
                "rounds": self._max_rounds,
            })
        return RegressionResult.MAX_ROUNDS
