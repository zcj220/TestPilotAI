"""
团队协作服务（v6.1）
"""

import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from loguru import logger

from src.auth.models import (
    Team, TeamMember, User, Project,
    TEAM_ROLE_ADMIN, TEAM_ROLE_TESTER, TEAM_ROLES,
)


def _gen_invite_code() -> str:
    return secrets.token_hex(12)


def create_team(db: Session, owner_id: int, name: str, description: str = "") -> Team:
    """创建团队，创建者自动成为admin。"""
    team = Team(
        name=name, description=description,
        owner_id=owner_id, invite_code=_gen_invite_code(),
    )
    db.add(team)
    db.flush()
    member = TeamMember(team_id=team.id, user_id=owner_id, role=TEAM_ROLE_ADMIN)
    db.add(member)
    db.commit()
    db.refresh(team)
    logger.info("团队创建 | {} (owner={})", name, owner_id)
    return team


def get_user_teams(db: Session, user_id: int) -> list[dict]:
    """获取用户所属的所有团队。"""
    memberships = db.query(TeamMember).filter(TeamMember.user_id == user_id).all()
    result = []
    for m in memberships:
        team = db.query(Team).filter(Team.id == m.team_id, Team.is_active == True).first()
        if team:
            member_count = db.query(TeamMember).filter(TeamMember.team_id == team.id).count()
            result.append({
                "id": team.id, "name": team.name, "description": team.description,
                "owner_id": team.owner_id, "my_role": m.role,
                "member_count": member_count, "invite_code": team.invite_code,
                "created_at": team.created_at.isoformat() if team.created_at else "",
            })
    return result


def get_team(db: Session, team_id: int) -> Optional[Team]:
    return db.query(Team).filter(Team.id == team_id, Team.is_active == True).first()


def get_member_role(db: Session, team_id: int, user_id: int) -> Optional[str]:
    m = db.query(TeamMember).filter(
        TeamMember.team_id == team_id, TeamMember.user_id == user_id
    ).first()
    return m.role if m else None


def join_team(db: Session, user_id: int, invite_code: str) -> dict:
    """通过邀请码加入团队。"""
    team = db.query(Team).filter(Team.invite_code == invite_code, Team.is_active == True).first()
    if not team:
        raise ValueError("无效的邀请码")
    existing = db.query(TeamMember).filter(
        TeamMember.team_id == team.id, TeamMember.user_id == user_id
    ).first()
    if existing:
        raise ValueError("已是该团队成员")
    count = db.query(TeamMember).filter(TeamMember.team_id == team.id).count()
    if count >= team.max_members:
        raise ValueError(f"团队已满（上限{team.max_members}人）")
    member = TeamMember(team_id=team.id, user_id=user_id, role=TEAM_ROLE_TESTER)
    db.add(member)
    db.commit()
    logger.info("用户加入团队 | user={} team={}", user_id, team.name)
    return {"team_id": team.id, "team_name": team.name, "role": TEAM_ROLE_TESTER}


def remove_member(db: Session, team_id: int, user_id: int, operator_id: int) -> bool:
    """移除成员（需admin权限，不能移除owner）。"""
    op_role = get_member_role(db, team_id, operator_id)
    if op_role != TEAM_ROLE_ADMIN:
        raise ValueError("仅管理员可移除成员")
    team = get_team(db, team_id)
    if not team:
        raise ValueError("团队不存在")
    if user_id == team.owner_id:
        raise ValueError("不能移除团队创建者")
    m = db.query(TeamMember).filter(
        TeamMember.team_id == team_id, TeamMember.user_id == user_id
    ).first()
    if not m:
        return False
    db.delete(m)
    db.commit()
    return True


def change_role(db: Session, team_id: int, user_id: int, new_role: str, operator_id: int) -> bool:
    """变更成员角色（需admin权限）。"""
    if new_role not in TEAM_ROLES:
        raise ValueError(f"无效角色，可选: {TEAM_ROLES}")
    op_role = get_member_role(db, team_id, operator_id)
    if op_role != TEAM_ROLE_ADMIN:
        raise ValueError("仅管理员可变更角色")
    m = db.query(TeamMember).filter(
        TeamMember.team_id == team_id, TeamMember.user_id == user_id
    ).first()
    if not m:
        raise ValueError("该用户不是团队成员")
    m.role = new_role
    db.commit()
    return True


def get_team_members(db: Session, team_id: int) -> list[dict]:
    """获取团队成员列表。"""
    members = db.query(TeamMember).filter(TeamMember.team_id == team_id).all()
    result = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        if user:
            result.append({
                "user_id": user.id, "username": user.username, "email": user.email,
                "role": m.role, "joined_at": m.joined_at.isoformat() if m.joined_at else "",
            })
    return result


def share_project(db: Session, project_id: int, team_id: int, user_id: int) -> Project:
    """将项目绑定到团队（需项目所有者且为团队成员）。"""
    project = db.query(Project).filter(
        Project.id == project_id, Project.owner_id == user_id, Project.is_active == True
    ).first()
    if not project:
        raise ValueError("项目不存在或无权限")
    role = get_member_role(db, team_id, user_id)
    if not role:
        raise ValueError("你不是该团队成员")
    project.team_id = team_id
    db.commit()
    db.refresh(project)
    return project


def unshare_project(db: Session, project_id: int, user_id: int) -> Project:
    """取消项目的团队绑定。"""
    project = db.query(Project).filter(
        Project.id == project_id, Project.owner_id == user_id, Project.is_active == True
    ).first()
    if not project:
        raise ValueError("项目不存在或无权限")
    project.team_id = None
    db.commit()
    db.refresh(project)
    return project


def get_team_projects(db: Session, team_id: int) -> list[Project]:
    """获取团队关联的所有项目。"""
    return db.query(Project).filter(
        Project.team_id == team_id, Project.is_active == True
    ).order_by(Project.updated_at.desc()).all()


def get_team_dashboard(db: Session, team_id: int) -> dict:
    """团队看板汇总数据。"""
    team = get_team(db, team_id)
    if not team:
        return {"error": "团队不存在"}
    members = get_team_members(db, team_id)
    projects = get_team_projects(db, team_id)
    total_tests = sum(p.test_count for p in projects)
    total_bugs = sum(p.total_bugs_found for p in projects)
    avg_pass = (sum(p.last_pass_rate for p in projects) / len(projects)) if projects else 0
    return {
        "team_name": team.name,
        "member_count": len(members),
        "project_count": len(projects),
        "total_tests": total_tests,
        "total_bugs": total_bugs,
        "avg_pass_rate": round(avg_pass, 4),
        "members": members,
        "projects": [
            {"id": p.id, "name": p.name, "test_count": p.test_count,
             "last_pass_rate": p.last_pass_rate, "total_bugs_found": p.total_bugs_found}
            for p in projects
        ],
    }


def regenerate_invite(db: Session, team_id: int, operator_id: int) -> str:
    """重新生成邀请码（需admin权限）。"""
    role = get_member_role(db, team_id, operator_id)
    if role != TEAM_ROLE_ADMIN:
        raise ValueError("仅管理员可重新生成邀请码")
    team = get_team(db, team_id)
    if not team:
        raise ValueError("团队不存在")
    team.invite_code = _gen_invite_code()
    db.commit()
    return team.invite_code


def delete_team(db: Session, team_id: int, operator_id: int) -> bool:
    """软删除团队（仅owner可执行）。"""
    team = get_team(db, team_id)
    if not team:
        return False
    if team.owner_id != operator_id:
        raise ValueError("仅团队创建者可删除团队")
    team.is_active = False
    db.commit()
    return True
