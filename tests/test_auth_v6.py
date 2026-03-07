"""
用户系统与项目空间测试（v6.0）

覆盖：注册/登录/JWT/项目CRUD/用量/配额/中间件
"""

import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth.models import Base, User, Project, UsageRecord, ROLE_FREE, ROLE_PRO, ROLE_QUOTAS
from src.auth import service


@pytest.fixture
def db():
    """创建内存 SQLite 数据库会话。"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ── 密码哈希 ──

class TestPasswordHash:
    def test_hash_and_verify(self):
        hashed = service.hash_password("mypassword123")
        assert hashed != "mypassword123"
        assert service.verify_password("mypassword123", hashed) is True
        assert service.verify_password("wrong", hashed) is False

    def test_different_hashes(self):
        h1 = service.hash_password("same")
        h2 = service.hash_password("same")
        assert h1 != h2  # bcrypt salt不同


# ── JWT Token ──

class TestJWT:
    def test_create_and_decode(self):
        token = service.create_access_token(42, "alice", "free")
        payload = service.decode_token(token)
        assert payload is not None
        assert payload["sub"] == "42"
        assert payload["username"] == "alice"
        assert payload["role"] == "free"

    def test_invalid_token(self):
        assert service.decode_token("invalid.token.here") is None
        assert service.decode_token("") is None

    def test_expired_token(self):
        from datetime import timedelta
        token = service.create_access_token(1, "bob", "free", expires_delta=timedelta(seconds=-1))
        assert service.decode_token(token) is None


# ── 用户注册/登录 ──

class TestUserRegistration:
    def test_register_success(self, db):
        user = service.register_user(db, "alice@test.com", "alice", "pass123456")
        assert user.id is not None
        assert user.email == "alice@test.com"
        assert user.username == "alice"
        assert user.role == ROLE_FREE
        assert user.is_active is True
        assert user.max_tests_per_day == ROLE_QUOTAS[ROLE_FREE]["max_tests_per_day"]

    def test_register_duplicate_email(self, db):
        service.register_user(db, "dup@test.com", "user1", "pass123456")
        with pytest.raises(ValueError, match="邮箱已注册"):
            service.register_user(db, "dup@test.com", "user2", "pass123456")

    def test_register_duplicate_username(self, db):
        service.register_user(db, "a@test.com", "samename", "pass123456")
        with pytest.raises(ValueError, match="用户名已存在"):
            service.register_user(db, "b@test.com", "samename", "pass123456")

    def test_authenticate_success(self, db):
        service.register_user(db, "login@test.com", "loginuser", "secret99")
        user = service.authenticate_user(db, "login@test.com", "secret99")
        assert user is not None
        assert user.username == "loginuser"

    def test_authenticate_wrong_password(self, db):
        service.register_user(db, "wrong@test.com", "wronguser", "correct")
        assert service.authenticate_user(db, "wrong@test.com", "incorrect") is None

    def test_authenticate_nonexistent(self, db):
        assert service.authenticate_user(db, "nobody@test.com", "pass") is None

    def test_get_user_by_id(self, db):
        user = service.register_user(db, "byid@test.com", "byid", "pass123456")
        found = service.get_user_by_id(db, user.id)
        assert found is not None
        assert found.email == "byid@test.com"

    def test_get_user_by_token(self, db):
        user = service.register_user(db, "bytoken@test.com", "bytoken", "pass123456")
        token = service.create_access_token(user.id, user.username, user.role)
        found = service.get_user_by_token(db, token)
        assert found is not None
        assert found.id == user.id


# ── 项目 CRUD ──

class TestProjectCRUD:
    def test_create_project(self, db):
        user = service.register_user(db, "proj@test.com", "projuser", "pass123456")
        proj = service.create_project(db, user.id, "My App", "描述", "http://localhost:3000")
        assert proj.id is not None
        assert proj.name == "My App"
        assert proj.owner_id == user.id

    def test_list_projects(self, db):
        user = service.register_user(db, "list@test.com", "listuser", "pass123456")
        service.create_project(db, user.id, "Proj A")
        service.create_project(db, user.id, "Proj B")
        projects = service.get_user_projects(db, user.id)
        assert len(projects) == 2

    def test_get_project_with_ownership(self, db):
        user1 = service.register_user(db, "u1@test.com", "u1", "pass123456")
        user2 = service.register_user(db, "u2@test.com", "u2", "pass123456")
        proj = service.create_project(db, user1.id, "Private")
        # 所有者能访问
        assert service.get_project(db, proj.id, user1.id) is not None
        # 非所有者不能
        assert service.get_project(db, proj.id, user2.id) is None

    def test_update_project(self, db):
        user = service.register_user(db, "upd@test.com", "upduser", "pass123456")
        proj = service.create_project(db, user.id, "Old Name")
        updated = service.update_project(db, proj.id, user.id, name="New Name")
        assert updated.name == "New Name"

    def test_delete_project(self, db):
        user = service.register_user(db, "del@test.com", "deluser", "pass123456")
        proj = service.create_project(db, user.id, "To Delete")
        assert service.delete_project(db, proj.id, user.id) is True
        # 软删除后不可访问
        assert service.get_project(db, proj.id, user.id) is None

    def test_project_quota(self, db):
        user = service.register_user(db, "quota@test.com", "quotauser", "pass123456")
        # free用户最多3个项目
        for i in range(user.max_projects):
            service.create_project(db, user.id, f"Proj {i}")
        with pytest.raises(ValueError, match="项目数已达上限"):
            service.create_project(db, user.id, "One Too Many")


# ── 用量管理 ──

class TestUsageManagement:
    def test_record_and_check(self, db):
        user = service.register_user(db, "usage@test.com", "usageuser", "pass123456")
        # 初始配额
        quota = service.check_quota(db, user.id, "test")
        assert quota["allowed"] is True
        assert quota["used"] == 0
        assert quota["limit"] == user.max_tests_per_day

        # 记录使用
        service.record_usage(db, user.id, tests=3, ai_calls=10)
        quota = service.check_quota(db, user.id, "test")
        assert quota["used"] == 3
        assert quota["remaining"] == user.max_tests_per_day - 3

    def test_quota_exceeded(self, db):
        user = service.register_user(db, "exceed@test.com", "exceed", "pass123456")
        service.record_usage(db, user.id, tests=user.max_tests_per_day)
        quota = service.check_quota(db, user.id, "test")
        assert quota["allowed"] is False
        assert quota["remaining"] == 0

    def test_usage_summary(self, db):
        user = service.register_user(db, "summary@test.com", "summary", "pass123456")
        service.record_usage(db, user.id, tests=5, ai_calls=20, screenshots=10)
        summary = service.get_usage_summary(db, user.id, days=7)
        assert summary["total_tests"] == 5
        assert summary["total_ai_calls"] == 20
        assert summary["total_screenshots"] == 10
        assert len(summary["daily_records"]) == 1

    def test_record_usage_accumulates(self, db):
        user = service.register_user(db, "acc@test.com", "acc", "pass123456")
        service.record_usage(db, user.id, tests=2)
        service.record_usage(db, user.id, tests=3)
        quota = service.check_quota(db, user.id, "test")
        assert quota["used"] == 5


# ── 模型验证 ──

class TestModels:
    def test_user_repr(self, db):
        user = service.register_user(db, "repr@test.com", "repruser", "pass123456")
        assert "repruser" in repr(user)
        assert "free" in repr(user)

    def test_project_repr(self, db):
        user = service.register_user(db, "repr2@test.com", "repr2", "pass123456")
        proj = service.create_project(db, user.id, "Test Project")
        assert "Test Project" in repr(proj)

    def test_role_quotas(self):
        assert ROLE_FREE in ROLE_QUOTAS
        assert ROLE_PRO in ROLE_QUOTAS
        assert ROLE_QUOTAS[ROLE_PRO]["max_tests_per_day"] > ROLE_QUOTAS[ROLE_FREE]["max_tests_per_day"]
