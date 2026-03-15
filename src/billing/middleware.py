"""
积分消耗中间件（v13.0-D）

提供 FastAPI 依赖注入函数：
- require_credits(n): 检查余额、扣分、余额不足返回 402
- check_plan_limit(feature): 检查套餐是否包含该功能

用法：
    @router.post("/test/run")
    def run_test(
        ...,
        _credits=Depends(require_credits(5)),
    ):
"""

from functools import lru_cache

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.auth.database import get_db
from src.auth.middleware import get_current_user
from src.auth.models import User
from src.billing.plans import PLANS, PlanType
from src.community.service import consume_credits, get_credit_balance


def require_credits(amount: int):
    """生成依赖函数：检查并扣除积分。

    余额不足返回 HTTP 402 Payment Required。
    """
    async def _check(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        balance = get_credit_balance(db, user.id)
        if balance["credits"] < amount:
            plan = balance.get("plan", "free")
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "insufficient_credits",
                    "credits_required": amount,
                    "credits_available": balance["credits"],
                    "plan": plan,
                    "message": f"积分不足（需要 {amount}，剩余 {balance['credits']}）。请充值或升级套餐。",
                },
            )
        tx = consume_credits(db, user.id, amount, reason="test_run", detail=f"consume {amount} credits")
        if not tx:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={"error": "insufficient_credits", "message": "积分扣除失败"},
            )
        return {"credits_consumed": amount, "credits_remaining": tx.balance_after}
    return _check


def check_plan_limit(feature: str):
    """检查用户套餐是否包含指定功能。

    功能不在套餐范围内返回 HTTP 403。
    """
    async def _check(
        user: User = Depends(get_current_user),
    ):
        plan_key = PlanType(user.plan) if user.plan in [p.value for p in PlanType] else PlanType.FREE
        plan_info = PLANS[plan_key]
        if feature not in plan_info.features and "全部功能" not in plan_info.features:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "plan_feature_unavailable",
                    "feature": feature,
                    "current_plan": plan_info.plan_type.value,
                    "message": f"当前套餐（{plan_info.name}）不包含「{feature}」功能。请升级套餐。",
                },
            )
        return {"plan": plan_info.plan_type.value, "feature": feature}
    return _check
