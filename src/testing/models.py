"""
测试执行的数据模型

定义测试生命周期中所有结构化数据：
- TestStep: 单个测试步骤（AI生成 → 解析 → 执行）
- StepResult: 步骤执行结果（含截图路径、分析结果）
- TestScript: 完整测试脚本（多个步骤的集合）
- TestReport: 测试报告（汇总所有结果）
- BugReport: Bug 报告条目
"""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """测试步骤的操作类型。"""

    NAVIGATE = "navigate"
    NAVIGATE_TO = "navigate_to"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    SCROLL = "scroll"
    ASSERT_TEXT = "assert_text"
    ASSERT_VISIBLE = "assert_visible"
    ASSERT_COMPARE = "assert_compare"
    EVALUATE = "evaluate"
    CALL_METHOD = "call_method"
    READ_TEXT = "read_text"
    TAP_MULTIPLE = "tap_multiple"
    RESET_STATE = "reset_state"


class StepStatus(str, Enum):
    """步骤执行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class BugSeverity(str, Enum):
    """Bug 严重程度。"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FixStatus(str, Enum):
    """Bug 修复状态。"""

    UNFIXED = "unfixed"
    FIXING = "fixing"
    FIXED = "fixed"
    FIX_FAILED = "fix_failed"
    VERIFIED = "verified"
    NEEDS_HUMAN = "needs_human"


class TestStep(BaseModel):
    """单个测试步骤。"""

    step: int = Field(..., description="步骤序号")
    action: ActionType = Field(..., description="操作类型")
    target: str = Field(default="", description="操作目标（URL/选择器/方向）")
    value: str = Field(default="", description="操作值（输入文本/选项值/像素数）")
    description: str = Field(default="", description="步骤描述")
    expected: str = Field(default="", description="预期结果描述")


class ScreenshotAnalysis(BaseModel):
    """截图视觉分析结果。"""

    matches_expected: bool = Field(..., description="是否符合预期")
    confidence: float = Field(default=0.0, description="置信度 0-1")
    page_description: str = Field(default="", description="页面内容描述")
    issues: list[str] = Field(default_factory=list, description="发现的问题")
    suggestions: list[str] = Field(default_factory=list, description="改进建议")


class StepResult(BaseModel):
    """步骤执行结果。"""

    step: int = Field(..., description="步骤序号")
    status: StepStatus = Field(default=StepStatus.PENDING, description="执行状态")
    description: str = Field(default="", description="步骤描述")
    action: ActionType = Field(..., description="操作类型")
    screenshot_path: Optional[str] = Field(default=None, description="截图文件路径")
    analysis: Optional[ScreenshotAnalysis] = Field(default=None, description="截图分析结果")
    error_message: str = Field(default="", description="错误信息（如果失败）")
    duration_seconds: float = Field(default=0.0, description="执行耗时（秒）")


class BugReport(BaseModel):
    """单个 Bug 报告。"""

    severity: BugSeverity = Field(..., description="严重程度")
    category: str = Field(default="", description="Bug 类别")
    title: str = Field(default="", description="Bug 标题")
    description: str = Field(default="", description="详细描述")
    location: str = Field(default="", description="问题位置")
    reproduction: str = Field(default="", description="复现步骤")
    screenshot_path: Optional[str] = Field(default=None, description="相关截图路径")
    step_number: Optional[int] = Field(default=None, description="关联的测试步骤号")
    is_blocking: bool = Field(default=False, description="是否为阻塞性Bug（页面崩溃/无法继续）")
    fix_status: FixStatus = Field(default=FixStatus.UNFIXED, description="修复状态")


class TestScript(BaseModel):
    """完整测试脚本。"""

    test_name: str = Field(..., description="测试名称")
    description: str = Field(default="", description="测试描述")
    steps: list[TestStep] = Field(default_factory=list, description="测试步骤列表")


class TestReport(BaseModel):
    """测试执行报告。"""

    test_name: str = Field(..., description="测试名称")
    url: str = Field(default="", description="被测应用 URL")
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = Field(default=None)
    total_steps: int = Field(default=0, description="总步骤数")
    passed_steps: int = Field(default=0, description="通过步骤数")
    failed_steps: int = Field(default=0, description="失败步骤数")
    error_steps: int = Field(default=0, description="错误步骤数")
    step_results: list[StepResult] = Field(default_factory=list, description="所有步骤结果")
    bugs: list[BugReport] = Field(default_factory=list, description="发现的 Bug")
    report_markdown: str = Field(default="", description="Markdown 格式的完整报告")
    repair_report: Optional[Any] = Field(default=None, description="修复报告（v0.4，RepairReport 类型）")

    @property
    def pass_rate(self) -> float:
        """计算通过率。"""
        if self.total_steps == 0:
            return 0.0
        return self.passed_steps / self.total_steps

    @property
    def duration_seconds(self) -> float:
        """计算总耗时。"""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()
