"""
操作录制与回放引擎（v9.0 Phase2）

录制多端操作序列，保存为可回放的蓝本。
支持：实时录制、时间戳精确回放、部分回放、蓝本导出。
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from loguru import logger


@dataclass
class RecordedAction:
    """一条录制的操作。"""
    player_id: str
    action: str
    params: dict = field(default_factory=dict)
    timestamp: float = 0.0       # 录制时的绝对时间
    offset: float = 0.0          # 相对于录制开始的偏移（秒）


class ActionRecorder:
    """操作录制器。"""

    def __init__(self) -> None:
        self._recording = False
        self._start_time: float = 0
        self.actions: list[RecordedAction] = []

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def action_count(self) -> int:
        return len(self.actions)

    @property
    def duration(self) -> float:
        if not self.actions:
            return 0
        return self.actions[-1].offset

    def start(self) -> None:
        """开始录制。"""
        self._recording = True
        self._start_time = time.time()
        self.actions.clear()
        logger.info("录制开始")

    def stop(self) -> None:
        """停止录制。"""
        self._recording = False
        logger.info("录制停止 | 操作: {} | 时长: {:.1f}s", len(self.actions), self.duration)

    def record(self, player_id: str, action: str, params: dict = None) -> RecordedAction:
        """录制一条操作。"""
        now = time.time()
        recorded = RecordedAction(
            player_id=player_id,
            action=action,
            params=params or {},
            timestamp=now,
            offset=now - self._start_time if self._start_time else 0,
        )
        self.actions.append(recorded)
        return recorded

    def export_blueprint(self) -> dict:
        """导出为多端蓝本格式。"""
        player_ids = list(dict.fromkeys(a.player_id for a in self.actions))
        players = [{"id": pid, "platform": "web"} for pid in player_ids]

        steps = []
        for a in self.actions:
            step = {"player": a.player_id, "action": a.action}
            step.update(a.params)
            steps.append(step)

        return {
            "mode": "multiplayer",
            "recorded": True,
            "duration": round(self.duration, 2),
            "players": players,
            "steps": steps,
        }

    def save(self, path: str) -> Path:
        """保存蓝本到文件。"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.export_blueprint(), ensure_ascii=False, indent=2),
                      encoding="utf-8")
        logger.info("蓝本已保存: {}", path)
        return p

    @staticmethod
    def load_recording(path: str) -> list[RecordedAction]:
        """从文件加载录制数据。"""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        data = json.loads(p.read_text(encoding="utf-8"))
        actions = []
        offset = 0.0
        for step in data.get("steps", []):
            pid = step.get("player", "")
            action = step.get("action", "")
            params = {k: v for k, v in step.items() if k not in ("player", "action")}
            actions.append(RecordedAction(
                player_id=pid, action=action, params=params, offset=offset,
            ))
            offset += 0.5  # 默认间隔
        return actions


class ActionReplayer:
    """操作回放器。"""

    def __init__(self, actions: list[RecordedAction] = None) -> None:
        self.actions = actions or []
        self._replaying = False
        self._current_index = 0

    @property
    def is_replaying(self) -> bool:
        return self._replaying

    @property
    def progress(self) -> float:
        if not self.actions:
            return 0
        return self._current_index / len(self.actions)

    @property
    def current_index(self) -> int:
        return self._current_index

    async def replay(self, orchestrator: Any, speed: float = 1.0,
                     player_filter: list[str] = None) -> list[dict]:
        """回放录制的操作序列。

        Args:
            orchestrator: MultiPlayerOrchestrator 实例
            speed: 回放速度倍率（2.0 = 2倍速）
            player_filter: 只回放这些玩家的操作（None=全部）
        """
        self._replaying = True
        self._current_index = 0
        results = []
        prev_offset = 0.0

        logger.info("回放开始 | 操作: {} | 速度: {}x | 过滤: {}",
                     len(self.actions), speed, player_filter or "全部")

        for i, action in enumerate(self.actions):
            if not self._replaying:
                break

            if player_filter and action.player_id not in player_filter:
                continue

            delay = (action.offset - prev_offset) / speed
            if delay > 0:
                await self._interruptible_sleep(delay)
            if not self._replaying:
                break
            prev_offset = action.offset

            self._current_index = i + 1
            success = True
            error = ""

            try:
                if action.action == "wait":
                    await self._interruptible_sleep(action.params.get("duration", 1) / speed)
                else:
                    await orchestrator.execute_action(
                        action.player_id, action.action, **action.params
                    )
            except Exception as e:
                success = False
                error = str(e)
                logger.warning("回放操作失败 | {} | {} | {}", action.player_id, action.action, e)

            results.append({
                "index": i,
                "player": action.player_id,
                "action": action.action,
                "params": action.params,
                "success": success,
                "error": error,
            })

        self._replaying = False
        passed = sum(1 for r in results if r["success"])
        logger.info("回放完成 | 执行: {} | 通过: {} | 失败: {}",
                     len(results), passed, len(results) - passed)
        return results

    async def _interruptible_sleep(self, duration: float) -> None:
        """可中断的 sleep。"""
        import asyncio
        end = time.time() + duration
        while time.time() < end and self._replaying:
            await asyncio.sleep(min(0.1, end - time.time()))

    def stop(self) -> None:
        self._replaying = False

    def get_status(self) -> dict:
        return {
            "replaying": self._replaying,
            "total": len(self.actions),
            "current": self._current_index,
            "progress": round(self.progress * 100, 1),
        }
