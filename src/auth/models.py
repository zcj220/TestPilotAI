"""
用户、项目、团队的 SQLAlchemy 模型（v6.0 + v6.1）

表结构：
- users: 用户账户（邮箱+密码哈希+角色+配额）
- projects: 项目空间（属于用户或团队）
- usage_records: 使用量记录（按日聚合）
- teams: 团队（v6.1）
- team_members: 团队成员关联（v6.1）
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, Index, create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase, relationship, Mapped, mapped_column, Session,
)


class Base(DeclarativeBase):
    """SQLAlchemy 基类。"""
    pass


class User(Base):
    """用户账户。"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="free", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # 配额
    max_tests_per_day: Mapped[int] = mapped_column(Integer, default=10)
    max_projects: Mapped[int] = mapped_column(Integer, default=3)
    max_ai_calls_per_day: Mapped[int] = mapped_column(Integer, default=50)
    storage_limit_mb: Mapped[int] = mapped_column(Integer, default=100)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 关系
    projects: Mapped[list["Project"]] = relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    usage_records: Mapped[list["UsageRecord"]] = relationship("UsageRecord", back_populates="user", cascade="all, delete-orphan")
    team_memberships: Mapped[list["TeamMember"]] = relationship("TeamMember", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


# 角色常量
ROLE_GUEST = "guest"
ROLE_FREE = "free"
ROLE_PRO = "pro"
ROLE_ADMIN = "admin"

# 各角色默认配额
ROLE_QUOTAS = {
    ROLE_FREE: {"max_tests_per_day": 10, "max_projects": 3, "max_ai_calls_per_day": 50, "storage_limit_mb": 100},
    ROLE_PRO: {"max_tests_per_day": 100, "max_projects": 20, "max_ai_calls_per_day": 500, "storage_limit_mb": 2000},
    ROLE_ADMIN: {"max_tests_per_day": 9999, "max_projects": 9999, "max_ai_calls_per_day": 9999, "storage_limit_mb": 99999},
}


class Project(Base):
    """项目空间。"""
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    team_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("teams.id"), nullable=True, index=True)
    base_url: Mapped[str] = mapped_column(String(500), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 关系
    owner: Mapped["User"] = relationship("User", back_populates="projects")
    team: Mapped[Optional["Team"]] = relationship("Team", back_populates="projects")

    # 统计缓存
    test_count: Mapped[int] = mapped_column(Integer, default=0)
    last_pass_rate: Mapped[float] = mapped_column(Float, default=0.0)
    total_bugs_found: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("idx_project_owner", "owner_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Project {self.name} (owner={self.owner_id})>"


class UsageRecord(Base):
    """使用量记录（按日聚合）。"""
    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    test_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_call_count: Mapped[int] = mapped_column(Integer, default=0)
    screenshot_count: Mapped[int] = mapped_column(Integer, default=0)
    storage_used_mb: Mapped[float] = mapped_column(Float, default=0.0)

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="usage_records")

    __table_args__ = (
        Index("idx_usage_user_date", "user_id", "date", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Usage user={self.user_id} date={self.date} tests={self.test_count}>"


# ── 团队协作（v6.1）──────────────────────────────

# 团队成员角色
TEAM_ROLE_ADMIN = "admin"
TEAM_ROLE_TESTER = "tester"
TEAM_ROLE_VIEWER = "viewer"

TEAM_ROLES = [TEAM_ROLE_ADMIN, TEAM_ROLE_TESTER, TEAM_ROLE_VIEWER]


class Team(Base):
    """团队。"""
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    invite_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    max_members: Mapped[int] = mapped_column(Integer, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 关系
    members: Mapped[list["TeamMember"]] = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    projects: Mapped[list["Project"]] = relationship("Project", back_populates="team")

    def __repr__(self) -> str:
        return f"<Team {self.name} (owner={self.owner_id})>"


class TeamMember(Base):
    """团队成员关联。"""
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=TEAM_ROLE_TESTER, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # 关系
    team: Mapped["Team"] = relationship("Team", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="team_memberships")

    __table_args__ = (
        Index("idx_team_member", "team_id", "user_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<TeamMember team={self.team_id} user={self.user_id} role={self.role}>"
