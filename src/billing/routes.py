"""
积分计费 API 路由（v13.0-D）

端点：
- GET  /billing/plans        — 查询所有订阅方案
- GET  /billing/my-plan      — 查看我的当前方案和积分
- GET  /billing/usage        — 查看用量统计
- POST /billing/webhook      — 支付回调（签名验证 + 积分充值）
- POST /billing/upgrade      — 升级套餐
"""

import hashlib
import hmac
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from loguru import logger

from src.auth.database import get_db
from src.auth.middleware import get_current_user
from src.auth.models import User
from src.billing.plans import PLANS, PlanType
from src.community import service as community_service

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans")
def list_plans():
    """获取所有可选订阅方案。"""
    return {
        "plans": [
            {
                "type": info.plan_type.value,
                "name": info.name,
                "price_monthly": info.price_monthly,
                "credits_monthly": info.credits_monthly,
                "max_concurrent_tests": info.max_concurrent_tests,
                "features": info.features,
            }
            for info in PLANS.values()
        ]
    }


@router.get("/my-plan")
def get_my_plan(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查看我的当前方案和积分余额。"""
    balance = community_service.get_credit_balance(db, user.id)
    plan_key = PlanType(balance["plan"]) if balance["plan"] in [p.value for p in PlanType] else PlanType.FREE
    plan_info = PLANS[plan_key]
    return {
        "plan": {
            "type": plan_info.plan_type.value,
            "name": plan_info.name,
            "price_monthly": plan_info.price_monthly,
            "credits_monthly": plan_info.credits_monthly,
            "features": plan_info.features,
        },
        "credits": balance["credits"],
        "credits_used": balance["credits_used"],
    }


@router.get("/usage")
def get_usage(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查看积分消费流水摘要。"""
    return community_service.list_credit_transactions(db, user.id, page=1, per_page=50)


class UpgradeRequest(BaseModel):
    plan: str = Field(..., pattern="^(free|basic|pro|team)$")


@router.post("/upgrade")
def upgrade_plan(
    body: UpgradeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """升级/切换套餐（实际扣费由支付 Webhook 完成，这里仅标记）。"""
    target = PlanType(body.plan)
    plan_info = PLANS[target]

    if plan_info.price_monthly > 0:
        return {
            "ok": False,
            "message": "付费套餐请通过支付页面完成购买",
            "payment_url": f"/pricing?plan={body.plan}",
        }

    user.plan = body.plan
    db.commit()
    return {
        "ok": True,
        "plan": plan_info.plan_type.value,
        "name": plan_info.name,
        "credits_monthly": plan_info.credits_monthly,
    }


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """支付网关回调。

    流程：
    1. 验证签名（HMAC-SHA256）
    2. 解析订单信息（user_id, plan, amount）
    3. 升级套餐 + 充值积分
    4. 返回 200（支付平台要求）

    支持的 event_type：
    - payment.success  — 支付成功
    - subscription.renewed — 订阅续费
    """
    body = await request.body()
    signature = request.headers.get("X-Webhook-Signature", "")
    webhook_secret = os.environ.get("PAYMENT_WEBHOOK_SECRET", "")

    if webhook_secret:
        expected = hmac.new(
            webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning("支付回调签名验证失败")
            raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        import json
        payload = json.loads(body)
    except Exception:
        logger.error("支付回调 JSON 解析失败")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("event_type", "")
    order_data = payload.get("data", {})
    user_id = order_data.get("user_id")
    plan_str = order_data.get("plan", "")
    amount_paid = order_data.get("amount", 0)
    order_id = order_data.get("order_id", "")

    logger.info(
        "支付回调 | event={} user={} plan={} amount={} order={}",
        event_type, user_id, plan_str, amount_paid, order_id,
    )

    if event_type in ("payment.success", "subscription.renewed") and user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.warning("支付回调用户不存在 | user_id={}", user_id)
            return {"ok": True, "message": "user not found, logged"}

        if plan_str and plan_str in [p.value for p in PlanType]:
            target_plan = PlanType(plan_str)
            plan_info = PLANS[target_plan]
            user.plan = plan_str
            community_service.add_credits(
                db, user.id,
                amount=plan_info.credits_monthly,
                reason="subscription",
                detail=f"套餐升级: {plan_info.name}",
                reference_id=order_id,
            )
            logger.info("套餐升级成功 | user={} plan={} credits=+{}", user_id, plan_str, plan_info.credits_monthly)

        db.commit()

    return {"ok": True, "message": "webhook processed"}
