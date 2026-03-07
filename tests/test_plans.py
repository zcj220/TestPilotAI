"""
订阅方案与用户账户的单元测试
"""

import pytest

from src.billing.plans import PLANS, PlanType, PlanInfo, UserAccount


class TestPlanType:
    """订阅方案枚举测试。"""

    def test_all_plans_defined(self):
        assert PlanType.FREE in PLANS
        assert PlanType.BASIC in PLANS
        assert PlanType.PRO in PLANS
        assert PlanType.TEAM in PLANS

    def test_free_plan_price(self):
        assert PLANS[PlanType.FREE].price_monthly == 0

    def test_free_plan_credits(self):
        assert PLANS[PlanType.FREE].credits_monthly == 50

    def test_basic_plan(self):
        p = PLANS[PlanType.BASIC]
        assert p.price_monthly == 19
        assert p.credits_monthly == 500

    def test_pro_plan(self):
        p = PLANS[PlanType.PRO]
        assert p.price_monthly == 59
        assert p.credits_monthly == 2000

    def test_team_plan(self):
        p = PLANS[PlanType.TEAM]
        assert p.price_monthly == 199
        assert p.credits_monthly == 10000

    def test_concurrent_limits(self):
        assert PLANS[PlanType.FREE].max_concurrent_tests == 1
        assert PLANS[PlanType.TEAM].max_concurrent_tests == 10


class TestUserAccount:
    """用户账户测试。"""

    def test_default_account(self):
        user = UserAccount(user_id="u_test", email="test@example.com")
        assert user.plan == PlanType.FREE
        assert user.credits_remaining == 50
        assert user.credits_used_this_month == 0

    def test_plan_info(self):
        user = UserAccount(user_id="u_test", plan=PlanType.PRO)
        assert user.plan_info.name == "专业版"
        assert user.credits_limit == 2000

    def test_usage_percent(self):
        user = UserAccount(
            user_id="u_test",
            plan=PlanType.FREE,
            credits_used_this_month=25,
        )
        assert user.usage_percent == 50.0

    def test_can_afford(self):
        user = UserAccount(user_id="u_test", credits_remaining=10)
        assert user.can_afford(5) is True
        assert user.can_afford(10) is True
        assert user.can_afford(11) is False

    def test_deduct(self):
        user = UserAccount(user_id="u_test", credits_remaining=20)
        assert user.deduct(5) is True
        assert user.credits_remaining == 15
        assert user.credits_used_this_month == 5

    def test_deduct_insufficient(self):
        user = UserAccount(user_id="u_test", credits_remaining=3)
        assert user.deduct(5) is False
        assert user.credits_remaining == 3

    def test_recharge(self):
        user = UserAccount(user_id="u_test", credits_remaining=10)
        user.recharge(100)
        assert user.credits_remaining == 110

    def test_reset_monthly(self):
        user = UserAccount(
            user_id="u_test",
            plan=PlanType.BASIC,
            credits_remaining=3,
            credits_used_this_month=497,
        )
        user.reset_monthly()
        assert user.credits_remaining == 500
        assert user.credits_used_this_month == 0
