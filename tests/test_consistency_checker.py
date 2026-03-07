"""跨端状态一致性验证器测试（v9.0 Phase2）。"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.testing.consistency_checker import (
    ConsistencyChecker,
    ConsistencyReport,
    DiffItem,
    ScreenCapture,
)


# ── 数据类 ──

class TestScreenCapture:
    def test_defaults(self):
        sc = ScreenCapture(player_id="p1")
        assert sc.player_id == "p1"
        assert sc.path is None
        assert sc.hash == ""

    def test_with_data(self):
        sc = ScreenCapture(player_id="p2", hash="abc123", text_content="hello")
        assert sc.hash == "abc123"
        assert sc.text_content == "hello"


class TestDiffItem:
    def test_creation(self):
        d = DiffItem(
            field="page_source",
            player_a="p1", player_b="p2",
            value_a="a", value_b="b",
            severity="warning",
        )
        assert d.field == "page_source"
        assert d.severity == "warning"


class TestConsistencyReport:
    def test_consistent_report(self):
        r = ConsistencyReport(consistent=True, player_count=2, score=100.0)
        assert r.consistent
        assert r.diff_count == 0

    def test_with_diffs(self):
        diffs = [
            DiffItem(field="src", player_a="a", player_b="b", value_a="x", value_b="y"),
        ]
        r = ConsistencyReport(consistent=False, player_count=2, diffs=diffs, score=80.0)
        assert not r.consistent
        assert r.diff_count == 1

    def test_to_dict(self):
        diffs = [
            DiffItem(field="src", player_a="a", player_b="b", value_a="x", value_b="y"),
        ]
        r = ConsistencyReport(consistent=False, player_count=2, diffs=diffs, score=90.0)
        d = r.to_dict()
        assert d["consistent"] is False
        assert d["score"] == 90.0
        assert d["diff_count"] == 1
        assert len(d["diffs"]) == 1
        assert d["diffs"][0]["field"] == "src"


# ── ConsistencyChecker ──

class TestConsistencyChecker:
    def test_initial_state(self):
        cc = ConsistencyChecker()
        assert len(cc.reports) == 0

    @pytest.mark.asyncio
    async def test_check_single_player_always_consistent(self):
        """单端时总是一致的。"""
        cc = ConsistencyChecker()
        orch = MagicMock()
        orch.players = {"p1": MagicMock()}
        report = await cc.check(orch, player_ids=["p1"])
        assert report.consistent is True
        assert report.player_count == 1

    @pytest.mark.asyncio
    async def test_check_identical_sources(self):
        """两端源码完全相同。"""
        cc = ConsistencyChecker()

        ctrl_mock = MagicMock()
        ctrl_mock.get_page_source = AsyncMock(return_value="<html>same</html>")
        ctrl_mock.screenshot = AsyncMock(return_value="/tmp/shot.png")

        slot1 = MagicMock()
        slot1.controller = ctrl_mock
        slot2 = MagicMock()
        slot2.controller = ctrl_mock

        orch = MagicMock()
        orch.players = {"p1": slot1, "p2": slot2}
        orch.get_player = lambda pid: orch.players.get(pid)

        report = await cc.check(orch, player_ids=["p1", "p2"],
                                check_source=True, check_screenshot=False)
        assert report.consistent is True
        assert report.score >= 95

    @pytest.mark.asyncio
    async def test_check_different_sources(self):
        """两端源码不同应产生差异。"""
        cc = ConsistencyChecker()

        ctrl1 = MagicMock()
        ctrl1.get_page_source = AsyncMock(return_value="<html>page A content</html>")
        ctrl1.screenshot = AsyncMock(return_value="/tmp/a.png")

        ctrl2 = MagicMock()
        ctrl2.get_page_source = AsyncMock(return_value="<html>page B completely different</html>")
        ctrl2.screenshot = AsyncMock(return_value="/tmp/b.png")

        slot1 = MagicMock()
        slot1.controller = ctrl1
        slot2 = MagicMock()
        slot2.controller = ctrl2

        orch = MagicMock()
        orch.players = {"p1": slot1, "p2": slot2}
        orch.get_player = lambda pid: orch.players.get(pid)

        report = await cc.check(orch, player_ids=["p1", "p2"],
                                check_source=True, check_screenshot=False)
        assert not report.consistent
        assert report.diff_count > 0

    def test_compare_text_content_same(self):
        cc = ConsistencyChecker()
        diffs = cc.compare_text_content({"p1": "hello", "p2": "hello"})
        assert len(diffs) == 0

    def test_compare_text_content_different(self):
        cc = ConsistencyChecker()
        diffs = cc.compare_text_content({"p1": "hello", "p2": "world"})
        assert len(diffs) == 1
        assert diffs[0].field == "text_content"

    def test_compare_text_content_three_players(self):
        cc = ConsistencyChecker()
        diffs = cc.compare_text_content({"p1": "a", "p2": "b", "p3": "a"})
        # p1!=p2, p2!=p3, p1==p3 → 2 个差异
        assert len(diffs) == 2

    def test_find_text_diff_same(self):
        cc = ConsistencyChecker()
        result = cc._find_text_diff("hello world", "hello world")
        assert result["similarity"] == 1.0

    def test_find_text_diff_empty(self):
        cc = ConsistencyChecker()
        result = cc._find_text_diff("", "hello")
        assert result["similarity"] == 0

    def test_find_text_diff_partial(self):
        cc = ConsistencyChecker()
        result = cc._find_text_diff("a b c d", "a b e f")
        assert 0 < result["similarity"] < 1.0

    def test_calculate_score_no_diffs(self):
        cc = ConsistencyChecker()
        caps = [ScreenCapture(player_id="p1", hash="abc"),
                ScreenCapture(player_id="p2", hash="abc")]
        score = cc._calculate_score(caps, [])
        assert score >= 95

    def test_calculate_score_with_critical(self):
        cc = ConsistencyChecker()
        caps = [ScreenCapture(player_id="p1"), ScreenCapture(player_id="p2")]
        diffs = [DiffItem(field="x", player_a="p1", player_b="p2",
                          value_a="a", value_b="b", severity="critical")]
        score = cc._calculate_score(caps, diffs)
        assert score == 80.0

    def test_calculate_score_with_warning(self):
        cc = ConsistencyChecker()
        caps = [ScreenCapture(player_id="p1"), ScreenCapture(player_id="p2")]
        diffs = [DiffItem(field="x", player_a="p1", player_b="p2",
                          value_a="a", value_b="b", severity="warning")]
        score = cc._calculate_score(caps, diffs)
        assert score == 90.0

    def test_calculate_score_clamp(self):
        cc = ConsistencyChecker()
        caps = [ScreenCapture(player_id="p1"), ScreenCapture(player_id="p2")]
        # 6个critical = -120, 应clamp到0
        diffs = [DiffItem(field="x", player_a="p1", player_b="p2",
                          value_a="a", value_b="b", severity="critical") for _ in range(6)]
        score = cc._calculate_score(caps, diffs)
        assert score == 0

    def test_get_summary_empty(self):
        cc = ConsistencyChecker()
        s = cc.get_summary()
        assert s["total_checks"] == 0
        assert s["consistency_rate"] == 0.0

    def test_get_summary_with_reports(self):
        cc = ConsistencyChecker()
        cc.reports.append(ConsistencyReport(consistent=True, player_count=2, score=100))
        cc.reports.append(ConsistencyReport(consistent=False, player_count=2, score=60))
        s = cc.get_summary()
        assert s["total_checks"] == 2
        assert s["consistent_count"] == 1
        assert s["avg_score"] == 80.0
