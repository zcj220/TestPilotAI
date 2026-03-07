"""
订阅方案与积分管理（v1.0）

基于项目规划中的定价方案：
- 免费版：50积分/月
- 基础版：19元/月，500积分
- 专业版：59元/月，2000积分
- 团队版：199元/月，10000积分
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PlanType(str, Enum):
    """订阅方案类型。"""
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    TEAM = "team"


class PlanInfo(BaseModel):
    """订阅方案详情。"""
    plan_type: PlanType
    name: str
    price_monthly: float = Field(description="月费（元）")
    credits_monthly: int = Field(description="每月积分额度")
    max_concurrent_tests: int = Field(default=1, description="最大并发测试数")
    features: list[str] = Field(default_factory=list, description="包含功能")


# 方案定义
PLANS: dict[PlanType, PlanInfo] = {
    PlanType.FREE: PlanInfo(
        plan_type=PlanType.FREE,
        name="免费版",
        price_monthly=0,
        credits_monthly=50,
        max_concurrent_tests=1,
        features=["基础测试", "Bug检测", "测试报告"],
    ),
    PlanType.BASIC: PlanInfo(
        plan_type=PlanType.BASIC,
        name="基础版",
        price_monthly=19,
        credits_monthly=500,
        max_concurrent_tests=2,
        features=["基础测试", "Bug检测", "测试报告", "自动修复", "历史记录"],
    ),
    PlanType.PRO: PlanInfo(
        plan_type=PlanType.PRO,
        name="专业版",
        price_monthly=59,
        credits_monthly=2000,
        max_concurrent_tests=5,
        features=["基础测试", "Bug检测", "测试报告", "自动修复", "历史记录", "交叉验证", "VNC实时观看", "优先支持"],
    ),
    PlanType.TEAM: PlanInfo(
        plan_type=PlanType.TEAM,
        name="团队版",
        price_monthly=199,
        credits_monthly=10000,
        max_concurrent_tests=10,
        features=["全部功能", "团队协作", "API访问", "自定义集成", "专属支持"],
    ),
}


class UserAccount(BaseModel):
    """用户账户。"""
    user_id: str = Field(description="用户ID")
    email: str = Field(default="", description="邮箱")
    plan: PlanType = Field(default=PlanType.FREE, description="当前方案")
    credits_remaining: int = Field(default=50, description="剩余积分")
    credits_used_this_month: int = Field(default=0, description="本月已用积分")
    api_key: str = Field(default="", description="API Key")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    plan_expires_at: Optional[datetime] = Field(default=None, description="方案到期时间")

    @property
    def plan_info(self) -> PlanInfo:
        return PLANS[self.plan]

    @property
    def credits_limit(self) -> int:
        return self.plan_info.credits_monthly

    @property
    def usage_percent(self) -> float:
        if self.credits_limit == 0:
            return 0.0
        return self.credits_used_this_month / self.credits_limit * 100

    def can_afford(self, credits: int) -> bool:
        """检查余额是否足够。"""
        return self.credits_remaining >= credits

    def deduct(self, credits: int) -> bool:
        """扣除积分，返回是否成功。"""
        if not self.can_afford(credits):
            return False
        self.credits_remaining -= credits
        self.credits_used_this_month += credits
        return True

    def recharge(self, credits: int) -> None:
        """充值积分。"""
        self.credits_remaining += credits

    def reset_monthly(self) -> None:
        """月度重置（每月初调用）。"""
        self.credits_remaining = self.plan_info.credits_monthly
        self.credits_used_this_month = 0
