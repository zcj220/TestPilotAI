"""
社区经验库业务逻辑（v13.0）

所有数据库操作封装在此，供路由层调用。
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, desc, or_
from sqlalchemy.orm import Session
from loguru import logger

from src.community.models import (
    SharedExperience, ExperienceVote, UserBadge, UserProfile,
    DebugSnapshot, CreditTransaction,
    BADGE_DEFINITIONS, BADGE_TYPE_MAP,
    EXP_STATUS_ACTIVE, EXP_STATUS_FLAGGED,
    VOTE_UPVOTE, VOTE_DOWNVOTE, VOTE_ADOPT,
)
from src.community.anonymizer import (
    anonymize_experience, calc_share_score, validate_content, ValidationResult,
)
from src.auth.models import User


# ══════════════════════════════════════════════════════
#  经验 CRUD
# ══════════════════════════════════════════════════════

def create_experience(db: Session, user_id: int, data: dict) -> SharedExperience:
    """创建一条共享经验。"""
    exp = SharedExperience(
        user_id=user_id,
        title=data["title"],
        platform=data["platform"],
        framework=data.get("framework", ""),
        error_type=data.get("error_type", ""),
        problem_desc=data["problem_desc"],
        solution_desc=data["solution_desc"],
        root_cause=data.get("root_cause", ""),
        code_snippet=data.get("code_snippet", ""),
        tags=data.get("tags", []),
        tool_versions=data.get("tool_versions", {}),
        difficulty=data.get("difficulty", "medium"),
        share_score=data.get("share_score", 0.0),
        fix_pattern=data.get("fix_pattern", ""),
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)

    _check_and_award_badges(db, user_id)
    return exp


def get_experience(db: Session, exp_id: int) -> Optional[SharedExperience]:
    """获取经验详情并增加浏览计数。"""
    exp = db.query(SharedExperience).filter(
        SharedExperience.id == exp_id,
        SharedExperience.status == EXP_STATUS_ACTIVE,
    ).first()
    if exp:
        exp.view_count += 1
        db.commit()
    return exp


def get_experience_raw(db: Session, exp_id: int) -> Optional[SharedExperience]:
    """获取经验详情（不增加浏览计数）。"""
    return db.query(SharedExperience).filter(SharedExperience.id == exp_id).first()


def list_experiences(
    db: Session,
    *,
    platform: str = "",
    framework: str = "",
    error_type: str = "",
    search: str = "",
    sort_by: str = "created_at",
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """搜索/过滤/分页获取经验列表。"""
    q = db.query(SharedExperience).filter(SharedExperience.status == EXP_STATUS_ACTIVE)

    if platform:
        q = q.filter(SharedExperience.platform == platform)
    if framework:
        q = q.filter(SharedExperience.framework == framework)
    if error_type:
        q = q.filter(SharedExperience.error_type == error_type)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            SharedExperience.title.ilike(like),
            SharedExperience.problem_desc.ilike(like),
            SharedExperience.solution_desc.ilike(like),
        ))

    total = q.count()

    sort_map = {
        "created_at": SharedExperience.created_at.desc(),
        "upvotes": SharedExperience.upvote_count.desc(),
        "views": SharedExperience.view_count.desc(),
        "adoption": SharedExperience.adoption_count.desc(),
        "score": SharedExperience.share_score.desc(),
    }
    order = sort_map.get(sort_by, SharedExperience.created_at.desc())
    items = q.order_by(order).offset((page - 1) * per_page).limit(per_page).all()

    return {
        "items": [e.to_dict() for e in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


def get_trending(db: Session, limit: int = 10) -> list[dict]:
    """获取近期热门经验（按浏览+投票综合排序）。"""
    items = (
        db.query(SharedExperience)
        .filter(SharedExperience.status == EXP_STATUS_ACTIVE)
        .order_by(
            desc(SharedExperience.upvote_count + SharedExperience.view_count * 0.1)
        )
        .limit(limit)
        .all()
    )
    return [e.to_dict() for e in items]


def suggest_for_error(db: Session, platform: str, error_type: str, limit: int = 5) -> list[dict]:
    """根据平台和错误类型推荐相似经验。"""
    q = (
        db.query(SharedExperience)
        .filter(
            SharedExperience.status == EXP_STATUS_ACTIVE,
            SharedExperience.platform == platform,
        )
    )
    if error_type:
        q = q.filter(SharedExperience.error_type == error_type)

    items = q.order_by(desc(SharedExperience.adoption_count)).limit(limit).all()
    return [e.to_dict() for e in items]


def update_experience(db: Session, exp_id: int, user_id: int, data: dict) -> Optional[SharedExperience]:
    """更新经验（仅作者可改）。"""
    exp = db.query(SharedExperience).filter(
        SharedExperience.id == exp_id,
        SharedExperience.user_id == user_id,
    ).first()
    if not exp:
        return None

    updatable = (
        "title", "problem_desc", "solution_desc", "root_cause",
        "code_snippet", "tags", "tool_versions",
    )
    for k in updatable:
        if k in data:
            setattr(exp, k, data[k])
    db.commit()
    db.refresh(exp)
    return exp


def delete_experience(db: Session, exp_id: int, user_id: int) -> bool:
    """软删除经验（仅作者/管理员）。"""
    exp = db.query(SharedExperience).filter(SharedExperience.id == exp_id).first()
    if not exp:
        return False
    if exp.user_id != user_id:
        return False
    exp.status = "deleted"
    db.commit()
    return True


# ══════════════════════════════════════════════════════
#  从快照分享（匿名化 → 审核 → 评分 → 存储）
# ══════════════════════════════════════════════════════

def share_from_snapshot(db: Session, user_id: int, snapshot_id: int, extra: dict) -> dict:
    """
    将调试快照转化为社区经验。

    流程：
    1. 查找快照（必须属于该用户且已解决）
    2. 组装原始经验数据
    3. 内容审核
    4. 匿名化处理
    5. 计算分享价值评分
    6. 存入 shared_experiences
    7. 反向关联 snapshot.shared_experience_id
    """
    snap = db.query(DebugSnapshot).filter(
        DebugSnapshot.id == snapshot_id,
        DebugSnapshot.user_id == user_id,
    ).first()
    if not snap:
        return {"ok": False, "error": "snapshot_not_found"}
    if not snap.resolved:
        return {"ok": False, "error": "snapshot_not_resolved"}
    if snap.shared_experience_id:
        return {"ok": False, "error": "already_shared"}

    raw_data = {
        "title": extra.get("title", f"{snap.framework} {snap.error_message[:60]}").strip(),
        "platform": extra.get("platform") or snap.platform,
        "framework": extra.get("framework") or snap.framework,
        "error_type": extra.get("error_type", ""),
        "problem_desc": extra.get("problem_desc") or snap.error_message,
        "solution_desc": extra.get("solution_desc") or snap.fix_description,
        "root_cause": extra.get("root_cause", ""),
        "code_snippet": extra.get("code_snippet", ""),
        "tags": extra.get("tags", []),
        "tool_versions": extra.get("tool_versions", {}),
        "difficulty": extra.get("difficulty", "medium"),
        "fix_pattern": extra.get("fix_pattern", ""),
    }

    validation = validate_content(raw_data)
    if not validation.valid:
        return {"ok": False, "error": "validation_failed", "reasons": validation.reasons}

    anonymized = anonymize_experience(raw_data)

    score = calc_share_score(anonymized)
    anonymized["share_score"] = score.total

    exp = create_experience(db, user_id, anonymized)

    snap.shared_experience_id = exp.id
    db.commit()

    logger.info("快照 {} 已分享为经验 {} | score={}", snapshot_id, exp.id, score.total)
    return {
        "ok": True,
        "experience": exp.to_dict(),
        "score_breakdown": {
            "total": score.total,
            "has_problem": score.has_problem,
            "has_solution": score.has_solution,
            "has_root_cause": score.has_root_cause,
            "has_code": score.has_code,
        },
    }


def share_direct(db: Session, user_id: int, data: dict) -> dict:
    """
    直接分享经验（不经快照，如 AI 编程工具发来的自动分享请求）。

    流程同上：审核 → 匿名化 → 评分 → 存储。
    """
    validation = validate_content(data)
    if not validation.valid:
        return {"ok": False, "error": "validation_failed", "reasons": validation.reasons}

    anonymized = anonymize_experience(data)
    score = calc_share_score(anonymized)
    anonymized["share_score"] = score.total

    exp = create_experience(db, user_id, anonymized)

    logger.info("直接分享经验 {} | user={} score={}", exp.id, user_id, score.total)
    return {
        "ok": True,
        "experience": exp.to_dict(),
        "score_breakdown": {
            "total": score.total,
            "has_problem": score.has_problem,
            "has_solution": score.has_solution,
            "has_root_cause": score.has_root_cause,
            "has_code": score.has_code,
        },
    }


def preview_anonymized(data: dict) -> dict:
    """预览匿名化结果（不写库），供用户确认。"""
    validation = validate_content(data)
    anonymized = anonymize_experience(data)
    score = calc_share_score(anonymized)

    return {
        "anonymized": anonymized,
        "score": score.total,
        "validation": {"valid": validation.valid, "reasons": validation.reasons},
    }


def report_experience(db: Session, exp_id: int, user_id: int, reason: str) -> dict:
    """举报经验。累计举报达到阈值自动隐藏。"""
    exp = db.query(SharedExperience).filter(
        SharedExperience.id == exp_id,
        SharedExperience.status == EXP_STATUS_ACTIVE,
    ).first()
    if not exp:
        return {"ok": False, "error": "not_found"}
    if exp.user_id == user_id:
        return {"ok": False, "error": "cannot_report_own"}

    existing = db.query(ExperienceVote).filter(
        ExperienceVote.experience_id == exp_id,
        ExperienceVote.user_id == user_id,
        ExperienceVote.vote_type == "report",
    ).first()
    if existing:
        return {"ok": False, "error": "already_reported"}

    vote = ExperienceVote(
        experience_id=exp_id, user_id=user_id, vote_type="report"
    )
    db.add(vote)
    exp.downvote_count += 1

    report_count = db.query(ExperienceVote).filter(
        ExperienceVote.experience_id == exp_id,
        ExperienceVote.vote_type == "report",
    ).count() + 1

    if report_count >= 5:
        exp.status = EXP_STATUS_FLAGGED
        logger.warning("经验 {} 因累计 {} 次举报被标记", exp_id, report_count)

    db.commit()
    return {"ok": True, "report_count": report_count}


# ══════════════════════════════════════════════════════
#  投票 / 采纳
# ══════════════════════════════════════════════════════

def vote_experience(db: Session, exp_id: int, user_id: int, vote_type: str) -> dict:
    """对经验投票或采纳。同类投票重复操作会取消。"""
    exp = db.query(SharedExperience).filter(
        SharedExperience.id == exp_id,
        SharedExperience.status == EXP_STATUS_ACTIVE,
    ).first()
    if not exp:
        return {"error": "经验不存在"}
    if exp.user_id == user_id and vote_type != VOTE_ADOPT:
        return {"error": "不能给自己的经验投票"}

    existing = db.query(ExperienceVote).filter(
        ExperienceVote.experience_id == exp_id,
        ExperienceVote.user_id == user_id,
        ExperienceVote.vote_type == vote_type,
    ).first()

    if existing:
        db.delete(existing)
        if vote_type == VOTE_UPVOTE:
            exp.upvote_count = max(0, exp.upvote_count - 1)
        elif vote_type == VOTE_DOWNVOTE:
            exp.downvote_count = max(0, exp.downvote_count - 1)
        elif vote_type == VOTE_ADOPT:
            exp.adoption_count = max(0, exp.adoption_count - 1)
        db.commit()
        return {"action": "removed", "vote_type": vote_type}

    vote = ExperienceVote(experience_id=exp_id, user_id=user_id, vote_type=vote_type)
    db.add(vote)
    if vote_type == VOTE_UPVOTE:
        exp.upvote_count += 1
    elif vote_type == VOTE_DOWNVOTE:
        exp.downvote_count += 1
    elif vote_type == VOTE_ADOPT:
        exp.adoption_count += 1
    db.commit()

    _check_and_award_badges(db, exp.user_id)
    return {"action": "added", "vote_type": vote_type}


# ══════════════════════════════════════════════════════
#  用户资料
# ══════════════════════════════════════════════════════

def get_or_create_profile(db: Session, user_id: int) -> UserProfile:
    """获取用户资料，不存在则自动创建。"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        user = db.query(User).filter(User.id == user_id).first()
        profile = UserProfile(
            user_id=user_id,
            display_name=user.username if user else "",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def update_profile(db: Session, user_id: int, data: dict) -> UserProfile:
    """更新用户资料。"""
    profile = get_or_create_profile(db, user_id)
    updatable = ("display_name", "avatar_url", "bio", "expertise_tags", "notification_settings")
    for k in updatable:
        if k in data:
            setattr(profile, k, data[k])
    db.commit()
    db.refresh(profile)
    return profile


def get_user_contributions(db: Session, user_id: int) -> list[dict]:
    """获取用户的所有公开贡献。"""
    items = (
        db.query(SharedExperience)
        .filter(
            SharedExperience.user_id == user_id,
            SharedExperience.status == EXP_STATUS_ACTIVE,
        )
        .order_by(SharedExperience.created_at.desc())
        .all()
    )
    return [e.to_dict() for e in items]


def get_user_stats(db: Session, user_id: int) -> dict:
    """获取用户统计数据。"""
    total_shares = (
        db.query(func.count(SharedExperience.id))
        .filter(SharedExperience.user_id == user_id, SharedExperience.status == EXP_STATUS_ACTIVE)
        .scalar() or 0
    )
    total_upvotes = (
        db.query(func.coalesce(func.sum(SharedExperience.upvote_count), 0))
        .filter(SharedExperience.user_id == user_id, SharedExperience.status == EXP_STATUS_ACTIVE)
        .scalar() or 0
    )
    total_adoptions = (
        db.query(func.coalesce(func.sum(SharedExperience.adoption_count), 0))
        .filter(SharedExperience.user_id == user_id, SharedExperience.status == EXP_STATUS_ACTIVE)
        .scalar() or 0
    )
    total_views = (
        db.query(func.coalesce(func.sum(SharedExperience.view_count), 0))
        .filter(SharedExperience.user_id == user_id, SharedExperience.status == EXP_STATUS_ACTIVE)
        .scalar() or 0
    )

    platform_counts = (
        db.query(SharedExperience.platform, func.count(SharedExperience.id))
        .filter(SharedExperience.user_id == user_id, SharedExperience.status == EXP_STATUS_ACTIVE)
        .group_by(SharedExperience.platform)
        .all()
    )

    return {
        "total_shares": total_shares,
        "total_upvotes": int(total_upvotes),
        "total_adoptions": int(total_adoptions),
        "total_views": int(total_views),
        "platform_breakdown": {p: c for p, c in platform_counts},
    }


def get_community_stats(db: Session) -> dict:
    """获取社区整体统计。"""
    total_exp = (
        db.query(func.count(SharedExperience.id))
        .filter(SharedExperience.status == EXP_STATUS_ACTIVE)
        .scalar() or 0
    )
    total_users = (
        db.query(func.count(func.distinct(SharedExperience.user_id)))
        .filter(SharedExperience.status == EXP_STATUS_ACTIVE)
        .scalar() or 0
    )
    total_adoptions = (
        db.query(func.coalesce(func.sum(SharedExperience.adoption_count), 0))
        .filter(SharedExperience.status == EXP_STATUS_ACTIVE)
        .scalar() or 0
    )
    total_upvotes = (
        db.query(func.coalesce(func.sum(SharedExperience.upvote_count), 0))
        .filter(SharedExperience.status == EXP_STATUS_ACTIVE)
        .scalar() or 0
    )
    return {
        "total_experiences": total_exp,
        "total_contributors": total_users,
        "total_upvotes": int(total_upvotes),
        "total_adoptions": int(total_adoptions),
    }


# ══════════════════════════════════════════════════════
#  勋章系统
# ══════════════════════════════════════════════════════

def get_user_badges(db: Session, user_id: int) -> list[dict]:
    """获取用户已获得的勋章。"""
    badges = db.query(UserBadge).filter(UserBadge.user_id == user_id).all()
    return [b.to_dict() for b in badges]


def _check_and_award_badges(db: Session, user_id: int) -> None:
    """检查并自动颁发勋章。"""
    stats = get_user_stats(db, user_id)
    existing = {
        b.badge_type
        for b in db.query(UserBadge).filter(UserBadge.user_id == user_id).all()
    }

    def _award(badge_type: str):
        if badge_type in existing:
            return
        info = BADGE_TYPE_MAP.get(badge_type, {})
        badge = UserBadge(
            user_id=user_id,
            badge_type=badge_type,
            badge_name=info.get("name", badge_type),
        )
        db.add(badge)
        logger.info("勋章颁发 | user={} badge={}", user_id, badge_type)

    total = stats["total_shares"]
    adoptions = stats["total_adoptions"]
    platforms = stats.get("platform_breakdown", {})

    if total >= 1:
        _award("first_share")
    if adoptions >= 10:
        _award("helpful_10")
    if adoptions >= 50:
        _award("helpful_50")
    if total >= 50:
        _award("community_star")
    if total >= 100 and adoptions >= 500:
        _award("legend")

    platform_badge_map = {
        "web": "web_master",
        "android": "mobile_hunter",
        "ios": "mobile_hunter",
        "miniprogram": "miniprogram_pro",
        "desktop": "desktop_guardian",
    }
    for plat, badge_type in platform_badge_map.items():
        if platforms.get(plat, 0) >= 10:
            _award(badge_type)

    db.commit()


# ══════════════════════════════════════════════════════
#  排行榜
# ══════════════════════════════════════════════════════

def get_leaderboard(db: Session, limit: int = 20) -> list[dict]:
    """获取贡献排行榜。"""
    rows = (
        db.query(
            SharedExperience.user_id,
            func.count(SharedExperience.id).label("share_count"),
            func.coalesce(func.sum(SharedExperience.upvote_count), 0).label("total_upvotes"),
            func.coalesce(func.sum(SharedExperience.adoption_count), 0).label("total_adoptions"),
        )
        .filter(SharedExperience.status == EXP_STATUS_ACTIVE)
        .group_by(SharedExperience.user_id)
        .order_by(desc("total_adoptions"), desc("total_upvotes"), desc("share_count"))
        .limit(limit)
        .all()
    )

    result = []
    for row in rows:
        user = db.query(User).filter(User.id == row.user_id).first()
        profile = db.query(UserProfile).filter(UserProfile.user_id == row.user_id).first()
        badges = db.query(UserBadge).filter(UserBadge.user_id == row.user_id).all()

        result.append({
            "user_id": row.user_id,
            "username": user.username if user else "unknown",
            "display_name": profile.display_name if profile else "",
            "avatar_url": profile.avatar_url if profile else "",
            "share_count": row.share_count,
            "total_upvotes": int(row.total_upvotes),
            "total_adoptions": int(row.total_adoptions),
            "badges": [b.to_dict() for b in badges],
        })
    return result


# ══════════════════════════════════════════════════════
#  调试快照（私有）
# ══════════════════════════════════════════════════════

def create_debug_snapshot(db: Session, user_id: int, data: dict) -> DebugSnapshot:
    """保存一个调试上下文快照。"""
    snap = DebugSnapshot(
        user_id=user_id,
        project_id=data.get("project_id"),
        platform=data.get("platform", ""),
        framework=data.get("framework", ""),
        error_message=data.get("error_message", ""),
        error_stack=data.get("error_stack", ""),
        context=data.get("context", {}),
        fix_description=data.get("fix_description", ""),
        fix_files=data.get("fix_files", []),
        resolved=data.get("resolved", False),
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def list_debug_snapshots(db: Session, user_id: int, resolved: Optional[bool] = None) -> list[dict]:
    """列出用户的调试快照。"""
    q = db.query(DebugSnapshot).filter(DebugSnapshot.user_id == user_id)
    if resolved is not None:
        q = q.filter(DebugSnapshot.resolved == resolved)
    items = q.order_by(DebugSnapshot.created_at.desc()).all()
    return [s.to_dict() for s in items]


def resolve_snapshot(db: Session, snapshot_id: int, user_id: int, fix_desc: str) -> Optional[DebugSnapshot]:
    """标记快照为已解决。"""
    snap = db.query(DebugSnapshot).filter(
        DebugSnapshot.id == snapshot_id,
        DebugSnapshot.user_id == user_id,
    ).first()
    if not snap:
        return None
    snap.resolved = True
    snap.fix_description = fix_desc
    snap.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(snap)
    return snap


# ══════════════════════════════════════════════════════
#  积分操作
# ══════════════════════════════════════════════════════

def add_credits(db: Session, user_id: int, amount: int, reason: str, detail: str = "", reference_id: str = "") -> CreditTransaction:
    """增加积分（正值=充值/奖励）。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("用户不存在")

    user.credits += amount
    balance = user.credits

    tx = CreditTransaction(
        user_id=user_id,
        amount=amount,
        reason=reason,
        detail=detail,
        balance_after=balance,
        reference_id=reference_id,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def consume_credits(db: Session, user_id: int, amount: int, reason: str, detail: str = "") -> Optional[CreditTransaction]:
    """消耗积分。余额不足返回 None。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    if user.credits < amount:
        return None

    user.credits -= amount
    user.credits_used += amount
    balance = user.credits

    tx = CreditTransaction(
        user_id=user_id,
        amount=-amount,
        reason=reason,
        detail=detail,
        balance_after=balance,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def get_credit_balance(db: Session, user_id: int) -> dict:
    """获取用户积分余额。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"credits": 0, "credits_used": 0, "plan": "free"}
    return {
        "credits": user.credits,
        "credits_used": user.credits_used,
        "plan": user.plan,
    }


def list_credit_transactions(db: Session, user_id: int, page: int = 1, per_page: int = 20) -> dict:
    """获取积分流水。"""
    q = db.query(CreditTransaction).filter(CreditTransaction.user_id == user_id)
    total = q.count()
    items = q.order_by(CreditTransaction.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": [t.to_dict() for t in items],
        "total": total,
        "page": page,
        "per_page": per_page,
    }
