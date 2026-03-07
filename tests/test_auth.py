"""
用户认证与 API Key 管理的单元测试
"""

import os
import tempfile

import pytest

from src.billing.auth import AuthManager
from src.billing.plans import PlanType


@pytest.fixture
def auth_manager():
    """创建临时数据库的 AuthManager。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    manager = AuthManager(db_path=path)
    yield manager
    os.unlink(path)


class TestRegister:
    """注册测试。"""

    def test_register_success(self, auth_manager):
        user, api_key = auth_manager.register("test@example.com")
        assert user.user_id.startswith("u_")
        assert user.email == "test@example.com"
        assert user.plan == PlanType.FREE
        assert user.credits_remaining == 50
        assert api_key.startswith("tp_")
        assert len(api_key) == 67  # "tp_" + 64 hex

    def test_register_with_plan(self, auth_manager):
        user, _ = auth_manager.register("pro@example.com", PlanType.PRO)
        assert user.plan == PlanType.PRO
        assert user.credits_remaining == 2000

    def test_register_duplicate_email(self, auth_manager):
        auth_manager.register("dup@example.com")
        with pytest.raises(ValueError, match="已注册"):
            auth_manager.register("dup@example.com")


class TestAuthenticate:
    """认证测试。"""

    def test_authenticate_success(self, auth_manager):
        _, api_key = auth_manager.register("auth@example.com")
        user = auth_manager.authenticate(api_key)
        assert user is not None
        assert user.email == "auth@example.com"

    def test_authenticate_invalid_key(self, auth_manager):
        user = auth_manager.authenticate("tp_invalid_key")
        assert user is None

    def test_authenticate_empty_key(self, auth_manager):
        user = auth_manager.authenticate("")
        assert user is None


class TestCredits:
    """积分管理测试。"""

    def test_deduct_credits(self, auth_manager):
        user, _ = auth_manager.register("credits@example.com")
        success = auth_manager.deduct_credits(user.user_id, 10)
        assert success is True

        updated = auth_manager.get_user(user.user_id)
        assert updated.credits_remaining == 40
        assert updated.credits_used_this_month == 10

    def test_deduct_insufficient(self, auth_manager):
        user, _ = auth_manager.register("poor@example.com")
        success = auth_manager.deduct_credits(user.user_id, 100)
        assert success is False

        updated = auth_manager.get_user(user.user_id)
        assert updated.credits_remaining == 50

    def test_recharge(self, auth_manager):
        user, _ = auth_manager.register("recharge@example.com")
        success = auth_manager.recharge_credits(user.user_id, 200)
        assert success is True

        updated = auth_manager.get_user(user.user_id)
        assert updated.credits_remaining == 250

    def test_deduct_nonexistent_user(self, auth_manager):
        success = auth_manager.deduct_credits("u_nonexistent", 10)
        assert success is False


class TestApiKey:
    """API Key 管理测试。"""

    def test_rotate_key(self, auth_manager):
        user, old_key = auth_manager.register("rotate@example.com")
        new_key = auth_manager.rotate_api_key(user.user_id)
        assert new_key is not None
        assert new_key != old_key
        assert new_key.startswith("tp_")

        # 旧 Key 失效
        assert auth_manager.authenticate(old_key) is None
        # 新 Key 有效
        assert auth_manager.authenticate(new_key) is not None

    def test_rotate_nonexistent_user(self, auth_manager):
        result = auth_manager.rotate_api_key("u_nonexistent")
        assert result is None


class TestPlanManagement:
    """方案管理测试。"""

    def test_upgrade_plan(self, auth_manager):
        user, _ = auth_manager.register("upgrade@example.com")
        assert user.credits_remaining == 50

        success = auth_manager.upgrade_plan(user.user_id, PlanType.BASIC)
        assert success is True

        updated = auth_manager.get_user(user.user_id)
        assert updated.plan == PlanType.BASIC
        assert updated.credits_remaining == 550  # 50 + 500

    def test_monthly_reset(self, auth_manager):
        user, _ = auth_manager.register("reset@example.com", PlanType.BASIC)
        auth_manager.deduct_credits(user.user_id, 300)

        count = auth_manager.reset_all_monthly()
        assert count == 1

        updated = auth_manager.get_user(user.user_id)
        assert updated.credits_remaining == 500
        assert updated.credits_used_this_month == 0
