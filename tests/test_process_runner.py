"""终端日志收集器（ProcessRunner）单元测试。"""

import asyncio
import time

import pytest

from src.testing.process_runner import ProcessRunner, ProcessState, LogLevel, TerminalLogEntry


@pytest.fixture
def runner():
    """创建新的ProcessRunner实例（无WebSocket广播）。"""
    return ProcessRunner()


class TestTerminalLogEntry:
    """日志条目测试。"""

    def test_to_dict(self):
        entry = TerminalLogEntry(
            timestamp=1000.0,
            level=LogLevel.STDOUT,
            content="hello world",
        )
        d = entry.to_dict()
        assert d["timestamp"] == 1000.0
        assert d["level"] == "stdout"
        assert d["content"] == "hello world"

    def test_stderr_level(self):
        entry = TerminalLogEntry(
            timestamp=1000.0,
            level=LogLevel.STDERR,
            content="error!",
        )
        assert entry.to_dict()["level"] == "stderr"


class TestProcessRunnerState:
    """状态测试。"""

    def test_initial_state(self, runner):
        assert runner.state == ProcessState.IDLE
        assert runner.command == ""

    def test_status_dict_idle(self, runner):
        d = runner.status_dict()
        assert d["state"] == "idle"
        assert d["log_count"] == 0
        assert d["uptime"] == 0


class TestProcessRunnerLifecycle:
    """进程生命周期测试。"""

    @pytest.mark.asyncio
    async def test_start_echo(self, runner):
        """启动一个简单的echo命令。"""
        success = await runner.start('python -c "print(\'hello\')"')
        assert success
        assert runner.state == ProcessState.RUNNING

        # 等待进程完成
        await asyncio.sleep(0.5)

        # 进程应该已退出
        assert runner.state == ProcessState.STOPPED
        logs = runner.get_all_logs()
        assert any("hello" in log["content"] for log in logs)

    @pytest.mark.asyncio
    async def test_start_stderr(self, runner):
        """捕获stderr输出。"""
        success = await runner.start(
            'python -c "import sys; sys.stderr.write(\'err_msg\\n\')"'
        )
        assert success
        await asyncio.sleep(0.5)

        logs = runner.get_all_logs()
        stderr_logs = [l for l in logs if l["level"] == "stderr"]
        assert any("err_msg" in l["content"] for l in stderr_logs)

    @pytest.mark.asyncio
    async def test_stop_running_process(self, runner):
        """停止长时间运行的进程。"""
        success = await runner.start(
            'python -c "import time; time.sleep(60)"'
        )
        assert success
        assert runner.state == ProcessState.RUNNING

        await runner.stop()
        assert runner.state == ProcessState.STOPPED

    @pytest.mark.asyncio
    async def test_double_start_fails(self, runner):
        """已运行时再次启动应失败。"""
        await runner.start('python -c "import time; time.sleep(60)"')
        success = await runner.start('python -c "print(1)"')
        assert success is False

        await runner.stop()

    @pytest.mark.asyncio
    async def test_stop_idle_is_safe(self, runner):
        """停止空闲状态不报错。"""
        await runner.stop()
        assert runner.state == ProcessState.IDLE


class TestLogBuffer:
    """日志缓冲区测试。"""

    @pytest.mark.asyncio
    async def test_multi_line_output(self, runner):
        """多行输出正确收集。"""
        success = await runner.start(
            'python -c "for i in range(5): print(f\'line{i}\')"'
        )
        assert success
        await asyncio.sleep(0.5)

        logs = runner.get_all_logs()
        contents = [l["content"] for l in logs]
        for i in range(5):
            assert f"line{i}" in contents

    @pytest.mark.asyncio
    async def test_get_recent_logs(self, runner):
        """获取最近N条日志。"""
        await runner.start(
            'python -c "for i in range(20): print(f\'line{i}\')"'
        )
        await asyncio.sleep(0.5)

        recent = runner.get_recent_logs(5)
        assert len(recent) == 5

    @pytest.mark.asyncio
    async def test_get_context_logs(self, runner):
        """按时间范围获取上下文日志。"""
        await runner.start(
            'python -c "for i in range(10): print(f\'line{i}\')"'
        )
        await asyncio.sleep(0.5)

        logs = runner.get_all_logs()
        if logs:
            mid_ts = logs[len(logs) // 2]["timestamp"]
            context = runner.get_context_logs(mid_ts, seconds=10)
            # 所有日志都应该在10秒窗口内
            assert len(context) == len(logs)

    @pytest.mark.asyncio
    async def test_timestamps_are_ordered(self, runner):
        """日志时间戳单调递增。"""
        await runner.start(
            'python -c "for i in range(10): print(f\'line{i}\')"'
        )
        await asyncio.sleep(0.5)

        logs = runner.get_all_logs()
        for i in range(1, len(logs)):
            assert logs[i]["timestamp"] >= logs[i - 1]["timestamp"]


class TestWebSocketBroadcast:
    """WebSocket广播集成测试。"""

    @pytest.mark.asyncio
    async def test_broadcast_called(self):
        """日志产生时调用广播函数。"""
        received = []

        async def fake_broadcast(msg_type, data):
            received.append((msg_type, data))

        runner = ProcessRunner(ws_broadcast=fake_broadcast)
        await runner.start('python -c "print(\'ws_test\')"')
        await asyncio.sleep(0.5)

        terminal_msgs = [r for r in received if r[0] == "terminal_log"]
        assert len(terminal_msgs) > 0
        assert any("ws_test" in r[1]["content"] for r in terminal_msgs)
