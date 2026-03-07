"""
快速探索器的单元测试。

验证：
- ExploreAction 数据结构
- PageExplorer 配置
- AI Bug 解析逻辑
"""

from src.testing.explorer import ExploreAction, PageExplorer


class TestExploreAction:
    """探索操作数据结构测试。"""

    def test_create_action(self) -> None:
        a = ExploreAction(
            step=1, action="click", target="#btn",
            description="点击按钮",
        )
        assert a.step == 1
        assert a.action == "click"
        assert a.screenshot_path == ""
        assert a.error == ""

    def test_action_with_error(self) -> None:
        a = ExploreAction(
            step=2, action="fill", target="#input",
            description="填写", error="元素不存在",
        )
        assert a.error == "元素不存在"


class TestPageExplorerConfig:
    """探索器配置测试（不需要浏览器）。"""

    def test_interactive_selectors_not_empty(self) -> None:
        assert len(PageExplorer.INTERACTIVE_SELECTORS) > 0

    def test_default_inputs_has_common_types(self) -> None:
        assert "email" in PageExplorer.DEFAULT_INPUTS
        assert "password" in PageExplorer.DEFAULT_INPUTS
        assert "number" in PageExplorer.DEFAULT_INPUTS

    def test_max_actions_positive(self) -> None:
        assert PageExplorer.MAX_ACTIONS > 0


class TestParseAiBugs:
    """AI Bug解析测试（不需要AI客户端）。"""

    def _make_explorer(self) -> PageExplorer:
        """创建无依赖的Explorer用于测试解析方法。"""
        return PageExplorer(browser=None, ai_client=None)  # type: ignore

    def test_parse_valid_bugs(self) -> None:
        explorer = self._make_explorer()
        response = '{"bugs": [{"title": "按钮无响应", "severity": "high", "description": "点击后无反应"}]}'
        bugs = explorer._parse_ai_bugs(response, "http://test.com")
        assert len(bugs) == 1
        assert bugs[0].title == "按钮无响应"
        assert bugs[0].severity.value == "high"

    def test_parse_no_bugs(self) -> None:
        explorer = self._make_explorer()
        response = '{"bugs": []}'
        bugs = explorer._parse_ai_bugs(response, "http://test.com")
        assert len(bugs) == 0

    def test_parse_invalid_json(self) -> None:
        explorer = self._make_explorer()
        response = "这不是JSON"
        bugs = explorer._parse_ai_bugs(response, "http://test.com")
        assert len(bugs) == 0

    def test_parse_markdown_wrapped(self) -> None:
        explorer = self._make_explorer()
        response = '一些说明文字\n```json\n{"bugs": [{"title": "布局错乱", "severity": "medium", "description": "元素重叠"}]}\n```'
        bugs = explorer._parse_ai_bugs(response, "http://test.com")
        assert len(bugs) == 1

    def test_parse_missing_title_skipped(self) -> None:
        explorer = self._make_explorer()
        response = '{"bugs": [{"title": "", "severity": "low", "description": "空标题应跳过"}, {"title": "有效Bug", "severity": "low", "description": "ok"}]}'
        bugs = explorer._parse_ai_bugs(response, "http://test.com")
        assert len(bugs) == 1
        assert bugs[0].title == "有效Bug"
