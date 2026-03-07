"""
积分计量数据模型

根据项目规划中的定价方案：
- 生成测试脚本: 1积分
- 生成测试数据（AI-B）: 2积分
- 执行测试每步（含截图分析）: 1积分
- 自动修复Bug（每个）: 3积分
- 生成测试报告: 1积分
- 记忆压缩: 免费
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OperationType(str, Enum):
    """可计费操作类型。"""
    GENERATE_SCRIPT = "generate_script"
    GENERATE_TEST_DATA = "generate_test_data"
    EXECUTE_STEP = "execute_step"
    REPAIR_BUG = "repair_bug"
    GENERATE_REPORT = "generate_report"
    MEMORY_COMPRESS = "memory_compress"
    CROSS_VALIDATE = "cross_validate"


# 每种操作的积分消耗
CREDIT_COSTS: dict[OperationType, int] = {
    OperationType.GENERATE_SCRIPT: 1,
    OperationType.GENERATE_TEST_DATA: 2,
    OperationType.EXECUTE_STEP: 1,
    OperationType.REPAIR_BUG: 3,
    OperationType.GENERATE_REPORT: 1,
    OperationType.MEMORY_COMPRESS: 0,
    OperationType.CROSS_VALIDATE: 1,
}

# 每种操作的估算API成本（元）
# 基于 Doubao-Seed-1.8 实际价格：输入0.8元/百万token，输出2.0元/百万token
# v1.3实战测试token数据精算
API_COSTS: dict[OperationType, float] = {
    OperationType.GENERATE_SCRIPT: 0.0048,    # 输入1000+输出2000
    OperationType.GENERATE_TEST_DATA: 0.0048,  # 输入1000+输出2000
    OperationType.EXECUTE_STEP: 0.0012,        # 截图分析：输入650+输出350
    OperationType.REPAIR_BUG: 0.0046,          # 输入2000+输出1500
    OperationType.GENERATE_REPORT: 0.0032,     # 输入1500+输出1000
    OperationType.MEMORY_COMPRESS: 0.0018,     # AI压缩：输入1000+输出500
    OperationType.CROSS_VALIDATE: 0.0016,      # 输入800+输出500
}


class UsageRecord(BaseModel):
    """单次操作的用量记录。"""
    operation: OperationType
    credits: int = Field(default=0, description="消耗的积分")
    api_cost: float = Field(default=0.0, description="估算API成本（元）")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    detail: str = Field(default="", description="操作详情")


class UsageSummary(BaseModel):
    """用量统计摘要。"""
    total_credits: int = Field(default=0, description="总消耗积分")
    total_api_cost: float = Field(default=0.0, description="总估算API成本（元）")
    record_count: int = Field(default=0, description="操作次数")
    breakdown: dict[str, int] = Field(default_factory=dict, description="按操作类型的积分分布")


class TestBill(BaseModel):
    """单次测试的账单。"""
    test_name: str = Field(default="", description="测试名称")
    url: str = Field(default="", description="测试URL")
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    records: list[UsageRecord] = Field(default_factory=list)

    @property
    def total_credits(self) -> int:
        return sum(r.credits for r in self.records)

    @property
    def total_api_cost(self) -> float:
        return sum(r.api_cost for r in self.records)

    @property
    def breakdown(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for r in self.records:
            key = r.operation.value
            result[key] = result.get(key, 0) + r.credits
        return result
