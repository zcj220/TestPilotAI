"""
认证与项目管理 API 路由（v6.0）
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.auth.database import get_db
from src.auth.middleware import get_current_user
from src.auth.models import User
from src.auth import service

router = APIRouter()


# ── 请求/响应模型 ──

class RegisterRequest(BaseModel):
    email: str = Field(..., description="邮箱")
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)

class LoginRequest(BaseModel):
    email_or_username: str = Field(..., description="邮箱或用户名")
    password: str = Field(...)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class ProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    base_url: str = Field(default="", max_length=500)

class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    base_url: str | None = None


# ── 工具函数 ──

def _user_dict(u: User) -> dict:
    return {
        "id": u.id, "email": u.email, "username": u.username,
        "role": u.role, "is_active": u.is_active,
        "max_tests_per_day": u.max_tests_per_day,
        "max_projects": u.max_projects,
        "max_ai_calls_per_day": u.max_ai_calls_per_day,
        "storage_limit_mb": u.storage_limit_mb,
        "created_at": u.created_at.isoformat() if u.created_at else "",
    }

def _project_dict(p) -> dict:
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "base_url": p.base_url, "owner_id": p.owner_id,
        "test_count": p.test_count, "last_pass_rate": p.last_pass_rate,
        "total_bugs_found": p.total_bugs_found,
        "created_at": p.created_at.isoformat() if p.created_at else "",
        "updated_at": p.updated_at.isoformat() if p.updated_at else "",
    }


# ── 认证端点 ──

@router.post("/auth/register", tags=["认证"])
async def register(req: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = service.register_user(db, req.email, req.username, req.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    token = service.create_access_token(user.id, user.username, user.role)
    return TokenResponse(access_token=token, user=_user_dict(user))

@router.post("/auth/login", tags=["认证"])
async def login(req: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    # 锁定检查
    locked, remaining = service.is_account_locked(req.email_or_username)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"账号已暂时锁定，请 {remaining // 60} 分 {remaining % 60} 秒后再试"
        )

    user = service.authenticate_user(db, req.email_or_username, req.password)
    if not user:
        failures = service.record_login_failure(req.email_or_username)
        remain_chances = max(0, service._MAX_FAILURES - failures)
        if remain_chances > 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"账号或密码错误，还可以尝试 {remain_chances} 次"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"连续失败次数过多，账号已锁定 {service._LOCK_SECONDS // 60} 分钟"
            )

    service.clear_login_failures(req.email_or_username)
    token = service.create_access_token(user.id, user.username, user.role)
    return TokenResponse(access_token=token, user=_user_dict(user))

@router.get("/auth/me", tags=["认证"])
async def get_me(user: User = Depends(get_current_user)) -> dict:
    return _user_dict(user)


# ── 项目端点 ──

@router.post("/projects", tags=["项目"])
async def create_project(req: ProjectRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        project = service.create_project(db, user.id, req.name, req.description, req.base_url)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return _project_dict(project)

@router.get("/projects", tags=["项目"])
async def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [_project_dict(p) for p in service.get_user_projects(db, user.id)]

@router.get("/projects/{project_id}", tags=["项目"])
async def get_project_detail(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    p = service.get_project(db, project_id, user.id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return _project_dict(p)

@router.put("/projects/{project_id}", tags=["项目"])
async def update_project(project_id: int, req: ProjectUpdateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="无更新内容")
    p = service.update_project(db, project_id, user.id, **updates)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return _project_dict(p)

@router.delete("/projects/{project_id}", tags=["项目"])
async def delete_project(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ok = service.delete_project(db, project_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"message": "项目已删除"}


# ── 用量端点 ──

@router.get("/usage", tags=["用量"])
async def get_usage(days: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return service.get_usage_summary(db, user.id, days)

@router.get("/usage/check", tags=["用量"])
async def check_quota(action: str = "test", user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return service.check_quota(db, user.id, action)
