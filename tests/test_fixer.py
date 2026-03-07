"""
AI 代码修复引擎的单元测试
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.core.exceptions import RepairAnalysisError
from src.repair.fixer import CodeFixer, MAX_FILE_CHARS, SOURCE_EXTENSIONS
from src.repair.models import FixPlan, RiskLevel
from src.testing.models import BugReport, BugSeverity, StepResult, StepStatus, ActionType


@pytest.fixture
def mock_ai():
    """创建 mock AI 客户端。"""
    return MagicMock()


@pytest.fixture
def tmp_project(tmp_path):
    """创建临时项目目录。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text(
        'function hello() { return "world"; }',
        encoding="utf-8",
    )
    (tmp_path / "src" / "index.html").write_text(
        '<html><body>Hello</body></html>',
        encoding="utf-8",
    )
    # 不应被扫描的文件
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("excluded", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    return tmp_path


def _make_bug(
    title="测试Bug",
    severity=BugSeverity.MEDIUM,
    category="功能缺陷",
) -> BugReport:
    return BugReport(
        severity=severity,
        title=title,
        category=category,
        description="按钮不响应",
        location="页面中央",
        reproduction="1. 点击按钮",
    )


class TestClassifyBug:
    """Bug 分类测试。"""

    def test_critical_is_blocking(self, mock_ai, tmp_path):
        fixer = CodeFixer(mock_ai, str(tmp_path))
        bug = _make_bug(severity=BugSeverity.CRITICAL)
        assert fixer.classify_bug(bug) is True

    def test_low_is_not_blocking(self, mock_ai, tmp_path):
        fixer = CodeFixer(mock_ai, str(tmp_path))
        bug = _make_bug(severity=BugSeverity.LOW)
        assert fixer.classify_bug(bug) is False

    def test_error_step_is_blocking(self, mock_ai, tmp_path):
        fixer = CodeFixer(mock_ai, str(tmp_path))
        bug = _make_bug(severity=BugSeverity.MEDIUM)
        step = StepResult(step=1, action=ActionType.CLICK, status=StepStatus.ERROR)
        assert fixer.classify_bug(bug, step) is True

    def test_medium_calls_ai(self, mock_ai, tmp_path):
        """medium 严重度、非error步骤时应调用 AI 分类。"""
        fixer = CodeFixer(mock_ai, str(tmp_path))
        mock_ai.chat.return_value = '{"is_blocking": false, "reason": "样式问题"}'
        bug = _make_bug(severity=BugSeverity.MEDIUM)
        step = StepResult(step=1, action=ActionType.CLICK, status=StepStatus.FAILED)
        result = fixer.classify_bug(bug, step)
        assert result is False
        mock_ai.chat.assert_called_once()

    def test_ai_classify_fallback_on_error(self, mock_ai, tmp_path):
        """AI 分类失败时，high 严重度回退为阻塞。"""
        fixer = CodeFixer(mock_ai, str(tmp_path))
        mock_ai.chat.side_effect = Exception("API错误")
        bug = _make_bug(severity=BugSeverity.HIGH)
        step = StepResult(step=1, action=ActionType.CLICK, status=StepStatus.FAILED)
        assert fixer.classify_bug(bug, step) is True


class TestGenerateFix:
    """修复方案生成测试。"""

    def test_generate_fix_success(self, mock_ai, tmp_project):
        fixer = CodeFixer(mock_ai, str(tmp_project))
        mock_ai.chat.return_value = json.dumps({
            "analysis": "变量名拼写错误",
            "can_fix": True,
            "confidence": 0.9,
            "patches": [
                {
                    "file_path": "src/app.js",
                    "description": "修复拼写",
                    "old_code": "hello",
                    "new_code": "greet",
                }
            ],
            "explanation": "修正函数名",
            "risk_level": "low",
        })

        bug = _make_bug()
        plan = fixer.generate_fix(bug)
        assert plan.can_fix is True
        assert plan.confidence == 0.9
        assert len(plan.patches) == 1
        assert plan.patches[0].file_path == "src/app.js"
        assert plan.risk_level == RiskLevel.LOW

    def test_generate_fix_no_source_files(self, mock_ai, tmp_path):
        """空项目目录应返回 can_fix=False。"""
        fixer = CodeFixer(mock_ai, str(tmp_path))
        bug = _make_bug()
        plan = fixer.generate_fix(bug)
        assert plan.can_fix is False
        mock_ai.chat.assert_not_called()

    def test_generate_fix_ai_cannot_fix(self, mock_ai, tmp_project):
        fixer = CodeFixer(mock_ai, str(tmp_project))
        mock_ai.chat.return_value = json.dumps({
            "analysis": "需要大规模重构",
            "can_fix": False,
            "confidence": 0.2,
            "patches": [],
            "explanation": "问题复杂度超出自动修复范围",
            "risk_level": "high",
        })

        bug = _make_bug()
        plan = fixer.generate_fix(bug)
        assert plan.can_fix is False
        assert len(plan.patches) == 0

    def test_generate_fix_ai_error(self, mock_ai, tmp_project):
        fixer = CodeFixer(mock_ai, str(tmp_project))
        mock_ai.chat.side_effect = Exception("API超时")
        bug = _make_bug()
        with pytest.raises(RepairAnalysisError):
            fixer.generate_fix(bug)


class TestCollectSourceFiles:
    """源码收集测试。"""

    def test_collect_skips_excluded_dirs(self, mock_ai, tmp_project):
        fixer = CodeFixer(mock_ai, str(tmp_project))
        context = fixer._collect_source_files()
        assert "node_modules" not in context
        assert "excluded" not in context

    def test_collect_skips_non_source_files(self, mock_ai, tmp_project):
        fixer = CodeFixer(mock_ai, str(tmp_project))
        context = fixer._collect_source_files()
        assert "PNG" not in context

    def test_collect_includes_source_files(self, mock_ai, tmp_project):
        fixer = CodeFixer(mock_ai, str(tmp_project))
        context = fixer._collect_source_files()
        assert "app.js" in context
        assert "index.html" in context
        assert "hello" in context

    def test_collect_empty_project(self, mock_ai, tmp_path):
        fixer = CodeFixer(mock_ai, str(tmp_path))
        context = fixer._collect_source_files()
        assert context == ""
