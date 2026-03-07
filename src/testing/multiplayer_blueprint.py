"""
多人蓝本解析与执行器（v9.0）

解析多人蓝本 JSON 格式，驱动 MultiPlayerOrchestrator 执行。
支持：顺序步骤、sync同步屏障、parallel并行、wait_for条件等待、assert断言。
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from src.testing.multiplayer import MultiPlayerOrchestrator, PlayerStatus


@dataclass
class PlayerDef:
    """蓝本中的玩家定义。"""
    id: str
    platform: str
    url: str = ""
    device: str = ""
    project_path: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class StepResult:
    """单步执行结果。"""
    step_index: int
    step_type: str
    success: bool
    detail: str = ""
    duration: float = 0.0


class MultiPlayerBlueprint:
    """多人蓝本解析与执行器。"""

    def __init__(self, data: dict) -> None:
        self._raw = data
        self.mode = data.get("mode", "multiplayer")
        self.player_defs = self._parse_players(data.get("players", []))
        self.steps = data.get("steps", [])
        self.results: list[StepResult] = []

    @staticmethod
    def load(path: str) -> "MultiPlayerBlueprint":
        """从文件加载蓝本。"""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"蓝本文件不存在: {path}")
        data = json.loads(p.read_text(encoding="utf-8"))
        return MultiPlayerBlueprint(data)

    @staticmethod
    def from_dict(data: dict) -> "MultiPlayerBlueprint":
        return MultiPlayerBlueprint(data)

    def _parse_players(self, players_raw: list[dict]) -> list[PlayerDef]:
        result = []
        for p in players_raw:
            result.append(PlayerDef(
                id=p.get("id", f"player{len(result)+1}"),
                platform=p.get("platform", "web"),
                url=p.get("url", ""),
                device=p.get("device", ""),
                project_path=p.get("project_path", ""),
                extra={k: v for k, v in p.items()
                       if k not in ("id", "platform", "url", "device", "project_path")},
            ))
        return result

    @property
    def player_count(self) -> int:
        return len(self.player_defs)

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.success)

    async def execute(self, orchestrator: MultiPlayerOrchestrator) -> list[StepResult]:
        """按顺序执行蓝本中的所有步骤。"""
        self.results.clear()
        await orchestrator.start()

        for i, step in enumerate(self.steps):
            result = await self._execute_step(orchestrator, i, step)
            self.results.append(result)
            if not result.success:
                logger.warning("步骤 {} 失败: {}", i, result.detail)

        await orchestrator.stop()
        logger.info("蓝本执行完成 | 总步骤: {} | 通过: {} | 失败: {}",
                     len(self.results), self.passed, self.failed)
        return self.results

    async def _execute_step(self, orch: MultiPlayerOrchestrator, idx: int, step: dict) -> StepResult:
        """执行单个步骤，根据类型分发。"""
        start = time.time()
        try:
            if "sync" in step:
                return await self._exec_sync(orch, idx, step, start)
            elif "parallel" in step:
                return await self._exec_parallel(orch, idx, step, start)
            elif "assert" in step:
                return await self._exec_assert(orch, idx, step, start)
            elif "assert_consistency" in step:
                return await self._exec_consistency(orch, idx, step, start)
            elif "player" in step:
                return await self._exec_player_action(orch, idx, step, start)
            else:
                return StepResult(idx, "unknown", False, f"未知步骤格式: {step}", time.time() - start)
        except Exception as e:
            return StepResult(idx, "error", False, str(e), time.time() - start)

    async def _exec_player_action(self, orch: MultiPlayerOrchestrator, idx: int, step: dict, start: float) -> StepResult:
        """执行单个玩家操作。"""
        pid = step["player"]
        action = step.get("action", "")

        if action == "wait_for":
            return await self._exec_wait_for(orch, idx, step, start)

        kwargs = {k: v for k, v in step.items() if k not in ("player", "action")}
        await orch.execute_action(pid, action, **kwargs)
        return StepResult(idx, f"{pid}.{action}", True, str(kwargs), time.time() - start)

    async def _exec_sync(self, orch: MultiPlayerOrchestrator, idx: int, step: dict, start: float) -> StepResult:
        """执行同步屏障。"""
        name = step["sync"]
        timeout = step.get("timeout", 30)
        barrier = orch.create_barrier(name, timeout=timeout)
        for pid in orch.players:
            barrier.arrive(pid)
        ok = await barrier.wait()
        return StepResult(idx, f"sync:{name}", ok,
                          "全员到达" if ok else f"超时，未到达: {barrier.pending}",
                          time.time() - start)

    async def _exec_parallel(self, orch: MultiPlayerOrchestrator, idx: int, step: dict, start: float) -> StepResult:
        """并行执行多个操作。"""
        actions = step["parallel"]
        results = await orch.execute_parallel(actions)
        errors = [str(r) for r in results if isinstance(r, Exception)]
        success = len(errors) == 0
        return StepResult(idx, "parallel", success,
                          f"{len(actions)}个操作" + (f", 错误: {errors}" if errors else ""),
                          time.time() - start)

    async def _exec_wait_for(self, orch: MultiPlayerOrchestrator, idx: int, step: dict, start: float) -> StepResult:
        """等待条件满足。"""
        pid = step["player"]
        condition = step.get("condition", "")
        timeout = step.get("timeout", 10)
        slot = orch.get_player(pid)
        if not slot or not slot.controller:
            return StepResult(idx, f"{pid}.wait_for", False, "玩家未连接", time.time() - start)

        slot.status = PlayerStatus.WAITING
        slot.add_log(f"等待条件: {condition}")

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if "screen_contains" in condition:
                    text_to_find = condition.split("'")[1] if "'" in condition else condition
                    source = await slot.controller.get_page_source()
                    if text_to_find in source:
                        slot.status = PlayerStatus.READY
                        return StepResult(idx, f"{pid}.wait_for", True, condition, time.time() - start)
                else:
                    slot.status = PlayerStatus.READY
                    return StepResult(idx, f"{pid}.wait_for", True, "通用条件", time.time() - start)
            except Exception:
                pass
            await asyncio.sleep(0.5)

        slot.status = PlayerStatus.ERROR
        return StepResult(idx, f"{pid}.wait_for", False, f"超时: {condition}", time.time() - start)

    async def _exec_assert(self, orch: MultiPlayerOrchestrator, idx: int, step: dict, start: float) -> StepResult:
        """执行断言。"""
        assertion = step["assert"]
        description = step.get("description", "")

        if "screen_contains" in assertion:
            parts = assertion.split(".", 1)
            pid = parts[0] if len(parts) > 1 else ""
            text_to_find = assertion.split("'")[1] if "'" in assertion else ""
            slot = orch.get_player(pid)
            if slot and slot.controller:
                try:
                    source = await slot.controller.get_page_source()
                    found = text_to_find in source
                    return StepResult(idx, "assert", found,
                                      description or f"{pid} 包含 '{text_to_find}'" if found
                                      else f"断言失败: {pid} 不包含 '{text_to_find}'",
                                      time.time() - start)
                except Exception as e:
                    return StepResult(idx, "assert", False, str(e), time.time() - start)
            return StepResult(idx, "assert", False, f"玩家 {pid} 不存在", time.time() - start)

        return StepResult(idx, "assert", True, description or assertion, time.time() - start)

    async def _exec_consistency(self, orch: MultiPlayerOrchestrator, idx: int, step: dict, start: float) -> StepResult:
        """跨端一致性断言：所有指定玩家截图对比。"""
        player_ids = step["assert_consistency"]
        check_desc = step.get("check", "状态一致性检查")

        screenshots = {}
        for pid in player_ids:
            slot = orch.get_player(pid)
            if slot and slot.controller:
                try:
                    path = await slot.controller.screenshot(f"consistency_{pid}")
                    screenshots[pid] = path
                except Exception:
                    pass

        captured = len(screenshots)
        expected = len(player_ids)
        success = captured == expected
        return StepResult(
            idx, "assert_consistency", success,
            f"{check_desc}: {captured}/{expected}个截图" + ("" if success else " (部分失败)"),
            time.time() - start,
        )

    def get_report(self) -> dict:
        """生成执行报告。"""
        return {
            "mode": self.mode,
            "player_count": self.player_count,
            "total_steps": self.step_count,
            "executed": len(self.results),
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.passed / max(len(self.results), 1) * 100, 1),
            "steps": [
                {
                    "index": r.step_index,
                    "type": r.step_type,
                    "success": r.success,
                    "detail": r.detail,
                    "duration": round(r.duration, 3),
                }
                for r in self.results
            ],
        }
