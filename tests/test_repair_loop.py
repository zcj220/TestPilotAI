"""
修复闭环编排器的单元测试
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repair.loop import RepairLoop, MAX_FIX_ATTEMPTS, SEVERITY_ORDER
from src.repair.models import AttemptStatus, RepairReport
from src.testing.models import (
    ActionType,
    BugReport,
    BugSeverity,
    FixStatus,
    StepResult,
    StepStatus,
    TestReport,
)


def _make_test_report(bugs=None, step_results=None) -> TestReport:
    """构造测试报告。"""
    return TestReport(
        test_name="测试报告",
        url="http://localhost:3000",
        total_steps=3,
        passed_steps=1,
        failed_steps=2,
        step_results=step_results or [],
        bugs=bugs or [],
    )


def _make_bug(
    title="测试Bug",
    severity=BugSeverity.HIGH,
    step_number=2,
) -> BugReport:
    return BugReport(
        severity=severity,
        title=title,
        description="按钮不响应",
        category="功能缺陷",
        location="页面中央",
        reproduction="点击按钮",
        step_number=step_number,
    )


def _make_step_result(step=1, status=StepStatus.FAILED) -> StepResult:
    return StepResult(
        step=step,
        action=ActionType.CLICK,
        status=status,
        description="点击登录按钮",
        error_message="元素不可点击" if status == StepStatus.FAILED else "",
    )


@pytest.fixture
def mock_ai():
    ai = MagicMock()
    # 默认: Bug分类返回非阻塞
    ai.chat.return_value = '{"is_blocking": false, "reason": "非阻塞"}'
    return ai


@pytest.fixture
def tmp_project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text(
        'function login() { return "ok"; }',
        encoding="utf-8",
    )
    return tmp_path


class TestRepairLoopNoBugs:
    """没有 Bug 时的行为。"""

    @pytest.mark.asyncio
    async def test_no_bugs_returns_empty_report(self, mock_ai, tmp_project):
        loop = RepairLoop(mock_ai, str(tmp_project))
        report = _make_test_report(bugs=[])
        result = await loop.run(report)
        assert isinstance(result, RepairReport)
        assert result.total_bugs == 0
        assert result.fixed_bugs == 0
        assert "没有 Bug" in result.summary


class TestBugSorting:
    """Bug 排序逻辑测试。"""

    def test_severity_order_values(self):
        assert SEVERITY_ORDER[BugSeverity.CRITICAL] > SEVERITY_ORDER[BugSeverity.HIGH]
        assert SEVERITY_ORDER[BugSeverity.HIGH] > SEVERITY_ORDER[BugSeverity.MEDIUM]
        assert SEVERITY_ORDER[BugSeverity.MEDIUM] > SEVERITY_ORDER[BugSeverity.LOW]


class TestRepairLoopCannotFix:
    """AI 无法修复时的行为。"""

    @pytest.mark.asyncio
    async def test_ai_cannot_fix(self, mock_ai, tmp_project):
        """AI 返回 can_fix=false 时应标记为失败。"""
        # 第一次调用: Bug分类
        # 第二次调用: 生成修复方案
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return '{"is_blocking": true, "reason": "崩溃"}'
            return json.dumps({
                "analysis": "无法修复",
                "can_fix": False,
                "confidence": 0.1,
                "patches": [],
                "explanation": "问题过于复杂",
                "risk_level": "high",
            })

        mock_ai.chat.side_effect = side_effect

        bug = _make_bug(severity=BugSeverity.CRITICAL)
        step = _make_step_result(step=2, status=StepStatus.FAILED)
        report = _make_test_report(bugs=[bug], step_results=[step])

        loop = RepairLoop(mock_ai, str(tmp_project))
        result = await loop.run(report)

        assert result.total_bugs == 1
        assert result.fixed_bugs == 0
        assert result.failed_bugs == 1
        assert bug.fix_status == FixStatus.FIX_FAILED


class TestRepairLoopFixSuccess:
    """修复成功（无重测函数）的行为。"""

    @pytest.mark.asyncio
    async def test_fix_without_retest(self, mock_ai, tmp_project):
        """没有重测函数时，补丁应用成功即视为修复成功。"""
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return '{"is_blocking": false, "reason": "非阻塞"}'
            return json.dumps({
                "analysis": "拼写错误",
                "can_fix": True,
                "confidence": 0.95,
                "patches": [
                    {
                        "file_path": "src/app.js",
                        "description": "修复返回值",
                        "old_code": 'return "ok"',
                        "new_code": 'return "success"',
                    }
                ],
                "explanation": "修正返回值",
                "risk_level": "low",
            })

        mock_ai.chat.side_effect = side_effect

        bug = _make_bug(severity=BugSeverity.MEDIUM)
        step = _make_step_result(step=2, status=StepStatus.FAILED)
        report = _make_test_report(bugs=[bug], step_results=[step])

        loop = RepairLoop(mock_ai, str(tmp_project), retest_func=None)
        result = await loop.run(report)

        assert result.total_bugs == 1
        assert result.fixed_bugs == 1
        assert result.failed_bugs == 0
        assert bug.fix_status == FixStatus.FIXED

        # 验证文件确实被修改
        content = (tmp_project / "src" / "app.js").read_text(encoding="utf-8")
        assert 'return "success"' in content


class TestRepairLoopWithRetest:
    """带重测的修复闭环测试。"""

    @pytest.mark.asyncio
    async def test_fix_and_retest_pass(self, mock_ai, tmp_project):
        """补丁应用后重测通过。"""
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return '{"is_blocking": false, "reason": "非阻塞"}'
            return json.dumps({
                "analysis": "返回值错误",
                "can_fix": True,
                "confidence": 0.9,
                "patches": [
                    {
                        "file_path": "src/app.js",
                        "description": "修复",
                        "old_code": 'return "ok"',
                        "new_code": 'return "fixed"',
                    }
                ],
                "explanation": "修正",
                "risk_level": "low",
            })

        mock_ai.chat.side_effect = side_effect

        # 重测函数返回全部通过
        async def retest_pass(step_numbers):
            return [
                StepResult(step=s, action=ActionType.CLICK, status=StepStatus.PASSED)
                for s in step_numbers
            ]

        bug = _make_bug(severity=BugSeverity.MEDIUM)
        step = _make_step_result(step=2, status=StepStatus.FAILED)
        report = _make_test_report(bugs=[bug], step_results=[step])

        loop = RepairLoop(mock_ai, str(tmp_project), retest_func=retest_pass)
        result = await loop.run(report)

        assert result.fixed_bugs == 1
        assert bug.fix_status == FixStatus.VERIFIED


class TestMaxAttempts:
    """最大重试次数测试。"""

    def test_max_attempts_constant(self):
        assert MAX_FIX_ATTEMPTS == 2


class TestRepairReportSummary:
    """修复报告摘要生成测试。"""

    def test_summary_contains_stats(self):
        report = RepairReport(
            total_bugs=3,
            blocking_bugs=1,
            fixed_bugs=2,
            failed_bugs=1,
            needs_human_bugs=0,
        )
        summary = RepairLoop._generate_summary(report)
        assert "总 Bug 数" in summary
        assert "3" in summary
        assert "成功修复" in summary
        assert "2" in summary
