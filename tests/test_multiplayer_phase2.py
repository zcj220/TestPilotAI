"""
多端协同测试 Phase2 测试（v9.0）

覆盖：AIPlayerEngine、ActionRecorder、ActionReplayer、ConsistencyChecker
"""

import asyncio
import json
import time
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.testing.ai_player import (
    AIStrategy, AIAction, AIPlayerConfig, AIPlayerEngine,
)
from src.testing.action_recorder import (
    RecordedAction, ActionRecorder, ActionReplayer,
)
from src.testing.consistency_checker import (
    ScreenCapture, DiffItem, ConsistencyReport, ConsistencyChecker,
)
from src.testing.multiplayer import MultiPlayerOrchestrator


# ── AI Models ───────────────────────────────────

class TestAIModels:
    def test_strategy_values(self):
        assert AIStrategy.RANDOM == "random"
        assert AIStrategy.BOUNDARY == "boundary"

    def test_ai_action(self):
        a = AIAction(action="tap", params={"selector": ".btn"}, reason="test", confidence=0.8)
        assert a.action == "tap"
        assert a.confidence == 0.8

    def test_config_defaults(self):
        cfg = AIPlayerConfig()
        assert cfg.strategy == AIStrategy.NORMAL
        assert cfg.max_actions == 50


# ── AIPlayerEngine ──────────────────────────────

class TestAIPlayerEngine:
    def test_init(self):
        engine = AIPlayerEngine()
        assert not engine.is_running
        assert engine.action_count == 0

    @pytest.mark.asyncio
    async def test_analyze_empty_source(self):
        engine = AIPlayerEngine()
        action = await engine.analyze_screen("")
        assert action.action == "wait"

    @pytest.mark.asyncio
    async def test_analyze_with_button(self):
        engine = AIPlayerEngine()
        source = '<button class="submit-btn">Submit</button>'
        action = await engine.analyze_screen(source)
        assert action.action in ("tap", "input")

    @pytest.mark.asyncio
    async def test_analyze_random_strategy(self):
        engine = AIPlayerEngine(AIPlayerConfig(strategy=AIStrategy.RANDOM))
        source = '<button class="a">A</button><input class="b" />'
        action = await engine.analyze_screen(source, AIStrategy.RANDOM)
        assert action.action in ("tap", "input")

    @pytest.mark.asyncio
    async def test_analyze_boundary_input(self):
        engine = AIPlayerEngine(AIPlayerConfig(strategy=AIStrategy.BOUNDARY))
        source = '<input class="name-field" />'
        action = await engine.analyze_screen(source, AIStrategy.BOUNDARY)
        assert action.action == "input"

    @pytest.mark.asyncio
    async def test_analyze_boundary_no_input(self):
        engine = AIPlayerEngine()
        source = '<button class="ok-btn">OK</button>'
        action = await engine.analyze_screen(source, AIStrategy.BOUNDARY)
        assert action.action == "tap"

    @pytest.mark.asyncio
    async def test_analyze_explorer(self):
        engine = AIPlayerEngine()
        source = '<button class="x">X</button><button class="y">Y</button>'
        a1 = await engine.analyze_screen(source, AIStrategy.EXPLORER)
        engine.action_history.append(a1)
        a2 = await engine.analyze_screen(source, AIStrategy.EXPLORER)
        assert a2.action == "tap"

    @pytest.mark.asyncio
    async def test_analyze_explorer_all_visited(self):
        engine = AIPlayerEngine()
        source = '<button class="x">X</button>'
        a1 = AIAction(action="tap", params={"selector": ".x"})
        engine.action_history.append(a1)
        a2 = await engine.analyze_screen(source, AIStrategy.EXPLORER)
        assert "全部已访问" in a2.reason

    @pytest.mark.asyncio
    async def test_run_player(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock_ctrl = AsyncMock()
        mock_ctrl.get_page_source.return_value = '<button class="btn">Go</button>'
        mock_ctrl.screenshot.return_value = Path("/tmp/s.png")
        await orch.connect_player("p1", mock_ctrl)

        config = AIPlayerConfig(max_actions=3, action_delay=0.01, screenshot_interval=2)
        engine = AIPlayerEngine(config)
        history = await engine.run_player(orch, "p1")
        assert len(history) >= 1
        assert engine.action_count <= 3

    @pytest.mark.asyncio
    async def test_run_player_with_error(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock_ctrl = AsyncMock()
        mock_ctrl.get_page_source.side_effect = RuntimeError("fail")
        await orch.connect_player("p1", mock_ctrl)

        config = AIPlayerConfig(max_actions=2, action_delay=0.01)
        engine = AIPlayerEngine(config)
        history = await engine.run_player(orch, "p1")
        assert any(a.action == "error" for a in history)

    def test_stop(self):
        engine = AIPlayerEngine()
        engine._running = True
        engine.stop()
        assert not engine.is_running

    def test_get_report(self):
        engine = AIPlayerEngine()
        engine._action_count = 5
        engine.action_history = [
            AIAction(action="tap", confidence=0.8),
            AIAction(action="tap", confidence=0.6),
        ]
        report = engine.get_report()
        assert report["total_actions"] == 5
        assert report["avg_confidence"] == 0.7

    def test_get_report_empty(self):
        engine = AIPlayerEngine()
        report = engine.get_report()
        assert report["total_actions"] == 0


# ── ActionRecorder ──────────────────────────────

class TestActionRecorder:
    def test_init(self):
        rec = ActionRecorder()
        assert not rec.is_recording
        assert rec.action_count == 0

    def test_start_stop(self):
        rec = ActionRecorder()
        rec.start()
        assert rec.is_recording
        rec.stop()
        assert not rec.is_recording

    def test_record(self):
        rec = ActionRecorder()
        rec.start()
        a = rec.record("p1", "tap", {"selector": ".btn"})
        assert a.player_id == "p1"
        assert a.offset >= 0
        assert rec.action_count == 1

    def test_duration(self):
        rec = ActionRecorder()
        assert rec.duration == 0
        rec.start()
        rec.record("p1", "tap")
        assert rec.duration >= 0

    def test_export_blueprint(self):
        rec = ActionRecorder()
        rec.start()
        rec.record("p1", "tap", {"selector": ".a"})
        rec.record("p2", "input", {"selector": ".b", "text": "hi"})
        bp = rec.export_blueprint()
        assert bp["mode"] == "multiplayer"
        assert bp["recorded"] is True
        assert len(bp["players"]) == 2
        assert len(bp["steps"]) == 2

    def test_save(self, tmp_path):
        rec = ActionRecorder()
        rec.start()
        rec.record("p1", "tap")
        path = rec.save(str(tmp_path / "test_bp.json"))
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["mode"] == "multiplayer"

    def test_load_recording(self, tmp_path):
        p = tmp_path / "bp.json"
        p.write_text(json.dumps({
            "steps": [
                {"player": "p1", "action": "tap", "selector": ".x"},
                {"player": "p2", "action": "input", "text": "hi"},
            ]
        }), encoding="utf-8")
        actions = ActionRecorder.load_recording(str(p))
        assert len(actions) == 2
        assert actions[0].player_id == "p1"

    def test_load_not_found(self):
        with pytest.raises(FileNotFoundError):
            ActionRecorder.load_recording("/nonexistent.json")


# ── ActionReplayer ──────────────────────────────

class TestActionReplayer:
    def test_init(self):
        rp = ActionReplayer()
        assert not rp.is_replaying
        assert rp.progress == 0

    def test_progress_empty(self):
        rp = ActionReplayer([])
        assert rp.progress == 0

    @pytest.mark.asyncio
    async def test_replay(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock = AsyncMock()
        await orch.connect_player("p1", mock)

        actions = [
            RecordedAction(player_id="p1", action="tap", params={"selector": ".a"}, offset=0),
            RecordedAction(player_id="p1", action="tap", params={"selector": ".b"}, offset=0.1),
        ]
        rp = ActionReplayer(actions)
        results = await rp.replay(orch, speed=10.0)
        assert len(results) == 2
        assert all(r["success"] for r in results)

    @pytest.mark.asyncio
    async def test_replay_with_filter(self):
        orch = MultiPlayerOrchestrator()
        for pid in ("p1", "p2"):
            orch.add_player(pid, "web")
            await orch.connect_player(pid, AsyncMock())

        actions = [
            RecordedAction(player_id="p1", action="tap", params={"selector": ".a"}, offset=0),
            RecordedAction(player_id="p2", action="tap", params={"selector": ".b"}, offset=0),
        ]
        rp = ActionReplayer(actions)
        results = await rp.replay(orch, speed=10.0, player_filter=["p1"])
        assert len(results) == 1
        assert results[0]["player"] == "p1"

    @pytest.mark.asyncio
    async def test_replay_error(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock = AsyncMock()
        mock.tap.side_effect = RuntimeError("fail")
        await orch.connect_player("p1", mock)

        actions = [RecordedAction(player_id="p1", action="tap", params={"selector": ".x"}, offset=0)]
        rp = ActionReplayer(actions)
        results = await rp.replay(orch, speed=10.0)
        assert not results[0]["success"]

    def test_stop(self):
        rp = ActionReplayer()
        rp._replaying = True
        rp.stop()
        assert not rp.is_replaying

    def test_get_status(self):
        actions = [RecordedAction(player_id="p1", action="tap", offset=0)]
        rp = ActionReplayer(actions)
        status = rp.get_status()
        assert status["total"] == 1
        assert status["progress"] == 0

    @pytest.mark.asyncio
    async def test_replay_wait_action(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        await orch.connect_player("p1", AsyncMock())

        actions = [RecordedAction(player_id="p1", action="wait", params={"duration": 0.05}, offset=0)]
        rp = ActionReplayer(actions)
        results = await rp.replay(orch, speed=10.0)
        assert len(results) == 1
        assert results[0]["success"]


# ── ConsistencyChecker ──────────────────────────

class TestConsistencyModels:
    def test_screen_capture(self):
        cap = ScreenCapture(player_id="p1", hash="abc123")
        assert cap.player_id == "p1"

    def test_diff_item(self):
        d = DiffItem(field="source", player_a="p1", player_b="p2",
                     value_a="x", value_b="y", severity="warning")
        assert d.severity == "warning"

    def test_report_consistent(self):
        r = ConsistencyReport(consistent=True, player_count=2, score=100)
        assert r.diff_count == 0
        d = r.to_dict()
        assert d["consistent"] is True
        assert d["score"] == 100

    def test_report_with_diffs(self):
        r = ConsistencyReport(
            consistent=False, player_count=2, score=80,
            diffs=[DiffItem("f", "p1", "p2", "a", "b")],
        )
        assert r.diff_count == 1


class TestConsistencyChecker:
    def test_init(self):
        checker = ConsistencyChecker()
        assert checker.reports == []

    @pytest.mark.asyncio
    async def test_check_single_player(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        checker = ConsistencyChecker()
        report = await checker.check(orch, ["p1"])
        assert report.consistent is True

    @pytest.mark.asyncio
    async def test_check_consistent(self):
        orch = MultiPlayerOrchestrator()
        for pid in ("p1", "p2"):
            orch.add_player(pid, "web")
            mock = AsyncMock()
            mock.get_page_source.return_value = "<div>same content</div>"
            mock.screenshot.return_value = Path(f"/tmp/{pid}.png")
            await orch.connect_player(pid, mock)

        checker = ConsistencyChecker()
        report = await checker.check(orch)
        assert report.consistent is True
        assert report.score >= 95

    @pytest.mark.asyncio
    async def test_check_inconsistent(self):
        orch = MultiPlayerOrchestrator()
        sources = {"p1": "<div>content A</div>", "p2": "<div>content B</div>"}
        for pid in ("p1", "p2"):
            orch.add_player(pid, "web")
            mock = AsyncMock()
            mock.get_page_source.return_value = sources[pid]
            mock.screenshot.return_value = Path(f"/tmp/{pid}.png")
            await orch.connect_player(pid, mock)

        checker = ConsistencyChecker()
        report = await checker.check(orch)
        assert report.consistent is False
        assert report.diff_count > 0

    @pytest.mark.asyncio
    async def test_check_no_source(self):
        orch = MultiPlayerOrchestrator()
        for pid in ("p1", "p2"):
            orch.add_player(pid, "web")
            mock = AsyncMock()
            mock.get_page_source.side_effect = RuntimeError("fail")
            await orch.connect_player(pid, mock)

        checker = ConsistencyChecker()
        report = await checker.check(orch, check_screenshot=False)
        assert report.consistent is True  # no hashes = no diff

    def test_compare_text_same(self):
        checker = ConsistencyChecker()
        diffs = checker.compare_text_content({"p1": "hello", "p2": "hello"})
        assert len(diffs) == 0

    def test_compare_text_different(self):
        checker = ConsistencyChecker()
        diffs = checker.compare_text_content({"p1": "hello", "p2": "world"})
        assert len(diffs) == 1

    def test_compare_text_three_players(self):
        checker = ConsistencyChecker()
        diffs = checker.compare_text_content({"p1": "a", "p2": "b", "p3": "a"})
        assert len(diffs) == 2  # p1-p2, p2-p3

    def test_get_summary_empty(self):
        checker = ConsistencyChecker()
        s = checker.get_summary()
        assert s["total_checks"] == 0

    @pytest.mark.asyncio
    async def test_get_summary_after_checks(self):
        orch = MultiPlayerOrchestrator()
        for pid in ("p1", "p2"):
            orch.add_player(pid, "web")
            mock = AsyncMock()
            mock.get_page_source.return_value = "<div>same</div>"
            mock.screenshot.return_value = Path(f"/tmp/{pid}.png")
            await orch.connect_player(pid, mock)

        checker = ConsistencyChecker()
        await checker.check(orch)
        await checker.check(orch)
        s = checker.get_summary()
        assert s["total_checks"] == 2
        assert s["consistency_rate"] == 100.0

    def test_find_text_diff(self):
        checker = ConsistencyChecker()
        result = checker._find_text_diff("hello world", "hello earth")
        assert 0 < result["similarity"] < 1

    def test_find_text_diff_identical(self):
        checker = ConsistencyChecker()
        result = checker._find_text_diff("same", "same")
        assert result["similarity"] == 1.0

    def test_find_text_diff_empty(self):
        checker = ConsistencyChecker()
        result = checker._find_text_diff("", "something")
        assert result["similarity"] == 0

    def test_calculate_score_no_diffs(self):
        checker = ConsistencyChecker()
        caps = [ScreenCapture("p1", hash="aaa"), ScreenCapture("p2", hash="aaa")]
        score = checker._calculate_score(caps, [])
        assert score >= 95

    def test_calculate_score_with_critical(self):
        checker = ConsistencyChecker()
        caps = [ScreenCapture("p1"), ScreenCapture("p2")]
        diffs = [DiffItem("f", "p1", "p2", "a", "b", "critical")]
        score = checker._calculate_score(caps, diffs)
        assert score == 80

    def test_calculate_score_single(self):
        checker = ConsistencyChecker()
        score = checker._calculate_score([ScreenCapture("p1")], [])
        assert score == 100
