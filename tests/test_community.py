"""
社区经验库模块测试（v13.0）

覆盖：经验CRUD、投票/采纳、用户资料、勋章、排行榜、调试快照、积分
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth.models import Base, User
from src.auth import service as auth_service
from src.community.models import (
    SharedExperience, ExperienceVote, UserBadge,
    UserProfile, DebugSnapshot, CreditTransaction,
    EXP_STATUS_ACTIVE,
)
from src.community import service


@pytest.fixture
def db():
    """内存 SQLite 测试数据库。"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def user1(db):
    """创建测试用户 1。"""
    u = User(
        email="alice@test.com",
        username="alice",
        hashed_password=auth_service.hash_password("pass123"),
        role="free",
        credits=100,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def user2(db):
    """创建测试用户 2。"""
    u = User(
        email="bob@test.com",
        username="bob",
        hashed_password=auth_service.hash_password("pass456"),
        role="free",
        credits=100,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_experience_data(**overrides) -> dict:
    """生成经验数据模板。"""
    data = {
        "title": "Playwright 定位器超时修复",
        "platform": "web",
        "framework": "playwright",
        "error_type": "TimeoutError",
        "problem_desc": "使用 page.click 时因为动态加载导致超时",
        "solution_desc": "改用 page.wait_for_selector + click，并增加重试逻辑",
        "root_cause": "SPA 页面异步加载组件",
        "tags": ["timeout", "spa", "playwright"],
        "difficulty": "medium",
        "share_score": 6.0,
        "fix_pattern": "add_wait",
    }
    data.update(overrides)
    return data


# ══════════════════════════════════════════════════════
#  经验 CRUD
# ══════════════════════════════════════════════════════

class TestExperienceCRUD:
    def test_create_experience(self, db, user1):
        exp = service.create_experience(db, user1.id, _make_experience_data())
        assert exp.id is not None
        assert exp.title == "Playwright 定位器超时修复"
        assert exp.platform == "web"
        assert exp.user_id == user1.id
        assert exp.status == EXP_STATUS_ACTIVE

    def test_get_experience(self, db, user1):
        exp = service.create_experience(db, user1.id, _make_experience_data())
        fetched = service.get_experience(db, exp.id)
        assert fetched is not None
        assert fetched.id == exp.id
        assert fetched.view_count == 1

    def test_get_experience_increments_view(self, db, user1):
        exp = service.create_experience(db, user1.id, _make_experience_data())
        service.get_experience(db, exp.id)
        service.get_experience(db, exp.id)
        raw = service.get_experience_raw(db, exp.id)
        assert raw.view_count == 2

    def test_list_experiences(self, db, user1):
        for i in range(5):
            service.create_experience(db, user1.id, _make_experience_data(title=f"经验{i}"))
        result = service.list_experiences(db, page=1, per_page=3)
        assert result["total"] == 5
        assert len(result["items"]) == 3
        assert result["pages"] == 2

    def test_list_filter_by_platform(self, db, user1):
        service.create_experience(db, user1.id, _make_experience_data(platform="web"))
        service.create_experience(db, user1.id, _make_experience_data(platform="android"))
        result = service.list_experiences(db, platform="android")
        assert result["total"] == 1
        assert result["items"][0]["platform"] == "android"

    def test_list_search(self, db, user1):
        service.create_experience(db, user1.id, _make_experience_data(title="React组件渲染"))
        service.create_experience(db, user1.id, _make_experience_data(title="Flutter动画卡顿"))
        result = service.list_experiences(db, search="React")
        assert result["total"] == 1

    def test_update_experience(self, db, user1):
        exp = service.create_experience(db, user1.id, _make_experience_data())
        updated = service.update_experience(db, exp.id, user1.id, {"title": "新标题"})
        assert updated is not None
        assert updated.title == "新标题"

    def test_update_by_other_user_fails(self, db, user1, user2):
        exp = service.create_experience(db, user1.id, _make_experience_data())
        result = service.update_experience(db, exp.id, user2.id, {"title": "黑客标题"})
        assert result is None

    def test_delete_experience(self, db, user1):
        exp = service.create_experience(db, user1.id, _make_experience_data())
        ok = service.delete_experience(db, exp.id, user1.id)
        assert ok is True
        assert service.get_experience(db, exp.id) is None


# ══════════════════════════════════════════════════════
#  投票 / 采纳
# ══════════════════════════════════════════════════════

class TestVoting:
    def test_upvote(self, db, user1, user2):
        exp = service.create_experience(db, user1.id, _make_experience_data())
        result = service.vote_experience(db, exp.id, user2.id, "upvote")
        assert result["action"] == "added"
        raw = service.get_experience_raw(db, exp.id)
        assert raw.upvote_count == 1

    def test_duplicate_upvote_toggles(self, db, user1, user2):
        exp = service.create_experience(db, user1.id, _make_experience_data())
        service.vote_experience(db, exp.id, user2.id, "upvote")
        result = service.vote_experience(db, exp.id, user2.id, "upvote")
        assert result["action"] == "removed"
        raw = service.get_experience_raw(db, exp.id)
        assert raw.upvote_count == 0

    def test_self_vote_blocked(self, db, user1):
        exp = service.create_experience(db, user1.id, _make_experience_data())
        result = service.vote_experience(db, exp.id, user1.id, "upvote")
        assert "error" in result

    def test_adopt(self, db, user1, user2):
        exp = service.create_experience(db, user1.id, _make_experience_data())
        result = service.vote_experience(db, exp.id, user2.id, "adopt")
        assert result["action"] == "added"
        raw = service.get_experience_raw(db, exp.id)
        assert raw.adoption_count == 1


# ══════════════════════════════════════════════════════
#  用户资料
# ══════════════════════════════════════════════════════

class TestUserProfile:
    def test_get_or_create_profile(self, db, user1):
        profile = service.get_or_create_profile(db, user1.id)
        assert profile.user_id == user1.id
        assert profile.display_name == "alice"

    def test_update_profile(self, db, user1):
        service.get_or_create_profile(db, user1.id)
        profile = service.update_profile(db, user1.id, {"bio": "测试爱好者"})
        assert profile.bio == "测试爱好者"

    def test_get_user_stats(self, db, user1):
        service.create_experience(db, user1.id, _make_experience_data(platform="web"))
        service.create_experience(db, user1.id, _make_experience_data(platform="android"))
        stats = service.get_user_stats(db, user1.id)
        assert stats["total_shares"] == 2
        assert stats["platform_breakdown"]["web"] == 1
        assert stats["platform_breakdown"]["android"] == 1

    def test_get_user_contributions(self, db, user1):
        service.create_experience(db, user1.id, _make_experience_data())
        items = service.get_user_contributions(db, user1.id)
        assert len(items) == 1


# ══════════════════════════════════════════════════════
#  勋章
# ══════════════════════════════════════════════════════

class TestBadges:
    def test_first_share_badge(self, db, user1):
        service.create_experience(db, user1.id, _make_experience_data())
        badges = service.get_user_badges(db, user1.id)
        badge_types = [b["badge_type"] for b in badges]
        assert "first_share" in badge_types

    def test_no_duplicate_badges(self, db, user1):
        service.create_experience(db, user1.id, _make_experience_data())
        service.create_experience(db, user1.id, _make_experience_data(title="第二条"))
        badges = service.get_user_badges(db, user1.id)
        first_share = [b for b in badges if b["badge_type"] == "first_share"]
        assert len(first_share) == 1


# ══════════════════════════════════════════════════════
#  排行榜
# ══════════════════════════════════════════════════════

class TestLeaderboard:
    def test_leaderboard(self, db, user1, user2):
        service.create_experience(db, user1.id, _make_experience_data())
        service.create_experience(db, user1.id, _make_experience_data(title="第二条"))
        service.create_experience(db, user2.id, _make_experience_data(title="Bob的"))
        lb = service.get_leaderboard(db, limit=10)
        assert len(lb) == 2
        assert lb[0]["share_count"] >= lb[1]["share_count"]


# ══════════════════════════════════════════════════════
#  调试快照
# ══════════════════════════════════════════════════════

class TestDebugSnapshot:
    def test_create_snapshot(self, db, user1):
        snap = service.create_debug_snapshot(db, user1.id, {
            "platform": "web",
            "error_message": "Element not found",
            "context": {"url": "http://example.com"},
        })
        assert snap.id is not None
        assert snap.resolved is False

    def test_list_snapshots(self, db, user1):
        service.create_debug_snapshot(db, user1.id, {"platform": "web"})
        service.create_debug_snapshot(db, user1.id, {"platform": "android", "resolved": True})
        all_snaps = service.list_debug_snapshots(db, user1.id)
        assert len(all_snaps) == 2
        unresolved = service.list_debug_snapshots(db, user1.id, resolved=False)
        assert len(unresolved) == 1

    def test_resolve_snapshot(self, db, user1):
        snap = service.create_debug_snapshot(db, user1.id, {"platform": "web"})
        resolved = service.resolve_snapshot(db, snap.id, user1.id, "增加了等待时间")
        assert resolved.resolved is True
        assert resolved.resolved_at is not None


# ══════════════════════════════════════════════════════
#  积分
# ══════════════════════════════════════════════════════

class TestCredits:
    def test_get_balance(self, db, user1):
        balance = service.get_credit_balance(db, user1.id)
        assert balance["credits"] == 100
        assert balance["plan"] == "free"

    def test_add_credits(self, db, user1):
        tx = service.add_credits(db, user1.id, 50, "recharge", "充值50积分")
        assert tx.amount == 50
        assert tx.balance_after == 150
        balance = service.get_credit_balance(db, user1.id)
        assert balance["credits"] == 150

    def test_consume_credits(self, db, user1):
        tx = service.consume_credits(db, user1.id, 10, "test_run", "执行测试")
        assert tx is not None
        assert tx.amount == -10
        assert tx.balance_after == 90

    def test_consume_insufficient(self, db, user1):
        tx = service.consume_credits(db, user1.id, 999, "test_run")
        assert tx is None

    def test_transaction_history(self, db, user1):
        service.add_credits(db, user1.id, 20, "bonus")
        service.consume_credits(db, user1.id, 5, "test_run")
        result = service.list_credit_transactions(db, user1.id)
        assert result["total"] == 2
        assert len(result["items"]) == 2


# ══════════════════════════════════════════════════════
#  社区统计
# ══════════════════════════════════════════════════════

class TestCommunityStats:
    def test_stats(self, db, user1, user2):
        service.create_experience(db, user1.id, _make_experience_data())
        service.create_experience(db, user2.id, _make_experience_data(title="Bob的"))
        stats = service.get_community_stats(db)
        assert stats["total_experiences"] == 2
        assert stats["total_contributors"] == 2

    def test_trending(self, db, user1):
        service.create_experience(db, user1.id, _make_experience_data())
        trending = service.get_trending(db, limit=5)
        assert len(trending) >= 1

    def test_suggest(self, db, user1):
        service.create_experience(db, user1.id, _make_experience_data(
            platform="web", error_type="TimeoutError"
        ))
        suggestions = service.suggest_for_error(db, "web", "TimeoutError")
        assert len(suggestions) >= 1
