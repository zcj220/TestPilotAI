"""
测试脚本解析器的单元测试。

验证：
- JSON 提取（纯JSON、markdown包裹、混合文字）
- TestScript 解析（正常、缺字段、空步骤）
- 截图分析结果解析
- Bug 检测结果解析
"""

import pytest

from src.core.exceptions import TestScriptParseError
from src.testing.parser import (
    extract_json_from_text,
    parse_bug_detection,
    parse_screenshot_analysis,
    parse_test_script,
)


class TestExtractJson:
    """JSON 提取测试。"""

    def test_pure_json(self) -> None:
        """纯JSON文本应直接提取。"""
        text = '{"test_name": "hello", "steps": []}'
        result = extract_json_from_text(text)
        assert result.startswith("{")

    def test_markdown_code_block(self) -> None:
        """从markdown代码块中提取JSON。"""
        text = '这是AI的回答\n```json\n{"test_name": "t", "steps": []}\n```\n完成'
        result = extract_json_from_text(text)
        assert '"test_name"' in result

    def test_mixed_text_with_braces(self) -> None:
        """从混合文字中提取大括号之间的JSON。"""
        text = '好的，以下是测试脚本：\n{"test_name": "x", "steps": []}\n希望对你有帮助'
        result = extract_json_from_text(text)
        assert '"test_name"' in result

    def test_no_json_raises_error(self) -> None:
        """完全没有JSON内容应该抛出异常。"""
        with pytest.raises(TestScriptParseError):
            extract_json_from_text("这里完全没有JSON")


class TestParseTestScript:
    """测试脚本解析测试。"""

    def test_valid_script(self) -> None:
        """合法的测试脚本应该正确解析。"""
        json_str = '''{
            "test_name": "登录测试",
            "description": "测试登录功能",
            "steps": [
                {
                    "step": 1,
                    "action": "navigate",
                    "target": "http://localhost:3000",
                    "description": "打开首页",
                    "expected": "页面正常加载"
                },
                {
                    "step": 2,
                    "action": "click",
                    "target": "#login-btn",
                    "description": "点击登录",
                    "expected": "弹出登录框"
                }
            ]
        }'''
        script = parse_test_script(json_str)
        assert script.test_name == "登录测试"
        assert len(script.steps) == 2
        assert script.steps[0].action.value == "navigate"
        assert script.steps[1].action.value == "click"

    def test_missing_steps_raises_error(self) -> None:
        """缺少steps字段应该报错。"""
        with pytest.raises(TestScriptParseError):
            parse_test_script('{"test_name": "no steps"}')

    def test_empty_steps_raises_error(self) -> None:
        """空steps列表应该报错。"""
        with pytest.raises(TestScriptParseError):
            parse_test_script('{"test_name": "empty", "steps": []}')

    def test_auto_number_steps(self) -> None:
        """没有step编号的步骤应自动编号。"""
        json_str = '''{
            "test_name": "auto",
            "steps": [
                {"action": "navigate", "target": "http://example.com"},
                {"action": "click", "target": "#btn"}
            ]
        }'''
        script = parse_test_script(json_str)
        assert script.steps[0].step == 1
        assert script.steps[1].step == 2

    def test_invalid_json_raises_error(self) -> None:
        """无效JSON应该报错。"""
        with pytest.raises(TestScriptParseError):
            parse_test_script("这不是JSON {broken")


class TestParseScreenshotAnalysis:
    """截图分析结果解析测试。"""

    def test_valid_analysis(self) -> None:
        """合法的分析结果应正确解析。"""
        json_str = '''{
            "matches_expected": true,
            "confidence": 0.95,
            "page_description": "登录页面",
            "issues": [],
            "suggestions": ["可以添加忘记密码链接"]
        }'''
        result = parse_screenshot_analysis(json_str)
        assert result["matches_expected"] is True
        assert result["confidence"] == 0.95

    def test_non_json_returns_fallback(self) -> None:
        """非JSON文本应返回兜底结果。"""
        result = parse_screenshot_analysis("这是一段纯文字描述")
        assert result["matches_expected"] is True
        assert result["confidence"] == 0.5


class TestParseBugDetection:
    """Bug检测结果解析测试。"""

    def test_valid_bugs(self) -> None:
        """合法的Bug检测结果应正确解析。"""
        json_str = '''{
            "bugs_found": [
                {
                    "severity": "high",
                    "category": "功能缺陷",
                    "title": "按钮无响应",
                    "description": "点击后无反应"
                }
            ],
            "warnings": [],
            "overall_quality": "良好"
        }'''
        result = parse_bug_detection(json_str)
        assert len(result["bugs_found"]) == 1
        assert result["bugs_found"][0]["severity"] == "high"

    def test_invalid_returns_empty(self) -> None:
        """解析失败应返回空结果。"""
        result = parse_bug_detection("无效内容")
        assert result["bugs_found"] == []
