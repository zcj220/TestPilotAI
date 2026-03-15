r"""
社区经验分享端到端测试（v13.0-C）

验证完整流程：
1. 匿名化模块（脱敏、安全关键词保留）
2. 内容审核（必填/长度/垃圾检测）
3. 分享价值评分
4. 快照 → 分享 → 数据库验证
5. 直接分享流程
6. 举报机制

运行方式：
  cd D:\projects\TestPilotAI
  poetry run python -m pytest tests/test_community_share.py -v
"""

import pytest
from src.community.anonymizer import (
    anonymize_text,
    anonymize_code,
    anonymize_experience,
    calc_share_score,
    validate_content,
)


# ═══════════════════════════════════════════════════════
#  匿名化测试
# ═══════════════════════════════════════════════════════

class TestAnonymizeText:

    def test_strips_windows_paths(self):
        text = "Error at C:\\Users\\zhangsan\\projects\\my-app\\src\\main.py line 42"
        result = anonymize_text(text)
        assert "zhangsan" not in result
        assert "my-app" not in result
        assert "<PATH>" in result

    def test_strips_unix_paths(self):
        text = "Cannot find /home/user/workspace/secret-project/config.yml"
        result = anonymize_text(text)
        assert "user" not in result.lower() or "<PATH>" in result
        assert "secret-project" not in result

    def test_strips_ip_addresses(self):
        text = "Failed to connect to 192.168.1.100:3306"
        result = anonymize_text(text)
        assert "192.168.1.100" not in result
        assert "<IP>" in result

    def test_strips_emails(self):
        text = "Contact admin@company.com for help"
        result = anonymize_text(text)
        assert "admin@company.com" not in result
        assert "<EMAIL>" in result

    def test_strips_api_keys(self):
        text = "Use key sk_live_1234567890abcdefghij to authenticate"
        result = anonymize_text(text)
        assert "sk_live_1234567890abcdefghij" not in result

    def test_strips_phone_numbers(self):
        text = "请联系 13812345678 获取帮助"
        result = anonymize_text(text)
        assert "13812345678" not in result
        assert "<PHONE>" in result

    def test_preserves_framework_names(self):
        text = "React useState hook throws error in useEffect cleanup"
        result = anonymize_text(text)
        assert "React" in result or "react" in result.lower()
        assert "useState" in result
        assert "useEffect" in result

    def test_preserves_error_types(self):
        text = "element_not_found: timeout waiting for selector #submit-btn"
        result = anonymize_text(text)
        assert "element_not_found" in result
        assert "timeout" in result


class TestAnonymizeCode:

    def test_strips_paths_in_code(self):
        code = 'config_path = "C:\\Users\\dev\\project\\settings.json"\ndata = load(config_path)'
        result = anonymize_code(code)
        assert "dev" not in result
        assert "<PATH>" in result

    def test_strips_secrets_in_code(self):
        code = 'api_key = "sk_test_abc123def456ghi789jkl012mno345"'
        result = anonymize_code(code)
        assert "sk_test_abc123def456ghi789jkl012mno345" not in result

    def test_preserves_code_structure(self):
        code = """
async function fetchData() {
  const resp = await fetch('/api/data');
  if (!resp.ok) throw new Error('HTTP ' + resp.status);
  return resp.json();
}
"""
        result = anonymize_code(code)
        assert "async function" in result
        assert "fetchData" in result
        assert "await fetch" in result


class TestAnonymizeExperience:

    def test_full_anonymization(self):
        raw = {
            "title": "Fix crash at C:\\Users\\zhangsan\\app\\src\\main.py",
            "platform": "web",
            "framework": "react",
            "error_type": "crash",
            "problem_desc": "App crashes when user 13812345678 logs in via admin@test.com",
            "solution_desc": "Fixed the auth flow in /home/user/project/auth.js",
            "root_cause": "Null pointer due to api_key=sk_test_1234567890abcdef being expired",
            "code_snippet": 'const key = "sk_test_1234567890abcdef";\nfetch("/api")',
            "tags": ["react", "auth"],
            "project_name": "secret_project",
            "user_email": "zhangsan@company.com",
        }
        result = anonymize_experience(raw)

        assert "zhangsan" not in str(result)
        assert "13812345678" not in str(result)
        assert "admin@test.com" not in str(result)
        assert "secret_project" not in str(result)
        assert "zhangsan@company.com" not in str(result)

        assert result["platform"] == "web"
        assert result["framework"] == "react"
        assert result["error_type"] == "crash"

        assert "project_name" not in result
        assert "user_email" not in result


# ═══════════════════════════════════════════════════════
#  分享价值评分测试
# ═══════════════════════════════════════════════════════

class TestShareScore:

    def test_perfect_score(self):
        data = {
            "platform": "web",
            "error_type": "element_not_found",
            "problem_desc": "Button #submit not found after page load, timeout at 30s waiting for DOM element to appear in the document",
            "solution_desc": "Added explicit wait for element visibility. The element was inside an iframe that needed to be switched to first. Used waitForSelector with increased timeout.",
            "root_cause": "The element was rendered inside a shadow DOM that playwright couldn't access directly",
            "code_snippet": 'await page.waitForSelector("#submit", { timeout: 60000 });',
            "tags": ["playwright", "dom", "iframe"],
        }
        score = calc_share_score(data)
        assert score.total >= 8.0

    def test_minimal_content_low_score(self):
        data = {
            "problem_desc": "it broke",
            "solution_desc": "fixed it",
        }
        score = calc_share_score(data)
        assert score.total <= 2.0

    def test_moderate_content(self):
        data = {
            "platform": "android",
            "problem_desc": "App crashes on launch after updating to SDK 34",
            "solution_desc": "Downgraded targetSdkVersion from 34 to 33 in build.gradle to fix compatibility issue",
        }
        score = calc_share_score(data)
        assert 4.0 <= score.total <= 8.0


# ═══════════════════════════════════════════════════════
#  内容审核测试
# ═══════════════════════════════════════════════════════

class TestContentValidation:

    def test_valid_content(self):
        data = {
            "title": "Fix element_not_found in login page",
            "platform": "web",
            "problem_desc": "The login button was not found after navigating to the login page",
            "solution_desc": "Added an explicit wait for the element to appear before clicking",
        }
        result = validate_content(data)
        assert result.valid is True
        assert len(result.reasons) == 0

    def test_rejects_empty_title(self):
        data = {
            "title": "",
            "platform": "web",
            "problem_desc": "some problem description text",
            "solution_desc": "some solution description text",
        }
        result = validate_content(data)
        assert result.valid is False
        assert any("title" in r for r in result.reasons)

    def test_rejects_invalid_platform(self):
        data = {
            "title": "Some title",
            "platform": "nintendo_switch",
            "problem_desc": "some problem description text",
            "solution_desc": "some solution description text",
        }
        result = validate_content(data)
        assert result.valid is False
        assert any("platform" in r for r in result.reasons)

    def test_rejects_short_problem(self):
        data = {
            "title": "Some title",
            "platform": "web",
            "problem_desc": "broke",
            "solution_desc": "a reasonable solution description here",
        }
        result = validate_content(data)
        assert result.valid is False

    def test_rejects_short_solution(self):
        data = {
            "title": "Some title",
            "platform": "web",
            "problem_desc": "a reasonable problem description here",
            "solution_desc": "fix",
        }
        result = validate_content(data)
        assert result.valid is False

    def test_rejects_identical_title_problem(self):
        data = {
            "title": "Button not found on page",
            "platform": "web",
            "problem_desc": "Button not found on page",
            "solution_desc": "Added an explicit wait for the element",
        }
        result = validate_content(data)
        assert result.valid is False
        assert any("identical" in r for r in result.reasons)

    def test_rejects_identical_problem_solution(self):
        data = {
            "title": "Some title",
            "platform": "web",
            "problem_desc": "The element was not found after page load timeout",
            "solution_desc": "The element was not found after page load timeout",
        }
        result = validate_content(data)
        assert result.valid is False

    def test_rejects_spam_content(self):
        data = {
            "title": "Great solution",
            "platform": "web",
            "problem_desc": "加微信 wxid123 获取最新修复方案",
            "solution_desc": "关注公众号获取更多技术分享经验",
        }
        result = validate_content(data)
        assert result.valid is False
        assert any("spam" in r for r in result.reasons)

    def test_rejects_url_spam(self):
        data = {
            "title": "Check this out",
            "platform": "web",
            "problem_desc": "Visit http://spam1.com http://spam2.com http://spam3.com for solutions",
            "solution_desc": "Click here to get the best fix available now",
        }
        result = validate_content(data)
        assert result.valid is False


# ═══════════════════════════════════════════════════════
#  数据库集成测试
# ═══════════════════════════════════════════════════════

class TestShareIntegration:
    """需要数据库环境。使用 SQLite 内存数据库。"""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from src.auth.models import Base, User
        from src.community.models import SharedExperience, DebugSnapshot

        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()

        user = User(username="testuser", email="test@test.com", hashed_password="fakehash")
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        self.user_id = user.id

        yield
        self.db.close()

    def test_share_direct_flow(self):
        from src.community.service import share_direct

        data = {
            "title": "Fix timeout in C:\\Users\\dev\\project\\test.py",
            "platform": "web",
            "framework": "playwright",
            "error_type": "timeout",
            "problem_desc": "Page load timeout at 192.168.1.50 when testing login with admin@secret.com",
            "solution_desc": "Increased wait timeout and added retry logic for network-dependent operations",
            "root_cause": "Unstable network caused intermittent timeouts during CI runs",
            "code_snippet": 'await page.goto("http://192.168.1.50/login", {timeout: 60000})',
            "tags": ["playwright", "timeout", "ci"],
        }

        result = share_direct(self.db, self.user_id, data)
        assert result["ok"] is True

        exp = result["experience"]
        assert "dev" not in exp["title"]
        assert "192.168.1.50" not in exp["problem_desc"]
        assert "admin@secret.com" not in exp["problem_desc"]

        assert exp["platform"] == "web"
        assert exp["framework"] == "playwright"
        assert exp["error_type"] == "timeout"
        assert exp["share_score"] > 0

        assert result["score_breakdown"]["total"] > 0

    def test_share_from_snapshot_flow(self):
        from src.community.service import create_debug_snapshot, resolve_snapshot, share_from_snapshot

        snap = create_debug_snapshot(self.db, self.user_id, {
            "platform": "android",
            "framework": "appium",
            "error_message": "Element 'com.myapp:id/login_btn' not found at /home/ci/workspace/test.py",
            "error_stack": "NoSuchElementException...",
            "context": {"device": "Pixel 6"},
        })

        resolved = resolve_snapshot(self.db, snap.id, self.user_id, "Added implicit wait and fixed locator strategy")
        assert resolved is not None
        assert resolved.resolved is True

        result = share_from_snapshot(self.db, self.user_id, snap.id, {
            "title": "Fix Android element not found",
            "error_type": "element_not_found",
            "problem_desc": "Login button not found on Pixel 6 with Appium 2.0 after app update",
            "solution_desc": "Added implicit wait and fixed locator strategy from id to accessibility_id",
            "tags": ["appium", "android", "locator"],
        })

        assert result["ok"] is True
        exp = result["experience"]
        assert exp["platform"] == "android"
        assert "ci/workspace" not in exp.get("problem_desc", "")

        from src.community.models import DebugSnapshot as SnapModel
        updated_snap = self.db.query(SnapModel).filter(SnapModel.id == snap.id).first()
        assert updated_snap.shared_experience_id == exp["id"]

    def test_share_unresolved_snapshot_fails(self):
        from src.community.service import create_debug_snapshot, share_from_snapshot

        snap = create_debug_snapshot(self.db, self.user_id, {
            "platform": "web",
            "error_message": "some error",
        })

        result = share_from_snapshot(self.db, self.user_id, snap.id, {
            "title": "test",
            "problem_desc": "problem is happening here and it is complex",
            "solution_desc": "solution is to do this and verify",
        })
        assert result["ok"] is False
        assert result["error"] == "snapshot_not_resolved"

    def test_share_validation_rejection(self):
        from src.community.service import share_direct

        data = {
            "title": "spam",
            "platform": "web",
            "problem_desc": "加微信 wxid123 获取修复方案",
            "solution_desc": "关注公众号获取更多分享经验",
        }
        result = share_direct(self.db, self.user_id, data)
        assert result["ok"] is False
        assert result["error"] == "validation_failed"

    def test_report_experience(self):
        from src.community.service import share_direct, report_experience
        from src.auth.models import User

        data = {
            "title": "Valid experience title",
            "platform": "web",
            "problem_desc": "A legitimate problem description for testing the report feature",
            "solution_desc": "A legitimate solution that actually works and helps people",
        }
        result = share_direct(self.db, self.user_id, data)
        assert result["ok"] is True
        exp_id = result["experience"]["id"]

        reporter = User(username="reporter1", email="r1@test.com", hashed_password="fakehash")
        self.db.add(reporter)
        self.db.commit()
        self.db.refresh(reporter)

        report_result = report_experience(self.db, exp_id, reporter.id, "misleading content")
        assert report_result["ok"] is True

    def test_preview_anonymized(self):
        from src.community.service import preview_anonymized

        data = {
            "title": "Fix crash at C:\\Users\\dev\\secret-app\\main.py",
            "platform": "web",
            "problem_desc": "App crashes when connecting to 192.168.1.100:8080 with token sk_live_abcdef1234567890",
            "solution_desc": "Updated connection retry logic and handled timeout properly across the application",
        }
        result = preview_anonymized(data)

        assert result["validation"]["valid"] is True
        assert "192.168.1.100" not in result["anonymized"]["problem_desc"]
        assert "dev" not in result["anonymized"]["title"]
        assert result["score"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
