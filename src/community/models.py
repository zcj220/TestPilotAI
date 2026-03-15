"""
社区经验库数据模型（v13.0）

新增 6 张表：
- shared_experiences: 社区分享的匿名经验
- experience_votes: 投票/采纳记录
- user_badges: 用户勋章
- user_profiles: 用户扩展资料
- debug_snapshots: 调试上下文快照（私有）
- api_keys: 第三方 API 密钥（商业化）

所有表共用 src.auth.models.Base，由 init_db() 统一 create_all。
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, Index, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.auth.models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── 勋章类型定义 ──────────────────────────────────

BADGE_DEFINITIONS: list[dict] = [
    {"type": "first_share",      "name": "修理工",      "icon": "🛠️", "condition": "首次分享修复经验",           "threshold": 1},
    {"type": "helpful_10",       "name": "灵光一闪",    "icon": "💡", "condition": "分享的方案被 10+ 人采纳",    "threshold": 10},
    {"type": "helpful_50",       "name": "乐于助人",    "icon": "🤝", "condition": "分享的方案被 50+ 人采纳",    "threshold": 50},
    {"type": "flutter_expert",   "name": "Flutter 专家","icon": "🦋", "condition": "分享 10+ 条 Flutter 经验",   "threshold": 10},
    {"type": "web_master",       "name": "Web 大师",    "icon": "🌐", "condition": "分享 10+ 条 Web 经验",       "threshold": 10},
    {"type": "mobile_hunter",    "name": "移动端猎手",  "icon": "📱", "condition": "分享 10+ 条移动端经验",      "threshold": 10},
    {"type": "desktop_guardian", "name": "桌面守护者",  "icon": "🖥️", "condition": "分享 10+ 条桌面应用经验",    "threshold": 10},
    {"type": "miniprogram_pro",  "name": "小程序达人",  "icon": "💬", "condition": "分享 10+ 条小程序经验",      "threshold": 10},
    {"type": "community_star",   "name": "社区之星",    "icon": "⭐", "condition": "累计分享 50+ 条经验",        "threshold": 50},
    {"type": "legend",           "name": "传奇调试师",  "icon": "🏆", "condition": "累计分享 100+ 条，采纳 500+","threshold": 100},
]

BADGE_TYPE_MAP: dict[str, dict] = {b["type"]: b for b in BADGE_DEFINITIONS}

# 平台常量
PLATFORMS = ("web", "android", "ios", "miniprogram", "desktop")

# 经验状态
EXP_STATUS_ACTIVE = "active"
EXP_STATUS_HIDDEN = "hidden"
EXP_STATUS_FLAGGED = "flagged"
EXP_STATUS_DELETED = "deleted"

# 投票类型
VOTE_UPVOTE = "upvote"
VOTE_DOWNVOTE = "downvote"
VOTE_ADOPT = "adopt"


# ── 表1: 社区分享的匿名经验 ──────────────────────────

class SharedExperience(Base):
    """匿名化后公开分享的调试/修复经验。"""
    __tablename__ = "shared_experiences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    framework: Mapped[str] = mapped_column(String(50), default="", index=True)
    error_type: Mapped[str] = mapped_column(String(80), default="", index=True)

    problem_desc: Mapped[str] = mapped_column(Text, nullable=False)
    solution_desc: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, default="")
    code_snippet: Mapped[str] = mapped_column(Text, default="")

    tags: Mapped[dict | list | None] = mapped_column(JSON, default=list)
    tool_versions: Mapped[dict | None] = mapped_column(JSON, default=dict)

    difficulty: Mapped[str] = mapped_column(String(10), default="medium")
    share_score: Mapped[float] = mapped_column(Float, default=0.0)
    fix_pattern: Mapped[str] = mapped_column(String(50), default="")

    view_count: Mapped[int] = mapped_column(Integer, default=0)
    upvote_count: Mapped[int] = mapped_column(Integer, default=0)
    downvote_count: Mapped[int] = mapped_column(Integer, default=0)
    adoption_count: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(20), default=EXP_STATUS_ACTIVE, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # 关系
    votes: Mapped[list["ExperienceVote"]] = relationship(
        "ExperienceVote", back_populates="experience", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_exp_platform_framework", "platform", "framework"),
        Index("idx_exp_status_created", "status", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "platform": self.platform,
            "framework": self.framework,
            "error_type": self.error_type,
            "problem_desc": self.problem_desc,
            "solution_desc": self.solution_desc,
            "root_cause": self.root_cause,
            "code_snippet": self.code_snippet,
            "tags": self.tags or [],
            "tool_versions": self.tool_versions or {},
            "difficulty": self.difficulty,
            "share_score": self.share_score,
            "fix_pattern": self.fix_pattern,
            "view_count": self.view_count,
            "upvote_count": self.upvote_count,
            "downvote_count": self.downvote_count,
            "adoption_count": self.adoption_count,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ── 表2: 投票/采纳记录 ───────────────────────────────

class ExperienceVote(Base):
    """用户对经验的投票或采纳记录。"""
    __tablename__ = "experience_votes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experience_id: Mapped[int] = mapped_column(Integer, ForeignKey("shared_experiences.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    vote_type: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    experience: Mapped["SharedExperience"] = relationship("SharedExperience", back_populates="votes")

    __table_args__ = (
        Index("idx_vote_unique", "experience_id", "user_id", "vote_type", unique=True),
    )


# ── 表3: 用户勋章 ────────────────────────────────────

class UserBadge(Base):
    """用户获得的勋章。"""
    __tablename__ = "user_badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    badge_type: Mapped[str] = mapped_column(String(50), nullable=False)
    badge_name: Mapped[str] = mapped_column(String(100), nullable=False)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("idx_badge_user_type", "user_id", "badge_type", unique=True),
    )

    def to_dict(self) -> dict:
        info = BADGE_TYPE_MAP.get(self.badge_type, {})
        return {
            "badge_type": self.badge_type,
            "badge_name": self.badge_name,
            "icon": info.get("icon", "🏅"),
            "condition": info.get("condition", ""),
            "earned_at": self.earned_at.isoformat() if self.earned_at else None,
        }


# ── 表4: 用户扩展资料 ────────────────────────────────

class UserProfile(Base):
    """用户公开资料（与 users 表一对一）。"""
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(50), default="")
    avatar_url: Mapped[str] = mapped_column(String(500), default="")
    bio: Mapped[str] = mapped_column(String(200), default="")
    expertise_tags: Mapped[dict | list | None] = mapped_column(JSON, default=list)
    stats_cache: Mapped[dict | None] = mapped_column(JSON, default=dict)
    notification_settings: Mapped[dict | None] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "bio": self.bio,
            "expertise_tags": self.expertise_tags or [],
            "stats_cache": self.stats_cache or {},
        }


# ── 表5: 调试上下文快照（私有） ──────────────────────

class DebugSnapshot(Base):
    """用户私有的调试上下文快照，可选择匿名分享到社区。"""
    __tablename__ = "debug_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("projects.id"), nullable=True)

    platform: Mapped[str] = mapped_column(String(20), default="")
    framework: Mapped[str] = mapped_column(String(50), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    error_stack: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[dict | None] = mapped_column(JSON, default=dict)

    fix_description: Mapped[str] = mapped_column(Text, default="")
    fix_files: Mapped[dict | list | None] = mapped_column(JSON, default=list)

    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    shared_experience_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("shared_experiences.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_snapshot_user_resolved", "user_id", "resolved"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "platform": self.platform,
            "framework": self.framework,
            "error_message": self.error_message[:200],
            "fix_description": self.fix_description[:200],
            "resolved": self.resolved,
            "shared_experience_id": self.shared_experience_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


# ── 表6: API 密钥（商业化） ──────────────────────────

class APIKey(Base):
    """第三方 API 密钥，用于 CI/CD 等自动化场景。"""
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    permissions: Mapped[dict | list | None] = mapped_column(JSON, default=lambda: ["read", "test"])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key_prefix": self.key_prefix,
            "name": self.name,
            "permissions": self.permissions or [],
            "is_active": self.is_active,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── 积分交易记录（扩展 billing 模块）─────────────────

class CreditTransaction(Base):
    """积分变动流水。正数=充值/奖励，负数=消耗。"""
    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str] = mapped_column(String(200), default="")
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_id: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("idx_credit_user_created", "user_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "amount": self.amount,
            "reason": self.reason,
            "detail": self.detail,
            "balance_after": self.balance_after,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
