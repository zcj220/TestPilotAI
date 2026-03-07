"""
多人协同测试引擎（v9.0）

核心组件：
- PlayerSlot: 玩家槽位，封装单个控制器实例+状态+日志
- SyncBarrier: 同步屏障，所有玩家到达后才继续
- EventBus: 全局事件总线，玩家间广播/监听事件
- MultiPlayerOrchestrator: 协调器，管理N个玩家的创建/同步/并行执行/截图
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger


class PlayerStatus(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    READY = "ready"
    EXECUTING = "executing"
    WAITING = "waiting"
    DONE = "done"
    ERROR = "error"
    DISCONNECTED = "disconnected"


@dataclass
class TimelineEvent:
    """时序轴事件。"""
    player_id: str
    action: str
    detail: str
    timestamp: float
    duration: float = 0.0
    success: bool = True


@dataclass
class PlayerSlot:
    """玩家槽位。"""
    player_id: str
    platform: str
    controller: Any = None
    config: dict = field(default_factory=dict)
    status: PlayerStatus = PlayerStatus.IDLE
    screenshots: list[Path] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    last_error: str = ""

    def add_log(self, msg: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.logs.append(f"[{ts}] {msg}")
        if len(self.logs) > 100:
            self.logs = self.logs[-100:]


class SyncBarrier:
    """同步屏障：所有指定玩家到达后才放行。"""

    def __init__(self, player_ids: list[str], timeout: float = 30.0):
        self.player_ids = set(player_ids)
        self.arrived: set[str] = set()
        self.timeout = timeout
        self._event = asyncio.Event()

    def arrive(self, player_id: str) -> bool:
        if player_id in self.player_ids:
            self.arrived.add(player_id)
        if self.arrived >= self.player_ids:
            self._event.set()
            return True
        return False

    async def wait(self) -> bool:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=self.timeout)
            return True
        except asyncio.TimeoutError:
            return False

    @property
    def is_complete(self) -> bool:
        return self.arrived >= self.player_ids

    @property
    def pending(self) -> set[str]:
        return self.player_ids - self.arrived


class EventBus:
    """全局事件总线。"""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable]] = {}
        self._events: list[dict] = []

    def on(self, event_name: str, callback: Callable) -> None:
        self._listeners.setdefault(event_name, []).append(callback)

    def off(self, event_name: str, callback: Callable) -> None:
        if event_name in self._listeners:
            self._listeners[event_name] = [
                cb for cb in self._listeners[event_name] if cb != callback
            ]

    async def emit(self, event_name: str, data: dict = None) -> None:
        event = {"name": event_name, "data": data or {}, "timestamp": time.time()}
        self._events.append(event)
        for cb in self._listeners.get(event_name, []):
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(event)
                else:
                    cb(event)
            except Exception as e:
                logger.warning("事件处理器异常 | {} | {}", event_name, e)

    @property
    def history(self) -> list[dict]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()
        self._listeners.clear()


class MultiPlayerOrchestrator:
    """多人协同测试协调器。"""

    MAX_PLAYERS = 8

    def __init__(self) -> None:
        self.players: dict[str, PlayerSlot] = {}
        self.event_bus = EventBus()
        self.timeline: list[TimelineEvent] = []
        self._barriers: dict[str, SyncBarrier] = {}
        self._running = False
        self._start_time: float = 0

    @property
    def player_count(self) -> int:
        return len(self.players)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def elapsed(self) -> float:
        if not self._start_time:
            return 0
        return time.time() - self._start_time

    def add_player(self, player_id: str, platform: str, config: dict = None) -> PlayerSlot:
        if len(self.players) >= self.MAX_PLAYERS:
            raise RuntimeError(f"最多支持 {self.MAX_PLAYERS} 个玩家")
        if player_id in self.players:
            raise RuntimeError(f"玩家 {player_id} 已存在")
        slot = PlayerSlot(player_id=player_id, platform=platform, config=config or {})
        self.players[player_id] = slot
        slot.add_log(f"已加入 | 平台: {platform}")
        logger.info("玩家加入 | {} | 平台: {} | 人数: {}", player_id, platform, len(self.players))
        return slot

    def remove_player(self, player_id: str) -> None:
        slot = self.players.pop(player_id, None)
        if slot:
            slot.status = PlayerStatus.DISCONNECTED
            logger.info("玩家移除 | {} | 剩余: {}", player_id, len(self.players))

    def get_player(self, player_id: str) -> Optional[PlayerSlot]:
        return self.players.get(player_id)

    async def connect_player(self, player_id: str, controller: Any) -> None:
        slot = self.players.get(player_id)
        if not slot:
            raise RuntimeError(f"玩家 {player_id} 不存在")
        slot.status = PlayerStatus.CONNECTING
        slot.controller = controller
        slot.add_log("正在连接...")
        try:
            await controller.launch()
            slot.status = PlayerStatus.READY
            slot.add_log("已连接")
            await self.event_bus.emit("player_connected", {"player_id": player_id})
        except Exception as e:
            slot.status = PlayerStatus.ERROR
            slot.last_error = str(e)
            slot.add_log(f"连接失败: {e}")
            raise

    async def disconnect_player(self, player_id: str) -> None:
        slot = self.players.get(player_id)
        if slot and slot.controller:
            try:
                await slot.controller.close()
            except Exception:
                pass
            slot.status = PlayerStatus.DISCONNECTED
            slot.controller = None
            slot.add_log("已断开")

    async def connect_all(self) -> dict[str, bool]:
        results = {}
        async def _connect(pid: str):
            slot = self.players[pid]
            if slot.controller:
                try:
                    await slot.controller.launch()
                    slot.status = PlayerStatus.READY
                    slot.add_log("已连接")
                    results[pid] = True
                except Exception as e:
                    slot.status = PlayerStatus.ERROR
                    slot.last_error = str(e)
                    results[pid] = False
            else:
                results[pid] = False
        await asyncio.gather(*[_connect(pid) for pid in self.players])
        return results

    async def disconnect_all(self) -> None:
        for pid in list(self.players.keys()):
            await self.disconnect_player(pid)

    async def execute_action(self, player_id: str, action: str, **kwargs) -> Any:
        slot = self.players.get(player_id)
        if not slot:
            raise RuntimeError(f"玩家 {player_id} 不存在")
        if not slot.controller:
            raise RuntimeError(f"玩家 {player_id} 未连接")

        slot.status = PlayerStatus.EXECUTING
        start = time.time()
        result = None
        success = True
        try:
            if action == "tap":
                await slot.controller.tap(kwargs.get("selector", ""))
            elif action == "input":
                await slot.controller.input_text(kwargs.get("selector", ""), kwargs.get("text", ""))
            elif action == "navigate":
                await slot.controller.navigate(kwargs.get("url", ""))
            elif action == "screenshot":
                path = await slot.controller.screenshot(kwargs.get("name", f"{player_id}_capture"))
                slot.screenshots.append(path)
                result = path
            elif action == "get_source":
                result = await slot.controller.get_page_source()
            elif action == "get_text":
                result = await slot.controller.get_text(kwargs.get("selector", ""))
            else:
                raise RuntimeError(f"未知操作: {action}")
            slot.add_log(f"{action} 成功")
        except Exception as e:
            success = False
            slot.last_error = str(e)
            slot.add_log(f"{action} 失败: {e}")
            raise
        finally:
            duration = time.time() - start
            slot.status = PlayerStatus.READY if success else PlayerStatus.ERROR
            self.timeline.append(TimelineEvent(
                player_id=player_id, action=action, detail=str(kwargs),
                timestamp=start, duration=duration, success=success,
            ))
            await self.event_bus.emit("action_done", {
                "player_id": player_id, "action": action,
                "success": success, "duration": duration,
            })
        return result

    async def execute_parallel(self, actions: list[dict]) -> list[Any]:
        async def _run(act: dict):
            pid = act.get("player", "")
            action = act.get("action", "")
            params = {k: v for k, v in act.items() if k not in ("player", "action")}
            return await self.execute_action(pid, action, **params)
        return await asyncio.gather(*[_run(a) for a in actions], return_exceptions=True)

    def create_barrier(self, name: str, player_ids: list[str] = None, timeout: float = 30.0) -> SyncBarrier:
        ids = player_ids or list(self.players.keys())
        barrier = SyncBarrier(ids, timeout)
        self._barriers[name] = barrier
        return barrier

    async def sync_all(self, name: str = "default", timeout: float = 30.0) -> bool:
        barrier = self.create_barrier(name, timeout=timeout)
        for pid in self.players:
            barrier.arrive(pid)
        return await barrier.wait()

    async def screenshot_all(self, name_prefix: str = "all") -> dict[str, Path]:
        results = {}
        actions = [{"player": pid, "action": "screenshot", "name": f"{name_prefix}_{pid}"}
                   for pid in self.players if self.players[pid].controller]
        raw = await self.execute_parallel(actions)
        pids = [pid for pid in self.players if self.players[pid].controller]
        for pid, res in zip(pids, raw):
            if isinstance(res, Path):
                results[pid] = res
        return results

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "player_count": self.player_count,
            "elapsed": round(self.elapsed, 2),
            "players": {
                pid: {
                    "status": slot.status.value,
                    "platform": slot.platform,
                    "screenshots": len(slot.screenshots),
                    "last_error": slot.last_error,
                }
                for pid, slot in self.players.items()
            },
            "timeline_count": len(self.timeline),
        }

    def get_timeline(self) -> list[dict]:
        base = self._start_time or (self.timeline[0].timestamp if self.timeline else 0)
        return [
            {
                "player": e.player_id,
                "action": e.action,
                "detail": e.detail,
                "offset": round(e.timestamp - base, 3),
                "duration": round(e.duration, 3),
                "success": e.success,
            }
            for e in self.timeline
        ]

    async def start(self) -> None:
        self._running = True
        self._start_time = time.time()
        self.timeline.clear()
        self.event_bus.clear()
        logger.info("多人测试开始 | 玩家: {}", list(self.players.keys()))
        await self.event_bus.emit("test_started", {"players": list(self.players.keys())})

    async def stop(self) -> None:
        self._running = False
        logger.info("多人测试结束 | 用时: {:.1f}s | 操作: {}次", self.elapsed, len(self.timeline))
        await self.event_bus.emit("test_stopped", {"elapsed": self.elapsed})

    async def reset(self) -> None:
        await self.disconnect_all()
        self.players.clear()
        self.timeline.clear()
        self._barriers.clear()
        self.event_bus.clear()
        self._running = False
        self._start_time = 0
