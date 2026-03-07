"""
多人协同测试引擎测试（v9.0）

覆盖：PlayerSlot、SyncBarrier、EventBus、MultiPlayerOrchestrator、MultiPlayerBlueprint
"""

import asyncio
import pytest
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.testing.multiplayer import (
    PlayerStatus, TimelineEvent, PlayerSlot, SyncBarrier, EventBus,
    MultiPlayerOrchestrator,
)
from src.testing.multiplayer_blueprint import (
    PlayerDef, StepResult, MultiPlayerBlueprint,
)


# ── PlayerSlot 测试 ─────────────────────────────

class TestPlayerSlot:
    def test_defaults(self):
        slot = PlayerSlot(player_id="p1", platform="web")
        assert slot.status == PlayerStatus.IDLE
        assert slot.screenshots == []
        assert slot.logs == []

    def test_add_log(self):
        slot = PlayerSlot(player_id="p1", platform="web")
        slot.add_log("test message")
        assert len(slot.logs) == 1
        assert "test message" in slot.logs[0]

    def test_log_limit(self):
        slot = PlayerSlot(player_id="p1", platform="web")
        for i in range(250):
            slot.add_log(f"msg {i}")
        assert len(slot.logs) <= 100


class TestTimelineEvent:
    def test_creation(self):
        ev = TimelineEvent(
            player_id="p1", action="tap", detail=".btn",
            timestamp=time.time(), duration=0.5, success=True,
        )
        assert ev.player_id == "p1"
        assert ev.success is True


# ── SyncBarrier 测试 ────────────────────────────

class TestSyncBarrier:
    def test_arrive_single(self):
        barrier = SyncBarrier(["p1", "p2"])
        assert not barrier.arrive("p1")
        assert barrier.arrive("p2")
        assert barrier.is_complete

    def test_pending(self):
        barrier = SyncBarrier(["p1", "p2", "p3"])
        barrier.arrive("p1")
        assert barrier.pending == {"p2", "p3"}

    def test_arrive_unknown_player(self):
        barrier = SyncBarrier(["p1"])
        barrier.arrive("unknown")
        assert not barrier.is_complete

    @pytest.mark.asyncio
    async def test_wait_success(self):
        barrier = SyncBarrier(["p1"], timeout=2.0)
        barrier.arrive("p1")
        ok = await barrier.wait()
        assert ok is True

    @pytest.mark.asyncio
    async def test_wait_timeout(self):
        barrier = SyncBarrier(["p1", "p2"], timeout=0.1)
        barrier.arrive("p1")
        ok = await barrier.wait()
        assert ok is False


# ── EventBus 测试 ───────────────────────────────

class TestEventBus:
    def test_empty(self):
        bus = EventBus()
        assert bus.history == []

    @pytest.mark.asyncio
    async def test_emit_sync_listener(self):
        bus = EventBus()
        received = []
        bus.on("test", lambda e: received.append(e))
        await bus.emit("test", {"x": 1})
        assert len(received) == 1
        assert received[0]["data"]["x"] == 1

    @pytest.mark.asyncio
    async def test_emit_async_listener(self):
        bus = EventBus()
        received = []
        async def handler(e):
            received.append(e)
        bus.on("test", handler)
        await bus.emit("test")
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_off(self):
        bus = EventBus()
        calls = []
        cb = lambda e: calls.append(1)
        bus.on("ev", cb)
        bus.off("ev", cb)
        await bus.emit("ev")
        assert len(calls) == 0

    @pytest.mark.asyncio
    async def test_history(self):
        bus = EventBus()
        await bus.emit("a")
        await bus.emit("b")
        assert len(bus.history) == 2

    def test_clear(self):
        bus = EventBus()
        bus.on("x", lambda e: None)
        bus.clear()
        assert bus.history == []

    @pytest.mark.asyncio
    async def test_listener_exception_handled(self):
        bus = EventBus()
        bus.on("err", lambda e: 1/0)
        await bus.emit("err")  # should not raise


# ── MultiPlayerOrchestrator 测试 ────────────────

class TestOrchestrator:
    def test_init(self):
        orch = MultiPlayerOrchestrator()
        assert orch.player_count == 0
        assert not orch.is_running

    def test_add_player(self):
        orch = MultiPlayerOrchestrator()
        slot = orch.add_player("p1", "web")
        assert slot.player_id == "p1"
        assert orch.player_count == 1

    def test_add_duplicate(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        with pytest.raises(RuntimeError, match="已存在"):
            orch.add_player("p1", "web")

    def test_add_max_players(self):
        orch = MultiPlayerOrchestrator()
        for i in range(8):
            orch.add_player(f"p{i}", "web")
        with pytest.raises(RuntimeError, match="最多支持"):
            orch.add_player("p8", "web")

    def test_remove_player(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        orch.remove_player("p1")
        assert orch.player_count == 0

    def test_get_player(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "android")
        assert orch.get_player("p1") is not None
        assert orch.get_player("xxx") is None

    @pytest.mark.asyncio
    async def test_connect_player(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock_ctrl = AsyncMock()
        await orch.connect_player("p1", mock_ctrl)
        assert orch.get_player("p1").status == PlayerStatus.READY
        mock_ctrl.launch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_player_not_found(self):
        orch = MultiPlayerOrchestrator()
        with pytest.raises(RuntimeError, match="不存在"):
            await orch.connect_player("xxx", AsyncMock())

    @pytest.mark.asyncio
    async def test_connect_player_failure(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock_ctrl = AsyncMock()
        mock_ctrl.launch.side_effect = RuntimeError("连接超时")
        with pytest.raises(RuntimeError):
            await orch.connect_player("p1", mock_ctrl)
        assert orch.get_player("p1").status == PlayerStatus.ERROR

    @pytest.mark.asyncio
    async def test_disconnect_player(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock_ctrl = AsyncMock()
        await orch.connect_player("p1", mock_ctrl)
        await orch.disconnect_player("p1")
        assert orch.get_player("p1").status == PlayerStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_disconnect_all(self):
        orch = MultiPlayerOrchestrator()
        for i in range(3):
            orch.add_player(f"p{i}", "web")
            mock = AsyncMock()
            await orch.connect_player(f"p{i}", mock)
        await orch.disconnect_all()
        for slot in orch.players.values():
            assert slot.status == PlayerStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_execute_action_tap(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock_ctrl = AsyncMock()
        await orch.connect_player("p1", mock_ctrl)
        await orch.execute_action("p1", "tap", selector=".btn")
        mock_ctrl.tap.assert_awaited_once_with(".btn")
        assert len(orch.timeline) == 1

    @pytest.mark.asyncio
    async def test_execute_action_input(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock_ctrl = AsyncMock()
        await orch.connect_player("p1", mock_ctrl)
        await orch.execute_action("p1", "input", selector=".inp", text="hello")
        mock_ctrl.input_text.assert_awaited_once_with(".inp", "hello")

    @pytest.mark.asyncio
    async def test_execute_action_navigate(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock_ctrl = AsyncMock()
        await orch.connect_player("p1", mock_ctrl)
        await orch.execute_action("p1", "navigate", url="/page2")
        mock_ctrl.navigate.assert_awaited_once_with("/page2")

    @pytest.mark.asyncio
    async def test_execute_action_screenshot(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock_ctrl = AsyncMock()
        mock_ctrl.screenshot.return_value = Path("/tmp/shot.png")
        await orch.connect_player("p1", mock_ctrl)
        result = await orch.execute_action("p1", "screenshot")
        assert result == Path("/tmp/shot.png")
        assert len(orch.get_player("p1").screenshots) == 1

    @pytest.mark.asyncio
    async def test_execute_action_unknown(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock_ctrl = AsyncMock()
        await orch.connect_player("p1", mock_ctrl)
        with pytest.raises(RuntimeError, match="未知操作"):
            await orch.execute_action("p1", "fly")

    @pytest.mark.asyncio
    async def test_execute_action_no_player(self):
        orch = MultiPlayerOrchestrator()
        with pytest.raises(RuntimeError, match="不存在"):
            await orch.execute_action("xxx", "tap")

    @pytest.mark.asyncio
    async def test_execute_action_no_controller(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        with pytest.raises(RuntimeError, match="未连接"):
            await orch.execute_action("p1", "tap")

    @pytest.mark.asyncio
    async def test_execute_parallel(self):
        orch = MultiPlayerOrchestrator()
        for i in range(2):
            orch.add_player(f"p{i}", "web")
            mock = AsyncMock()
            await orch.connect_player(f"p{i}", mock)
        results = await orch.execute_parallel([
            {"player": "p0", "action": "tap", "selector": ".a"},
            {"player": "p1", "action": "tap", "selector": ".b"},
        ])
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_sync_all(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        orch.add_player("p2", "web")
        ok = await orch.sync_all(timeout=1.0)
        assert ok is True

    def test_get_status(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        status = orch.get_status()
        assert status["player_count"] == 1
        assert "p1" in status["players"]

    def test_get_timeline_empty(self):
        orch = MultiPlayerOrchestrator()
        assert orch.get_timeline() == []

    @pytest.mark.asyncio
    async def test_start_stop(self):
        orch = MultiPlayerOrchestrator()
        await orch.start()
        assert orch.is_running
        await orch.stop()
        assert not orch.is_running

    @pytest.mark.asyncio
    async def test_reset(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        await orch.reset()
        assert orch.player_count == 0
        assert orch.timeline == []

    @pytest.mark.asyncio
    async def test_connect_all(self):
        orch = MultiPlayerOrchestrator()
        for i in range(2):
            slot = orch.add_player(f"p{i}", "web")
            slot.controller = AsyncMock()
        results = await orch.connect_all()
        assert all(results.values())

    @pytest.mark.asyncio
    async def test_connect_all_partial_failure(self):
        orch = MultiPlayerOrchestrator()
        slot0 = orch.add_player("p0", "web")
        slot0.controller = AsyncMock()
        slot1 = orch.add_player("p1", "web")
        slot1.controller = AsyncMock()
        slot1.controller.launch.side_effect = RuntimeError("fail")
        results = await orch.connect_all()
        assert results["p0"] is True
        assert results["p1"] is False

    @pytest.mark.asyncio
    async def test_elapsed(self):
        orch = MultiPlayerOrchestrator()
        assert orch.elapsed == 0
        await orch.start()
        await asyncio.sleep(0.05)
        assert orch.elapsed > 0

    @pytest.mark.asyncio
    async def test_execute_action_emits_event(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock_ctrl = AsyncMock()
        await orch.connect_player("p1", mock_ctrl)
        events = []
        orch.event_bus.on("action_done", lambda e: events.append(e))
        await orch.execute_action("p1", "tap", selector=".x")
        assert len(events) == 1


# ── MultiPlayerBlueprint 测试 ───────────────────

class TestBlueprint:
    def _sample_bp(self):
        return {
            "mode": "multiplayer",
            "players": [
                {"id": "p1", "platform": "web", "url": "http://example.com"},
                {"id": "p2", "platform": "android", "device": "abc123"},
            ],
            "steps": [
                {"player": "p1", "action": "tap", "selector": ".btn"},
                {"sync": "ready", "timeout": 5},
                {"parallel": [
                    {"player": "p1", "action": "screenshot"},
                    {"player": "p2", "action": "screenshot"},
                ]},
            ],
        }

    def test_parse(self):
        bp = MultiPlayerBlueprint(self._sample_bp())
        assert bp.player_count == 2
        assert bp.step_count == 3
        assert bp.mode == "multiplayer"

    def test_player_defs(self):
        bp = MultiPlayerBlueprint(self._sample_bp())
        assert bp.player_defs[0].id == "p1"
        assert bp.player_defs[0].platform == "web"
        assert bp.player_defs[1].device == "abc123"

    def test_from_dict(self):
        bp = MultiPlayerBlueprint.from_dict(self._sample_bp())
        assert bp.player_count == 2

    @pytest.mark.asyncio
    async def test_execute_player_action(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock = AsyncMock()
        await orch.connect_player("p1", mock)

        bp = MultiPlayerBlueprint({
            "players": [{"id": "p1", "platform": "web"}],
            "steps": [{"player": "p1", "action": "tap", "selector": ".btn"}],
        })
        results = await bp.execute(orch)
        assert len(results) == 1
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_execute_sync(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        orch.add_player("p2", "web")

        bp = MultiPlayerBlueprint({
            "players": [{"id": "p1"}, {"id": "p2"}],
            "steps": [{"sync": "barrier1", "timeout": 2}],
        })
        results = await bp.execute(orch)
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_execute_parallel(self):
        orch = MultiPlayerOrchestrator()
        for i in range(2):
            orch.add_player(f"p{i}", "web")
            mock = AsyncMock()
            mock.screenshot.return_value = Path(f"/tmp/{i}.png")
            await orch.connect_player(f"p{i}", mock)

        bp = MultiPlayerBlueprint({
            "players": [{"id": "p0"}, {"id": "p1"}],
            "steps": [{"parallel": [
                {"player": "p0", "action": "screenshot"},
                {"player": "p1", "action": "screenshot"},
            ]}],
        })
        results = await bp.execute(orch)
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_execute_assert(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock = AsyncMock()
        mock.get_page_source.return_value = "<div>你的回合</div>"
        await orch.connect_player("p1", mock)

        bp = MultiPlayerBlueprint({
            "players": [{"id": "p1"}],
            "steps": [{"assert": "p1.screen_contains('你的回合')", "description": "检查回合"}],
        })
        results = await bp.execute(orch)
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_execute_assert_fail(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock = AsyncMock()
        mock.get_page_source.return_value = "<div>等待中</div>"
        await orch.connect_player("p1", mock)

        bp = MultiPlayerBlueprint({
            "players": [{"id": "p1"}],
            "steps": [{"assert": "p1.screen_contains('你的回合')"}],
        })
        results = await bp.execute(orch)
        assert results[0].success is False

    @pytest.mark.asyncio
    async def test_execute_consistency(self):
        orch = MultiPlayerOrchestrator()
        for i in range(2):
            orch.add_player(f"p{i}", "web")
            mock = AsyncMock()
            mock.screenshot.return_value = Path(f"/tmp/c{i}.png")
            await orch.connect_player(f"p{i}", mock)

        bp = MultiPlayerBlueprint({
            "players": [{"id": "p0"}, {"id": "p1"}],
            "steps": [{"assert_consistency": ["p0", "p1"], "check": "牌桌一致"}],
        })
        results = await bp.execute(orch)
        assert results[0].success is True
        assert "牌桌一致" in results[0].detail

    @pytest.mark.asyncio
    async def test_execute_wait_for_success(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock = AsyncMock()
        mock.get_page_source.return_value = "<div>你的回合</div>"
        await orch.connect_player("p1", mock)

        bp = MultiPlayerBlueprint({
            "players": [{"id": "p1"}],
            "steps": [{"player": "p1", "action": "wait_for",
                       "condition": "screen_contains('你的回合')", "timeout": 2}],
        })
        results = await bp.execute(orch)
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_execute_wait_for_timeout(self):
        orch = MultiPlayerOrchestrator()
        orch.add_player("p1", "web")
        mock = AsyncMock()
        mock.get_page_source.return_value = "<div>等待</div>"
        await orch.connect_player("p1", mock)

        bp = MultiPlayerBlueprint({
            "players": [{"id": "p1"}],
            "steps": [{"player": "p1", "action": "wait_for",
                       "condition": "screen_contains('不存在的文本')", "timeout": 0.5}],
        })
        results = await bp.execute(orch)
        assert results[0].success is False

    def test_get_report(self):
        bp = MultiPlayerBlueprint({
            "players": [{"id": "p1"}],
            "steps": [],
        })
        bp.results = [
            StepResult(0, "tap", True, "", 0.1),
            StepResult(1, "assert", False, "fail", 0.2),
        ]
        report = bp.get_report()
        assert report["passed"] == 1
        assert report["failed"] == 1
        assert report["pass_rate"] == 50.0

    @pytest.mark.asyncio
    async def test_unknown_step(self):
        orch = MultiPlayerOrchestrator()
        bp = MultiPlayerBlueprint({
            "players": [],
            "steps": [{"weird_key": "???"}],
        })
        results = await bp.execute(orch)
        assert results[0].success is False

    def test_load_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            MultiPlayerBlueprint.load("/nonexistent/file.json")

    def test_load_file(self, tmp_path):
        import json
        p = tmp_path / "test.json"
        p.write_text(json.dumps({
            "players": [{"id": "p1"}], "steps": [],
        }), encoding="utf-8")
        bp = MultiPlayerBlueprint.load(str(p))
        assert bp.player_count == 1
