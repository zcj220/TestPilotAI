"""
用户认证服务（v6.0）

提供：
- 用户注册/登录
- JWT token 生成/验证
- 密码哈希
- 用量检查与记录
"""

import hashlib
import os
import random
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Optional

import bcrypt as _bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from loguru import logger

from src.auth.models import (
    User, Project, UsageRecord, ROLE_QUOTAS, ROLE_FREE,
    LoginAttempt, RefreshToken, EmailVerification,
)


# JWT 配置
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "testpilot-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))   # Access Token：1小时
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "30"))  # Refresh Token：30天

# 登录失败锁定配置
_MAX_FAILURES = 5          # 最多允许失败次数
_LOCK_SECONDS = 900        # 锁定时长（秒）：15分钟

# 邮箱验证码配置
EMAIL_CODE_EXPIRE_MINUTES = 10
REQUIRE_EMAIL_VERIFICATION = os.environ.get("REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true"


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


# ── 登录失败锁定（DB持久化，v14.0-E） ──

def _lock_key(identifier: str) -> str:
    return identifier.lower().strip()

def is_account_locked(db: Session, identifier: str) -> tuple[bool, int]:
    """检查账号是否被锁定（DB持久化）。返回 (是否锁定, 剩余秒数)。"""
    key = _lock_key(identifier)
    window_start = datetime.now(timezone.utc) - timedelta(seconds=_LOCK_SECONDS)
    failures = (
        db.query(LoginAttempt)
        .filter(
            LoginAttempt.identifier == key,
            LoginAttempt.is_success == False,
            LoginAttempt.attempted_at > window_start,
        )
        .order_by(LoginAttempt.attempted_at.desc())
        .all()
    )
    if len(failures) < _MAX_FAILURES:
        return False, 0
    latest = failures[0].attempted_at
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - latest).total_seconds()
    if elapsed < _LOCK_SECONDS:
        return True, int(_LOCK_SECONDS - elapsed)
    return False, 0

def record_login_failure(db: Session, identifier: str) -> int:
    """记录一次登录失败（DB持久化），返回当前窗口内失败次数。"""
    key = _lock_key(identifier)
    db.add(LoginAttempt(identifier=key, is_success=False))
    db.commit()
    window_start = datetime.now(timezone.utc) - timedelta(seconds=_LOCK_SECONDS)
    return (
        db.query(LoginAttempt)
        .filter(
            LoginAttempt.identifier == key,
            LoginAttempt.is_success == False,
            LoginAttempt.attempted_at > window_start,
        )
        .count()
    )

def clear_login_failures(db: Session, identifier: str) -> None:
    """登录成功后清除该账号在当前窗口内的失败记录。"""
    key = _lock_key(identifier)
    window_start = datetime.now(timezone.utc) - timedelta(seconds=_LOCK_SECONDS)
    db.query(LoginAttempt).filter(
        LoginAttempt.identifier == key,
        LoginAttempt.is_success == False,
        LoginAttempt.attempted_at > window_start,
    ).delete(synchronize_session=False)
    db.commit()


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


# ── JWT Refresh Token（v14.0-E）──────────────────────────────────────────────

def create_token_pair(db: Session, user: User) -> tuple[str, str]:
    """生成 access_token（1小时）+ refresh_token（7天）。

    Returns: (access_token, raw_refresh_token)
    """
    access_token = create_access_token(user.id, user.username, user.role)
    raw_refresh = secrets.token_hex(48)  # 96字符随机字符串，仅返回给客户端一次
    token_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    db.add(RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    db.commit()
    return access_token, raw_refresh


def verify_and_rotate_refresh_token(
    db: Session, raw_token: str
) -> Optional[tuple[str, str, "User"]]:
    """验证 refresh_token，验证通过则：旧 token 作废，生成新的 access+refresh 对。

    Returns: (access_token, new_refresh_token, user) or None
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    rt = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.is_revoked == False,
    ).first()
    if not rt:
        return None
    expires = rt.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        return None
    user = get_user_by_id(db, rt.user_id)
    if not user:
        return None
    rt.is_revoked = True  # 旧 token 作废（轮换机制）
    db.commit()
    access_token, new_refresh = create_token_pair(db, user)
    return access_token, new_refresh, user


# ── 邮箱验证码（v14.0-E）────────────────────────────────────────────────────

def create_verification_code(db: Session, email: str) -> str:
    """为邮箱生成6位验证码，自动作废该邮箱旧的未使用验证码。"""
    db.query(EmailVerification).filter(
        EmailVerification.email == email,
        EmailVerification.is_used == False,
    ).update({"is_used": True}, synchronize_session=False)
    db.commit()
    code = f"{random.randint(0, 999999):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=EMAIL_CODE_EXPIRE_MINUTES)
    db.add(EmailVerification(email=email, code=code, expires_at=expires_at))
    db.commit()
    return code


def verify_email_code(db: Session, email: str, code: str) -> bool:
    """验证邮箱验证码，成功后标记为已使用。"""
    now = datetime.now(timezone.utc)
    record = db.query(EmailVerification).filter(
        EmailVerification.email == email,
        EmailVerification.code == code,
        EmailVerification.is_used == False,
        EmailVerification.expires_at > now,
    ).first()
    if not record:
        return False
    record.is_used = True
    db.commit()
    return True


def send_verification_email(email: str, code: str) -> bool:
    """发送验证码邮件（需配置 SMTP_HOST / SMTP_USER / SMTP_PASS 环境变量）。"""
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    from_email = os.environ.get("SMTP_FROM", smtp_user)
    if not smtp_host or not smtp_user:
        logger.warning("SMTP 未配置，跳过发送验证码邮件 → {}", email)
        return False
    body = (
        f"您的 TestPilot AI 验证码是：{code}\n\n"
        f"有效期 {EMAIL_CODE_EXPIRE_MINUTES} 分钟，请勿泄露给他人。"
    )
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"【TestPilot AI】注册验证码 {code}"
    msg["From"] = from_email
    msg["To"] = email
    try:
        if smtp_port == 465:
            # 端口 465：直接 SSL
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(from_email, [email], msg.as_string())
        else:
            # 端口 587：STARTTLS
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(from_email, [email], msg.as_string())
        logger.info("验证码邮件已发送 → {}", email)
        return True
    except Exception as e:
        logger.error("发送验证码邮件失败 {} → {}", email, e)
        return False
