"""Watch模式 + Regression循环 单元测试。"""

import asyncio
import os
import tempfile
import time

import pytest

from src.testing.watcher import (
    BlueprintWatcher,
    RegressionResult,
    RegressionRunner,
    WatcherState,
)


@pytest.fixture
def tmp_blueprint():
    """创建临时蓝本文件。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write('{"app_name": "test"}')
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


class TestBlueprintWatcher:
    """Watch模式测试。"""

    @pytest.mark.asyncio
    async def test_initial_state(self):
        async def noop(_path):
            return (0, 0, 0)
        w = BlueprintWatcher(noop)
        assert w.state == WatcherState.IDLE
        assert w.run_count == 0

    @pytest.mark.asyncio
    async def test_start_watching(self, tmp_blueprint):
        async def noop(_path):
            return (0, 0, 0)
        w = BlueprintWatcher(noop, poll_interval=0.1)
        result = await w.start(tmp_blueprint)
        assert result is True
        assert w.state == WatcherState.WATCHING
        await w.stop()
        assert w.state == WatcherState.STOPPED

    @pytest.mark.asyncio
    async def test_start_nonexistent_file(self):
        async def noop(_path):
            return (0, 0, 0)
        w = BlueprintWatcher(noop)
        result = await w.start("/nonexistent/file.json")
        assert result is False
        assert w.state == WatcherState.IDLE

    @pytest.mark.asyncio
    async def test_double_start_fails(self, tmp_blueprint):
        async def noop(_path):
            return (0, 0, 0)
        w = BlueprintWatcher(noop, poll_interval=0.1)
        await w.start(tmp_blueprint)
        result = await w.start(tmp_blueprint)
        assert result is False
        await w.stop()

    @pytest.mark.asyncio
    async def test_detects_file_change(self, tmp_blueprint):
        results = []

        async def on_test(path):
            results.append(path)
            return (5, 5, 0)

        w = BlueprintWatcher(on_test, poll_interval=0.1)
        await w.start(tmp_blueprint)

        # 修改文件触发测试
        await asyncio.sleep(0.15)
        with open(tmp_blueprint, "w") as f:
            f.write('{"app_name": "updated"}')

        await asyncio.sleep(0.5)
        await w.stop()

        assert len(results) >= 1
        assert w.run_count >= 1

    @pytest.mark.asyncio
    async def test_no_trigger_without_change(self, tmp_blueprint):
        results = []

        async def on_test(path):
            results.append(path)
            return (0, 0, 0)

        w = BlueprintWatcher(on_test, poll_interval=0.1)
        await w.start(tmp_blueprint)
        await asyncio.sleep(0.5)
        await w.stop()

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_notify_callback(self, tmp_blueprint):
        events = []

        async def on_test(_path):
            return (0, 0, 0)

        async def on_notify(msg_type, data):
            events.append(msg_type)

        w = BlueprintWatcher(on_test, notify_callback=on_notify, poll_interval=0.1)
        await w.start(tmp_blueprint)
        await w.stop()

        assert "watch_start" in events
        assert "watch_stop" in events

    @pytest.mark.asyncio
    async def test_status_dict(self, tmp_blueprint):
        async def noop(_path):
            return (0, 0, 0)
        w = BlueprintWatcher(noop, poll_interval=0.5)
        await w.start(tmp_blueprint)
        d = w.status_dict()
        assert d["state"] == "watching"
        assert d["blueprint_path"] == tmp_blueprint
        await w.stop()


class TestRegressionRunner:
    """Regression循环测试。"""

    @pytest.mark.asyncio
    async def test_all_passed_first_round(self):
        async def perfect_test(_path):
            return (10, 10, 0)

        r = RegressionRunner(perfect_test, max_rounds=5)
        result = await r.run("test.json")
        assert result == RegressionResult.ALL_PASSED
        assert r.current_round == 1

    @pytest.mark.asyncio
    async def test_passes_after_retries(self):
        call_count = 0

        async def improving_test(_path):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return (8, 10, 2)
            return (10, 10, 0)

        r = RegressionRunner(improving_test, max_rounds=5)
        result = await r.run("test.json")
        assert result == RegressionResult.ALL_PASSED
        assert r.current_round == 3

    @pytest.mark.asyncio
    async def test_max_rounds_reached(self):
        async def always_buggy(_path):
            return (7, 10, 3)

        r = RegressionRunner(always_buggy, max_rounds=3)
        result = await r.run("test.json")
        assert result == RegressionResult.MAX_ROUNDS
        assert r.current_round == 3

    @pytest.mark.asyncio
    async def test_cancel(self):
        call_count = 0

        async def slow_test(_path):
            nonlocal call_count
            call_count += 1
            return (5, 10, 5)

        r = RegressionRunner(slow_test, max_rounds=10)

        async def cancel_later():
            await asyncio.sleep(0.05)
            r.cancel()

        task = asyncio.create_task(cancel_later())
        result = await r.run("test.json")
        await task

        assert result == RegressionResult.CANCELLED
        assert call_count <= 2

    @pytest.mark.asyncio
    async def test_notify_callbacks(self):
        events = []

        async def perfect_test(_path):
            return (10, 10, 0)

        async def on_notify(msg_type, data):
            events.append(msg_type)

        r = RegressionRunner(perfect_test, notify_callback=on_notify, max_rounds=3)
        await r.run("test.json")

        assert "regression_start" in events
        assert "regression_round" in events
        assert "regression_done" in events

    @pytest.mark.asyncio
    async def test_test_callback_exception_handled(self):
        call_count = 0

        async def flaky_test(_path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("boom")
            return (10, 10, 0)

        r = RegressionRunner(flaky_test, max_rounds=3)
        result = await r.run("test.json")
        assert result == RegressionResult.ALL_PASSED
        assert call_count == 2
