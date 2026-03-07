"""
测试数据模型的单元测试。

验证：
- 枚举类型定义正确
- TestStep / StepResult / TestReport 的字段和默认值
- TestReport 的 pass_rate 和 duration_seconds 计算
"""

from datetime import datetime, timezone

from src.testing.models import (
    ActionType,
    BugReport,
    BugSeverity,
    ScreenshotAnalysis,
    StepResult,
    StepStatus,
    TestReport,
    TestScript,
    TestStep,
)


class TestActionType:
    """操作类型枚举测试。"""

    def test_all_actions_defined(self) -> None:
        """所有预期的操作类型都应存在。"""
        expected = {"navigate", "click", "fill", "select", "wait", "screenshot", "scroll", "assert_text", "assert_visible"}
        actual = {a.value for a in ActionType}
        assert expected == actual


class TestStepStatus:
    """步骤状态枚举测试。"""

    def test_all_statuses_defined(self) -> None:
        expected = {"pending", "running", "passed", "failed", "error", "skipped"}
        actual = {s.value for s in StepStatus}
        assert expected == actual


class TestTestStep:
    """测试步骤模型测试。"""

    def test_create_navigate_step(self) -> None:
        step = TestStep(step=1, action=ActionType.NAVIGATE, target="http://example.com")
        assert step.step == 1
        assert step.action == ActionType.NAVIGATE
        assert step.value == ""
        assert step.expected == ""

    def test_create_fill_step(self) -> None:
        step = TestStep(
            step=2, action=ActionType.FILL,
            target="#username", value="admin",
            description="输入用户名", expected="输入框显示admin",
        )
        assert step.value == "admin"
        assert step.description == "输入用户名"


class TestTestScript:
    """测试脚本模型测试。"""

    def test_create_script(self) -> None:
        script = TestScript(
            test_name="登录测试",
            description="测试登录功能",
            steps=[
                TestStep(step=1, action=ActionType.NAVIGATE, target="http://localhost"),
                TestStep(step=2, action=ActionType.CLICK, target="#btn"),
            ],
        )
        assert script.test_name == "登录测试"
        assert len(script.steps) == 2


class TestTestReport:
    """测试报告模型测试。"""

    def test_pass_rate_calculation(self) -> None:
        """通过率计算应该正确。"""
        report = TestReport(
            test_name="test",
            total_steps=10,
            passed_steps=8,
            failed_steps=2,
        )
        assert report.pass_rate == 0.8

    def test_pass_rate_zero_steps(self) -> None:
        """零步骤时通过率应为0。"""
        report = TestReport(test_name="empty", total_steps=0)
        assert report.pass_rate == 0.0

    def test_duration_calculation(self) -> None:
        """耗时计算应该正确。"""
        start = datetime(2026, 3, 3, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 3, 12, 1, 30, tzinfo=timezone.utc)
        report = TestReport(test_name="test", start_time=start, end_time=end)
        assert report.duration_seconds == 90.0

    def test_duration_no_end_time(self) -> None:
        """没有结束时间时耗时应为0。"""
        report = TestReport(test_name="test")
        assert report.duration_seconds == 0.0


class TestBugReport:
    """Bug报告模型测试。"""

    def test_create_bug(self) -> None:
        bug = BugReport(
            severity=BugSeverity.HIGH,
            category="功能缺陷",
            title="按钮无响应",
            description="点击登录按钮后页面无变化",
        )
        assert bug.severity == BugSeverity.HIGH
        assert bug.screenshot_path is None
