"""
修复数据模型的单元测试
"""

from datetime import datetime, timezone, timedelta

from src.repair.models import (
    AttemptStatus,
    FileBackup,
    FixAttempt,
    FixPlan,
    PatchInfo,
    RepairReport,
    RiskLevel,
)


class TestPatchInfo:
    """PatchInfo 模型测试。"""

    def test_create_patch(self):
        patch = PatchInfo(
            file_path="src/app.js",
            description="修复按钮事件",
            old_code="onClick={handleClick}",
            new_code="onClick={() => handleClick()}",
        )
        assert patch.file_path == "src/app.js"
        assert patch.old_code == "onClick={handleClick}"
        assert patch.new_code == "onClick={() => handleClick()}"

    def test_patch_default_description(self):
        patch = PatchInfo(file_path="a.py", old_code="x", new_code="y")
        assert patch.description == ""


class TestFixPlan:
    """FixPlan 模型测试。"""

    def test_create_fix_plan(self):
        plan = FixPlan(
            analysis="变量名拼写错误",
            can_fix=True,
            confidence=0.9,
            patches=[
                PatchInfo(file_path="a.py", old_code="nmae", new_code="name"),
            ],
            explanation="修正拼写错误",
            risk_level=RiskLevel.LOW,
        )
        assert plan.can_fix is True
        assert plan.confidence == 0.9
        assert len(plan.patches) == 1
        assert plan.risk_level == RiskLevel.LOW

    def test_empty_fix_plan(self):
        plan = FixPlan()
        assert plan.can_fix is False
        assert plan.patches == []
        assert plan.risk_level == RiskLevel.MEDIUM


class TestFixAttempt:
    """FixAttempt 模型测试。"""

    def test_create_attempt(self):
        attempt = FixAttempt(
            attempt_number=1,
            bug_title="登录按钮无响应",
            status=AttemptStatus.PATCHED,
        )
        assert attempt.attempt_number == 1
        assert attempt.status == AttemptStatus.PATCHED

    def test_attempt_defaults(self):
        attempt = FixAttempt(attempt_number=1)
        assert attempt.status == AttemptStatus.PENDING
        assert attempt.fix_plan is None
        assert attempt.backups == []
        assert attempt.error_message == ""


class TestRepairReport:
    """RepairReport 模型测试。"""

    def test_fix_rate_calculation(self):
        report = RepairReport(total_bugs=4, fixed_bugs=3)
        assert report.fix_rate == 0.75

    def test_fix_rate_zero_bugs(self):
        report = RepairReport(total_bugs=0)
        assert report.fix_rate == 0.0

    def test_duration_calculation(self):
        t0 = datetime(2026, 3, 3, 12, 0, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(seconds=45.5)
        report = RepairReport(start_time=t0, end_time=t1)
        assert report.duration_seconds == 45.5

    def test_duration_no_end_time(self):
        report = RepairReport()
        assert report.duration_seconds == 0.0

    def test_report_defaults(self):
        report = RepairReport()
        assert report.total_bugs == 0
        assert report.fixed_bugs == 0
        assert report.failed_bugs == 0
        assert report.needs_human_bugs == 0
        assert report.attempts == []
