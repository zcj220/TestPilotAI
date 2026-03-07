"""
API 鉴权中间件（v6.0）

提供 FastAPI 依赖注入用的鉴权函数：
- get_current_user: 必须登录
- get_current_user_optional: 可选登录（游客也能用）
- require_role: 要求特定角色
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from src.auth.database import get_db
from src.auth.models import User
from src.auth.service import decode_token, get_user_by_id

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """解析 Bearer token，返回当前用户。未认证时抛 401。"""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证凭据")

    payload = decode_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证令牌")

    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证令牌")

    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """可选认证：有token就解析，没有返回 None（游客模式）。"""
    if not credentials:
        return None

    payload = decode_token(credentials.credentials)
    if not payload or "sub" not in payload:
        return None

    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        return None

    return get_user_by_id(db, user_id)


def require_role(*roles: str):
    """角色检查依赖工厂。

    Usage:
        @router.get("/admin/xxx", dependencies=[Depends(require_role("admin"))])
    """
    async def _check(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user
    return _check
