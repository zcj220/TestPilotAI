"""
社区经验库 API 路由（v13.0）

15 个端点覆盖：
- 经验 CRUD（创建/列表/详情/更新/删除）
- 投票/采纳
- 用户资料/贡献/统计
- 排行榜 / 热门 / 推荐
- 调试快照
- 社区统计
- 积分
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.auth.database import get_db
from src.auth.middleware import get_current_user, get_current_user_optional
from src.auth.models import User
from src.community import service

router = APIRouter(prefix="/community", tags=["community"])


# ── 请求/响应模型 ─────────────────────────────────

class ExperienceCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    platform: str = Field(..., max_length=20)
    framework: str = Field(default="", max_length=50)
    error_type: str = Field(default="", max_length=80)
    problem_desc: str = Field(..., min_length=10)
    solution_desc: str = Field(..., min_length=10)
    root_cause: str = Field(default="")
    code_snippet: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    tool_versions: dict = Field(default_factory=dict)
    difficulty: str = Field(default="medium")
    share_score: float = Field(default=0.0)
    fix_pattern: str = Field(default="")

class ExperienceUpdate(BaseModel):
    title: str | None = None
    problem_desc: str | None = None
    solution_desc: str | None = None
    root_cause: str | None = None
    code_snippet: str | None = None
    tags: list[str] | None = None
    tool_versions: dict | None = None

class VoteRequest(BaseModel):
    vote_type: str = Field(..., pattern="^(upvote|downvote|adopt)$")

class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=500)
    bio: str | None = Field(default=None, max_length=200)
    expertise_tags: list[str] | None = None
    notification_settings: dict | None = None

class SnapshotCreate(BaseModel):
    project_id: int | None = None
    platform: str = Field(default="")
    framework: str = Field(default="")
    error_message: str = Field(default="")
    error_stack: str = Field(default="")
    context: dict = Field(default_factory=dict)
    fix_description: str = Field(default="")
    fix_files: list = Field(default_factory=list)
    resolved: bool = False

class SnapshotResolve(BaseModel):
    fix_description: str = Field(default="")

class ShareFromSnapshotRequest(BaseModel):
    snapshot_id: int
    title: str = Field(default="")
    platform: str = Field(default="")
    framework: str = Field(default="")
    error_type: str = Field(default="")
    problem_desc: str = Field(default="")
    solution_desc: str = Field(default="")
    root_cause: str = Field(default="")
    code_snippet: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    tool_versions: dict = Field(default_factory=dict)
    difficulty: str = Field(default="medium")
    fix_pattern: str = Field(default="")

class ShareDirectRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    platform: str = Field(..., max_length=20)
    framework: str = Field(default="", max_length=50)
    error_type: str = Field(default="", max_length=80)
    problem_desc: str = Field(..., min_length=10)
    solution_desc: str = Field(..., min_length=10)
    root_cause: str = Field(default="")
    code_snippet: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    tool_versions: dict = Field(default_factory=dict)
    difficulty: str = Field(default="medium")
    fix_pattern: str = Field(default="")

class PreviewRequest(BaseModel):
    title: str = Field(default="")
    platform: str = Field(default="")
    framework: str = Field(default="")
    error_type: str = Field(default="")
    problem_desc: str = Field(default="")
    solution_desc: str = Field(default="")
    root_cause: str = Field(default="")
    code_snippet: str = Field(default="")
    tags: list[str] = Field(default_factory=list)

class ReportRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


# ── 1. 经验 CRUD ──────────────────────────────────

@router.post("/experiences", status_code=status.HTTP_201_CREATED)
def create_experience(
    body: ExperienceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """分享一条调试经验。"""
    exp = service.create_experience(db, user.id, body.model_dump())
    return {"ok": True, "experience": exp.to_dict()}


@router.get("/experiences")
def list_experiences(
    platform: str = Query(default="", description="按平台过滤"),
    framework: str = Query(default="", description="按框架过滤"),
    error_type: str = Query(default="", description="按错误类型过滤"),
    search: str = Query(default="", description="关键词搜索"),
    sort_by: str = Query(default="created_at", description="排序方式"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """浏览/搜索经验列表。"""
    return service.list_experiences(
        db, platform=platform, framework=framework,
        error_type=error_type, search=search,
        sort_by=sort_by, page=page, per_page=per_page,
    )


@router.get("/experiences/trending")
def get_trending(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """获取热门经验。"""
    return {"items": service.get_trending(db, limit=limit)}


@router.get("/experiences/suggest")
def suggest_experiences(
    platform: str = Query(...),
    error_type: str = Query(default=""),
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """根据平台和错误类型推荐经验。"""
    return {"items": service.suggest_for_error(db, platform, error_type, limit=limit)}


@router.get("/experiences/{exp_id}")
def get_experience(
    exp_id: int,
    db: Session = Depends(get_db),
):
    """获取经验详情。"""
    exp = service.get_experience(db, exp_id)
    if not exp:
        raise HTTPException(status_code=404, detail="经验不存在")
    return {"experience": exp.to_dict()}


@router.put("/experiences/{exp_id}")
def update_experience(
    exp_id: int,
    body: ExperienceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新经验（仅作者）。"""
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    exp = service.update_experience(db, exp_id, user.id, data)
    if not exp:
        raise HTTPException(status_code=404, detail="经验不存在或无权修改")
    return {"ok": True, "experience": exp.to_dict()}


@router.delete("/experiences/{exp_id}")
def delete_experience(
    exp_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除经验（软删除，仅作者）。"""
    ok = service.delete_experience(db, exp_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="经验不存在或无权删除")
    return {"ok": True}


# ── 2. 投票 / 采纳 ─────────────────────────────────

@router.post("/experiences/{exp_id}/vote")
def vote_experience(
    exp_id: int,
    body: VoteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """对经验投票或采纳。重复操作=取消。"""
    result = service.vote_experience(db, exp_id, user.id, body.vote_type)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── 3. 用户资料 ───────────────────────────────────

@router.get("/profile/{user_id}")
def get_user_profile(
    user_id: int,
    db: Session = Depends(get_db),
):
    """获取用户公开资料。"""
    profile = service.get_or_create_profile(db, user_id)
    badges = service.get_user_badges(db, user_id)
    stats = service.get_user_stats(db, user_id)
    return {
        "profile": profile.to_dict(),
        "badges": badges,
        "stats": stats,
    }


@router.put("/profile")
def update_my_profile(
    body: ProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新自己的资料。"""
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    profile = service.update_profile(db, user.id, data)
    return {"ok": True, "profile": profile.to_dict()}


@router.get("/profile/{user_id}/contributions")
def get_user_contributions(
    user_id: int,
    db: Session = Depends(get_db),
):
    """获取用户的公开贡献列表。"""
    return {"items": service.get_user_contributions(db, user_id)}


@router.get("/profile/{user_id}/stats")
def get_user_stats(
    user_id: int,
    db: Session = Depends(get_db),
):
    """获取用户统计。"""
    return service.get_user_stats(db, user_id)


# ── 4. 排行榜 ────────────────────────────────────

@router.get("/leaderboard")
def get_leaderboard(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """社区贡献排行榜。"""
    return {"items": service.get_leaderboard(db, limit=limit)}


# ── 5. 社区统计 ───────────────────────────────────

@router.get("/stats")
def get_community_stats(db: Session = Depends(get_db)):
    """社区整体统计（总经验数/贡献者/采纳量）。"""
    return service.get_community_stats(db)


# ── 6. 调试快照 ───────────────────────────────────

@router.post("/snapshots", status_code=status.HTTP_201_CREATED)
def create_snapshot(
    body: SnapshotCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """保存调试上下文快照（私有）。"""
    snap = service.create_debug_snapshot(db, user.id, body.model_dump())
    return {"ok": True, "snapshot": snap.to_dict()}


@router.get("/snapshots")
def list_snapshots(
    resolved: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出我的调试快照。"""
    return {"items": service.list_debug_snapshots(db, user.id, resolved=resolved)}


@router.post("/snapshots/{snapshot_id}/resolve")
def resolve_snapshot(
    snapshot_id: int,
    body: SnapshotResolve,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """标记快照为已解决。"""
    snap = service.resolve_snapshot(db, snapshot_id, user.id, body.fix_description)
    if not snap:
        raise HTTPException(status_code=404, detail="快照不存在")
    return {"ok": True, "snapshot": snap.to_dict()}


# ── 7. 分享（从快照 / 直接） ──────────────────────

@router.post("/share/from-snapshot")
def share_from_snapshot(
    body: ShareFromSnapshotRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """将已解决的调试快照匿名化后分享到社区。"""
    extra = {k: v for k, v in body.model_dump().items() if k != "snapshot_id"}
    result = service.share_from_snapshot(db, user.id, body.snapshot_id, extra)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/share/direct")
def share_direct(
    body: ShareDirectRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """直接分享经验（AI 编程工具自动上传入口）。"""
    result = service.share_direct(db, user.id, body.model_dump())
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/share/preview")
def preview_share(
    body: PreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """预览匿名化结果，不写库。供用户分享前确认。"""
    return service.preview_anonymized(body.model_dump())


@router.post("/experiences/{exp_id}/report")
def report_experience(
    exp_id: int,
    body: ReportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """举报经验。累计达阈值自动隐藏。"""
    result = service.report_experience(db, exp_id, user.id, body.reason)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result


# ── 8. 积分 ──────────────────────────────────────

@router.get("/credits")
def get_credits(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取我的积分余额。"""
    return service.get_credit_balance(db, user.id)


@router.get("/credits/transactions")
def list_transactions(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取积分流水。"""
    return service.list_credit_transactions(db, user.id, page=page, per_page=per_page)
