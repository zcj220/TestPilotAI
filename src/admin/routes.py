"""
管理后台 API（v13.0-D）

仅限 admin 角色访问，提供：
- 用户管理（列表/封禁/修改角色/调整积分）
- 经验审核（列表被举报经验/审核通过/删除）
- 系统统计概览
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from src.auth.database import get_db
from src.auth.middleware import require_role
from src.auth.models import User
from src.community.models import (
    SharedExperience, ExperienceVote, UserProfile,
    EXP_STATUS_ACTIVE, EXP_STATUS_FLAGGED, EXP_STATUS_HIDDEN, EXP_STATUS_DELETED,
)
from src.community.service import add_credits

router = APIRouter(prefix="/admin", tags=["admin"])


# ── 请求模型 ─────────────────────────────────────

class UserActionRequest(BaseModel):
    action: str = Field(..., pattern="^(ban|unban|set_role|add_credits)$")
    role: str = Field(default="")
    credits: int = Field(default=0)
    reason: str = Field(default="")

class ExperienceActionRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|delete|hide)$")
    reason: str = Field(default="")


# ── 1. 系统统计 ───────────────────────────────────

@router.get(
    "/dashboard",
    dependencies=[Depends(require_role("admin"))],
)
def admin_dashboard(db: Session = Depends(get_db)):
    """管理后台首页统计。"""
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar() or 0

    total_experiences = db.query(func.count(SharedExperience.id)).filter(
        SharedExperience.status == EXP_STATUS_ACTIVE
    ).scalar() or 0

    flagged_count = db.query(func.count(SharedExperience.id)).filter(
        SharedExperience.status == EXP_STATUS_FLAGGED
    ).scalar() or 0

    report_count = db.query(func.count(ExperienceVote.id)).filter(
        ExperienceVote.vote_type == "report"
    ).scalar() or 0

    plan_breakdown = db.query(
        User.plan, func.count(User.id)
    ).group_by(User.plan).all()

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "plan_breakdown": {p: c for p, c in plan_breakdown},
        },
        "experiences": {
            "total": total_experiences,
            "flagged": flagged_count,
            "pending_reports": report_count,
        },
    }


# ── 2. 用户管理 ───────────────────────────────────

@router.get(
    "/users",
    dependencies=[Depends(require_role("admin"))],
)
def list_users(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str = Query(default=""),
    db: Session = Depends(get_db),
):
    """分页列出所有用户。"""
    q = db.query(User)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (User.username.ilike(like)) | (User.email.ilike(like))
        )
    total = q.count()
    users = q.order_by(User.id.desc()).offset((page - 1) * per_page).limit(per_page).all()

    items = []
    for u in users:
        profile = db.query(UserProfile).filter(UserProfile.user_id == u.id).first()
        items.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "plan": u.plan,
            "credits": u.credits,
            "is_active": u.is_active,
            "display_name": profile.display_name if profile else "",
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })

    return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.post(
    "/users/{user_id}/action",
    dependencies=[Depends(require_role("admin"))],
)
def user_action(
    user_id: int,
    body: UserActionRequest,
    db: Session = Depends(get_db),
):
    """对用户执行管理操作。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if body.action == "ban":
        user.is_active = False
        db.commit()
        return {"ok": True, "message": f"用户 {user.username} 已封禁"}

    elif body.action == "unban":
        user.is_active = True
        db.commit()
        return {"ok": True, "message": f"用户 {user.username} 已解封"}

    elif body.action == "set_role":
        if body.role not in ("free", "basic", "pro", "team", "admin"):
            raise HTTPException(status_code=400, detail="无效角色")
        user.role = body.role
        db.commit()
        return {"ok": True, "message": f"用户角色已更改为 {body.role}"}

    elif body.action == "add_credits":
        if body.credits == 0:
            raise HTTPException(status_code=400, detail="积分数不能为 0")
        tx = add_credits(
            db, user.id, body.credits,
            reason="admin_adjust",
            detail=body.reason or f"管理员调整 {body.credits:+d}",
        )
        return {
            "ok": True,
            "message": f"积分调整 {body.credits:+d}，余额 {tx.balance_after}",
        }


# ── 3. 经验审核 ───────────────────────────────────

@router.get(
    "/experiences/flagged",
    dependencies=[Depends(require_role("admin"))],
)
def list_flagged_experiences(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """列出被举报/标记的经验。"""
    q = db.query(SharedExperience).filter(
        SharedExperience.status == EXP_STATUS_FLAGGED
    )
    total = q.count()
    items = q.order_by(SharedExperience.updated_at.desc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()

    result = []
    for exp in items:
        report_count = db.query(func.count(ExperienceVote.id)).filter(
            ExperienceVote.experience_id == exp.id,
            ExperienceVote.vote_type == "report",
        ).scalar() or 0

        author = db.query(User).filter(User.id == exp.user_id).first()

        result.append({
            **exp.to_dict(),
            "report_count": report_count,
            "author_username": author.username if author else "unknown",
        })

    return {"items": result, "total": total, "page": page, "per_page": per_page}


@router.post(
    "/experiences/{exp_id}/action",
    dependencies=[Depends(require_role("admin"))],
)
def experience_action(
    exp_id: int,
    body: ExperienceActionRequest,
    db: Session = Depends(get_db),
):
    """对经验执行管理操作。"""
    exp = db.query(SharedExperience).filter(SharedExperience.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="经验不存在")

    if body.action == "approve":
        exp.status = EXP_STATUS_ACTIVE
        db.query(ExperienceVote).filter(
            ExperienceVote.experience_id == exp_id,
            ExperienceVote.vote_type == "report",
        ).delete()
        db.commit()
        return {"ok": True, "message": "经验已恢复为正常状态，举报记录已清除"}

    elif body.action == "delete":
        exp.status = EXP_STATUS_DELETED
        db.commit()
        return {"ok": True, "message": "经验已删除"}

    elif body.action == "hide":
        exp.status = EXP_STATUS_HIDDEN
        db.commit()
        return {"ok": True, "message": "经验已隐藏"}
