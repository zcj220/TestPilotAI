"""SmartRepairDecider 单元测试。"""

import pytest

from src.testing.models import BugReport, BugSeverity, StepResult, StepStatus, ActionType
from src.testing.smart_repair import (
    CONSECUTIVE_FAIL_THRESHOLD,
    RepairStrategy,
    SmartRepairDecider,
)


class TestRepairStrategy:
    def test_enum_values(self):
        assert RepairStrategy.IMMEDIATE == "immediate"
        assert RepairStrategy.DEFERRED == "deferred"


class TestSmartRepairDecider:
    def _make_bug(self, severity=BugSeverity.MEDIUM, title="test bug", category="test"):
        return BugReport(severity=severity, title=title, category=category)

    def _make_result(self, status=StepStatus.PASSED):
        return StepResult(step=1, action=ActionType.CLICK, status=status)

    def test_critical_bug_immediate(self):
        d = SmartRepairDecider()
        bug = self._make_bug(severity=BugSeverity.CRITICAL)
        assert d.decide(bug) == RepairStrategy.IMMEDIATE
        assert bug.is_blocking is True

    def test_error_step_immediate(self):
        d = SmartRepairDecider()
        bug = self._make_bug()
        result = self._make_result(status=StepStatus.ERROR)
        assert d.decide(bug, result) == RepairStrategy.IMMEDIATE

    def test_medium_bug_deferred(self):
        d = SmartRepairDecider()
        bug = self._make_bug(severity=BugSeverity.MEDIUM)
        result = self._make_result(status=StepStatus.FAILED)
        assert d.decide(bug, result) == RepairStrategy.DEFERRED

    def test_low_bug_deferred(self):
        d = SmartRepairDecider()
        bug = self._make_bug(severity=BugSeverity.LOW)
        assert d.decide(bug) == RepairStrategy.DEFERRED

    def test_consecutive_failures_trigger_immediate(self):
        d = SmartRepairDecider()
        for _ in range(CONSECUTIVE_FAIL_THRESHOLD):
            d.record_step(self._make_result(status=StepStatus.FAILED))
        bug = self._make_bug(severity=BugSeverity.LOW)
        assert d.decide(bug) == RepairStrategy.IMMEDIATE

    def test_passed_step_resets_consecutive(self):
        d = SmartRepairDecider()
        d.record_step(self._make_result(status=StepStatus.FAILED))
        d.record_step(self._make_result(status=StepStatus.FAILED))
        d.record_step(self._make_result(status=StepStatus.PASSED))
        assert d.consecutive_failures == 0
        bug = self._make_bug(severity=BugSeverity.LOW)
        assert d.decide(bug) == RepairStrategy.DEFERRED

    def test_blank_page_bug_immediate(self):
        d = SmartRepairDecider()
        bug = self._make_bug(title="白屏检测", category="blank_page")
        assert d.decide(bug) == RepairStrategy.IMMEDIATE

    def test_on_immediate_repair_resets_failures(self):
        d = SmartRepairDecider()
        for _ in range(CONSECUTIVE_FAIL_THRESHOLD):
            d.record_step(self._make_result(status=StepStatus.FAILED))
        assert d.consecutive_failures == CONSECUTIVE_FAIL_THRESHOLD
        d.on_immediate_repair_done(success=True)
        assert d.consecutive_failures == 0

    def test_on_immediate_repair_failed_keeps_failures(self):
        d = SmartRepairDecider()
        for _ in range(2):
            d.record_step(self._make_result(status=StepStatus.FAILED))
        d.on_immediate_repair_done(success=False)
        assert d.consecutive_failures == 2

    def test_stats(self):
        d = SmartRepairDecider()
        d.record_step(self._make_result(status=StepStatus.PASSED))
        d.record_step(self._make_result(status=StepStatus.FAILED))
        d.on_immediate_repair_done(True)
        stats = d.stats
        assert stats["total_steps"] == 2
        assert stats["failed_steps"] == 1
        assert stats["immediate_repairs"] == 1
