"""测试控制器（TestController）单元测试。"""

import asyncio

import pytest

from src.testing.controller import TestController, TestState


@pytest.fixture
def ctrl():
    """创建新的TestController实例。"""
    return TestController()


class TestStateTransitions:
    """状态转换测试。"""

    def test_initial_state_is_idle(self, ctrl):
        assert ctrl.state == TestState.IDLE
        assert not ctrl.is_cancelled
        assert not ctrl.is_running

    def test_start_transitions_to_running(self, ctrl):
        ctrl.start(total_steps=10)
        assert ctrl.state == TestState.RUNNING
        assert ctrl.is_running
        assert ctrl.total_steps == 10

    def test_pause_from_running(self, ctrl):
        ctrl.start()
        assert ctrl.pause() is True
        assert ctrl.state == TestState.PAUSED
        assert ctrl.is_running  # PAUSED仍算is_running

    def test_pause_from_idle_fails(self, ctrl):
        assert ctrl.pause() is False
        assert ctrl.state == TestState.IDLE

    def test_resume_from_paused(self, ctrl):
        ctrl.start()
        ctrl.pause()
        assert ctrl.resume() is True
        assert ctrl.state == TestState.RUNNING

    def test_resume_from_running_fails(self, ctrl):
        ctrl.start()
        assert ctrl.resume() is False

    def test_stop_from_running(self, ctrl):
        ctrl.start()
        assert ctrl.stop() is True
        assert ctrl.state == TestState.STOPPED
        assert ctrl.is_cancelled

    def test_stop_from_paused(self, ctrl):
        ctrl.start()
        ctrl.pause()
        assert ctrl.stop() is True
        assert ctrl.state == TestState.STOPPED
        assert ctrl.is_cancelled

    def test_stop_from_idle_fails(self, ctrl):
        assert ctrl.stop() is False

    def test_double_stop_fails(self, ctrl):
        ctrl.start()
        ctrl.stop()
        assert ctrl.stop() is False

    def test_reset(self, ctrl):
        ctrl.start(total_steps=20)
        ctrl.update_progress(5, "doing something")
        ctrl.stop()
        ctrl.reset()
        assert ctrl.state == TestState.IDLE
        assert not ctrl.is_cancelled
        assert ctrl.current_step == 0
        assert ctrl.total_steps == 0

    def test_on_test_complete_from_running(self, ctrl):
        ctrl.start()
        ctrl.on_test_complete()
        assert ctrl.state == TestState.IDLE

    def test_on_test_complete_from_stopped(self, ctrl):
        ctrl.start()
        ctrl.stop()
        ctrl.on_test_complete()
        assert ctrl.state == TestState.STOPPED  # 保持STOPPED


class TestConfiguration:
    """配置测试。"""

    def test_set_step_mode(self, ctrl):
        ctrl.set_step_mode(True)
        assert ctrl.step_mode is True
        ctrl.set_step_mode(False)
        assert ctrl.step_mode is False

    def test_set_step_delay(self, ctrl):
        ctrl.set_step_delay(1.5)
        assert ctrl.step_delay_seconds == 1.5

    def test_step_delay_clamped(self, ctrl):
        ctrl.set_step_delay(-1)
        assert ctrl.step_delay_seconds == 0.0
        ctrl.set_step_delay(999)
        assert ctrl.step_delay_seconds == 10.0

    def test_update_progress(self, ctrl):
        ctrl.start(total_steps=10)
        ctrl.update_progress(3, "clicking button")
        assert ctrl.current_step == 3
        assert ctrl.status_dict()["description"] == "clicking button"


class TestStatusDict:
    """status_dict输出测试。"""

    def test_idle_status(self, ctrl):
        d = ctrl.status_dict()
        assert d["state"] == "idle"
        assert d["current_step"] == 0
        assert d["cancelled"] is False

    def test_running_status(self, ctrl):
        ctrl.start(total_steps=5)
        ctrl.update_progress(2, "step 2")
        d = ctrl.status_dict()
        assert d["state"] == "running"
        assert d["current_step"] == 2
        assert d["total_steps"] == 5
        assert d["description"] == "step 2"

    def test_paused_status(self, ctrl):
        ctrl.start()
        ctrl.pause()
        d = ctrl.status_dict()
        assert d["state"] == "paused"


class TestAsyncBehavior:
    """异步行为测试。"""

    @pytest.mark.asyncio
    async def test_wait_if_paused_passes_when_running(self, ctrl):
        ctrl.start()
        # 不应阻塞
        await asyncio.wait_for(ctrl.wait_if_paused(), timeout=1.0)

    @pytest.mark.asyncio
    async def test_wait_if_paused_blocks_when_paused(self, ctrl):
        ctrl.start()
        ctrl.pause()

        # 应该阻塞
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ctrl.wait_if_paused(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_resume_unblocks_wait(self, ctrl):
        ctrl.start()
        ctrl.pause()

        async def resume_later():
            await asyncio.sleep(0.05)
            ctrl.resume()

        # 启动resume任务
        task = asyncio.create_task(resume_later())
        # wait_if_paused应该在resume后解除阻塞
        await asyncio.wait_for(ctrl.wait_if_paused(), timeout=1.0)
        await task
        assert ctrl.state == TestState.RUNNING

    @pytest.mark.asyncio
    async def test_stop_unblocks_paused_wait(self, ctrl):
        ctrl.start()
        ctrl.pause()

        async def stop_later():
            await asyncio.sleep(0.05)
            ctrl.stop()

        task = asyncio.create_task(stop_later())
        await asyncio.wait_for(ctrl.wait_if_paused(), timeout=1.0)
        await task
        assert ctrl.is_cancelled

    @pytest.mark.asyncio
    async def test_step_delay_waits(self, ctrl):
        ctrl.start()
        ctrl.set_step_delay(0.1)

        start = asyncio.get_event_loop().time()
        await ctrl.step_delay()
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed >= 0.08  # 容差

    @pytest.mark.asyncio
    async def test_step_delay_zero_is_instant(self, ctrl):
        ctrl.start()
        ctrl.set_step_delay(0)

        start = asyncio.get_event_loop().time()
        await ctrl.step_delay()
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 0.05

    @pytest.mark.asyncio
    async def test_step_delay_skipped_when_cancelled(self, ctrl):
        ctrl.start()
        ctrl.set_step_delay(5.0)
        ctrl.stop()

        start = asyncio.get_event_loop().time()
        await ctrl.step_delay()
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 0.1  # 取消后不应等待

    @pytest.mark.asyncio
    async def test_step_mode_auto_pauses(self, ctrl):
        ctrl.set_step_mode(True)
        ctrl.start(total_steps=5)

        # 步骤0：不暂停（让用户先看到启动）
        ctrl.update_progress(0)
        await asyncio.wait_for(ctrl.wait_if_paused(), timeout=0.1)

        # 步骤1+：应自动暂停
        ctrl.update_progress(1)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ctrl.wait_if_paused(), timeout=0.1)
        assert ctrl.state == TestState.PAUSED

        # resume后继续
        ctrl.resume()
        ctrl.update_progress(2)
        # 又会自动暂停
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ctrl.wait_if_paused(), timeout=0.1)
        assert ctrl.state == TestState.PAUSED


class TestSimulatedRun:
    """模拟完整测试流程。"""

    @pytest.mark.asyncio
    async def test_full_run_without_control(self, ctrl):
        """正常跑完所有步骤。"""
        ctrl.start(total_steps=5)
        for i in range(5):
            ctrl.update_progress(i + 1, f"step {i + 1}")
            await ctrl.wait_if_paused()
            if ctrl.is_cancelled:
                break
            await ctrl.step_delay()
        ctrl.on_test_complete()
        assert ctrl.current_step == 5
        assert ctrl.state == TestState.IDLE

    @pytest.mark.asyncio
    async def test_run_with_early_stop(self, ctrl):
        """中途停止。"""
        ctrl.start(total_steps=10)
        completed = 0
        for i in range(10):
            ctrl.update_progress(i + 1)
            await ctrl.wait_if_paused()
            if ctrl.is_cancelled:
                break
            completed += 1
            if i == 3:
                ctrl.stop()
        assert completed == 4  # 完成了0,1,2,3
        assert ctrl.state == TestState.STOPPED
        ctrl.on_test_complete()
        assert ctrl.state == TestState.STOPPED  # on_test_complete保持STOPPED

    @pytest.mark.asyncio
    async def test_run_with_pause_resume(self, ctrl):
        """暂停后继续。"""
        ctrl.start(total_steps=5)
        results = []

        async def run_steps():
            for i in range(5):
                ctrl.update_progress(i + 1)
                await ctrl.wait_if_paused()
                if ctrl.is_cancelled:
                    break
                results.append(i + 1)

        async def pause_and_resume():
            await asyncio.sleep(0.02)
            ctrl.pause()
            await asyncio.sleep(0.1)  # 暂停100ms
            ctrl.resume()

        await asyncio.gather(run_steps(), pause_and_resume())
        assert len(results) == 5  # 所有步骤都应该完成
