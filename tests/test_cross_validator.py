"""
交叉验证引擎的单元测试。

验证：
- 分析结果聚合逻辑（投票、置信度、issues合并）
- 单次分析和多次分析的结果差异
"""

from src.testing.cross_validator import CrossValidator
from src.testing.models import ScreenshotAnalysis


class TestAggregateAnalyses:
    """聚合逻辑测试（不需要AI客户端）。"""

    def test_single_analysis_passthrough(self) -> None:
        """单次分析应直接返回。"""
        a = ScreenshotAnalysis(
            matches_expected=True, confidence=0.9,
            page_description="ok", issues=[], suggestions=[],
        )
        result = CrossValidator._aggregate_analyses([a])
        assert result.matches_expected is True
        assert result.confidence == 0.9

    def test_majority_vote_pass(self) -> None:
        """多数通过时应标记为通过。"""
        analyses = [
            ScreenshotAnalysis(matches_expected=True, confidence=0.9),
            ScreenshotAnalysis(matches_expected=True, confidence=0.8),
            ScreenshotAnalysis(matches_expected=False, confidence=0.6),
        ]
        result = CrossValidator._aggregate_analyses(analyses)
        assert result.matches_expected is True

    def test_majority_vote_fail(self) -> None:
        """多数失败时应标记为失败。"""
        analyses = [
            ScreenshotAnalysis(matches_expected=False, confidence=0.8),
            ScreenshotAnalysis(matches_expected=False, confidence=0.7),
            ScreenshotAnalysis(matches_expected=True, confidence=0.5),
        ]
        result = CrossValidator._aggregate_analyses(analyses)
        assert result.matches_expected is False

    def test_confidence_average(self) -> None:
        """置信度应取平均值。"""
        analyses = [
            ScreenshotAnalysis(matches_expected=True, confidence=0.8),
            ScreenshotAnalysis(matches_expected=True, confidence=0.6),
        ]
        result = CrossValidator._aggregate_analyses(analyses)
        assert abs(result.confidence - 0.7) < 0.01

    def test_issues_dedup_for_many_rounds(self) -> None:
        """多轮分析时，只保留出现多次的issue。"""
        analyses = [
            ScreenshotAnalysis(matches_expected=False, confidence=0.5,
                              issues=["button missing", "rare glitch"]),
            ScreenshotAnalysis(matches_expected=False, confidence=0.6,
                              issues=["button missing"]),
            ScreenshotAnalysis(matches_expected=False, confidence=0.4,
                              issues=["button missing", "color wrong"]),
        ]
        result = CrossValidator._aggregate_analyses(analyses)
        # "button missing" appears 3 times -> kept
        # "rare glitch" appears 1 time -> filtered
        # "color wrong" appears 1 time -> filtered
        assert "button missing" in result.issues
        assert "rare glitch" not in result.issues

    def test_issues_kept_for_two_rounds(self) -> None:
        """两轮分析时，所有issues都保留（因为样本太少不做过滤）。"""
        analyses = [
            ScreenshotAnalysis(matches_expected=False, confidence=0.5,
                              issues=["issue A"]),
            ScreenshotAnalysis(matches_expected=False, confidence=0.5,
                              issues=["issue B"]),
        ]
        result = CrossValidator._aggregate_analyses(analyses)
        assert "issue A" in result.issues
        assert "issue B" in result.issues

    def test_suggestions_merged_no_dup(self) -> None:
        """建议应合并去重。"""
        analyses = [
            ScreenshotAnalysis(matches_expected=True, confidence=0.9,
                              suggestions=["add tooltip"]),
            ScreenshotAnalysis(matches_expected=True, confidence=0.8,
                              suggestions=["add tooltip", "bigger font"]),
        ]
        result = CrossValidator._aggregate_analyses(analyses)
        assert len(result.suggestions) == 2

    def test_best_description_used(self) -> None:
        """应使用置信度最高的描述。"""
        analyses = [
            ScreenshotAnalysis(matches_expected=True, confidence=0.5,
                              page_description="bad desc"),
            ScreenshotAnalysis(matches_expected=True, confidence=0.95,
                              page_description="best desc"),
            ScreenshotAnalysis(matches_expected=True, confidence=0.7,
                              page_description="ok desc"),
        ]
        result = CrossValidator._aggregate_analyses(analyses)
        assert result.page_description == "best desc"
