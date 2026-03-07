"""
用户认证与 API Key 管理（v1.0）

轻量级本地认证系统：
- 基于 API Key 认证
- 本地 SQLite 存储用户信息
- 支持注册/登录/密钥轮换
"""

import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

from src.billing.plans import PLANS, PlanType, UserAccount


def _generate_api_key() -> str:
    """生成 API Key（tp_开头，32字节随机）。"""
    return f"tp_{secrets.token_hex(32)}"


def _hash_key(key: str) -> str:
    """对 API Key 做 SHA256 哈希存储。"""
    return hashlib.sha256(key.encode()).hexdigest()


class AuthManager:
    """用户认证管理器。

    使用 SQLite 存储用户账户、积分余额和 API Key。

    典型使用：
        auth = AuthManager("data/auth.db")
        user, api_key = auth.register("user@example.com")
        user = auth.authenticate(api_key)
        auth.deduct_credits(user.user_id, 5)
    """

    def __init__(self, db_path: str = "data/auth.db") -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表。"""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    api_key_hash TEXT NOT NULL,
                    plan TEXT DEFAULT 'free',
                    credits_remaining INTEGER DEFAULT 50,
                    credits_used_this_month INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    plan_expires_at TEXT
                )
            """)
            conn.commit()

    def register(self, email: str, plan: PlanType = PlanType.FREE) -> tuple[UserAccount, str]:
        """注册新用户。

        Args:
            email: 用户邮箱
            plan: 订阅方案

        Returns:
            (UserAccount, api_key) 元组，api_key 仅在注册时返回明文
        """
        user_id = f"u_{secrets.token_hex(8)}"
        api_key = _generate_api_key()
        key_hash = _hash_key(api_key)
        now = datetime.now(timezone.utc).isoformat()
        plan_info = PLANS[plan]

        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """INSERT INTO users
                       (user_id, email, api_key_hash, plan, credits_remaining,
                        credits_used_this_month, created_at)
                       VALUES (?, ?, ?, ?, ?, 0, ?)""",
                    (user_id, email, key_hash, plan.value,
                     plan_info.credits_monthly, now),
                )
                conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"邮箱 {email} 已注册")

        user = UserAccount(
            user_id=user_id,
            email=email,
            plan=plan,
            credits_remaining=plan_info.credits_monthly,
            api_key=api_key[:8] + "...",
        )
        logger.info("新用户注册 | {} | {} | {}", user_id, email, plan.value)
        return user, api_key

    def authenticate(self, api_key: str) -> Optional[UserAccount]:
        """通过 API Key 认证用户。

        Returns:
            UserAccount 或 None（认证失败）
        """
        key_hash = _hash_key(api_key)
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM users WHERE api_key_hash = ?",
                (key_hash,),
            ).fetchone()

        if row is None:
            return None

        return UserAccount(
            user_id=row["user_id"],
            email=row["email"],
            plan=PlanType(row["plan"]),
            credits_remaining=row["credits_remaining"],
            credits_used_this_month=row["credits_used_this_month"],
            api_key=api_key[:8] + "...",
        )

    def get_user(self, user_id: str) -> Optional[UserAccount]:
        """通过 user_id 获取用户。"""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        if row is None:
            return None

        return UserAccount(
            user_id=row["user_id"],
            email=row["email"],
            plan=PlanType(row["plan"]),
            credits_remaining=row["credits_remaining"],
            credits_used_this_month=row["credits_used_this_month"],
        )

    def deduct_credits(self, user_id: str, credits: int) -> bool:
        """扣除用户积分。

        Returns:
            是否扣除成功（余额不足则返回 False）
        """
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT credits_remaining FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            if row is None or row[0] < credits:
                return False

            conn.execute(
                """UPDATE users
                   SET credits_remaining = credits_remaining - ?,
                       credits_used_this_month = credits_used_this_month + ?
                   WHERE user_id = ?""",
                (credits, credits, user_id),
            )
            conn.commit()
        return True

    def recharge_credits(self, user_id: str, credits: int) -> bool:
        """为用户充值积分。"""
        with sqlite3.connect(self._db_path) as conn:
            result = conn.execute(
                "UPDATE users SET credits_remaining = credits_remaining + ? WHERE user_id = ?",
                (credits, user_id),
            )
            conn.commit()
        return result.rowcount > 0

    def rotate_api_key(self, user_id: str) -> Optional[str]:
        """轮换 API Key，返回新的明文 Key。"""
        new_key = _generate_api_key()
        key_hash = _hash_key(new_key)

        with sqlite3.connect(self._db_path) as conn:
            result = conn.execute(
                "UPDATE users SET api_key_hash = ? WHERE user_id = ?",
                (key_hash, user_id),
            )
            conn.commit()

        if result.rowcount == 0:
            return None

        logger.info("API Key 已轮换 | {}", user_id)
        return new_key

    def upgrade_plan(self, user_id: str, new_plan: PlanType) -> bool:
        """升级用户方案。"""
        plan_info = PLANS[new_plan]
        with sqlite3.connect(self._db_path) as conn:
            result = conn.execute(
                """UPDATE users
                   SET plan = ?, credits_remaining = credits_remaining + ?
                   WHERE user_id = ?""",
                (new_plan.value, plan_info.credits_monthly, user_id),
            )
            conn.commit()
        return result.rowcount > 0

    def reset_all_monthly(self) -> int:
        """月度重置所有用户积分（定时任务调用）。"""
        count = 0
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT user_id, plan FROM users").fetchall()
            for row in rows:
                plan_info = PLANS[PlanType(row["plan"])]
                conn.execute(
                    """UPDATE users
                       SET credits_remaining = ?,
                           credits_used_this_month = 0
                       WHERE user_id = ?""",
                    (plan_info.credits_monthly, row["user_id"]),
                )
                count += 1
            conn.commit()
        logger.info("月度积分重置完成 | {} 个用户", count)
        return count
