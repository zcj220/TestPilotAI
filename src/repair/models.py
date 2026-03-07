"""
自动修复数据模型

定义修复闭环中所有结构化数据：
- PatchInfo: 单个代码补丁（文件路径 + 替换内容）
- FixPlan: AI 生成的修复方案（分析 + 补丁列表）
- FixAttempt: 单次修复尝试记录
- RepairReport: 修复闭环的最终报告
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """修复方案风险等级。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AttemptStatus(str, Enum):
    """修复尝试状态。"""

    PENDING = "pending"
    PATCHED = "patched"
    PATCH_FAILED = "patch_failed"
    RETEST_PASSED = "retest_passed"
    RETEST_FAILED = "retest_failed"
    ROLLED_BACK = "rolled_back"


class PatchInfo(BaseModel):
    """单个代码补丁。"""

    file_path: str = Field(..., description="相对于项目根目录的文件路径")
    description: str = Field(default="", description="此处修改的说明")
    old_code: str = Field(..., description="需要被替换的原始代码片段")
    new_code: str = Field(..., description="替换后的新代码")


class FixPlan(BaseModel):
    """AI 生成的修复方案。"""

    analysis: str = Field(default="", description="Bug 原因分析")
    can_fix: bool = Field(default=False, description="AI 是否有把握修复")
    confidence: float = Field(default=0.0, description="修复方案置信度 0-1")
    patches: list[PatchInfo] = Field(default_factory=list, description="补丁列表")
    explanation: str = Field(default="", description="修复方案整体说明")
    risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM, description="风险等级")


class FileBackup(BaseModel):
    """文件备份信息（用于回滚）。"""

    file_path: str = Field(..., description="文件的绝对路径")
    original_content: str = Field(..., description="原始文件内容")


class FixAttempt(BaseModel):
    """单次修复尝试记录。"""

    attempt_number: int = Field(..., description="尝试次数（第几次）")
    bug_title: str = Field(default="", description="关联的 Bug 标题")
    status: AttemptStatus = Field(default=AttemptStatus.PENDING, description="尝试状态")
    fix_plan: Optional[FixPlan] = Field(default=None, description="AI 生成的修复方案")
    backups: list[FileBackup] = Field(default_factory=list, description="文件备份")
    error_message: str = Field(default="", description="失败原因")
    duration_seconds: float = Field(default=0.0, description="耗时（秒）")


class RepairReport(BaseModel):
    """修复闭环最终报告。"""

    project_path: str = Field(default="", description="项目路径")
    total_bugs: int = Field(default=0, description="总 Bug 数")
    blocking_bugs: int = Field(default=0, description="阻塞性 Bug 数")
    fixed_bugs: int = Field(default=0, description="成功修复的 Bug 数")
    failed_bugs: int = Field(default=0, description="修复失败的 Bug 数")
    needs_human_bugs: int = Field(default=0, description="需人工介入的 Bug 数")
    attempts: list[FixAttempt] = Field(default_factory=list, description="所有修复尝试")
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = Field(default=None)
    summary: str = Field(default="", description="修复总结")

    @property
    def duration_seconds(self) -> float:
        """计算总耗时。"""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()

    @property
    def fix_rate(self) -> float:
        """计算修复成功率。"""
        if self.total_bugs == 0:
            return 0.0
        return self.fixed_bugs / self.total_bugs
