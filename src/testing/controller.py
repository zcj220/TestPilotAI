"""
测试控制器（v2.0）

管理测试执行的生命周期，支持暂停/继续/停止/单步等控制操作。

状态机：
    IDLE → RUNNING → PAUSED → RUNNING（继续）
                   → STOPPED
    IDLE → RUNNING → STOPPED

核心机制：
- asyncio.Event 控制步骤间暂停/继续
- cancel标志控制停止（当前步骤完成后终止）
- 单步模式：每步自动暂停，等收到resume信号
- 观看延迟：每步执行后可配置等待时间

典型使用：
    controller = TestController()
    controller.start()

    # 在BlueprintRunner的步骤循环中：
    await controller.wait_if_paused()  # 步骤前检查
    if controller.is_cancelled:
        break
    # ... 执行步骤 ...
    await controller.step_delay()      # 步骤后延迟（观看模式）

    # 前端/API调用：
    controller.pause()
    controller.resume()
    controller.stop()
    controller.set_step_mode(True)
"""

import asyncio
from enum import Enum
from typing import Optional

from loguru import logger


class TestState(str, Enum):
    """测试执行状态。"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class TestController:
    """测试执行控制器。

    通过 asyncio.Event 实现非阻塞的暂停/继续机制，
    BlueprintRunner 在每步执行前调用 wait_if_paused() 检查状态。
    """

    def __init__(self) -> None:
        self._state: TestState = TestState.IDLE
        self._resume_event: asyncio.Event = asyncio.Event()
        self._resume_event.set()  # 初始为非暂停状态
        self._cancelled: bool = False
        self._step_mode: bool = False
        self._step_delay_seconds: float = 0.0
        self._current_step: int = 0
        self._total_steps: int = 0
        self._current_description: str = ""

    # ── 状态查询 ──────────────────────────────────────

    @property
    def state(self) -> TestState:
        """当前测试状态。"""
        return self._state

    @property
    def is_cancelled(self) -> bool:
        """是否已取消。"""
        return self._cancelled

    @property
    def is_running(self) -> bool:
        """是否正在运行（含暂停中）。"""
        return self._state in (TestState.RUNNING, TestState.PAUSED)

    @property
    def current_step(self) -> int:
        return self._current_step

    @property
    def total_steps(self) -> int:
        return self._total_steps

    @property
    def step_mode(self) -> bool:
        return self._step_mode

    @property
    def step_delay_seconds(self) -> float:
        return self._step_delay_seconds

    def status_dict(self) -> dict:
        """返回状态字典，供API响应使用。"""
        return {
            "state": self._state.value,
            "current_step": self._current_step,
            "total_steps": self._total_steps,
            "description": self._current_description,
            "step_mode": self._step_mode,
            "step_delay": self._step_delay_seconds,
            "cancelled": self._cancelled,
        }

    # ── 生命周期控制 ─────────────────────────────────

    def start(self, total_steps: int = 0) -> None:
        """开始测试。

        Args:
            total_steps: 总步骤数（用于进度显示）
        """
        self._state = TestState.RUNNING
        self._cancelled = False
        self._resume_event.set()
        self._current_step = 0
        self._total_steps = total_steps
        self._current_description = ""
        logger.info("测试控制器 | 启动 | 总步骤={} | 单步模式={} | 观看延迟={}s",
                     total_steps, self._step_mode, self._step_delay_seconds)

    def pause(self) -> bool:
        """暂停测试（当前步骤完成后生效）。

        Returns:
            bool: 是否成功暂停（只有RUNNING状态才能暂停）
        """
        if self._state != TestState.RUNNING:
            return False
        self._state = TestState.PAUSED
        self._resume_event.clear()
        logger.info("测试控制器 | 暂停 | 当前步骤={}/{}", self._current_step, self._total_steps)
        return True

    def resume(self) -> bool:
        """继续执行。

        Returns:
            bool: 是否成功继续（只有PAUSED状态才能继续）
        """
        if self._state != TestState.PAUSED:
            return False
        self._state = TestState.RUNNING
        self._resume_event.set()
        logger.info("测试控制器 | 继续 | 从步骤={}/{}", self._current_step, self._total_steps)
        return True

    def stop(self) -> bool:
        """停止测试（当前步骤完成后终止）。

        Returns:
            bool: 是否成功停止
        """
        if self._state == TestState.IDLE or self._state == TestState.STOPPED:
            return False
        self._cancelled = True
        self._state = TestState.STOPPED
        self._resume_event.set()  # 如果正在暂停中，释放等待
        logger.info("测试控制器 | 停止 | 在步骤={}/{}", self._current_step, self._total_steps)
        return True

    def reset(self) -> None:
        """重置到IDLE状态（测试结束后调用）。"""
        self._state = TestState.IDLE
        self._cancelled = False
        self._resume_event.set()
        self._current_step = 0
        self._total_steps = 0
        self._current_description = ""

    # ── 配置 ──────────────────────────────────────────

    def set_step_mode(self, enabled: bool) -> None:
        """设置单步执行模式。

        开启后每步自动暂停，等待resume信号。
        """
        self._step_mode = enabled
        logger.info("测试控制器 | 单步模式={}", enabled)

    def set_step_delay(self, seconds: float) -> None:
        """设置每步之间的观看延迟。

        Args:
            seconds: 延迟秒数（0=无延迟，0.5=快速，1=正常，3=慢速）
        """
        self._step_delay_seconds = max(0.0, min(seconds, 10.0))
        logger.info("测试控制器 | 观看延迟={}s", self._step_delay_seconds)

    # ── BlueprintRunner 集成点 ────────────────────────

    def update_progress(self, step: int, description: str = "") -> None:
        """更新当前进度（BlueprintRunner每步调用）。"""
        self._current_step = step
        self._current_description = description

    async def wait_if_paused(self) -> None:
        """等待暂停结束（BlueprintRunner每步前调用）。

        如果当前是PAUSED状态，会阻塞直到resume()被调用。
        如果是单步模式且当前RUNNING，自动暂停。
        """
        # 单步模式：每步自动暂停（第一步除外，让用户先看到启动）
        if self._step_mode and self._state == TestState.RUNNING and self._current_step > 0:
            self.pause()
            logger.debug("单步模式 | 自动暂停于步骤 {}", self._current_step + 1)

        # 等待resume信号
        await self._resume_event.wait()

    async def step_delay(self) -> None:
        """步骤间观看延迟（BlueprintRunner每步后调用）。

        只在有延迟配置时生效，用于实时观看模式。
        """
        if self._step_delay_seconds > 0 and not self._cancelled:
            await asyncio.sleep(self._step_delay_seconds)

    @property
    def was_stopped(self) -> bool:
        """测试是否因用户停止而结束（供批量测试判断是否中断后续蓝本）。"""
        return self._state == TestState.STOPPED

    def on_test_complete(self) -> None:
        """测试完成时调用。

        注意：用户停止时保留 STOPPED 状态和 _cancelled 标志，
        供批量测试的外层循环检查 was_stopped 后决定是否中断。
        外层循环在确认中断后应调用 reset() 清理状态。
        """
        if self._state != TestState.STOPPED:
            self._state = TestState.IDLE
            self._cancelled = False
        # STOPPED 状态下保留 _cancelled=True，让批量调用者能检测到
        self._resume_event.set()
        logger.info("测试控制器 | 测试完成 | 最终状态={}", self._state.value)


# 全局单例（与ws_manager类似）
test_controller = TestController()
