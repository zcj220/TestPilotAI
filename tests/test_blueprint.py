"""
蓝本模式的单元测试：数据模型、解析器、验证器
"""

import json
import tempfile
import os

import pytest

from src.testing.blueprint import (
    Blueprint,
    BlueprintPage,
    BlueprintParser,
    BlueprintScenario,
    BlueprintStep,
)


# ── 样例蓝本数据 ──

SAMPLE_BLUEPRINT = {
    "app_name": "测试应用",
    "base_url": "http://localhost:3000",
    "version": "1.0",
    "pages": [
        {
            "url": "/",
            "title": "首页",
            "elements": {
                "输入框": "#input",
                "按钮": "#btn",
            },
            "scenarios": [
                {
                    "name": "基本功能",
                    "steps": [
                        {"action": "navigate", "value": "http://localhost:3000"},
                        {"action": "fill", "target": "#input", "value": "hello"},
                        {"action": "click", "target": "#btn"},
                        {"action": "screenshot", "expected": "页面显示hello"},
                    ],
                }
            ],
        }
    ],
}


class TestBlueprintStep:
    """蓝本步骤模型测试。"""

    def test_navigate_step(self):
        step = BlueprintStep(action="navigate", value="http://localhost:3000")
        assert step.action == "navigate"
        assert step.target is None

    def test_fill_step(self):
        step = BlueprintStep(action="fill", target="#input", value="hello")
        assert step.action == "fill"
        assert step.target == "#input"
        assert step.value == "hello"

    def test_click_step(self):
        step = BlueprintStep(action="click", target=".btn")
        assert step.action == "click"
        assert step.target == ".btn"

    def test_screenshot_step(self):
        step = BlueprintStep(action="screenshot", expected="看到标题")
        assert step.expected == "看到标题"

    def test_default_values(self):
        step = BlueprintStep(action="click", target="#x")
        assert step.value is None
        assert step.expected is None
        assert step.timeout_ms is None
        assert step.description is None


class TestBlueprintScenario:
    """蓝本场景模型测试。"""

    def test_basic_scenario(self):
        s = BlueprintScenario(
            name="登录测试",
            steps=[BlueprintStep(action="navigate", value="/login")],
        )
        assert s.name == "登录测试"
        assert len(s.steps) == 1

    def test_empty_steps(self):
        s = BlueprintScenario(name="空场景")
        assert len(s.steps) == 0


class TestBlueprintPage:
    """蓝本页面模型测试。"""

    def test_page_with_elements(self):
        p = BlueprintPage(
            url="/",
            title="首页",
            elements={"输入框": "#input", "按钮": "#btn"},
        )
        assert p.elements["输入框"] == "#input"
        assert len(p.elements) == 2

    def test_page_without_title(self):
        p = BlueprintPage(url="/about")
        assert p.title is None
        assert p.elements == {}


class TestBlueprint:
    """蓝本顶层模型测试。"""

    def test_from_dict(self):
        bp = Blueprint(**SAMPLE_BLUEPRINT)
        assert bp.app_name == "测试应用"
        assert bp.base_url == "http://localhost:3000"
        assert len(bp.pages) == 1
        assert bp.total_scenarios == 1
        assert bp.total_steps == 4

    def test_global_elements(self):
        bp = Blueprint(
            app_name="App",
            global_elements={"导航栏": "nav.main"},
        )
        assert bp.global_elements["导航栏"] == "nav.main"

    def test_empty_blueprint(self):
        bp = Blueprint(app_name="空应用")
        assert bp.total_scenarios == 0
        assert bp.total_steps == 0

    def test_default_platform_is_web(self):
        bp = Blueprint(app_name="App")
        assert bp.platform == "web"
        assert bp.permissions == []
        assert bp.app_package == ""
        assert bp.app_activity == ""

    def test_android_blueprint_with_permissions(self):
        bp = Blueprint(
            app_name="手机应用",
            platform="android",
            app_package="com.example.app",
            app_activity=".MainActivity",
            permissions=[
                "android.permission.CAMERA",
                "android.permission.ACCESS_FINE_LOCATION",
            ],
        )
        assert bp.platform == "android"
        assert bp.app_package == "com.example.app"
        assert bp.app_activity == ".MainActivity"
        assert len(bp.permissions) == 2
        assert "android.permission.CAMERA" in bp.permissions

    def test_android_blueprint_from_dict(self):
        data = {
            "app_name": "手机测试",
            "platform": "android",
            "app_package": "com.test.app",
            "permissions": ["CAMERA", "WRITE_EXTERNAL_STORAGE"],
            "pages": [{"url": "com.test.app/.Main", "scenarios": [
                {"name": "启动", "steps": [{"action": "screenshot"}]}
            ]}],
        }
        bp = BlueprintParser.parse_dict(data)
        assert bp.platform == "android"
        assert bp.app_package == "com.test.app"
        assert len(bp.permissions) == 2

    def test_web_blueprint_ignores_mobile_fields(self):
        bp = Blueprint(**SAMPLE_BLUEPRINT)
        assert bp.platform == "web"
        assert bp.permissions == []
        assert bp.app_package == ""


class TestBlueprintParser:
    """蓝本解析器测试。"""

    def test_parse_file(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(SAMPLE_BLUEPRINT, f)
            bp = BlueprintParser.parse_file(path)
            assert bp.app_name == "测试应用"
            assert bp.total_steps == 4
        finally:
            os.unlink(path)

    def test_parse_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            BlueprintParser.parse_file("/nonexistent/file.json")

    def test_parse_invalid_json(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            with open(path, "w") as f:
                f.write("not json {{{")
            with pytest.raises(ValueError, match="JSON格式错误"):
                BlueprintParser.parse_file(path)
        finally:
            os.unlink(path)

    def test_parse_dict(self):
        bp = BlueprintParser.parse_dict(SAMPLE_BLUEPRINT)
        assert bp.app_name == "测试应用"

    def test_parse_invalid_dict(self):
        with pytest.raises(ValueError, match="蓝本结构无效"):
            BlueprintParser.parse_dict({"invalid": True})


class TestBlueprintValidation:
    """蓝本验证测试。"""

    def test_valid_blueprint(self):
        bp = Blueprint(**SAMPLE_BLUEPRINT)
        issues = BlueprintParser.validate(bp)
        assert issues == []

    def test_missing_app_name(self):
        bp = Blueprint(app_name="", pages=[])
        issues = BlueprintParser.validate(bp)
        assert any("app_name" in i for i in issues)

    def test_missing_pages(self):
        bp = Blueprint(app_name="App")
        issues = BlueprintParser.validate(bp)
        assert any("pages" in i for i in issues)

    def test_missing_scenario_steps(self):
        bp = Blueprint(
            app_name="App",
            pages=[
                BlueprintPage(
                    url="/",
                    scenarios=[BlueprintScenario(name="空场景")],
                )
            ],
        )
        issues = BlueprintParser.validate(bp)
        assert any("没有步骤" in i for i in issues)

    def test_unknown_action(self):
        bp = Blueprint(
            app_name="App",
            pages=[
                BlueprintPage(
                    url="/",
                    scenarios=[
                        BlueprintScenario(
                            name="测试",
                            steps=[BlueprintStep(action="fly", target="#x")],
                        )
                    ],
                )
            ],
        )
        issues = BlueprintParser.validate(bp)
        assert any("未知操作类型" in i for i in issues)

    def test_fill_without_value(self):
        bp = Blueprint(
            app_name="App",
            pages=[
                BlueprintPage(
                    url="/",
                    scenarios=[
                        BlueprintScenario(
                            name="测试",
                            steps=[BlueprintStep(action="fill", target="#x")],
                        )
                    ],
                )
            ],
        )
        issues = BlueprintParser.validate(bp)
        assert any("value" in i for i in issues)

    def test_click_without_target(self):
        bp = Blueprint(
            app_name="App",
            pages=[
                BlueprintPage(
                    url="/",
                    scenarios=[
                        BlueprintScenario(
                            name="测试",
                            steps=[BlueprintStep(action="click")],
                        )
                    ],
                )
            ],
        )
        issues = BlueprintParser.validate(bp)
        assert any("target" in i for i in issues)

    def test_navigate_no_target_ok(self):
        """navigate 不需要 target，只需要 value。"""
        bp = Blueprint(
            app_name="App",
            pages=[
                BlueprintPage(
                    url="/",
                    scenarios=[
                        BlueprintScenario(
                            name="测试",
                            steps=[BlueprintStep(action="navigate", value="http://x")],
                        )
                    ],
                )
            ],
        )
        issues = BlueprintParser.validate(bp)
        assert issues == []
