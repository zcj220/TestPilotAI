"""
测试报告分析引擎测试（v5.2）
"""

import json
import tempfile
import os

import pytest

from src.memory.store import MemoryStore
from src.testing.report_analytics import ReportAnalytics


@pytest.fixture
def store_with_data():
    """创建带有测试数据的 MemoryStore。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = MemoryStore(db_path=__import__("pathlib").Path(path))

    # 插入多条测试记录
    store.save_test_result(
        test_name="测试-首页", url="http://localhost:3000",
        total_steps=10, passed_steps=8, failed_steps=2, bug_count=2,
        pass_rate=0.8, duration_seconds=15.0,
        steps_json=json.dumps([
            {"step": 1, "action": "navigate", "status": "passed", "description": "打开首页", "error": None},
            {"step": 2, "action": "click", "status": "passed", "description": "点击登录", "error": None},
            {"step": 3, "action": "fill", "status": "passed", "description": "输入用户名", "error": None},
            {"step": 4, "action": "screenshot", "status": "failed", "description": "验证登录", "error": "元素不存在"},
        ]),
        bugs_json=json.dumps([
            {"severity": "major", "title": "登录按钮无响应", "description": "点击后无反应", "category": "UI", "location": "#login-btn"},
            {"severity": "minor", "title": "样式错位", "description": "按钮位置偏移", "category": "CSS", "location": ".header"},
        ]),
    )

    store.save_test_result(
        test_name="测试-首页v2", url="http://localhost:3000",
        total_steps=10, passed_steps=9, failed_steps=1, bug_count=1,
        pass_rate=0.9, duration_seconds=12.0,
        steps_json=json.dumps([
            {"step": 1, "action": "navigate", "status": "passed", "description": "打开首页"},
            {"step": 2, "action": "click", "status": "passed", "description": "点击登录"},
            {"step": 3, "action": "screenshot", "status": "passed", "description": "验证登录"},
        ]),
        bugs_json=json.dumps([
            {"severity": "minor", "title": "样式错位", "description": "按钮位置偏移", "category": "CSS", "location": ".header"},
        ]),
    )

    store.save_test_result(
        test_name="测试-关于页", url="http://localhost:3000/about",
        total_steps=5, passed_steps=5, failed_steps=0, bug_count=0,
        pass_rate=1.0, duration_seconds=8.0,
        steps_json=json.dumps([
            {"step": 1, "action": "navigate", "status": "passed", "description": "打开关于页"},
        ]),
        bugs_json="[]",
    )

    yield store, path
    store._conn.close()
    os.unlink(path)


class TestPassRateTrend:
    """通过率趋势测试。"""

    def test_trend_all(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.get_pass_rate_trend()

        assert result["count"] == 3
        assert len(result["labels"]) == 3
        assert len(result["pass_rates"]) == 3
        # 按时间正序，第一个是0.8
        assert result["pass_rates"][0] == 0.8
        assert result["pass_rates"][1] == 0.9
        assert result["pass_rates"][2] == 1.0

    def test_trend_filtered_by_url(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.get_pass_rate_trend(url="about")

        assert result["count"] == 1
        assert result["pass_rates"][0] == 1.0

    def test_trend_with_limit(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.get_pass_rate_trend(limit=2)

        assert result["count"] == 2

    def test_trend_empty_store(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        store = MemoryStore(db_path=__import__("pathlib").Path(path))
        analytics = ReportAnalytics(store)
        result = analytics.get_pass_rate_trend()
        assert result["count"] == 0
        assert result["labels"] == []
        store._conn.close()
        os.unlink(path)

    def test_trend_has_all_fields(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.get_pass_rate_trend()
        for key in ["labels", "pass_rates", "total_steps", "bug_counts", "durations", "test_names"]:
            assert key in result
            assert len(result[key]) == result["count"]


class TestScreenshotTimeline:
    """截图时间线测试。"""

    def test_timeline_exists(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.get_screenshot_timeline(1)

        assert result["test_name"] == "测试-首页"
        assert len(result["steps"]) == 4
        assert result["steps"][0]["action"] == "navigate"
        assert result["steps"][3]["status"] == "failed"
        assert result["steps"][3]["error"] == "元素不存在"

    def test_timeline_not_found(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.get_screenshot_timeline(999)

        assert result["error"] == "记录不存在"
        assert result["steps"] == []

    def test_timeline_fields(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.get_screenshot_timeline(1)
        for key in ["test_name", "url", "pass_rate", "created_at", "steps"]:
            assert key in result


class TestBugHeatmap:
    """Bug热力图测试。"""

    def test_heatmap_all(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.get_bug_heatmap()

        assert result["total_bugs"] == 3
        # by_page: localhost:3000有3个bug
        assert len(result["by_page"]) >= 1
        assert result["by_page"][0]["url"] == "http://localhost:3000"
        assert result["by_page"][0]["count"] == 3

    def test_heatmap_by_severity(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.get_bug_heatmap()

        assert result["by_severity"]["major"] == 1
        assert result["by_severity"]["minor"] == 2

    def test_heatmap_by_category(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.get_bug_heatmap()

        categories = {c["category"]: c["count"] for c in result["by_category"]}
        assert categories["UI"] == 1
        assert categories["CSS"] == 2

    def test_heatmap_by_location(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.get_bug_heatmap()

        locations = {l["location"]: l["count"] for l in result["by_location"]}
        assert locations[".header"] == 2
        assert locations["#login-btn"] == 1

    def test_heatmap_filtered(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.get_bug_heatmap(url="about")

        assert result["total_bugs"] == 0


class TestCompareReports:
    """历史对比测试。"""

    def test_compare_two_reports(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.compare_reports(1, 2)

        assert result["summary"]["pass_rate_a"] == 0.8
        assert result["summary"]["pass_rate_b"] == 0.9
        assert result["summary"]["pass_rate_change"] == 0.1
        assert result["summary"]["bug_count_change"] == -1
        assert result["improved"] is True

    def test_compare_new_bugs(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.compare_reports(1, 2)

        # "登录按钮无响应" 在v2中不存在 → fixed
        fixed_titles = [b["title"] for b in result["fixed_bugs"]]
        assert "登录按钮无响应" in fixed_titles

        # "样式错位" 两次都有 → persistent
        persistent_titles = [b["title"] for b in result["persistent_bugs"]]
        assert "样式错位" in persistent_titles

        # 新增Bug应为空
        assert len(result["new_bugs"]) == 0

    def test_compare_not_found(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        result = analytics.compare_reports(1, 999)

        assert result["error"] == "记录不存在"


class TestExportHtml:
    """HTML报告导出测试。"""

    def test_export_html_basic(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        html = analytics.export_html_report(1)

        assert "<!DOCTYPE html>" in html
        assert "TestPilot AI" in html
        assert "测试-首页" in html
        assert "80.0%" in html
        assert "登录按钮无响应" in html

    def test_export_html_not_found(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        html = analytics.export_html_report(999)

        assert "报告不存在" in html

    def test_export_html_no_bugs(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        html = analytics.export_html_report(3)  # 关于页，0 bugs

        assert "未发现Bug" in html
        assert "100.0%" in html

    def test_export_html_contains_steps(self, store_with_data):
        store, _ = store_with_data
        analytics = ReportAnalytics(store)
        html = analytics.export_html_report(1)

        assert "navigate" in html
        assert "元素不存在" in html
