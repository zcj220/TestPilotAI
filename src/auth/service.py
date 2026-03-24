"""
用户认证服务（v6.0）

提供：
- 用户注册/登录
- JWT token 生成/验证
- 密码哈希
- 用量检查与记录
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt as _bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from loguru import logger

from src.auth.models import User, Project, UsageRecord, ROLE_QUOTAS, ROLE_FREE


# JWT 配置
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "testpilot-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "1440"))  # 默认24小时

# 登录失败锁定配置（内存级，重启后重置；生产环境应换 Redis）
_MAX_FAILURES = 5          # 最多允许失败次数
_LOCK_SECONDS = 900        # 锁定时长（秒）：15分钟
_login_failures: dict[str, list[datetime]] = {}  # {key: [失败时间戳...]}


def hash_password(password: str) -> str:
    """生成密码哈希。"""
    pw = password.encode("utf-8")[:72]
    return _bcrypt.hashpw(pw, _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码。"""
    pw = plain.encode("utf-8")[:72]
    try:
        return _bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: int, username: str, role: str, expires_delta: Optional[timedelta] = None) -> str:
    """生成 JWT access token。"""
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """解码 JWT token，返回 payload 或 None。"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# ── 用户 CRUD ──

def register_user(db: Session, email: str, username: str, password: str) -> User:
    """注册新用户。

    Raises:
        ValueError: 邮箱或用户名已存在
    """
    if db.query(User).filter(User.email == email).first():
        raise ValueError("邮箱已注册")
    if db.query(User).filter(User.username == username).first():
        raise ValueError("用户名已存在")

    quotas = ROLE_QUOTAS.get(ROLE_FREE, {})
    user = User(
        email=email,
        username=username,
        hashed_password=hash_password(password),
        role=ROLE_FREE,
        **quotas,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("新用户注册 | {} ({})", username, email)
    return user


# ── 登录失败锁定 ──

def _lock_key(identifier: str) -> str:
    return identifier.lower().strip()

def is_account_locked(identifier: str) -> tuple[bool, int]:
    """检查账号是否被锁定。返回 (是否锁定, 剩余秒数)。"""
    key = _lock_key(identifier)
    failures = _login_failures.get(key, [])
    if len(failures) < _MAX_FAILURES:
        return False, 0
    latest = failures[-1]
    elapsed = (datetime.now(timezone.utc) - latest).total_seconds()
    if elapsed < _LOCK_SECONDS:
        return True, int(_LOCK_SECONDS - elapsed)
    # 锁定已过期，清除记录
    _login_failures.pop(key, None)
    return False, 0

def record_login_failure(identifier: str) -> int:
    """记录一次登录失败，返回当前失败次数。"""
    key = _lock_key(identifier)
    now = datetime.now(timezone.utc)
    # 只保留最近窗口内的失败（避免无限积累）
    window_start = now - timedelta(seconds=_LOCK_SECONDS)
    recent = [t for t in _login_failures.get(key, []) if t > window_start]
    recent.append(now)
    _login_failures[key] = recent
    return len(recent)

def clear_login_failures(identifier: str) -> None:
    """登录成功后清除失败记录。"""
    _login_failures.pop(_lock_key(identifier), None)


def authenticate_user(db: Session, email_or_username: str, password: str) -> Optional[User]:
    """验证用户凭据，支持邮箱或用户名登录，成功返回 User，失败返回 None。"""
    # 优先按邮箱查，其次按用户名查
    user = db.query(User).filter(User.email == email_or_username).first()
    if not user:
        user = db.query(User).filter(User.username == email_or_username).first()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """按ID查询用户。"""
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


def get_user_by_token(db: Session, token: str) -> Optional[User]:
    """从token解析并查询用户。"""
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        return None
    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        return None
    return get_user_by_id(db, user_id)


# ── 项目 CRUD ──

def create_project(db: Session, owner_id: int, name: str, description: str = "", base_url: str = "") -> Project:
    """创建项目。

    Raises:
        ValueError: 超过项目配额
    """
    user = get_user_by_id(db, owner_id)
    if not user:
        raise ValueError("用户不存在")

    project_count = db.query(Project).filter(Project.owner_id == owner_id, Project.is_active == True).count()
    if project_count >= user.max_projects:
        raise ValueError(f"项目数已达上限 ({user.max_projects})")

    project = Project(
        name=name,
        description=description,
        owner_id=owner_id,
        base_url=base_url,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    logger.info("项目创建 | {} (owner={})", name, owner_id)
    return project


def get_user_projects(db: Session, owner_id: int) -> list[Project]:
    """获取用户的所有项目。"""
    return db.query(Project).filter(
        Project.owner_id == owner_id, Project.is_active == True
    ).order_by(Project.updated_at.desc()).all()


def get_project(db: Session, project_id: int, owner_id: int) -> Optional[Project]:
    """获取指定项目（验证所有权）。"""
    return db.query(Project).filter(
        Project.id == project_id, Project.owner_id == owner_id, Project.is_active == True
    ).first()


def update_project(db: Session, project_id: int, owner_id: int, **kwargs) -> Optional[Project]:
    """更新项目信息。"""
    project = get_project(db, project_id, owner_id)
    if not project:
        return None
    for key, value in kwargs.items():
        if hasattr(project, key) and key not in ("id", "owner_id", "created_at"):
            setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project_id: int, owner_id: int) -> bool:
    """软删除项目。"""
    project = get_project(db, project_id, owner_id)
    if not project:
        return False
    project.is_active = False
    db.commit()
    return True


# ── 用量管理 ──

def check_quota(db: Session, user_id: int, action: str = "test") -> dict:
    """检查用户今日用量是否超限。

    Args:
        action: "test" | "ai_call" | "screenshot"

    Returns:
        {"allowed": bool, "used": int, "limit": int, "remaining": int}
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return {"allowed": False, "used": 0, "limit": 0, "remaining": 0}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    record = db.query(UsageRecord).filter(
        UsageRecord.user_id == user_id, UsageRecord.date == today
    ).first()

    if action == "test":
        used = record.test_count if record else 0
        limit = user.max_tests_per_day
    elif action == "ai_call":
        used = record.ai_call_count if record else 0
        limit = user.max_ai_calls_per_day
    else:
        used = 0
        limit = 9999

    remaining = max(0, limit - used)
    return {"allowed": remaining > 0, "used": used, "limit": limit, "remaining": remaining}


def record_usage(db: Session, user_id: int, tests: int = 0, ai_calls: int = 0, screenshots: int = 0) -> None:
    """记录使用量。"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    record = db.query(UsageRecord).filter(
        UsageRecord.user_id == user_id, UsageRecord.date == today
    ).first()

    if record:
        record.test_count += tests
        record.ai_call_count += ai_calls
        record.screenshot_count += screenshots
    else:
        record = UsageRecord(
            user_id=user_id,
            date=today,
            test_count=tests,
            ai_call_count=ai_calls,
            screenshot_count=screenshots,
        )
        db.add(record)

    db.commit()


def get_usage_summary(db: Session, user_id: int, days: int = 30) -> dict:
    """获取用量汇总。"""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    records = db.query(UsageRecord).filter(
        UsageRecord.user_id == user_id, UsageRecord.date >= cutoff
    ).all()

    total_tests = sum(r.test_count for r in records)
    total_ai = sum(r.ai_call_count for r in records)
    total_ss = sum(r.screenshot_count for r in records)

    user = get_user_by_id(db, user_id)
    return {
        "period_days": days,
        "total_tests": total_tests,
        "total_ai_calls": total_ai,
        "total_screenshots": total_ss,
        "daily_records": [
            {"date": r.date, "tests": r.test_count, "ai_calls": r.ai_call_count, "screenshots": r.screenshot_count}
            for r in sorted(records, key=lambda x: x.date)
        ],
        "quotas": {
            "max_tests_per_day": user.max_tests_per_day if user else 0,
            "max_ai_calls_per_day": user.max_ai_calls_per_day if user else 0,
            "max_projects": user.max_projects if user else 0,
            "storage_limit_mb": user.storage_limit_mb if user else 0,
        },
    }


# ── 积分系统 ──

def calc_blueprint_credits(step_count: int) -> int:
    """计算蓝本测试所需积分：每10步1积分，向上取整，最少1积分。"""
    import math
    return max(1, math.ceil(step_count / 10))


def check_credits(db: Session, user_id: int, required: int) -> dict:
    """检查用户积分是否足够。

    Returns:
        {"ok": bool, "balance": int, "required": int, "plan": str}
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return {"ok": False, "balance": 0, "required": required, "plan": "free"}
    return {
        "ok": user.credits >= required,
        "balance": user.credits,
        "required": required,
        "plan": user.plan,
    }


def deduct_credits(db: Session, user_id: int, amount: int, reason: str, detail: str = "") -> dict:
    """扣减用户积分并记录流水。

    Returns:
        {"ok": bool, "balance": int}
    """
    from src.community.models import CreditTransaction
    user = get_user_by_id(db, user_id)
    if not user:
        return {"ok": False, "balance": 0}
    if user.credits < amount:
        return {"ok": False, "balance": user.credits}

    user.credits -= amount
    user.credits_used += amount
    balance_after = user.credits

    tx = CreditTransaction(
        user_id=user_id,
        amount=-amount,
        reason=reason,
        detail=detail[:200],
        balance_after=balance_after,
    )
    db.add(tx)
    db.commit()
    logger.info("积分扣减 | user_id={} amount={} reason={} balance_after={}", user_id, amount, reason, balance_after)
    return {"ok": True, "balance": balance_after}


def get_credits_history(db: Session, user_id: int, limit: int = 20) -> list[dict]:
    """获取积分变动历史（最新在前）。"""
    from src.community.models import CreditTransaction
    records = (
        db.query(CreditTransaction)
        .filter(CreditTransaction.user_id == user_id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return [r.to_dict() for r in records]
