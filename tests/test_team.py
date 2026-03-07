"""
团队协作测试（v6.1）

覆盖：创建/加入/邀请码/成员管理/角色变更/项目共享/看板/删除
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth.models import Base, TEAM_ROLE_ADMIN, TEAM_ROLE_TESTER, TEAM_ROLE_VIEWER
from src.auth import service
from src.auth import team_service


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def users(db):
    """创建3个测试用户。"""
    u1 = service.register_user(db, "alice@t.com", "alice", "pass123456")
    u2 = service.register_user(db, "bob@t.com", "bob", "pass123456")
    u3 = service.register_user(db, "carol@t.com", "carol", "pass123456")
    return u1, u2, u3


class TestCreateTeam:
    def test_create_success(self, db, users):
        alice, _, _ = users
        team = team_service.create_team(db, alice.id, "Test Team", "描述")
        assert team.id is not None
        assert team.name == "Test Team"
        assert team.owner_id == alice.id
        assert len(team.invite_code) == 24  # 12 bytes hex

    def test_creator_is_admin(self, db, users):
        alice, _, _ = users
        team = team_service.create_team(db, alice.id, "T")
        role = team_service.get_member_role(db, team.id, alice.id)
        assert role == TEAM_ROLE_ADMIN

    def test_team_in_user_list(self, db, users):
        alice, _, _ = users
        team_service.create_team(db, alice.id, "My Team")
        teams = team_service.get_user_teams(db, alice.id)
        assert len(teams) == 1
        assert teams[0]["name"] == "My Team"
        assert teams[0]["my_role"] == TEAM_ROLE_ADMIN


class TestJoinTeam:
    def test_join_by_invite_code(self, db, users):
        alice, bob, _ = users
        team = team_service.create_team(db, alice.id, "Open Team")
        result = team_service.join_team(db, bob.id, team.invite_code)
        assert result["team_id"] == team.id
        assert result["role"] == TEAM_ROLE_TESTER

    def test_join_invalid_code(self, db, users):
        _, bob, _ = users
        with pytest.raises(ValueError, match="无效的邀请码"):
            team_service.join_team(db, bob.id, "bad_code")

    def test_join_already_member(self, db, users):
        alice, bob, _ = users
        team = team_service.create_team(db, alice.id, "T")
        team_service.join_team(db, bob.id, team.invite_code)
        with pytest.raises(ValueError, match="已是该团队成员"):
            team_service.join_team(db, bob.id, team.invite_code)

    def test_join_full_team(self, db, users):
        alice, bob, carol = users
        team = team_service.create_team(db, alice.id, "Tiny")
        # 设置max_members=2（alice已占1个）
        team.max_members = 2
        db.commit()
        team_service.join_team(db, bob.id, team.invite_code)
        with pytest.raises(ValueError, match="团队已满"):
            team_service.join_team(db, carol.id, team.invite_code)


class TestMemberManagement:
    def test_get_members(self, db, users):
        alice, bob, _ = users
        team = team_service.create_team(db, alice.id, "T")
        team_service.join_team(db, bob.id, team.invite_code)
        members = team_service.get_team_members(db, team.id)
        assert len(members) == 2
        usernames = {m["username"] for m in members}
        assert usernames == {"alice", "bob"}

    def test_remove_member(self, db, users):
        alice, bob, _ = users
        team = team_service.create_team(db, alice.id, "T")
        team_service.join_team(db, bob.id, team.invite_code)
        result = team_service.remove_member(db, team.id, bob.id, alice.id)
        assert result is True
        members = team_service.get_team_members(db, team.id)
        assert len(members) == 1

    def test_remove_member_not_admin(self, db, users):
        alice, bob, carol = users
        team = team_service.create_team(db, alice.id, "T")
        team_service.join_team(db, bob.id, team.invite_code)
        team_service.join_team(db, carol.id, team.invite_code)
        with pytest.raises(ValueError, match="仅管理员"):
            team_service.remove_member(db, team.id, carol.id, bob.id)

    def test_cannot_remove_owner(self, db, users):
        alice, bob, _ = users
        team = team_service.create_team(db, alice.id, "T")
        team_service.join_team(db, bob.id, team.invite_code)
        team_service.change_role(db, team.id, bob.id, TEAM_ROLE_ADMIN, alice.id)
        with pytest.raises(ValueError, match="不能移除团队创建者"):
            team_service.remove_member(db, team.id, alice.id, bob.id)


class TestRoleChange:
    def test_change_role(self, db, users):
        alice, bob, _ = users
        team = team_service.create_team(db, alice.id, "T")
        team_service.join_team(db, bob.id, team.invite_code)
        team_service.change_role(db, team.id, bob.id, TEAM_ROLE_VIEWER, alice.id)
        assert team_service.get_member_role(db, team.id, bob.id) == TEAM_ROLE_VIEWER

    def test_change_role_not_admin(self, db, users):
        alice, bob, carol = users
        team = team_service.create_team(db, alice.id, "T")
        team_service.join_team(db, bob.id, team.invite_code)
        team_service.join_team(db, carol.id, team.invite_code)
        with pytest.raises(ValueError, match="仅管理员"):
            team_service.change_role(db, team.id, carol.id, TEAM_ROLE_ADMIN, bob.id)

    def test_invalid_role(self, db, users):
        alice, bob, _ = users
        team = team_service.create_team(db, alice.id, "T")
        team_service.join_team(db, bob.id, team.invite_code)
        with pytest.raises(ValueError, match="无效角色"):
            team_service.change_role(db, team.id, bob.id, "superadmin", alice.id)


class TestProjectSharing:
    def test_share_project(self, db, users):
        alice, bob, _ = users
        team = team_service.create_team(db, alice.id, "T")
        proj = service.create_project(db, alice.id, "My App")
        shared = team_service.share_project(db, proj.id, team.id, alice.id)
        assert shared.team_id == team.id

    def test_share_not_owner(self, db, users):
        alice, bob, _ = users
        team = team_service.create_team(db, alice.id, "T")
        team_service.join_team(db, bob.id, team.invite_code)
        proj = service.create_project(db, alice.id, "Private")
        with pytest.raises(ValueError, match="项目不存在或无权限"):
            team_service.share_project(db, proj.id, team.id, bob.id)

    def test_share_not_team_member(self, db, users):
        alice, bob, _ = users
        team = team_service.create_team(db, bob.id, "Bob Team")
        proj = service.create_project(db, alice.id, "Alice Proj")
        with pytest.raises(ValueError, match="你不是该团队成员"):
            team_service.share_project(db, proj.id, team.id, alice.id)

    def test_unshare_project(self, db, users):
        alice, _, _ = users
        team = team_service.create_team(db, alice.id, "T")
        proj = service.create_project(db, alice.id, "Shared")
        team_service.share_project(db, proj.id, team.id, alice.id)
        unshared = team_service.unshare_project(db, proj.id, alice.id)
        assert unshared.team_id is None

    def test_team_projects_list(self, db, users):
        alice, _, _ = users
        team = team_service.create_team(db, alice.id, "T")
        p1 = service.create_project(db, alice.id, "A")
        p2 = service.create_project(db, alice.id, "B")
        team_service.share_project(db, p1.id, team.id, alice.id)
        team_service.share_project(db, p2.id, team.id, alice.id)
        projects = team_service.get_team_projects(db, team.id)
        assert len(projects) == 2


class TestTeamDashboard:
    def test_dashboard_data(self, db, users):
        alice, bob, _ = users
        team = team_service.create_team(db, alice.id, "Dashboard Team")
        team_service.join_team(db, bob.id, team.invite_code)
        proj = service.create_project(db, alice.id, "App")
        team_service.share_project(db, proj.id, team.id, alice.id)
        data = team_service.get_team_dashboard(db, team.id)
        assert data["team_name"] == "Dashboard Team"
        assert data["member_count"] == 2
        assert data["project_count"] == 1
        assert "avg_pass_rate" in data

    def test_dashboard_nonexistent(self, db):
        data = team_service.get_team_dashboard(db, 9999)
        assert "error" in data


class TestInviteAndDelete:
    def test_regenerate_invite(self, db, users):
        alice, _, _ = users
        team = team_service.create_team(db, alice.id, "T")
        old_code = team.invite_code
        new_code = team_service.regenerate_invite(db, team.id, alice.id)
        assert new_code != old_code
        assert len(new_code) == 24

    def test_regenerate_not_admin(self, db, users):
        alice, bob, _ = users
        team = team_service.create_team(db, alice.id, "T")
        team_service.join_team(db, bob.id, team.invite_code)
        with pytest.raises(ValueError, match="仅管理员"):
            team_service.regenerate_invite(db, team.id, bob.id)

    def test_delete_team(self, db, users):
        alice, _, _ = users
        team = team_service.create_team(db, alice.id, "To Delete")
        assert team_service.delete_team(db, team.id, alice.id) is True
        assert team_service.get_team(db, team.id) is None

    def test_delete_not_owner(self, db, users):
        alice, bob, _ = users
        team = team_service.create_team(db, alice.id, "T")
        team_service.join_team(db, bob.id, team.invite_code)
        team_service.change_role(db, team.id, bob.id, TEAM_ROLE_ADMIN, alice.id)
        with pytest.raises(ValueError, match="仅团队创建者"):
            team_service.delete_team(db, team.id, bob.id)


class TestModelRepr:
    def test_team_repr(self, db, users):
        alice, _, _ = users
        team = team_service.create_team(db, alice.id, "Repr Team")
        assert "Repr Team" in repr(team)

    def test_member_repr(self, db, users):
        alice, _, _ = users
        team = team_service.create_team(db, alice.id, "T")
        members = db.query(team_service.TeamMember).filter_by(team_id=team.id).all()
        assert "admin" in repr(members[0])
