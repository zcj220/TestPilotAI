"""
蓝本自动生成器（v10.1）单元测试
"""

import json
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src.testing.blueprint import Blueprint
from src.testing.blueprint_generator import BlueprintGenerator


# ── 样例数据 ──

SAMPLE_BLUEPRINT_JSON = json.dumps({
    "app_name": "测试商店",
    "base_url": "http://localhost:3000",
    "version": "1.0",
    "pages": [
        {
            "url": "/",
            "title": "首页",
            "elements": {"购买按钮": "#buy-btn"},
            "scenarios": [
                {
                    "name": "基本浏览",
                    "steps": [
                        {"action": "navigate", "value": "http://localhost:3000"},
                        {"action": "click", "target": "#buy-btn"},
                        {"action": "screenshot", "expected": "商品加入购物车"},
                    ],
                }
            ],
        }
    ],
}, ensure_ascii=False)


# ── JSON 提取测试 ──


class TestExtractJson:
    """测试从 AI 回复中提取 JSON。"""

    def test_plain_json(self):
        raw = '{"app_name": "App", "base_url": "/"}'
        result = BlueprintGenerator._extract_json(raw)
        assert json.loads(result)["app_name"] == "App"

    def test_json_in_code_fence(self):
        raw = '```json\n{"app_name": "App"}\n```'
        result = BlueprintGenerator._extract_json(raw)
        assert json.loads(result)["app_name"] == "App"

    def test_json_in_plain_fence(self):
        raw = '```\n{"key": "value"}\n```'
        result = BlueprintGenerator._extract_json(raw)
        assert json.loads(result)["key"] == "value"

    def test_json_with_surrounding_text(self):
        raw = '好的，这是蓝本：\n{"app_name": "X"}\n请检查。'
        result = BlueprintGenerator._extract_json(raw)
        assert json.loads(result)["app_name"] == "X"

    def test_nested_braces(self):
        raw = '{"a": {"b": {"c": 1}}, "d": 2}'
        result = BlueprintGenerator._extract_json(raw)
        data = json.loads(result)
        assert data["a"]["b"]["c"] == 1
        assert data["d"] == 2

    def test_no_json_returns_stripped(self):
        raw = "  no json here  "
        result = BlueprintGenerator._extract_json(raw)
        assert result == "no json here"


# ── 元素/文本格式化测试 ──


class TestFormatHelpers:

    def setup_method(self):
        self.gen = BlueprintGenerator(ai_client=None)

    def test_format_elements_normal(self):
        elements = [
            {"tag": "button", "selector": "#buy",
             "text": "购买", "placeholder": "", "type": ""},
            {"tag": "input", "selector": "#search",
             "text": "", "placeholder": "搜索...", "type": "text"},
        ]
        result = self.gen._format_elements(elements)
        assert "#buy" in result
        assert "购买" in result
        assert "#search" in result
        assert "搜索..." in result

    def test_format_elements_empty(self):
        assert "无" in self.gen._format_elements([])

    def test_format_elements_with_select_options(self):
        elements = [{
            "tag": "select", "selector": "#color",
            "text": "", "placeholder": "", "type": "",
            "hasOptions": [
                {"value": "red", "text": "红"},
                {"value": "blue", "text": "蓝"},
            ],
        }]
        result = self.gen._format_elements(elements)
        assert "红" in result
        assert "蓝" in result

    def test_format_texts_normal(self):
        texts = [
            {"selector": "h1", "text": "欢迎"},
            {"selector": ".price", "text": "¥99"},
        ]
        result = self.gen._format_texts(texts)
        assert "欢迎" in result
        assert "¥99" in result

    def test_format_texts_empty(self):
        assert "无" in self.gen._format_texts([])


# ── AI 响应解析测试 ──


class TestParseAiResponse:

    def setup_method(self):
        self.gen = BlueprintGenerator(ai_client=None)

    def test_valid_json_response(self):
        bp = self.gen._parse_ai_response(
            SAMPLE_BLUEPRINT_JSON,
            "http://localhost:3000", "测试商店",
        )
        assert bp.app_name == "测试商店"
        assert bp.total_scenarios == 1
        assert bp.total_steps == 3

    def test_json_in_markdown_fence(self):
        raw = f"```json\n{SAMPLE_BLUEPRINT_JSON}\n```"
        bp = self.gen._parse_ai_response(
            raw, "http://localhost:3000", "测试商店",
        )
        assert bp.app_name == "测试商店"
        assert len(bp.pages) == 1

    def test_invalid_json_returns_empty_blueprint(self):
        bp = self.gen._parse_ai_response(
            "这不是JSON", "http://localhost:3000", "App",
        )
        assert bp.app_name == "App"
        assert bp.total_scenarios == 0

    def test_missing_app_name_uses_fallback(self):
        raw = json.dumps({"base_url": "/", "pages": []})
        bp = self.gen._parse_ai_response(raw, "/", "我的应用")
        assert bp.app_name == "我的应用"


# ── from_html 集成测试（mock AI）──


class TestFromHtml:

    @pytest.mark.asyncio
    async def test_from_html_calls_ai_and_returns_blueprint(self):
        mock_ai = MagicMock()
        mock_ai.chat.return_value = SAMPLE_BLUEPRINT_JSON

        gen = BlueprintGenerator(ai_client=mock_ai)
        bp = await gen.from_html(
            "<body><button id='buy-btn'>购买</button></body>",
            base_url="http://localhost:3000",
            app_name="测试商店",
        )

        assert bp.app_name == "测试商店"
        assert bp.total_scenarios >= 1
        mock_ai.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_from_html_with_bad_ai_response(self):
        mock_ai = MagicMock()
        mock_ai.chat.return_value = "抱歉，我无法生成"

        gen = BlueprintGenerator(ai_client=mock_ai)
        bp = await gen.from_html("<body></body>", app_name="App")

        assert bp.app_name == "App"
        assert bp.total_scenarios == 0


# ── from_url 集成测试（mock 浏览器 + AI）──


class TestFromUrl:

    @pytest.mark.asyncio
    async def test_from_url_full_flow(self):
        mock_ai = MagicMock()
        # from_url 有截图 → 走 analyze_screenshot 分支
        mock_ai.analyze_screenshot.return_value = SAMPLE_BLUEPRINT_JSON

        gen = BlueprintGenerator(ai_client=mock_ai)

        # mock 浏览器上下文
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=[
            # 第一次：EXTRACT_PAGE_INFO_JS
            {"elements": [], "texts": [], "links": [],
             "title": "测试商店"},
            # 第二次：_get_clean_html
            "<div>hello</div>",
        ])

        mock_browser = AsyncMock()
        mock_browser.navigate = AsyncMock()
        mock_browser.screenshot = AsyncMock(
            return_value="screenshots/test.png",
        )
        mock_browser.page = mock_page

        with patch(
            "src.testing.blueprint_generator.BrowserAutomator"
        ) as MockBA, patch(
            "src.testing.blueprint_generator.Path"
        ) as MockPath:
            # BrowserAutomator 作为异步上下文管理器
            MockBA.return_value.__aenter__ = AsyncMock(
                return_value=mock_browser,
            )
            MockBA.return_value.__aexit__ = AsyncMock(
                return_value=False,
            )
            # 截图文件读取
            mock_path_inst = MagicMock()
            mock_path_inst.read_bytes.return_value = b"\x89PNG_FAKE"
            MockPath.return_value = mock_path_inst
            # unlink for temp file
            mock_path_inst.unlink = MagicMock()

            bp = await gen.from_url(
                "http://localhost:3000",
                app_name="测试商店",
            )

        assert bp.app_name == "测试商店"

    @pytest.mark.asyncio
    async def test_without_ai_client_raises(self):
        gen = BlueprintGenerator(ai_client=None)
        with pytest.raises(RuntimeError, match="需要 AIClient"):
            await gen.from_html("<body></body>")

