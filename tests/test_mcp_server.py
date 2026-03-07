"""MCP Server 工具函数测试。"""

import json
from unittest.mock import patch, MagicMock

import pytest

from src.mcp_server import (
    _format_report,
    _http_get,
    _http_post_json,
    check_engine_health,
    generate_blueprint_template,
    get_test_report,
    list_blueprints,
    run_blueprint_batch,
    run_miniprogram_test,
    run_desktop_test,
)


# ── _format_report ──

class TestFormatReport:
    def test_all_passed(self):
        data = {
            "test_name": "Demo",
            "url": "http://localhost",
            "total_steps": 5,
            "passed_steps": 5,
            "failed_steps": 0,
            "bug_count": 0,
            "pass_rate": 100,
            "duration_seconds": 3.2,
            "report_markdown": "",
        }
        report = _format_report(data)
        assert "通过率" in report
        assert "100%" in report
        assert "所有测试通过" in report
        assert "Bug" not in report or "0" in report

    def test_with_bugs(self):
        data = {
            "test_name": "Shop",
            "url": "http://shop.local",
            "total_steps": 10,
            "passed_steps": 7,
            "failed_steps": 3,
            "bug_count": 2,
            "pass_rate": 70,
            "duration_seconds": 8.5,
            "report_markdown": "## Bug详情\n- Bug1\n- Bug2",
        }
        report = _format_report(data)
        assert "70%" in report
        assert "发现 2 个Bug" in report
        assert "请修复以上Bug" in report
        assert "Bug详情" in report

    def test_empty_data(self):
        data = {
            "total_steps": 0,
            "passed_steps": 0,
            "failed_steps": 0,
            "bug_count": 0,
            "pass_rate": 0,
            "duration_seconds": 0,
        }
        report = _format_report(data)
        assert "TestPilot 测试报告" in report


# ── generate_blueprint_template ──

class TestGenerateBlueprintTemplate:
    def test_basic_template(self):
        result = generate_blueprint_template(
            app_name="我的商城",
            base_url="http://localhost:3000",
            pages_description="首页展示商品，购物车功能",
        )
        assert "我的商城" in result
        assert "http://localhost:3000" in result
        assert "testpilot.json" in result
        assert "补充要点" in result

    def test_template_is_valid_json_block(self):
        result = generate_blueprint_template(
            app_name="App",
            base_url="http://example.com",
            pages_description="登录页",
        )
        # 提取json代码块
        start = result.index("```json\n") + len("```json\n")
        end = result.index("\n```", start)
        json_str = result[start:end]
        data = json.loads(json_str)
        assert data["app_name"] == "App"
        assert data["base_url"] == "http://example.com"
        assert len(data["pages"]) >= 1


# ── get_test_report ──

class TestGetTestReport:
    def test_no_report(self):
        import src.mcp_server as mod
        old = mod._last_report
        mod._last_report = None
        result = get_test_report()
        assert "暂无" in result
        mod._last_report = old

    def test_with_report(self):
        import src.mcp_server as mod
        old = mod._last_report
        mod._last_report = {"report_markdown": "# 测试OK"}
        result = get_test_report()
        assert "测试OK" in result
        mod._last_report = old


# ── check_engine_health ──

class TestCheckEngineHealth:
    @patch("src.mcp_server._http_get")
    def test_healthy(self, mock_get):
        mock_get.return_value = (200, json.dumps({
            "version": "10.0",
            "browser_ready": True,
            "sandbox_count": 3,
        }))
        result = check_engine_health()
        assert "运行正常" in result
        assert "10.0" in result

    @patch("src.mcp_server._http_get")
    def test_connection_error(self, mock_get):
        mock_get.side_effect = ConnectionError("refused")
        result = check_engine_health()
        assert "未运行" in result

    @patch("src.mcp_server._http_get")
    def test_abnormal_status(self, mock_get):
        mock_get.return_value = (500, "Internal Error")
        result = check_engine_health()
        assert "异常" in result


# ── HTTP 工具函数 ──

class TestHttpHelpers:
    @patch("src.mcp_server.urllib.request.urlopen")
    def test_http_get_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"ok":true}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        status, text = _http_get("http://localhost:8900/health")
        assert status == 200
        assert '"ok"' in text

    @patch("src.mcp_server.urllib.request.urlopen")
    def test_http_get_url_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        with pytest.raises(ConnectionError):
            _http_get("http://localhost:9999/nope")

    @patch("src.mcp_server.urllib.request.urlopen")
    def test_http_post_json_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"result":"ok"}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        status, text = _http_post_json("http://localhost:8900/api", {"key": "val"})
        assert status == 200
        assert "ok" in text


# ── run_miniprogram_test ──

class TestRunMiniprogramTest:
    def test_blueprint_not_found(self):
        result = run_miniprogram_test(
            blueprint_path="D:/not_exist/testpilot.json",
        )
        assert "不存在" in result

    @patch("src.mcp_server._http_post_json")
    def test_success(self, mock_post):
        mock_post.return_value = (200, json.dumps({
            "test_name": "小程序测试",
            "url": "miniprogram://demo",
            "total_steps": 4,
            "passed_steps": 3,
            "failed_steps": 1,
            "bug_count": 1,
            "pass_rate": 75,
            "duration_seconds": 5.0,
            "report_markdown": "## 小程序测试\n- Bug1",
        }))
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"app_name": "test"}, f)
            f.flush()
            result = run_miniprogram_test(blueprint_path=f.name)
        os.unlink(f.name)
        assert "小程序测试报告" in result
        assert "75%" in result

    @patch("src.mcp_server._http_post_json")
    def test_api_error(self, mock_post):
        mock_post.return_value = (500, "Internal Error")
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"app_name": "test"}, f)
            f.flush()
            result = run_miniprogram_test(blueprint_path=f.name)
        os.unlink(f.name)
        assert "失败" in result

    @patch("src.mcp_server._http_post_json")
    def test_connection_error(self, mock_post):
        mock_post.side_effect = ConnectionError("refused")
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"app_name": "test"}, f)
            f.flush()
            result = run_miniprogram_test(blueprint_path=f.name)
        os.unlink(f.name)
        assert "无法连接" in result


# ── run_desktop_test ──

class TestRunDesktopTest:
    def test_blueprint_not_found(self):
        result = run_desktop_test(
            blueprint_path="D:/not_exist/testpilot.json",
        )
        assert "不存在" in result

    @patch("src.mcp_server._http_post_json")
    def test_success(self, mock_post):
        mock_post.return_value = (200, json.dumps({
            "test_name": "桌面测试",
            "url": "desktop://App",
            "total_steps": 6,
            "passed_steps": 6,
            "failed_steps": 0,
            "bug_count": 0,
            "pass_rate": 100,
            "duration_seconds": 3.0,
            "report_markdown": "",
        }))
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"app_name": "test"}, f)
            f.flush()
            result = run_desktop_test(blueprint_path=f.name)
        os.unlink(f.name)
        assert "桌面应用测试报告" in result
        assert "100%" in result
        assert "所有测试通过" in result

    @patch("src.mcp_server._http_post_json")
    def test_with_window_title(self, mock_post):
        mock_post.return_value = (200, json.dumps({
            "test_name": "桌面测试",
            "url": "desktop://App",
            "total_steps": 2,
            "passed_steps": 1,
            "failed_steps": 1,
            "bug_count": 1,
            "pass_rate": 50,
            "duration_seconds": 2.0,
            "report_markdown": "## Bug\n- 按钮点击无响应",
        }))
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"app_name": "test"}, f)
            f.flush()
            result = run_desktop_test(
                blueprint_path=f.name,
                window_title="TestPilot AI",
            )
        os.unlink(f.name)
        assert "50%" in result
        assert "请修复" in result

    @patch("src.mcp_server._http_post_json")
    def test_connection_error(self, mock_post):
        mock_post.side_effect = ConnectionError("refused")
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"app_name": "test"}, f)
            f.flush()
            result = run_desktop_test(blueprint_path=f.name)
        os.unlink(f.name)
        assert "无法连接" in result


# ── list_blueprints ──

class TestListBlueprints:
    @patch("src.mcp_server._http_get")
    def test_success(self, mock_get):
        mock_get.return_value = (200, json.dumps({
            "blueprints": [
                {
                    "file_path": "/app/testpilot.json",
                    "file_name": "testpilot.json",
                    "app_name": "商城",
                    "description": "测试登录和购物车功能",
                    "platform": "web",
                    "scenario_count": 3,
                    "step_count": 12,
                },
                {
                    "file_path": "/app/testpilot/cart.testpilot.json",
                    "file_name": "cart.testpilot.json",
                    "app_name": "购物车",
                    "description": "",
                    "platform": "web",
                    "scenario_count": 2,
                    "step_count": 8,
                },
            ],
            "total": 2,
        }))
        result = list_blueprints(directory="/app")
        assert "2 个蓝本" in result
        assert "商城" in result
        assert "购物车" in result

    @patch("src.mcp_server._http_get")
    def test_empty(self, mock_get):
        mock_get.return_value = (200, json.dumps({"blueprints": [], "total": 0}))
        result = list_blueprints(directory="/empty")
        assert "未找到" in result

    @patch("src.mcp_server._http_get")
    def test_connection_error(self, mock_get):
        mock_get.side_effect = ConnectionError("refused")
        result = list_blueprints(directory="/app")
        assert "无法连接" in result


# ── run_blueprint_batch ──

class TestRunBlueprintBatch:
    def test_missing_files(self):
        result = run_blueprint_batch(
            blueprint_paths=["D:/not_exist/a.json", "D:/not_exist/b.json"],
        )
        assert "不存在" in result

    @patch("src.mcp_server._http_post_json")
    def test_success(self, mock_post):
        mock_post.return_value = (200, json.dumps({
            "total_blueprints": 2,
            "passed_blueprints": 1,
            "failed_blueprints": 1,
            "total_steps": 10,
            "passed_steps": 8,
            "failed_steps": 2,
            "total_bugs": 1,
            "overall_pass_rate": 80,
            "total_duration_seconds": 5.0,
            "results": [],
            "summary_markdown": "# 批量蓝本测试汇总报告\n\n- 蓝本数: 2",
        }))
        import tempfile, os
        files = []
        for _ in range(2):
            f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
            json.dump({"app_name": "test"}, f)
            f.flush()
            files.append(f.name)
            f.close()
        result = run_blueprint_batch(blueprint_paths=files)
        for f in files:
            os.unlink(f)
        assert "批量蓝本测试汇总" in result
        assert "请修复" in result

    @patch("src.mcp_server._http_post_json")
    def test_all_passed(self, mock_post):
        mock_post.return_value = (200, json.dumps({
            "total_blueprints": 1,
            "passed_blueprints": 1,
            "failed_blueprints": 0,
            "total_steps": 5,
            "passed_steps": 5,
            "failed_steps": 0,
            "total_bugs": 0,
            "overall_pass_rate": 100,
            "total_duration_seconds": 2.0,
            "results": [],
            "summary_markdown": "# 批量蓝本测试汇总报告",
        }))
        import tempfile, os
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({"app_name": "test"}, f)
        f.flush()
        f.close()
        result = run_blueprint_batch(blueprint_paths=[f.name])
        os.unlink(f.name)
        assert "所有蓝本测试通过" in result

    @patch("src.mcp_server._http_post_json")
    def test_connection_error(self, mock_post):
        mock_post.side_effect = ConnectionError("refused")
        import tempfile, os
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({"app_name": "test"}, f)
        f.flush()
        f.close()
        result = run_blueprint_batch(blueprint_paths=[f.name])
        os.unlink(f.name)
        assert "无法连接" in result
