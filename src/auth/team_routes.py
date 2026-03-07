"""
团队协作 API 路由（v6.1）
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.auth.database import get_db
from src.auth.middleware import get_current_user
from src.auth.models import User
from src.auth import team_service

router = APIRouter()


class CreateTeamRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)

class JoinTeamRequest(BaseModel):
    invite_code: str = Field(..., min_length=1)

class ChangeRoleRequest(BaseModel):
    user_id: int
    role: str = Field(..., pattern="^(admin|tester|viewer)$")

class ShareProjectRequest(BaseModel):
    project_id: int
    team_id: int


@router.post("/teams", tags=["团队"])
async def create_team(req: CreateTeamRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    team = team_service.create_team(db, user.id, req.name, req.description)
    return {"id": team.id, "name": team.name, "invite_code": team.invite_code}

@router.get("/teams", tags=["团队"])
async def list_teams(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return team_service.get_user_teams(db, user.id)

@router.post("/teams/join", tags=["团队"])
async def join_team(req: JoinTeamRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        return team_service.join_team(db, user.id, req.invite_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/teams/{team_id}/members", tags=["团队"])
async def get_members(team_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    role = team_service.get_member_role(db, team_id, user.id)
    if not role:
        raise HTTPException(status_code=403, detail="你不是该团队成员")
    return team_service.get_team_members(db, team_id)

@router.post("/teams/{team_id}/members/remove", tags=["团队"])
async def remove_member(team_id: int, user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        team_service.remove_member(db, team_id, user_id, user.id)
        return {"message": "成员已移除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/teams/{team_id}/members/role", tags=["团队"])
async def change_role(team_id: int, req: ChangeRoleRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        team_service.change_role(db, team_id, req.user_id, req.role, user.id)
        return {"message": "角色已变更"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/teams/{team_id}/projects", tags=["团队"])
async def get_team_projects(team_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    role = team_service.get_member_role(db, team_id, user.id)
    if not role:
        raise HTTPException(status_code=403, detail="你不是该团队成员")
    projects = team_service.get_team_projects(db, team_id)
    return [{"id": p.id, "name": p.name, "base_url": p.base_url, "test_count": p.test_count,
             "last_pass_rate": p.last_pass_rate, "total_bugs_found": p.total_bugs_found} for p in projects]

@router.post("/teams/share-project", tags=["团队"])
async def share_project(req: ShareProjectRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        p = team_service.share_project(db, req.project_id, req.team_id, user.id)
        return {"message": "项目已共享", "project_id": p.id, "team_id": p.team_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/teams/{team_id}/unshare/{project_id}", tags=["团队"])
async def unshare_project(team_id: int, project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        team_service.unshare_project(db, project_id, user.id)
        return {"message": "项目已取消共享"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/teams/{team_id}/dashboard", tags=["团队"])
async def get_dashboard(team_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    role = team_service.get_member_role(db, team_id, user.id)
    if not role:
        raise HTTPException(status_code=403, detail="你不是该团队成员")
    return team_service.get_team_dashboard(db, team_id)

@router.post("/teams/{team_id}/regenerate-invite", tags=["团队"])
async def regenerate_invite(team_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        code = team_service.regenerate_invite(db, team_id, user.id)
        return {"invite_code": code}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/teams/{team_id}", tags=["团队"])
async def delete_team(team_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        ok = team_service.delete_team(db, team_id, user.id)
        if not ok:
            raise HTTPException(status_code=404, detail="团队不存在")
        return {"message": "团队已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
