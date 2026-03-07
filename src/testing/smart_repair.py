"""
智能修复模式

策略：
- 阻塞性Bug → 立即修复，修完继续测试
- 非阻塞性Bug → 记录，最后批量汇报修复
"""

from enum import Enum
from typing import Optional

from loguru import logger

from src.testing.models import BugReport, BugSeverity, StepResult, StepStatus


class RepairStrategy(str, Enum):
    IMMEDIATE = "immediate"
    DEFERRED = "deferred"


CONSECUTIVE_FAIL_THRESHOLD = 3


class SmartRepairDecider:
    """智能修复决策器。"""

    def __init__(self) -> None:
        self._consecutive_failures: int = 0
        self._total_steps: int = 0
        self._failed_steps: int = 0
        self._immediate_repairs: int = 0

    def record_step(self, result: StepResult) -> None:
        self._total_steps += 1
        if result.status in (StepStatus.FAILED, StepStatus.ERROR):
            self._consecutive_failures += 1
            self._failed_steps += 1
        else:
            self._consecutive_failures = 0

    def decide(self, bug: BugReport, step_result: Optional[StepResult] = None) -> RepairStrategy:
        if bug.severity == BugSeverity.CRITICAL:
            logger.info("  阻塞性Bug（CRITICAL）→ 立即修复: {}", bug.title)
            bug.is_blocking = True
            return RepairStrategy.IMMEDIATE

        if step_result and step_result.status == StepStatus.ERROR:
            logger.info("  阻塞性Bug（步骤ERROR）→ 立即修复: {}", bug.title)
            bug.is_blocking = True
            return RepairStrategy.IMMEDIATE

        if self._consecutive_failures >= CONSECUTIVE_FAIL_THRESHOLD:
            logger.info("  连续{}步失败 → 立即修复: {}", self._consecutive_failures, bug.title)
            bug.is_blocking = True
            return RepairStrategy.IMMEDIATE

        if "白屏" in bug.title or "崩溃" in bug.title or "blank_page" in bug.category:
            logger.info("  阻塞性Bug（白屏/崩溃）→ 立即修复: {}", bug.title)
            bug.is_blocking = True
            return RepairStrategy.IMMEDIATE

        logger.debug("  非阻塞性Bug → 延迟修复: {}", bug.title)
        return RepairStrategy.DEFERRED

    def on_immediate_repair_done(self, success: bool) -> None:
        self._immediate_repairs += 1
        if success:
            self._consecutive_failures = 0

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def stats(self) -> dict:
        return {
            "total_steps": self._total_steps,
            "failed_steps": self._failed_steps,
            "immediate_repairs": self._immediate_repairs,
            "consecutive_failures": self._consecutive_failures,
        }
