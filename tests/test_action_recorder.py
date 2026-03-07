"""操作录制与回放引擎测试（v9.0 Phase2）。"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.testing.action_recorder import ActionRecorder, ActionReplayer, RecordedAction


# ── RecordedAction 数据类 ──

class TestRecordedAction:
    def test_defaults(self):
        a = RecordedAction(player_id="p1", action="click")
        assert a.player_id == "p1"
        assert a.action == "click"
        assert a.params == {}
        assert a.timestamp == 0.0
        assert a.offset == 0.0

    def test_with_params(self):
        a = RecordedAction(player_id="p2", action="type", params={"text": "hello"}, offset=1.5)
        assert a.params == {"text": "hello"}
        assert a.offset == 1.5


# ── ActionRecorder ──

class TestActionRecorder:
    def test_initial_state(self):
        rec = ActionRecorder()
        assert not rec.is_recording
        assert rec.action_count == 0
        assert rec.duration == 0

    def test_start_stop(self):
        rec = ActionRecorder()
        rec.start()
        assert rec.is_recording
        rec.stop()
        assert not rec.is_recording

    def test_record_action(self):
        rec = ActionRecorder()
        rec.start()
        a = rec.record("p1", "click", {"selector": "#btn"})
        assert a.player_id == "p1"
        assert a.action == "click"
        assert a.params == {"selector": "#btn"}
        assert rec.action_count == 1

    def test_record_multiple(self):
        rec = ActionRecorder()
        rec.start()
        rec.record("p1", "click")
        rec.record("p2", "type", {"text": "hi"})
        rec.record("p1", "wait")
        assert rec.action_count == 3

    def test_duration(self):
        rec = ActionRecorder()
        rec.start()
        # 手动设置偏移测试
        rec.record("p1", "a")
        rec.actions[-1].offset = 0.0
        rec.record("p1", "b")
        rec.actions[-1].offset = 2.5
        assert rec.duration == 2.5

    def test_export_blueprint(self):
        rec = ActionRecorder()
        rec.start()
        rec.record("p1", "click", {"selector": "#a"})
        rec.record("p2", "type", {"text": "hi"})
        bp = rec.export_blueprint()
        assert bp["mode"] == "multiplayer"
        assert bp["recorded"] is True
        assert len(bp["players"]) == 2
        assert len(bp["steps"]) == 2
        assert bp["steps"][0]["player"] == "p1"
        assert bp["steps"][1]["text"] == "hi"

    def test_save_and_load(self):
        rec = ActionRecorder()
        rec.start()
        rec.record("p1", "click", {"selector": "#btn"})
        rec.record("p2", "type", {"text": "hello"})

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name

        rec.save(path)
        assert Path(path).exists()

        actions = ActionRecorder.load_recording(path)
        assert len(actions) == 2
        assert actions[0].player_id == "p1"
        assert actions[0].action == "click"
        assert actions[1].params["text"] == "hello"

        Path(path).unlink(missing_ok=True)

    def test_load_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            ActionRecorder.load_recording("/nonexistent/path.json")

    def test_start_clears_previous(self):
        rec = ActionRecorder()
        rec.start()
        rec.record("p1", "a")
        assert rec.action_count == 1
        rec.stop()
        rec.start()
        assert rec.action_count == 0


# ── ActionReplayer ──

class TestActionReplayer:
    def test_initial_state(self):
        rp = ActionReplayer()
        assert not rp.is_replaying
        assert rp.progress == 0
        assert rp.current_index == 0

    def test_with_actions(self):
        actions = [
            RecordedAction(player_id="p1", action="click", offset=0),
            RecordedAction(player_id="p1", action="type", offset=0.5),
        ]
        rp = ActionReplayer(actions)
        assert len(rp.actions) == 2

    def test_get_status(self):
        actions = [RecordedAction(player_id="p1", action="a", offset=0)]
        rp = ActionReplayer(actions)
        status = rp.get_status()
        assert status["replaying"] is False
        assert status["total"] == 1
        assert status["current"] == 0

    @pytest.mark.asyncio
    async def test_replay_basic(self):
        actions = [
            RecordedAction(player_id="p1", action="click", params={"selector": "#a"}, offset=0),
            RecordedAction(player_id="p1", action="type", params={"text": "hi"}, offset=0),
        ]
        orch = MagicMock()
        orch.execute_action = AsyncMock()
        rp = ActionReplayer(actions)
        results = await rp.replay(orch, speed=10.0)
        assert len(results) == 2
        assert all(r["success"] for r in results)

    @pytest.mark.asyncio
    async def test_replay_with_filter(self):
        actions = [
            RecordedAction(player_id="p1", action="click", offset=0),
            RecordedAction(player_id="p2", action="type", offset=0),
            RecordedAction(player_id="p1", action="wait", params={"duration": 0.01}, offset=0),
        ]
        orch = MagicMock()
        orch.execute_action = AsyncMock()
        rp = ActionReplayer(actions)
        results = await rp.replay(orch, speed=100.0, player_filter=["p1"])
        # 只有p1的操作被执行
        assert all(r["player"] == "p1" for r in results)

    @pytest.mark.asyncio
    async def test_replay_error_handling(self):
        actions = [
            RecordedAction(player_id="p1", action="click", offset=0),
        ]
        orch = MagicMock()
        orch.execute_action = AsyncMock(side_effect=RuntimeError("boom"))
        rp = ActionReplayer(actions)
        results = await rp.replay(orch, speed=100.0)
        assert len(results) == 1
        assert not results[0]["success"]
        assert "boom" in results[0]["error"]

    def test_stop(self):
        rp = ActionReplayer()
        rp._replaying = True
        rp.stop()
        assert not rp.is_replaying
