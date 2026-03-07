"""用户认证服务测试（v6.0）。"""

from datetime import timedelta

import pytest

from src.auth.service import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
)


# ── 密码哈希 ──

class TestPasswordHash:
    def test_hash_and_verify(self):
        pw = "MySecretP@ss123"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed)

    def test_wrong_password(self):
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_empty_password(self):
        hashed = hash_password("")
        assert verify_password("", hashed)

    def test_long_password_truncated(self):
        """bcrypt 限制72字节，超长密码会被截断。"""
        long_pw = "A" * 100
        hashed = hash_password(long_pw)
        assert verify_password(long_pw, hashed)

    def test_unicode_password(self):
        pw = "中文密码测试🔑"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed)

    def test_verify_bad_hash(self):
        assert not verify_password("test", "not-a-valid-hash")


# ── JWT Token ──

class TestJWT:
    def test_create_and_decode(self):
        token = create_access_token(user_id=1, username="alice", role="free")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "1"
        assert payload["username"] == "alice"
        assert payload["role"] == "free"

    def test_custom_expiry(self):
        token = create_access_token(
            user_id=2, username="bob", role="pro",
            expires_delta=timedelta(hours=1),
        )
        payload = decode_token(token)
        assert payload is not None
        assert payload["username"] == "bob"

    def test_expired_token(self):
        token = create_access_token(
            user_id=3, username="charlie", role="free",
            expires_delta=timedelta(seconds=-10),  # 已过期
        )
        payload = decode_token(token)
        assert payload is None

    def test_invalid_token(self):
        payload = decode_token("this.is.not.a.jwt")
        assert payload is None

    def test_empty_token(self):
        payload = decode_token("")
        assert payload is None

    def test_different_users_different_tokens(self):
        t1 = create_access_token(1, "a", "free")
        t2 = create_access_token(2, "b", "free")
        assert t1 != t2
